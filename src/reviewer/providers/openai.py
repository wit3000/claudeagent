"""OpenAI. https://platform.openai.com/api-keys"""
from ._openai_compat import OpenAICompatProvider


class Provider(OpenAICompatProvider):
    name = "openai"
    api_key_env = "OPENAI_API_KEY"
    default_model = "gpt-4o-mini"
    base_url = None  # SDK default
