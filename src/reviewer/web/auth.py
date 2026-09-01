"""Auth: skipped when PUBLIC_MODE=1 (link-shareable), HTTP Basic otherwise."""
import os
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic(auto_error=False)


def _public_mode() -> bool:
    return os.environ.get("PUBLIC_MODE", "0") == "1"


def require_auth(creds: HTTPBasicCredentials | None = Depends(security)) -> str:
    if _public_mode():
        return "public"
    expected = os.environ.get("APP_PASSWORD", "")
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: set APP_PASSWORD or PUBLIC_MODE=1",
        )
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth required",
            headers={"WWW-Authenticate": "Basic"},
        )
    ok = secrets.compare_digest(creds.password.encode(), expected.encode())
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username
