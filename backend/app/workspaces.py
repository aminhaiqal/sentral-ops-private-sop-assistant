import hashlib

from fastapi import Depends, HTTPException, Request, Response

from app.auth import SessionIdentity, require_user
from app.config import get_settings


def identity_workspace(identity: SessionIdentity) -> str:
    return hashlib.sha256(f"clerk:v1\0{identity.issuer}\0{identity.user_id}".encode()).hexdigest()


def workspace_id(
    request: Request, response: Response, identity: SessionIdentity = Depends(require_user)
) -> str:
    """Account-owned scope, stable across sessions and devices. Browser cookies do not select it."""
    settings = get_settings()
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        if origin not in settings.cors_origins:
            raise HTTPException(status_code=403, detail="This request came from another website.")
    response.headers["Cache-Control"] = "private, no-store"
    return identity_workspace(identity)
