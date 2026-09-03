import pytest

from reviewer.llm import LLMResponse
from reviewer.orchestrator import _run_pass, review


def _json(findings_json: str) -> str:
    return f"```json\n{{\"findings\":{findings_json}}}\n```"


# Source has two real quotes; a "fabricated" quote is one not present here.
SOURCE = "Первое предложение. Второе предложение.\n\nВторой абзац здесь."


class ScriptedClient:
    """Returns queued responses in order; records how many calls happened."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.model_id = "scripted"
        self.provider_name = "scripted"
        self.switch_notes = []

    async def call(self, system, user, max_tokens=4096):
        self.calls += 1
        text = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        return LLMResponse(text=text, tokens_in=1, tokens_out=1, latency_ms=1)


@pytest.mark.asyncio
async def test_nudge_retry_fires_on_low_validity():
    # First reply: 1 valid + 2 fabricated quotes -> validity 0.33 (< 0.70).
    bad = _json(
        '[{"quote":"Первое предложение.","paragraph":1,"sentence":1,"category":"facts","defect":"d","fix":"f"},'
        '{"quote":"Такого текста нет один","paragraph":1,"sentence":1,"category":"facts","defect":"d","fix":"f"},'
        '{"quote":"Такого текста нет два","paragraph":1,"sentence":1,"category":"facts","defect":"d","fix":"f"}]'
    )
    # Retry reply: 1 valid, 0 fabricated -> validity 1.0, should replace.
    good = _json(
        '[{"quote":"Второе предложение.","paragraph":1,"sentence":2,"category":"facts","defect":"d","fix":"f"}]'
    )
    client = ScriptedClient([bad, good])
    result = await _run_pass(client, "p1", f"Text:\n{SOURCE}", SOURCE, max_paragraph=2)
    # Parsed once, then a nudge retry happened.
    assert client.calls == 2
    # Cleaner retry won: no hallucinations remain.
    assert result.hallucinated_count == 0
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_no_nudge_when_clean():
    good = _json(
        '[{"quote":"Первое предложение.","paragraph":1,"sentence":1,"category":"facts","defect":"d","fix":"f"}]'
    )
    client = ScriptedClient([good])
    result = await _run_pass(client, "p1", f"Text:\n{SOURCE}", SOURCE, max_paragraph=2)
    assert client.calls == 1  # no retry
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_review_populates_provider_field():
    empty = _json("[]")
    client = ScriptedClient([empty])
    report = await review(SOURCE, "tid", client=client)
    assert report.provider == "scripted"
    assert report.model_id == "scripted"
