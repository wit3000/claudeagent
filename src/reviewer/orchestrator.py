"""Run three independent passes in parallel and merge results."""
import asyncio
import random
from datetime import datetime, timezone

from .llm import LLMClient
from .passes import PASSES, PASS_VERSION
from .preprocess import number_text
from .parser import parse_pass, ParseError
from .consensus import build_consensus
from .schema import PassResult, ReviewReport, PassId


HALLUCINATION_UNRELIABLE_RATIO = 0.30
RETRY_JSON_MESSAGE = (
    "Your previous reply did not contain a valid JSON block matching the schema. "
    "Return ONLY the JSON block now, nothing else."
)


async def _run_pass(
    client: LLMClient,
    pass_id: PassId,
    user_msg: str,
    source_text: str,
    max_paragraph: int,
) -> PassResult:
    system = PASSES[pass_id]
    try:
        resp = await client.call(system=system, user=user_msg)
    except Exception as e:
        return PassResult(
            pass_id=pass_id,
            pass_version=PASS_VERSION,
            failed=True,
            failure_reason=f"LLM call failed: {e}",
        )

    raw = resp.text
    tokens_in, tokens_out, latency = resp.tokens_in, resp.tokens_out, resp.latency_ms

    try:
        findings, hallucinated = parse_pass(raw, pass_id, source_text, max_paragraph)
    except ParseError:
        try:
            resp2 = await client.call(
                system=system,
                user=user_msg + "\n\n" + RETRY_JSON_MESSAGE,
            )
            raw2 = resp2.text
            tokens_in += resp2.tokens_in
            tokens_out += resp2.tokens_out
            latency += resp2.latency_ms
            findings, hallucinated = parse_pass(raw2, pass_id, source_text, max_paragraph)
            raw = raw + "\n\n---retry---\n\n" + raw2
        except (ParseError, Exception) as e:
            return PassResult(
                pass_id=pass_id,
                pass_version=PASS_VERSION,
                raw_response=raw,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency,
                failed=True,
                failure_reason=f"Could not parse JSON after retry: {e}",
            )

    return PassResult(
        pass_id=pass_id,
        pass_version=PASS_VERSION,
        findings=findings,
        raw_response=raw,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency,
        hallucinated_count=hallucinated,
    )


async def review(
    text: str,
    text_id: str,
    client: LLMClient | None = None,
) -> ReviewReport:
    client = client or LLMClient()
    numbered, index = number_text(text)
    max_paragraph = len(index)
    user_msg = f"Text to review:\n\n{numbered}"

    pass_order: list[PassId] = ["p1", "p2", "p3"]
    random.shuffle(pass_order)
    tasks = [_run_pass(client, pid, user_msg, text, max_paragraph) for pid in pass_order]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda r: r.pass_id)

    warnings: list[str] = []
    for pr in results:
        if pr.failed:
            warnings.append(f"Pass {pr.pass_id} failed: {pr.failure_reason}")
            continue
        total = len(pr.findings) + pr.hallucinated_count
        if total and pr.hallucinated_count / total > HALLUCINATION_UNRELIABLE_RATIO:
            warnings.append(
                f"Pass {pr.pass_id} unreliable: {pr.hallucinated_count}/{total} findings hallucinated"
            )
        elif pr.hallucinated_count:
            warnings.append(
                f"Pass {pr.pass_id}: {pr.hallucinated_count} findings excluded as hallucinated"
            )

    consensus, clean = build_consensus(results)

    return ReviewReport(
        text_id=text_id,
        created_at=datetime.now(timezone.utc),
        model_id=client.model_id,
        pass_version=PASS_VERSION,
        passes=results,
        consensus=consensus,
        clean_categories=clean,
        warnings=warnings,
        source_text=text,
    )
