"""Groq — free tier, no card required. https://console.groq.com/keys"""
from ._openai_compat import OpenAICompatProvider


class Provider(OpenAICompatProvider):
    name = "groq"
    api_key_env = "GROQ_API_KEY"
    default_model = "llama-3.3-70b-versatile"
    base_url = "https://api.groq.com/openai/v1"
