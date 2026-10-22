from app.config import Settings


def test_task_api_isolates_owners_and_hides_runtime_transcript(
    tmp_path, monkeypatch, authenticated_client
):
    import app.harness.api as api
    import app.main as main
    import app.workspaces as workspaces

    settings = Settings(_env_file=None, harness_db_path=tmp_path / "api.sqlite3")
    for module in (api, main, workspaces):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    with authenticated_client(main.app) as owner, authenticated_client(main.app) as stranger:
        response = owner.post(
            "/api/tasks",
            json={
                "goal": "Prepare a checklist",
                "completion_criteria": "Save a cited report",
            },
        )
        assert response.status_code == 202
        assert "sentral_workspace" not in response.headers.get("set-cookie", "")
        assert response.headers["cache-control"] == "private, no-store"
        task = response.json()
        task_id = task["id"]
        assert task["status"] == "queued"
        assert "messages" not in task and "workspace" not in task
        assert owner.get("/api/tasks").json()[0]["id"] == task_id
        assert "artifacts" not in owner.get("/api/tasks").json()[0]
        assert stranger.get("/api/tasks").json() == []
        assert stranger.get(f"/api/tasks/{task_id}").status_code == 404
        assert stranger.post(f"/api/tasks/{task_id}/cancel").status_code == 404
        assert (
            stranger.post(f"/api/tasks/{task_id}/resume", json={"message": "Continue"}).status_code
            == 404
        )
        assert (
            owner.post(f"/api/tasks/{task_id}/resume", json={"message": "Continue"}).status_code
            == 409
        )
        assert (
            owner.post(
                f"/api/tasks/{task_id}/cancel",
                headers={
                    "Origin": "https://another-site.example",
                },
            ).status_code
            == 403
        )
        assert owner.post(f"/api/tasks/{task_id}/cancel").json()["status"] == "cancelled"
        assert owner.get(f"/api/tasks/{task_id}").json()["status"] == "cancelled"


def test_blank_tasks_and_client_supplied_runtime_overrides_are_rejected(
    tmp_path, monkeypatch, authenticated_client
):
    import app.harness.api as api
    import app.main as main

    settings = Settings(_env_file=None, harness_db_path=tmp_path / "api.sqlite3")
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    with authenticated_client(main.app) as browser:
        assert (
            browser.post(
                "/api/tasks",
                json={
                    "goal": "   ",
                    "completion_criteria": "A report",
                },
            ).status_code
            == 422
        )
        assert (
            browser.post(
                "/api/tasks",
                json={
                    "goal": "Prepare a report",
                    "completion_criteria": "A report",
                    "max_turns": 100000,
                },
            ).status_code
            == 422
        )


def test_single_input_tasks_need_no_bot_and_retired_routes_are_absent(
    tmp_path, monkeypatch, authenticated_client
):
    import app.harness.api as api
    import app.main as main

    settings = Settings(_env_file=None, harness_db_path=tmp_path / "api.sqlite3")
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    with authenticated_client(main.app) as browser:
        response = browser.post("/api/tasks", json={"goal": "Prepare a cited document"})
        assert response.status_code == 202
        task = response.json()
        assert task["completion_criteria"]
        assert not {"bot_id", "routine_id", "memory_ids"} & task.keys()
        assert (
            browser.post(
                "/api/tasks", json={"goal": "Prepare a report", "bot_id": "old-bot"}
            ).status_code
            == 422
        )
        for path in [
            "/api/bots",
            "/api/routines",
            "/api/studio/catalog",
            "/api/connections",
            "/api/demo-questions",
        ]:
            assert browser.get(path).status_code == 404
        for path in ["/api/ask", "/api/ingest"]:
            assert browser.post(path, json={"question": "A question"}).status_code == 404
