"""FastAPI app: browser UI + JSON API for triple-pass review."""
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, jobs
from .auth import require_auth
from .ratelimit import check_rate, check_text_size
from ..report import render_markdown
from ..schema import ReviewReport

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Triple-Pass Text Reviewer")


@app.on_event("startup")
def _startup() -> None:
    db.init()


class ReviewRequest(BaseModel):
    text: str
    text_id: str | None = None


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/api/review")
def create_review(
    req: ReviewRequest,
    request: Request,
    _user: str = Depends(require_auth),
):
    if not req.text.strip():
        raise HTTPException(400, "Empty text")
    check_text_size(req.text)
    check_rate(request)
    text_id = req.text_id or datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    job_id = jobs.submit(req.text, text_id)
    return {"job_id": job_id, "text_id": text_id}


@app.get("/api/review/{job_id}")
def read_review(job_id: str, _user: str = Depends(require_auth)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/history")
def history(limit: int = 50, _user: str = Depends(require_auth)):
    return jobs.history(limit)


@app.get("/api/report/{job_id}.md", response_class=PlainTextResponse)
def report_md(job_id: str, _user: str = Depends(require_auth)):
    job = jobs.get(job_id)
    if not job or not job.get("report"):
        raise HTTPException(404, "Report not ready")
    return render_markdown(ReviewReport.model_validate(job["report"]))


@app.get("/api/report/{job_id}.json")
def report_json(job_id: str, _user: str = Depends(require_auth)):
    job = jobs.get(job_id)
    if not job or not job.get("report"):
        raise HTTPException(404, "Report not ready")
    return job["report"]


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/r/{job_id}", response_class=HTMLResponse)
def shared(job_id: str):
    """Direct link to a specific report — same UI, auto-loads that job."""
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
