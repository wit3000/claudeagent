"""Async job execution with SQLite persistence."""
import asyncio
import uuid

from ..orchestrator import review as run_review
from . import db


async def _run(job_id: str, text: str, text_id: str) -> None:
    row = db.get(job_id)
    if not row:
        return
    try:
        report = await run_review(text, text_id)
        row.status = "done"
        row.report_json = db.dump_report(report)
        row.high = sum(1 for c in report.consensus if c.priority == "high")
        row.low = sum(1 for c in report.consensus if c.priority == "low")
    except Exception as e:
        row.status = "error"
        row.error = f"{type(e).__name__}: {e}"
    db.save(row)


def submit(text: str, text_id: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    db.save(db.new_row(job_id, text_id))
    asyncio.create_task(_run(job_id, text, text_id))
    return job_id


def get(job_id: str) -> dict | None:
    row = db.get(job_id)
    if not row:
        return None
    report = db.load_report(row) if row.status == "done" else None
    return {
        "job_id": row.job_id,
        "text_id": row.text_id,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "error": row.error,
        "report": report.model_dump(mode="json") if report else None,
    }


def history(limit: int = 50) -> list[dict]:
    return [
        {
            "job_id": r.job_id,
            "text_id": r.text_id,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "high": r.high,
            "low": r.low,
        }
        for r in db.recent(limit)
    ]
