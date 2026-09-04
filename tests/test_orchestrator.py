import pytest

from reviewer.llm import LLMResponse
from reviewer.orchestrator import MAX_OUTPUT_TOKENS, _run_pass, review


def _json(findings_json: str) -> str:
    return f"```json\n{{\"findings\":{findings_json}}}\n```"


# Source has two real quotes; a "fabricated" quote is one not present here.
SOURCE = "Первое предложение. Второе предложение.\n\nВторой абзац здесь."


class ScriptedClient:
    """Returns queued responses in order; records calls and the max_tokens seen."""
    def __init__(self, responses, truncated=False):
        self._responses = list(responses)
        self.calls = 0
        self.max_tokens_seen: list[int] = []
        self.model_id = "scripted"
        self.provider_name = "scripted"
        self.switch_notes = []
        self._truncated = truncated

    async def call(self, system, user, max_tokens=4096):
        self.calls += 1
        self.max_tokens_seen.append(max_tokens)
        text = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        return LLMResponse(
            text=text, tokens_in=1, tokens_out=1, latency_ms=1,
            truncated=self._truncated,
        )


class FailingClient:
    """Raises on every call, simulating a provider that never responds."""
    def __init__(self):
        self.calls = 0
        self.model_id = "failing"
        self.provider_name = "failing"
        self.switch_notes = []

    async def call(self, system, user, max_tokens=4096):
        self.calls += 1
        raise RuntimeError("boom")


class BudgetCappedClient:
    """Rejects a large max_tokens, but answers at the safe fallback budget."""
    def __init__(self, response, cap=4096):
        self._response = response
        self._cap = cap
        self.calls = 0
        self.max_tokens_seen: list[int] = []
        self.model_id = "capped"
        self.provider_name = "capped"
        self.switch_notes = []

    async def call(self, system, user, max_tokens=4096):
        self.calls += 1
        self.max_tokens_seen.append(max_tokens)
        if max_tokens > self._cap:
            raise RuntimeError(
                f"max_tokens: must be less than or equal to model limit {self._cap}"
            )
        return LLMResponse(text=self._response, tokens_in=1, tokens_out=1, latency_ms=1)


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


@pytest.mark.asyncio
async def test_on_progress_called_once_per_pass():
    empty = _json("[]")
    client = ScriptedClient([empty])
    events: list[tuple[int, int, str]] = []

    def cb(done, total, pass_id):
        events.append((done, total, pass_id))

    await review(SOURCE, "tid", client=client, on_progress=cb)
    assert len(events) == 3
    assert all(total == 3 for _, total, _ in events)
    assert [done for done, _, _ in events] == [1, 2, 3]
    assert sorted(pid for _, _, pid in events) == ["p1", "p2", "p3"]


@pytest.mark.asyncio
async def test_run_pass_passes_max_tokens():
    empty = _json("[]")
    client = ScriptedClient([empty])
    await _run_pass(client, "p1", f"Text:\n{SOURCE}", SOURCE, max_paragraph=2)
    assert client.max_tokens_seen == [MAX_OUTPUT_TOKENS]


@pytest.mark.asyncio
async def test_truncated_pass_yields_warning():
    empty = _json("[]")
    client = ScriptedClient([empty], truncated=True)
    report = await review(SOURCE, "tid", client=client)
    assert any("truncated" in w for w in report.warnings)


@pytest.mark.asyncio
async def test_run_pass_falls_back_on_max_tokens_error():
    good = _json(
        '[{"quote":"Первое предложение.","paragraph":1,"sentence":1,'
        '"category":"facts","defect":"d","fix":"f"}]'
    )
    client = BudgetCappedClient(good, cap=4096)
    result = await _run_pass(client, "p1", f"Text:\n{SOURCE}", SOURCE, max_paragraph=2)
    assert not result.failed
    assert len(result.findings) == 1
    # First tried the big budget, then retried once at the safe fallback.
    assert client.max_tokens_seen == [MAX_OUTPUT_TOKENS, 4096]


@pytest.mark.asyncio
async def test_all_passes_failed_no_exception():
    client = FailingClient()
    report = await review(SOURCE, "tid", client=client)
    assert report.consensus == []
    failed_warnings = [w for w in report.warnings if "failed" in w]
    assert len(failed_warnings) == 3
