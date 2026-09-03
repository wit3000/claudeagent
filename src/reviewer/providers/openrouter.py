"""OpenRouter — gateway with free-tier models. https://openrouter.ai/keys"""
from ._openai_compat import OpenAICompatProvider


class Provider(OpenAICompatProvider):
    name = "openrouter"
    api_key_env = "OPENROUTER_API_KEY"
    default_model = "meta-llama/llama-3.3-70b-instruct:free"
    base_url = "https://openrouter.ai/api/v1"
    # OpenRouter uses these for attribution and rate-limit tiering.
    extra_headers = {
        "HTTP-Referer": "https://huggingface.co/spaces",
        "X-Title": "Triple-Pass Text Reviewer",
    }
