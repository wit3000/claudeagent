import os
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def require_auth(creds: HTTPBasicCredentials = Depends(security)) -> str:
    expected = os.environ.get("APP_PASSWORD", "")
    if not expected:
        return creds.username
    ok = secrets.compare_digest(creds.password.encode(), expected.encode())
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username
