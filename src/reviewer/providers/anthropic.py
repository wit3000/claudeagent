"""Anthropic Claude. https://console.anthropic.com/settings/keys"""
from __future__ import annotations

import time

from .base import BaseProvider, LLMResponse, ProviderError


class Provider(BaseProvider):
    name = "anthropic"
    api_key_env = "ANTHROPIC_API_KEY"
    default_model = "claude-sonnet-5"

    def __init__(self, model_id: str | None = None, api_key: str | None = None):
        super().__init__(model_id=model_id, api_key=api_key)
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise ProviderError(
                "anthropic: the 'anthropic' package is required "
                "(pip install anthropic)"
            ) from e
        self.client = AsyncAnthropic(api_key=self.api_key, timeout=120.0)

    async def call(self, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        t0 = time.perf_counter()
        msg = await self.client.messages.create(
            model=self.model_id,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        text = "".join(
            b.text for b in msg.content if getattr(b, "type", None) == "text"
        ).strip()
        return LLMResponse(
            text=text,
            tokens_in=msg.usage.input_tokens,
            tokens_out=msg.usage.output_tokens,
            latency_ms=elapsed,
            truncated=getattr(msg, "stop_reason", None) == "max_tokens",
        )

    @staticmethod
    def retryable_exceptions() -> tuple[type[BaseException], ...]:
        try:
            from anthropic import (
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                RateLimitError,
            )
        except ImportError:
            return (TimeoutError, ConnectionError)
        return (
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
        )
