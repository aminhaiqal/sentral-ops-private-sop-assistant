"""Verify Clerk session JWTs with the configured instance's public signing keys."""

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

bearer = HTTPBearer(
    auto_error=False, description="Clerk session token from the signed-in frontend."
)


@dataclass(frozen=True)
class SessionIdentity:
    issuer: str
    user_id: str
    session_id: str


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Sign in to access this workspace.",
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "private, no-store"},
    )


@lru_cache(maxsize=8)
def signing_keys(issuer: str) -> jwt.PyJWKClient:
    # Always use the configured issuer. Never discover URLs from an unverified token.
    return jwt.PyJWKClient(
        issuer + "/.well-known/jwks.json", cache_jwk_set=True, lifespan=300, timeout=5
    )


def verify_session_token(token: str, settings: Settings) -> SessionIdentity:
    if not settings.clerk_issuer_url or not settings.authorized_parties:
        raise HTTPException(
            status_code=503,
            detail="Sign-in is temporarily unavailable.",
            headers={"Cache-Control": "private, no-store"},
        )
    if len(token) > 16384:
        raise unauthorized()
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or header.get("typ", "JWT") != "JWT":
            raise unauthorized()
        if settings.clerk_jwt_key:
            key = settings.clerk_jwt_key.replace("\\n", "\n")
        else:
            key = signing_keys(settings.clerk_issuer_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer_url,
            audience=settings.clerk_audience,
            leeway=5,
            options={
                "require": ["exp", "iat", "nbf", "iss", "sub", "sid", "azp"],
                "verify_aud": bool(settings.clerk_audience),
            },
        )
        if (
            claims["azp"] not in settings.authorized_parties
            or claims.get("sts") not in {None, "active"}
            or not isinstance(claims["sub"], str)
            or not claims["sub"].startswith("user_")
            or not isinstance(claims["sid"], str)
            or not claims["sid"].startswith("sess_")
        ):
            raise unauthorized()
        return SessionIdentity(claims["iss"], claims["sub"], claims["sid"])
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Sign-in is temporarily unavailable.",
            headers={"Cache-Control": "private, no-store"},
        ) from exc
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise unauthorized() from exc


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> SessionIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    return verify_session_token(credentials.credentials, get_settings())
