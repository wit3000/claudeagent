"""Thin async wrapper around Google Gemini API with retries."""
import os
import time
from dataclasses import dataclass

from google import genai
from google.genai import types
from google.genai import errors as genai_errors
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
        self.model_id = model_id or os.environ.get("MODEL_ID", "gemini-2.5-flash")
        key = (
            api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
        self.client = genai.Client(api_key=key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception_type((
            genai_errors.APIError,
            genai_errors.ServerError,
        )),
        reraise=True,
    )
    async def call(self, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        t0 = time.perf_counter()
        resp = await self.client.aio.models.generate_content(
            model=self.model_id,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0,
                max_output_tokens=max_tokens,
            ),
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        text = (resp.text or "").strip()
        usage = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            text=text,
            tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
            latency_ms=elapsed,
        )
