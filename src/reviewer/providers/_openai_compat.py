"""Shared implementation for providers speaking the OpenAI chat-completions API.

Groq, OpenRouter and OpenAI itself all accept the same request shape, so they
differ only in base URL, key env var and default model.
"""
from __future__ import annotations

import time

from .base import BaseProvider, LLMResponse, ProviderError


class OpenAICompatProvider(BaseProvider):
    #: Override in subclasses; None means the SDK default (api.openai.com).
    base_url: str | None = None
    #: Extra headers some gateways require (OpenRouter attribution, etc.).
    extra_headers: dict[str, str] = {}

    def __init__(self, model_id: str | None = None, api_key: str | None = None):
        super().__init__(model_id=model_id, api_key=api_key)
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ProviderError(
                f"{self.name}: the 'openai' package is required "
                f"(pip install openai)"
            ) from e
        kwargs: dict = {"api_key": self.api_key, "timeout": 120.0}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.extra_headers:
            kwargs["default_headers"] = dict(self.extra_headers)
        self.client = AsyncOpenAI(**kwargs)

    async def call(self, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        t0 = time.perf_counter()
        resp = await self.client.chat.completions.create(
            model=self.model_id,
            temperature=0,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        text = (resp.choices[0].message.content or "").strip()
        usage = resp.usage
        finish_reason = getattr(resp.choices[0], "finish_reason", None)
        return LLMResponse(
            text=text,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=elapsed,
            truncated=finish_reason == "length",
        )

    @staticmethod
    def retryable_exceptions() -> tuple[type[BaseException], ...]:
        try:
            from openai import (
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
