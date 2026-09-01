"""Thin async wrapper around Groq API (OpenAI-compatible) with retries."""
import os
import time
from dataclasses import dataclass

from groq import AsyncGroq, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry, stop_after_attempt, wait_exponential, retry_if_exception_type,
)


@dataclass
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


class LLMClient:
    def __init__(self, model_id: str | None = None, api_key: str | None = None):
        self.model_id = model_id or os.environ.get("MODEL_ID", "llama-3.3-70b-versatile")
        self.client = AsyncGroq(
            api_key=api_key or os.environ.get("GROQ_API_KEY"),
            timeout=120.0,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception_type((
            APIConnectionError, APITimeoutError, RateLimitError,
        )),
        reraise=True,
    )
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
        return LLMResponse(
            text=text,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=elapsed,
        )
