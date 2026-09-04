import types

import pytest

from reviewer.llm import (
    SAFE_FALLBACK_TOKENS,
    LLMClient,
    _is_max_tokens_error,
    parse_chain,
)
from reviewer.providers import PROVIDERS, ProviderError, get_provider
from reviewer.providers._openai_compat import OpenAICompatProvider
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


def _openai_provider_with_response(content: str, finish_reason: str):
    """Build an OpenAICompatProvider whose SDK client returns a canned reply."""
    resp = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
        usage=types.SimpleNamespace(prompt_tokens=5, completion_tokens=7),
    )

    class _Completions:
        async def create(self, **kwargs):
            return resp

    provider = object.__new__(OpenAICompatProvider)
    provider.model_id = "m"
    provider.client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_Completions())
    )
    return provider


@pytest.mark.asyncio
async def test_openai_compat_marks_truncated_on_length():
    provider = _openai_provider_with_response("partial", "length")
    resp = await provider.call("s", "u")
    assert resp.truncated is True


@pytest.mark.asyncio
async def test_openai_compat_not_truncated_on_stop():
    provider = _openai_provider_with_response("done", "stop")
    resp = await provider.call("s", "u")
    assert resp.truncated is False


def test_gemini_salvages_text_when_resp_text_raises():
    from reviewer.providers.gemini import _text_from_candidates

    part = types.SimpleNamespace(text="частичный вывод")
    content = types.SimpleNamespace(parts=[part])
    cand = types.SimpleNamespace(content=content)
    assert _text_from_candidates([cand]) == "частичный вывод"
    # No candidates / no parts must not raise.
    assert _text_from_candidates([]) == ""
    assert _text_from_candidates([types.SimpleNamespace(content=None)]) == ""


class _RaisingText:
    """Fake genai result whose .text raises, like a MAX_TOKENS cut-off."""
    def __init__(self, finish_reason, salvage="частичный"):
        part = types.SimpleNamespace(text=salvage)
        content = types.SimpleNamespace(parts=[part])
        self.candidates = [types.SimpleNamespace(
            finish_reason=types.SimpleNamespace(name=finish_reason), content=content,
        )]
        self.usage_metadata = types.SimpleNamespace(
            prompt_token_count=3, candidates_token_count=4,
        )

    @property
    def text(self):
        raise ValueError("no parts assembled")


def test_gemini_truncated_true_only_on_max_tokens():
    from reviewer.providers.gemini import _response_from_raw

    # Length cut-off: salvage text AND flag truncated.
    resp = _response_from_raw(_RaisingText("MAX_TOKENS"), elapsed_ms=1)
    assert resp.text == "частичный"
    assert resp.truncated is True

    # Non-length stop (e.g. SAFETY): salvage text but do NOT flag truncated.
    resp = _response_from_raw(_RaisingText("SAFETY"), elapsed_ms=1)
    assert resp.text == "частичный"
    assert resp.truncated is False


def test_is_max_tokens_error_recognises_common_phrasings():
    positives = [
        "max_tokens: must be less than or equal to model limit 4096",
        "requested max_tokens exceeds the maximum allowed",
        "max_completion_tokens is too large for this model",
        "This model supports at most 4096 completion tokens: max_tokens=8000",
        "max_tokens too many for model",
    ]
    for msg in positives:
        assert _is_max_tokens_error(RuntimeError(msg)), msg
    negatives = [
        "connection reset by peer",
        "rate limit exceeded",  # no max_tokens key
        "invalid api key",
        "max_tokens must be a positive integer",  # no overage indicator
    ]
    for msg in negatives:
        assert not _is_max_tokens_error(RuntimeError(msg)), msg


class _BudgetCappedProvider(_FakeProvider):
    """Rejects a large max_tokens, but answers at the safe fallback budget."""
    name = "capped"

    def __init__(self, model_id=None, api_key=None):
        super().__init__(model_id=model_id, api_key=api_key)
        self.max_tokens_seen = []

    async def call(self, system, user, max_tokens=4096):
        self.max_tokens_seen.append(max_tokens)
        if max_tokens > SAFE_FALLBACK_TOKENS:
            raise RuntimeError(
                f"max_tokens: must be less than or equal to model limit "
                f"{SAFE_FALLBACK_TOKENS}"
            )
        return LLMResponse(text="ok", tokens_in=1, tokens_out=1, latency_ms=1)


@pytest.mark.asyncio
async def test_client_retries_same_provider_on_max_tokens(monkeypatch):
    import reviewer.llm as llm_mod

    provider = _BudgetCappedProvider(model_id="m1")
    monkeypatch.setattr(llm_mod, "get_provider", lambda name: lambda **kw: provider)
    # Two-provider chain: a max_tokens error must NOT switch providers.
    client = LLMClient(chain=[("capped", "m1"), ("other", "m2")])
    resp = await client.call("s", "u", max_tokens=8000)
    assert resp.text == "ok"
    assert provider.max_tokens_seen == [8000, SAFE_FALLBACK_TOKENS]
    assert client.provider_name == "capped"  # stayed put
    assert client.switch_notes == []  # no bogus fallback note
