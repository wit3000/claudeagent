"""Lightweight SQLite history for the Gradio app.

Stores rendered reports keyed by a short job id so the UI can list recent runs
and reopen a specific one via ?job=<id>. On HF free tier the disk is ephemeral,
so this is best-effort: any failure degrades to "no history", never crashes.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "data/reviewer.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    job_id     TEXT PRIMARY KEY,
    text_id    TEXT,
    created_at TEXT,
    high       INTEGER,
    low        INTEGER,
    report_md  TEXT
)
"""


def _connect() -> sqlite3.Connection | None:
    try:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute(_SCHEMA)
        return conn
    except (sqlite3.Error, OSError):
        return None


def save(text_id: str, high: int, low: int, report_md: str) -> str:
    """Persist a report, returning its job id. Never raises."""
    job_id = uuid.uuid4().hex[:12]
    conn = _connect()
    if conn is None:
        return job_id
    try:
        with conn:
            conn.execute(
                "INSERT INTO reports VALUES (?,?,?,?,?,?)",
                (
                    job_id,
                    text_id,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    high,
                    low,
                    report_md,
                ),
            )
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return job_id


def get(job_id: str) -> str | None:
    """Return the stored markdown for a job id, or None."""
    conn = _connect()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT report_md FROM reports WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def recent(limit: int = 30) -> list[tuple[str, str, str, int, int]]:
    """Return recent runs as (job_id, text_id, created_at, high, low)."""
    conn = _connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT job_id, text_id, created_at, high, low "
            "FROM reports ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return list(rows)
    except sqlite3.Error:
        return []
    finally:
        conn.close()
