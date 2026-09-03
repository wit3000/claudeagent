"""Pluggable LLM providers. Selected at runtime via LLM_PROVIDER."""
from .base import BaseProvider, LLMResponse, ProviderError

__all__ = ["BaseProvider", "LLMResponse", "ProviderError", "get_provider", "PROVIDERS"]

PROVIDERS = ("groq", "openai", "anthropic", "gemini", "openrouter")


def get_provider(name: str) -> type[BaseProvider]:
    """Import and return the provider class for `name`. Raises ValueError if unknown."""
    key = (name or "").strip().lower()
    if key not in PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER {name!r}. Supported: {', '.join(PROVIDERS)}"
        )
    module = __import__(f"reviewer.providers.{key}", fromlist=["Provider"])
    return module.Provider
