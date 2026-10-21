import io
import json
from urllib.error import URLError

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth import SessionIdentity, signing_keys, verify_session_token
from app.config import Settings
from app.workspaces import identity_workspace


def test_valid_session_uses_a_stable_account_scope_across_sessions(clerk_settings, session_token):
    first = verify_session_token(session_token("user_owner", "sess_first"), clerk_settings)
    second = verify_session_token(session_token("user_owner", "sess_second"), clerk_settings)
    assert first.user_id == "user_owner"
    assert identity_workspace(first) == identity_workspace(second)
    assert identity_workspace(first) != identity_workspace(
        SessionIdentity("https://other.test", "user_owner", "sess_first")
    )


@pytest.mark.parametrize(
    "changes,remove",
    [
        ({"exp": 1}, ()),
        ({"nbf": 9999999999}, ()),
        ({"iat": 9999999999}, ()),
        ({"iss": "https://another-clerk.test"}, ()),
        ({"iss": "https://clerk.t"}, ()),
        ({"azp": "https://untrusted.test"}, ()),
        ({"sts": "pending"}, ()),
        ({"sts": "ended"}, ()),
        ({"sub": "machine_client"}, ()),
        ({"sid": "client_machine"}, ()),
        ({}, ("exp",)),
        ({}, ("sub",)),
        ({}, ("sid",)),
        ({}, ("azp",)),
        ({}, ("iss",)),
    ],
)
def test_invalid_session_claims_are_rejected(changes, remove, clerk_settings, session_token):
    with pytest.raises(HTTPException) as caught:
        verify_session_token(session_token(changes=changes, remove=remove), clerk_settings)
    assert caught.value.status_code == 401


def test_tampered_and_wrong_algorithm_tokens_are_rejected(clerk_settings, session_token):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tokens = [
        session_token(key=other_key),
        jwt.encode({"sub": "user_owner"}, "s" * 32, algorithm="HS256"),
        jwt.encode({"sub": "user_owner"}, None, algorithm="none"),
        "not-a-jwt",
    ]
    for token in tokens:
        with pytest.raises(HTTPException) as caught:
            verify_session_token(token, clerk_settings)
        assert caught.value.status_code == 401


def test_missing_configuration_fails_closed(session_token):
    with pytest.raises(HTTPException) as caught:
        verify_session_token(session_token(), Settings(_env_file=None))
    assert caught.value.status_code == 503


def test_audience_is_checked_when_configured(clerk_settings, session_token):
    settings = clerk_settings.model_copy(update={"clerk_audience": "sentral-api"})
    assert (
        verify_session_token(session_token(changes={"aud": "sentral-api"}), settings).user_id
        == "user_test"
    )
    with pytest.raises(HTTPException):
        verify_session_token(session_token(changes={"aud": "different-api"}), settings)


def test_jwks_comes_from_configured_issuer_and_is_cached(
    monkeypatch, clerk_settings, clerk_keys, session_token
):
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(clerk_keys[0].public_key(), as_dict=True)
    jwk.update({"kid": "test", "use": "sig", "alg": "RS256"})
    urls = []

    class Opener:
        def open(self, request, timeout):
            urls.append(request.full_url)
            assert timeout == 5
            return io.BytesIO(json.dumps({"keys": [jwk]}).encode())

    signing_keys.cache_clear()
    monkeypatch.setattr("jwt.jwks_client.urllib.request.build_opener", lambda *args: Opener())
    settings = clerk_settings.model_copy(update={"clerk_jwt_key": None})
    try:
        verify_session_token(session_token(), settings)
        verify_session_token(session_token(), settings)
        assert urls == ["https://clerk.test/.well-known/jwks.json"]
        with pytest.raises(HTTPException):
            verify_session_token(session_token(changes={"iss": "http://169.254.169.254"}), settings)
        assert urls == ["https://clerk.test/.well-known/jwks.json"]
    finally:
        signing_keys.cache_clear()


def test_jwks_service_failure_is_safe_and_does_not_accept_the_token(
    monkeypatch, clerk_settings, session_token
):
    class Opener:
        def open(self, request, timeout):
            raise URLError("private-service-error")

    signing_keys.cache_clear()
    monkeypatch.setattr("jwt.jwks_client.urllib.request.build_opener", lambda *args: Opener())
    try:
        with pytest.raises(HTTPException) as caught:
            verify_session_token(
                session_token(), clerk_settings.model_copy(update={"clerk_jwt_key": None})
            )
        assert caught.value.status_code == 503
        assert "private-service-error" not in caught.value.detail
    finally:
        signing_keys.cache_clear()


@pytest.mark.parametrize(
    "issuer",
    [
        "http://clerk.test",
        "https://clerk.test/path",
        "https://name:pass@clerk.test",
        "https://clerk.test?x=1",
    ],
)
def test_issuer_configuration_requires_a_trusted_https_origin(issuer):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, clerk_issuer_url=issuer)


def test_unauthenticated_requests_cannot_use_legacy_cookies(monkeypatch, tmp_path):
    import app.harness.api as api
    import app.main as main

    settings = Settings(
        _env_file=None, auto_ingest_on_startup=False, harness_db_path=tmp_path / "tasks.sqlite3"
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    with TestClient(main.app, cookies={"sentral_workspace": "a" * 64}) as client:
        for path in [
            "/api/documents",
            "/api/tasks",
            "/api/bots",
            "/api/documents/unknown/download",
        ]:
            response = client.get(path)
            assert response.status_code == 401
            assert response.headers["cache-control"] == "private, no-store"
        assert client.post("/api/ask", json={"question": "What is the SOP?"}).status_code == 401
        assert client.post("/api/ingest").status_code == 401
        assert client.get("/api/health").status_code == 200


def test_same_account_reaches_memory_on_a_second_device_and_cookie_cannot_override_owner(
    monkeypatch, tmp_path, authenticated_client
):
    import app.harness.api as api
    import app.main as main

    settings = Settings(
        _env_file=None, auto_ingest_on_startup=False, harness_db_path=tmp_path / "tasks.sqlite3"
    )
    for module in (main, api):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    with (
        authenticated_client(main.app, "user_owner", "sess_first") as first,
        authenticated_client(main.app, "user_owner", "sess_other_device") as second,
        authenticated_client(main.app, "user_stranger") as stranger,
    ):
        bot = first.post("/api/bots", json={"name": "Ops", "role": "Prepare guides"}).json()
        first.put(f"/api/bots/{bot['id']}/preferences/style", json={"value": "brief"})
        assert second.get(f"/api/bots/{bot['id']}/memories").json()[0]["value"] == "brief"
        owner_scope = identity_workspace(
            SessionIdentity("https://clerk.test", "user_owner", "sess_first")
        )
        stranger.cookies.set("sentral_workspace", owner_scope)
        assert stranger.get(f"/api/bots/{bot['id']}/memories").status_code == 404
