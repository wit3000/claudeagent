"""LLM client factory: picks a provider from env, walks a fallback chain."""
from __future__ import annotations

import logging
import os

from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .providers import ProviderError, get_provider
from .providers.base import BaseProvider, LLMResponse

log = logging.getLogger(__name__)

__all__ = ["LLMClient", "LLMResponse", "ProviderError", "parse_chain"]

DEFAULT_PROVIDER = "groq"
RETRY_ATTEMPTS = 3

#: Conservative per-call output budget every current model accepts; used as a
#: one-shot fallback when a model rejects the requested max_tokens as too large.
SAFE_FALLBACK_TOKENS = 4096

_MAX_TOKENS_KEYS = ("max_tokens", "max_completion_tokens")
_OVERAGE_KEYS = (
    "limit", "maximum", "exceed", "too large", "at most", "too many",
)
#: Markers of a rate-limit / quota error. These mention the same words as a real
#: budget rejection ("reduce your max_tokens", "limit exceeded"), so their
#: presence vetoes the max_tokens classification to avoid a bogus 4096 fallback.
_RATE_LIMIT_KEYS = (
    "rate limit", "rate_limit", "requests per", "tokens per minute",
    "tpm", "rpm", "429", "quota",
)


def _is_max_tokens_error(exc: BaseException) -> bool:
    """True when the provider rejected the request for an oversized token budget.

    Rate-limit / quota errors are excluded even when they name ``max_tokens``,
    since throttling is not fixed by shrinking the output budget.
    """
    msg = str(exc).lower()
    if any(k in msg for k in _RATE_LIMIT_KEYS):
        return False
    return any(k in msg for k in _MAX_TOKENS_KEYS) and any(
        k in msg for k in _OVERAGE_KEYS
    )


def parse_chain(raw: str | None) -> list[tuple[str, str | None]]:
    """Parse LLM_FALLBACK_CHAIN into [(provider, model_or_None), ...].

    Format: "groq:llama-3.3-70b-versatile,openrouter:meta-llama/llama-3.3-70b-instruct:free"
    A bare provider name means "use that provider's default model".
    Model ids may contain colons, so only the FIRST colon separates the two.
    """
    if not raw or not raw.strip():
        return []
    out: list[tuple[str, str | None]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        provider, _, model = part.partition(":")
        out.append((provider.strip().lower(), model.strip() or None))
    return out


class LLMClient:
    """Calls the first working provider in the chain.

    The chain comes from LLM_FALLBACK_CHAIN when set, otherwise it is the single
    entry (LLM_PROVIDER, MODEL_ID). A provider is skipped when it cannot even be
    constructed (missing key / SDK); it is abandoned mid-run only after its own
    retries are exhausted.
    """

    def __init__(
        self,
        model_id: str | None = None,
        api_key: str | None = None,
        chain: list[tuple[str, str | None]] | None = None,
    ):
        if chain is None:
            chain = parse_chain(os.environ.get("LLM_FALLBACK_CHAIN"))
        if not chain:
            provider = os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER)
            chain = [(provider.strip().lower(), model_id)]
        self._chain = chain
        self._explicit_model = model_id
        self._api_key = api_key
        self._active: BaseProvider | None = None
        self._active_index = 0
        #: Provider switches that happened during this client's lifetime.
        self.switch_notes: list[str] = []

        self._active, self._active_index = self._build_from(0)

    # -- construction ------------------------------------------------------

    def _build_from(self, start: int) -> tuple[BaseProvider, int]:
        """Instantiate the first constructible provider at or after `start`."""
        errors: list[str] = []
        for i in range(start, len(self._chain)):
            provider_name, chain_model = self._chain[i]
            model = self._explicit_model or chain_model
            try:
                cls = get_provider(provider_name)
                # Chain entries pin their own model; don't let MODEL_ID override it.
                instance = cls(model_id=model, api_key=self._api_key)
            except (ProviderError, ValueError) as e:
                errors.append(f"{provider_name}: {e}")
                log.warning("provider %s unavailable: %s", provider_name, e)
                continue
            return instance, i
        raise ProviderError(
            "No usable LLM provider. Tried: " + "; ".join(errors or ["(empty chain)"])
        )

    # -- introspection -----------------------------------------------------

    @property
    def provider_name(self) -> str:
        return self._active.name if self._active else "none"

    @property
    def model_id(self) -> str:
        return self._active.model_id if self._active else ""

    def describe(self) -> str:
        return self._active.describe() if self._active else "no provider"

    # -- calling -----------------------------------------------------------

    async def call(self, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        last_error: BaseException | None = None
        index = self._active_index

        while index < len(self._chain):
            provider = self._active
            assert provider is not None
            try:
                return await self._call_with_retries(provider, system, user, max_tokens)
            except Exception as e:  # noqa: BLE001 — any failure means try the next one
                last_error = e
                log.warning("provider %s failed: %s", provider.name, e)
                if index + 1 >= len(self._chain):
                    break
                try:
                    self._active, index = self._build_from(index + 1)
                except ProviderError:
                    break
                self._active_index = index
                note = (
                    f"{provider.name} не ответил ({type(e).__name__}), "
                    f"переключился на {self._active.name} · {self._active.model_id}"
                )
                self.switch_notes.append(note)

        raise last_error if last_error else ProviderError("no provider produced a reply")

    async def _call_with_retries(
        self, provider: BaseProvider, system: str, user: str, max_tokens: int
    ) -> LLMResponse:
        # A max_tokens rejection is handled here, on the SAME provider, before the
        # caller decides "provider failed, switch" — dropping to a safe budget once
        # instead of triggering a bogus provider fallback.
        try:
            return await self._attempt(provider, system, user, max_tokens)
        except Exception as e:  # noqa: BLE001 — narrow the decision to the message
            if max_tokens > SAFE_FALLBACK_TOKENS and _is_max_tokens_error(e):
                log.warning(
                    "provider %s rejected max_tokens=%s (%s); retrying at %s",
                    provider.name, max_tokens, e, SAFE_FALLBACK_TOKENS,
                )
                return await self._attempt(
                    provider, system, user, SAFE_FALLBACK_TOKENS
                )
            raise

    async def _attempt(
        self, provider: BaseProvider, system: str, user: str, max_tokens: int
    ) -> LLMResponse:
        retryable = provider.retryable_exceptions()

        def _should_retry(exc: BaseException) -> bool:
            # A budget rejection is deterministic: retrying the same oversized
            # request only burns attempts, so let it surface at once for the
            # single 4096 fallback instead of spinning RETRY_ATTEMPTS times.
            if _is_max_tokens_error(exc):
                return False
            return isinstance(exc, retryable)

        retryer = AsyncRetrying(
            stop=stop_after_attempt(RETRY_ATTEMPTS),
            wait=wait_exponential(multiplier=2, min=2, max=8),
            retry=retry_if_exception(_should_retry),
            reraise=True,
        )
        async for attempt in retryer:
            with attempt:
                return await provider.call(system, user, max_tokens=max_tokens)
        raise ProviderError("retry loop exited without a result")  # unreachable
