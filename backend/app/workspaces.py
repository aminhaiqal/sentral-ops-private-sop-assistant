import re
import secrets

from fastapi import HTTPException, Request, Response

from app.config import get_settings

COOKIE_NAME = "sentral_workspace"
WORKSPACE_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def workspace_id(request: Request, response: Response) -> str:
    """An unguessable browser credential scopes both stored objects and vector searches."""
    settings = get_settings()
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        if origin not in settings.cors_origins:
            raise HTTPException(status_code=403, detail="This request came from another website.")
    value = request.cookies.get(COOKIE_NAME, "")
    if not WORKSPACE_PATTERN.fullmatch(value):
        value = secrets.token_hex(32)
        response.set_cookie(
            COOKIE_NAME,
            value,
            httponly=True,
            secure=settings.workspace_cookie_secure,
            samesite="lax",
            max_age=365 * 24 * 60 * 60,
            path="/api",
        )
    response.headers["Cache-Control"] = "private, no-store"
    return value
