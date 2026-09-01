"""SQLite persistence for jobs — history survives restarts."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

DB_PATH = os.environ.get("DB_PATH", "data/reviewer.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
_engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


class JobRow(SQLModel, table=True):
    job_id: str = Field(primary_key=True)
    text_id: str = Field(index=True)
    status: str
    created_at: datetime
    error: Optional[str] = None
    report_json: Optional[str] = None
    high: int = 0
    low: int = 0


def init() -> None:
    SQLModel.metadata.create_all(_engine)


def save(row: JobRow) -> None:
    with Session(_engine) as s:
        existing = s.get(JobRow, row.job_id)
        if existing:
            for k, v in row.model_dump().items():
                setattr(existing, k, v)
            s.add(existing)
        else:
            s.add(row)
        s.commit()


def get(job_id: str) -> Optional[JobRow]:
    with Session(_engine) as s:
        return s.get(JobRow, job_id)


def recent(limit: int = 50) -> list[JobRow]:
    with Session(_engine) as s:
        return list(
            s.exec(select(JobRow).order_by(JobRow.created_at.desc()).limit(limit))
        )


def new_row(job_id: str, text_id: str) -> JobRow:
    return JobRow(
        job_id=job_id,
        text_id=text_id,
        status="running",
        created_at=datetime.now(timezone.utc),
    )


def dump_report(report) -> str:
    return report.model_dump_json()


def load_report(row: JobRow):
    if not row.report_json:
        return None
    from ..schema import ReviewReport
    return ReviewReport.model_validate(json.loads(row.report_json))
