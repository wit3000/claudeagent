"""Run three independent passes in parallel and merge results."""
import asyncio
import os
import random
from collections.abc import Callable
from datetime import datetime, timezone

from .consensus import build_consensus
from .llm import LLMClient
from .parser import ParseError, parse_pass
from .passes import PASS_VERSION, PASSES
from .preprocess import number_text
from .schema import PassId, PassResult, ReviewReport

#: Output token budget per LLM call. High enough that a full report + JSON block
#: fits without truncation on ~20k-char inputs; override via env if needed.
MAX_OUTPUT_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "8000"))

#: Note appended when a pass answer was cut off at the output token limit.
TRUNCATION_NOTE = (
    "output may have been cut off at the token limit — the text is possibly "
    "too long for a single pass"
)

HALLUCINATION_UNRELIABLE_RATIO = 0.30
#: Below this validity ratio we retry the pass once with a stern reminder.
LOW_VALIDITY_RATIO = 0.70
RETRY_JSON_MESSAGE = (
    "Your previous reply did not contain a valid JSON block matching the schema. "
    "Return ONLY the JSON block now, nothing else."
)
RETRY_NUDGE_MESSAGE = (
    "\n\nВ твоём предыдущем ответе были цитаты, которых нет в тексте дословно. "
    "Возьми каждую цитату ровно как в оригинале (те же слова, знаки, регистр) "
    "и включай замечание, только если цитата действительно есть в тексте."
)


def _validity(findings_count: int, hallucinated: int) -> float:
    total = findings_count + hallucinated
    return 1.0 if total == 0 else findings_count / total


async def _run_pass(
    client: LLMClient,
    pass_id: PassId,
    user_msg: str,
    source_text: str,
    max_paragraph: int,
) -> PassResult:
    system = PASSES[pass_id]
    try:
        resp = await client.call(system=system, user=user_msg, max_tokens=MAX_OUTPUT_TOKENS)
    except Exception as e:
        return PassResult(
            pass_id=pass_id,
            pass_version=PASS_VERSION,
            failed=True,
            failure_reason=f"LLM call failed: {e}",
        )

    raw = resp.text
    tokens_in, tokens_out, latency = resp.tokens_in, resp.tokens_out, resp.latency_ms
    truncated = resp.truncated

    try:
        findings, hallucinated = parse_pass(raw, pass_id, source_text, max_paragraph)
    except ParseError:
        try:
            resp2 = await client.call(
                system=system,
                user=user_msg + "\n\n" + RETRY_JSON_MESSAGE,
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            raw2 = resp2.text
            tokens_in += resp2.tokens_in
            tokens_out += resp2.tokens_out
            latency += resp2.latency_ms
            truncated = resp2.truncated
            findings, hallucinated = parse_pass(raw2, pass_id, source_text, max_paragraph)
            raw = raw + "\n\n---retry---\n\n" + raw2
        except (ParseError, Exception) as e:
            reason = f"Could not parse JSON after retry: {e}"
            if truncated:
                reason += f" ({TRUNCATION_NOTE})"
            return PassResult(
                pass_id=pass_id,
                pass_version=PASS_VERSION,
                raw_response=raw,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency,
                failed=True,
                failure_reason=reason,
                truncated=truncated,
            )

    # Quality gate: if the model fabricated many quotes, retry once with a
    # sharper reminder and keep whichever attempt was cleaner.
    if _validity(len(findings), hallucinated) < LOW_VALIDITY_RATIO:
        try:
            resp3 = await client.call(
                system=system,
                user=user_msg + RETRY_NUDGE_MESSAGE,
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            f3, h3 = parse_pass(resp3.text, pass_id, source_text, max_paragraph)
            tokens_in += resp3.tokens_in
            tokens_out += resp3.tokens_out
            latency += resp3.latency_ms
            if _validity(len(f3), h3) > _validity(len(findings), hallucinated):
                findings, hallucinated = f3, h3
                raw = raw + "\n\n---nudge-retry---\n\n" + resp3.text
                truncated = resp3.truncated
        except Exception:  # noqa: BLE001 — retry is best-effort, keep first result
            pass

    return PassResult(
        pass_id=pass_id,
        pass_version=PASS_VERSION,
        findings=findings,
        raw_response=raw,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency,
        hallucinated_count=hallucinated,
        truncated=truncated,
    )


async def review(
    text: str,
    text_id: str,
    client: LLMClient | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> ReviewReport:
    client = client or LLMClient()
    numbered, index = number_text(text)
    max_paragraph = len(index)
    user_msg = f"Text to review:\n\n{numbered}"

    pass_order: list[PassId] = ["p1", "p2", "p3"]
    random.shuffle(pass_order)
    total_passes = len(pass_order)
    tasks = [
        asyncio.ensure_future(_run_pass(client, pid, user_msg, text, max_paragraph))
        for pid in pass_order
    ]

    results: list[PassResult] = []
    for coro in asyncio.as_completed(tasks):
        pr = await coro
        results.append(pr)
        if on_progress is not None:
            on_progress(len(results), total_passes, pr.pass_id)
    results.sort(key=lambda r: r.pass_id)

    warnings: list[str] = []
    for pr in results:
        if pr.failed:
            warnings.append(f"Pass {pr.pass_id} failed: {pr.failure_reason}")
            continue
        if pr.truncated:
            warnings.append(
                f"Pass {pr.pass_id} truncated: output hit the token limit, "
                f"some findings may be missing"
            )
        total = len(pr.findings) + pr.hallucinated_count
        if total and pr.hallucinated_count / total > HALLUCINATION_UNRELIABLE_RATIO:
            warnings.append(
                f"Pass {pr.pass_id} unreliable: "
                f"{pr.hallucinated_count}/{total} findings hallucinated"
            )
        elif pr.hallucinated_count:
            warnings.append(
                f"Pass {pr.pass_id}: {pr.hallucinated_count} findings excluded as hallucinated"
            )

    # Surface any mid-run provider fallback as a Russian warning.
    for note in getattr(client, "switch_notes", []):
        warnings.append(note)

    consensus, clean = build_consensus(results)

    return ReviewReport(
        text_id=text_id,
        created_at=datetime.now(timezone.utc),
        model_id=client.model_id,
        provider=getattr(client, "provider_name", ""),
        pass_version=PASS_VERSION,
        passes=results,
        consensus=consensus,
        clean_categories=clean,
        warnings=warnings,
        source_text=text,
    )
