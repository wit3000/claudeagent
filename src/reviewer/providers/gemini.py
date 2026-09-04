"""Google Gemini. Free key at https://aistudio.google.com/apikey"""
from __future__ import annotations

import os
import time

from .base import BaseProvider, LLMResponse, ProviderError


def _text_from_candidates(candidates) -> str:
    """Concatenate any text parts present on the candidates (best-effort)."""
    out: list[str] = []
    for cand in candidates:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            piece = getattr(part, "text", None)
            if piece:
                out.append(piece)
    return "".join(out)


class Provider(BaseProvider):
    name = "gemini"
    api_key_env = "GOOGLE_API_KEY"
    default_model = "gemini-2.5-flash"

    def __init__(self, model_id: str | None = None, api_key: str | None = None):
        # Google's own tooling also uses GEMINI_API_KEY; accept either.
        api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get(
            "GEMINI_API_KEY"
        )
        super().__init__(model_id=model_id, api_key=api_key)
        try:
            from google import genai
        except ImportError as e:
            raise ProviderError(
                "gemini: the 'google-genai' package is required "
                "(pip install google-genai)"
            ) from e
        self.client = genai.Client(api_key=self.api_key)

    async def call(self, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        from google.genai import types

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
        usage = getattr(resp, "usage_metadata", None)
        candidates = getattr(resp, "candidates", None) or []
        truncated = False
        if candidates:
            finish_reason = getattr(candidates[0], "finish_reason", None)
            truncated = str(getattr(finish_reason, "name", finish_reason)) == "MAX_TOKENS"
        # On a MAX_TOKENS cut-off google-genai's resp.text can raise (no assembled
        # parts); fall back to whatever partial text the parts hold and flag it.
        try:
            text = (resp.text or "").strip()
        except Exception:  # noqa: BLE001 — salvage partial output instead of failing
            text = _text_from_candidates(candidates).strip()
            truncated = True
        return LLMResponse(
            text=text,
            tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
            latency_ms=elapsed,
            truncated=truncated,
        )

    @staticmethod
    def retryable_exceptions() -> tuple[type[BaseException], ...]:
        try:
            from google.genai import errors
        except ImportError:
            return (TimeoutError, ConnectionError)
        return (errors.ServerError, errors.APIError)
