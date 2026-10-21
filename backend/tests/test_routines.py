import json
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.harness.memory import BotRequest, MemoryStore
from app.harness.memory_demo import DemoModel
from app.harness.routines import RoutineRequest, RoutineStore, next_occurrence
from app.harness.store import TaskStore
from app.harness.tools import document_tools
from app.schemas import SourceSnippet


@pytest.fixture
def scheduled(tmp_path):
    settings = Settings(_env_file=None, harness_db_path=tmp_path / "tasks.sqlite3")
    tasks = TaskStore(settings.harness_db_path)
    memory = MemoryStore(tasks)
    bot = memory.create_bot("owner", BotRequest(name="Chief of Staff", role="Prepare briefings"))
    routines = RoutineStore(tasks, settings)
    request = RoutineRequest(
        bot_id=bot.id,
        name="Morning briefing",
        goal="Prepare a cited briefing",
        timezone="Asia/Kuala_Lumpur",
        local_time="08:00",
    )
    return settings, tasks, memory, routines, request


@pytest.mark.parametrize(
    "recurrence,after,expected",
    [
        ("daily", "2026-10-23T00:00:00+00:00", "2026-10-24T00:00:00+00:00"),
        ("weekdays", "2026-10-23T01:00:00+00:00", "2026-10-26T00:00:00+00:00"),
        ("weekly", "2026-10-21T01:00:00+00:00", "2026-10-26T00:00:00+00:00"),
    ],
)
def test_local_calendar_dates(scheduled, recurrence, after, expected):
    request = scheduled[-1].model_copy(update={"recurrence": recurrence})
    assert next_occurrence(request, datetime.fromisoformat(after)).isoformat() == expected


def test_dst_gap_and_fold_do_not_duplicate_or_skip_local_date(scheduled):
    request = scheduled[-1].model_copy(
        update={"timezone": "America/New_York", "recurrence": "daily", "local_time": "02:30"}
    )
    assert next_occurrence(request, datetime(2026, 3, 8, tzinfo=UTC)) == datetime(
        2026, 3, 8, 7, 30, tzinfo=UTC
    )
    request.local_time = "01:30"
    first = next_occurrence(request, datetime(2026, 11, 1, tzinfo=UTC))
    assert first == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert next_occurrence(request, first) == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)


def test_dispatch_survives_reopen_coalesces_missed_runs_and_blocks_overlap(scheduled):
    settings, tasks, _, routines, request = scheduled
    routine = routines.save("owner", request)
    overdue = routine.next_run_at + timedelta(days=14)
    reopened = RoutineStore(TaskStore(settings.harness_db_path), settings)
    ids = reopened.dispatch(overdue)
    assert len(ids) == 1
    task = tasks.get("owner", ids[0])
    assert task.bot_id == request.bot_id and task.routine_id == routine.id
    assert tasks.list("owner")[0].bot_id == request.bot_id
    assert reopened.dispatch(overdue) == []
    assert reopened.run_now("owner", routine.id).id == task.id
    with tasks.connection() as db:
        db.execute("UPDATE tasks SET status='needs_input' WHERE id=?", (task.id,))
    reopened.dispatch(overdue + timedelta(days=2))
    assert len(tasks.list("owner")) == 1
    tasks.cancel("owner", task.id)
    assert reopened.run_now("owner", routine.id).id != task.id
    assert reopened.list("owner")[0].next_run_at > overdue


def test_paused_routine_never_dispatches_and_deletion_preserves_history(scheduled):
    _, tasks, _, routines, request = scheduled
    request.enabled = False
    routine = routines.save("owner", request)
    assert routines.dispatch(routine.next_run_at + timedelta(days=10)) == []
    task = routines.run_now("owner", routine.id)
    routines.delete("owner", routine.id)
    assert routines.list("owner") == []
    assert tasks.get("owner", task.id).routine_id == routine.id


