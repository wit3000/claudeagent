"""FastAPI app: browser UI + JSON API for triple-pass review."""
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import jobs
from .auth import require_auth
from ..report import render_markdown

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Triple-Pass Text Reviewer")


class ReviewRequest(BaseModel):
    text: str
    text_id: str | None = None


@app.post("/api/review")
def create_review(req: ReviewRequest, _user: str = Depends(require_auth)):
    if not req.text.strip():
        raise HTTPException(400, "Empty text")
    text_id = req.text_id or datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    job = jobs.submit(req.text, text_id)
    return {"job_id": job.job_id, "text_id": text_id}


@app.get("/api/review/{job_id}")
def read_review(job_id: str, _user: str = Depends(require_auth)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.model_dump(mode="json")


@app.get("/api/history")
def history(limit: int = 50, _user: str = Depends(require_auth)):
    return [
        {
            "job_id": j.job_id,
            "text_id": j.text_id,
            "status": j.status,
            "created_at": j.created_at.isoformat(),
            "high": sum(1 for c in j.report.consensus if c.priority == "high") if j.report else 0,
            "low": sum(1 for c in j.report.consensus if c.priority == "low") if j.report else 0,
        }
        for j in jobs.list_recent(limit)
    ]


@app.get("/api/report/{job_id}.md", response_class=PlainTextResponse)
def report_md(job_id: str, _user: str = Depends(require_auth)):
    job = jobs.get(job_id)
    if not job or not job.report:
        raise HTTPException(404, "Report not ready")
    return render_markdown(job.report)


@app.get("/api/report/{job_id}.json")
def report_json(job_id: str, _user: str = Depends(require_auth)):
    job = jobs.get(job_id)
    if not job or not job.report:
        raise HTTPException(404, "Report not ready")
    return job.report.model_dump(mode="json")


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
