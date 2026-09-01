"""Simple in-memory sliding-window rate limiter per client IP."""
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_MAX_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "20"))
_MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "20000"))
_WINDOW_S = 3600

_hits: dict[str, deque[float]] = defaultdict(deque)


def check_rate(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > _WINDOW_S:
        q.popleft()
    if len(q) >= _MAX_PER_HOUR:
        retry_in = int(_WINDOW_S - (now - q[0]))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: {_MAX_PER_HOUR} reviews/hour. Try again in {retry_in}s.",
        )
    q.append(now)


def check_text_size(text: str) -> None:
    if len(text) > _MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Text too long: {len(text)} chars. Max {_MAX_TEXT_CHARS}.",
        )
