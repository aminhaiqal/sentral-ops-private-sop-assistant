import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings


@pytest.fixture(scope="session")
def clerk_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


@pytest.fixture
def clerk_settings(clerk_keys):
    return Settings(
        _env_file=None, clerk_issuer_url="https://clerk.test", clerk_jwt_key=clerk_keys[1]
    )


@pytest.fixture
def session_token(clerk_keys):
    def issue(
        user_id="user_test", session_id=None, *, changes=None, remove=(), key=None, kid="test"
    ):
        now = int(time.time())
        claims = {
            "iss": "https://clerk.test",
            "sub": user_id,
            "sid": session_id or "sess_" + uuid.uuid4().hex,
            "iat": now - 1,
            "nbf": now - 1,
            "exp": now + 120,
            "azp": "http://localhost:5173",
        }
        claims.update(changes or {})
        for name in remove:
            claims.pop(name, None)
        return jwt.encode(claims, key or clerk_keys[0], algorithm="RS256", headers={"kid": kid})

    return issue


@pytest.fixture
def authenticated_client(monkeypatch, clerk_settings, session_token):
    import app.auth as auth

    monkeypatch.setattr(auth, "get_settings", lambda: clerk_settings)

    def client(app, user_id=None, session_id=None):
        token = session_token(user_id or "user_" + uuid.uuid4().hex, session_id)
        return TestClient(app, headers={"Authorization": "Bearer " + token})

    return client
