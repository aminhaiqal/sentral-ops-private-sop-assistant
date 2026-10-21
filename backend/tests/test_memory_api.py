from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings


@pytest.fixture
def memory_app(tmp_path, monkeypatch):
    import app.harness.api as api
    import app.main as main
    import app.workspaces as workspaces

    settings = Settings(
        _env_file=None,
        openai_api_key=None,
        auto_ingest_on_startup=False,
        harness_db_path=tmp_path / "api.sqlite3",
    )
    for module in (api, main, workspaces):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    return main.app


def test_owner_can_configure_bot_edit_memory_and_attach_tasks(memory_app, authenticated_client):
    with authenticated_client(memory_app) as owner:
        created = owner.post(
            "/api/bots", json={"name": "Operations", "role": "Prepare delivery guides"}
        )
        assert created.status_code == 201
        assert created.headers["cache-control"] == "private, no-store"
        bot = created.json()
        assert "workspace" not in bot
        bot_id = bot["id"]
        assert owner.get("/api/bots").json()[0]["id"] == bot_id
        assert owner.get(f"/api/bots/{bot_id}").json()["name"] == "Operations"
        updated = owner.put(
            f"/api/bots/{bot_id}",
            json={
                "name": "Operations",
                "role": "Prepare delivery guides",
                "instructions": "Use concise summaries",
            },
        )
        assert updated.json()["instructions"] == "Use concise summaries"
        saved = owner.put(
            f"/api/bots/{bot_id}/preferences/report_format", json={"value": "checklist"}
        )
        assert saved.status_code == 200
        record = saved.json()
        assert record["source"] == "user" and record["kind"] == "preference"
        edited = owner.put(
            f"/api/bots/{bot_id}/preferences/report_format", json={"value": "paragraph"}
        )
        assert edited.json()["id"] == record["id"]
        assert (
            owner.get(f"/api/bots/{bot_id}/memories?q=paragraph").json()[0]["value"] == "paragraph"
        )
        task = owner.post(
            "/api/tasks",
            json={
                "bot_id": bot_id,
                "goal": "Prepare a delivery guide",
                "completion_criteria": "Save a cited guide.",
            },
        )
        assert task.status_code == 202 and task.json()["bot_id"] == bot_id
        deleted = owner.delete(f"/api/bots/{bot_id}/memories/{record['id']}")
        assert deleted.status_code == 204 and deleted.content == b""
        assert deleted.headers["cache-control"] == "private, no-store"
        assert owner.get(f"/api/bots/{bot_id}/memories").json() == []


def test_other_workspaces_cannot_access_profiles_memories_or_assign_bots(
    memory_app, authenticated_client
):
    with authenticated_client(memory_app) as owner, authenticated_client(memory_app) as stranger:
        request = {"name": "Operations", "role": "Prepare delivery guides"}
        bot_id = owner.post("/api/bots", json=request).json()["id"]
        record = owner.put(f"/api/bots/{bot_id}/preferences/style", json={"value": "brief"}).json()
        assert stranger.get("/api/bots").json() == []
        assert stranger.get(f"/api/bots/{bot_id}").status_code == 404
        assert stranger.put(f"/api/bots/{bot_id}", json=request).status_code == 404
        assert stranger.get(f"/api/bots/{bot_id}/memories").status_code == 404
        assert (
            stranger.put(
                f"/api/bots/{bot_id}/preferences/style", json={"value": "long"}
            ).status_code
            == 404
        )
        assert stranger.delete(f"/api/bots/{bot_id}/memories/{record['id']}").status_code == 404
        assert (
            stranger.post(
                "/api/tasks",
                json={"bot_id": bot_id, "goal": "Read a guide", "completion_criteria": "Read it"},
            ).status_code
            == 404
        )
        assert (
            owner.put(
                f"/api/bots/{bot_id}/preferences/style",
                json={"value": "long"},
                headers={"Origin": "https://another-site.example"},
            ).status_code
            == 403
        )


def test_clients_cannot_forge_outcome_provenance_or_save_invalid_expiry(
    memory_app, authenticated_client
):
    with authenticated_client(memory_app) as owner:
        bot_id = owner.post(
            "/api/bots", json={"name": "Operations", "role": "Prepare guides"}
        ).json()["id"]
        path = f"/api/bots/{bot_id}/preferences/style"
        for payload in [
            {"value": "brief", "source": "harness"},
            {"value": "brief", "kind": "outcome"},
            {"value": "brief", "evidence": {"verified": True}},
            {"value": "brief", "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
            {"value": "brief", "expires_at": "2030-01-01T00:00:00"},
        ]:
            assert owner.put(path, json=payload).status_code == 422
        assert (
            owner.put(
                f"/api/bots/{bot_id}/preferences/Bad Key", json={"value": "brief"}
            ).status_code
            == 409
        )
        assert owner.get(f"/api/bots/{bot_id}/memories?limit=1000000").status_code == 422
