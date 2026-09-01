"""In-memory job registry with async execution."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel

from ..orchestrator import review as run_review
from ..schema import ReviewReport


class Job(BaseModel):
    job_id: str
    text_id: str
    status: Literal["running", "done", "error"]
    created_at: datetime
    error: str | None = None
    report: ReviewReport | None = None


_JOBS: dict[str, Job] = {}
_TASKS: dict[str, asyncio.Task] = {}


def get(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def list_recent(limit: int = 50) -> list[Job]:
    return sorted(_JOBS.values(), key=lambda j: j.created_at, reverse=True)[:limit]


async def _run(job_id: str, text: str, text_id: str) -> None:
    try:
        report = await run_review(text, text_id)
        job = _JOBS[job_id]
        job.status = "done"
        job.report = report
    except Exception as e:
        job = _JOBS[job_id]
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"


def submit(text: str, text_id: str) -> Job:
    job_id = uuid.uuid4().hex[:12]
    job = Job(
        job_id=job_id,
        text_id=text_id,
        status="running",
        created_at=datetime.now(timezone.utc),
    )
    _JOBS[job_id] = job
    _TASKS[job_id] = asyncio.create_task(_run(job_id, text, text_id))
    return job
