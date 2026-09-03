import pytest

from reviewer.llm import LLMClient, parse_chain
from reviewer.providers import PROVIDERS, ProviderError, get_provider
from reviewer.providers.base import LLMResponse


def test_all_providers_importable():
    for name in PROVIDERS:
        cls = get_provider(name)
        assert cls.name == name
        assert cls.api_key_env
        assert cls.default_model


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("nonesuch")


def test_provider_missing_key_raises(monkeypatch):
    for env in ("GROQ_API_KEY",):
        monkeypatch.delenv(env, raising=False)
    cls = get_provider("groq")
    with pytest.raises(ProviderError):
        cls()


def test_parse_chain_basic():
    chain = parse_chain("groq:llama-3.3-70b-versatile,openrouter:meta-llama/x:free")
    assert chain == [
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "meta-llama/x:free"),
    ]


def test_parse_chain_bare_provider():
    assert parse_chain("groq") == [("groq", None)]


def test_parse_chain_empty():
    assert parse_chain("") == []
    assert parse_chain(None) == []


def test_parse_chain_model_with_colons():
    # model id itself contains colons; only the first colon splits
    chain = parse_chain("openrouter:vendor/model:free")
    assert chain == [("openrouter", "vendor/model:free")]


class _FakeProvider:
    name = "fake"
    def __init__(self, model_id=None, api_key=None):
        self.model_id = model_id or "fake-model"
    def describe(self):
        return f"{self.name} · {self.model_id}"
    @staticmethod
    def retryable_exceptions():
        return (ConnectionError,)
    async def call(self, system, user, max_tokens=4096):
        return LLMResponse(text="ok", tokens_in=1, tokens_out=1, latency_ms=5)


def test_client_uses_explicit_chain(monkeypatch):
    import reviewer.llm as llm_mod
    monkeypatch.setattr(llm_mod, "get_provider", lambda name: _FakeProvider)
    client = LLMClient(chain=[("fake", "m1")])
    assert client.provider_name == "fake"
    assert client.model_id == "m1"


@pytest.mark.asyncio
async def test_client_falls_back_on_failure(monkeypatch):
    import reviewer.llm as llm_mod

    class Failing(_FakeProvider):
        name = "failing"
        async def call(self, system, user, max_tokens=4096):
            raise ConnectionError("down")

    class Working(_FakeProvider):
        name = "working"

    def fake_get(name):
        return Failing if name == "failing" else Working

    monkeypatch.setattr(llm_mod, "get_provider", fake_get)
    client = LLMClient(chain=[("failing", "m1"), ("working", "m2")])
    resp = await client.call("s", "u")
    assert resp.text == "ok"
    assert client.provider_name == "working"
    assert client.switch_notes
    assert "переключился" in client.switch_notes[0]
