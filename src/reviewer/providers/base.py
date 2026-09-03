"""Provider contract shared by every LLM backend."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


class ProviderError(RuntimeError):
    """Raised when a provider cannot be constructed (missing key, missing SDK)."""


class BaseProvider(ABC):
    #: Human-readable provider name shown in the UI.
    name: str = "base"
    #: Environment variable holding the API key.
    api_key_env: str = ""
    #: Model used when MODEL_ID is unset.
    default_model: str = ""

    def __init__(self, model_id: str | None = None, api_key: str | None = None):
        self.model_id = model_id or os.environ.get("MODEL_ID") or self.default_model
        self.api_key = api_key or os.environ.get(self.api_key_env)
        if not self.api_key:
            raise ProviderError(
                f"{self.name}: environment variable {self.api_key_env} is not set"
            )

    @abstractmethod
    async def call(self, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        """Send one system+user turn and return the raw text with usage."""

    @staticmethod
    def retryable_exceptions() -> tuple[type[BaseException], ...]:
        """Exception types worth retrying (transient network / rate limits)."""
        return (TimeoutError, ConnectionError)

    def describe(self) -> str:
        return f"{self.name} · {self.model_id}"
