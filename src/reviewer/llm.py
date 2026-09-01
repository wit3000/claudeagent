"""Thin async wrapper around Anthropic Messages API with retries."""
import os
import time
from dataclasses import dataclass
from anthropic import AsyncAnthropic, APIConnectionError, APITimeoutError
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
        self.model_id = model_id or os.environ.get("MODEL_ID", "claude-sonnet-5")
        self.client = AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            timeout=120.0,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
        reraise=True,
    )
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
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )
        return LLMResponse(
            text=text,
            tokens_in=msg.usage.input_tokens,
            tokens_out=msg.usage.output_tokens,
            latency_ms=elapsed,
        )