def test_dispatch_rolls_back_task_and_schedule_together(scheduled, monkeypatch):
    _, tasks, _, routines, request = scheduled
    routine = routines.save("owner", request)
    original = tasks.create_in

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Process interrupted")

    monkeypatch.setattr(tasks, "create_in", interrupted)
    with pytest.raises(RuntimeError):
        routines.dispatch(routine.next_run_at)
    assert tasks.list("owner") == []
    assert routines.list("owner")[0].next_run_at == routine.next_run_at


def test_starter_profiles_are_account_scoped_and_preserve_edits(scheduled):
    _, _, memory, _, _ = scheduled
    first = memory.starter_bots("new_owner")
    bot = first[0]
    memory.update_bot("new_owner", bot.id, BotRequest(name="Edited", role=bot.role))
    again = memory.starter_bots("new_owner")
    assert len(again) == 4
    assert memory.get_bot("new_owner", bot.id).name == "Edited"
    assert {b.id for b in first}.isdisjoint({b.id for b in memory.starter_bots("other_owner")})


def test_worker_dispatches_a_due_routine_and_saves_the_deliverable(scheduled, monkeypatch):
    import sys

    import app.harness.worker as worker

    settings, tasks, memory, routines, request = scheduled
    routine = routines.save("owner", request)
    with tasks.connection() as db:
        db.execute(
            "UPDATE routines SET next_run_at=? WHERE id=?",
            ((datetime.now(UTC) - timedelta(minutes=1)).isoformat(), routine.id),
        )

    class Model(DemoModel):
        def close(self):
            pass

    def search(query, limit, workspace):
        assert workspace == "owner"
        return [
            SourceSnippet(
                document_id="delivery",
                chunk_id="delivery-1",
                title="Delivery policy",
                score=0.9,
                excerpt="Contact Operations about delivery delays.",
            )
        ]

    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "ResponsesModel", lambda _: Model())
    monkeypatch.setattr(
        worker,
        "document_tools",
        lambda settings, memory: document_tools(settings, search=search, memory=memory),
    )
    monkeypatch.setattr(worker.signal, "signal", lambda *_: None)
    monkeypatch.setattr(sys, "argv", ["worker", "--once"])
    worker.main()
    result = tasks.get("owner", tasks.list("owner")[0].id)
    assert result.status == "completed" and result.routine_id == routine.id
    assert "[S1]" in result.artifacts[0].content
    assert (
        memory.list_memories("owner", request.bot_id, kind="outcome")[0].source_task_id == result.id
    )


def test_routine_api_enforces_account_scope_and_server_owned_assignment(
    scheduled, authenticated_client, monkeypatch
):
    import app.harness.api as api
    from app.main import app

    settings, _, _, _, _ = scheduled
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    owner, stranger = (
        authenticated_client(app, "user_owner"),
        authenticated_client(app, "user_stranger"),
    )
    bot = owner.post("/api/bots/starter").json()[0]
    payload = dict(
        bot_id=bot["id"],
        name="Morning briefing",
        goal="Prepare a briefing",
        timezone="Asia/Kuala_Lumpur",
    )
    assert stranger.post("/api/routines", json=payload).status_code == 404
    response = owner.post("/api/routines", json=payload)
    assert response.status_code == 201
    routine = response.json()
    assert stranger.get("/api/routines").json() == []
    for method, path, body in [("put", "", payload), ("delete", "", None), ("post", "/run", None)]:
        response = getattr(stranger, method)(
            f"/api/routines/{routine['id']}{path}", **({"json": body} if body else {})
        )
        assert response.status_code == 404
    for extra in [{"workspace": "other"}, {"timezone": "invalid"}, {"local_time": "25:00"}]:
        assert owner.post("/api/routines", json=payload | extra).status_code == 422
    task = owner.post(f"/api/routines/{routine['id']}/run").json()
    assert task["routine_id"] == routine["id"] and task["bot_id"] == bot["id"]
    assert "workspace" not in json.dumps(task)
