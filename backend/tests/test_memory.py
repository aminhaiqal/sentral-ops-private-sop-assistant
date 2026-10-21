import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.harness.memory import (
    BotRequest,
    MemoryConflict,
    MemoryNotFound,
    MemoryStore,
    PreferenceRequest,
)
from app.harness.memory_demo import DemoModel, run_demo
from app.harness.models import TaskRequest
from app.harness.runner import Harness
from app.harness.store import TaskStore
from app.harness.tools import document_tools
from app.schemas import SourceSnippet


@pytest.fixture
def memory_setup(tmp_path):
    settings = Settings(
        _env_file=None, openai_api_key=None, harness_db_path=tmp_path / "memory.sqlite3"
    )
    store = TaskStore(settings.harness_db_path)
    memory = MemoryStore(store)
    bot = memory.create_bot("owner", BotRequest(name="Operations", role="Prepare delivery guides"))

    def search(query, limit, workspace):
        assert workspace == "owner"
        return [
            SourceSnippet(
                document_id="sop",
                chunk_id="sop-1",
                title="Delivery SOP",
                score=0.9,
                excerpt="Contact Operations about a delivery delay.",
            )
        ]

    tools = document_tools(settings, search=search, memory=memory)
    return settings, store, memory, bot, tools


def execute(memory_setup, model=None):
    settings, store, _, bot, tools = memory_setup
    task = store.create(
        "owner",
        TaskRequest(
            bot_id=bot.id,
            goal="Prepare a delivery guide",
            completion_criteria="Save a cited guide.",
        ),
        settings,
    )
    model = model or DemoModel()
    Harness(store, model, tools, settings).run(store.claim())
    return store.get("owner", task.id), model


def test_owner_can_update_forget_and_reopen_preferences(memory_setup):
    settings, _, memory, bot, _ = memory_setup
    first = memory.put_preference(
        "owner", bot.id, "report_format", PreferenceRequest(value="checklist")
    )
    updated = memory.put_preference(
        "owner", bot.id, "report_format", PreferenceRequest(value="paragraph")
    )
    assert first.id == updated.id
    assert first.created_at == updated.created_at
    assert updated.source == "user" and updated.evidence == {}
    reopened = MemoryStore(TaskStore(settings.harness_db_path))
    assert reopened.list_memories("owner", bot.id)[0].value == "paragraph"
    reopened.delete_memory("owner", bot.id, updated.id)
    assert memory.context("owner", bot.id, "delivery")["preferences"] == []


def test_scope_is_enforced_for_bots_memories_and_task_assignment(memory_setup):
    settings, store, memory, bot, _ = memory_setup
    preference = memory.put_preference(
        "owner", bot.id, "report_format", PreferenceRequest(value="checklist")
    )
    assert memory.list_bots("stranger") == []
    for operation in [
        lambda: memory.get_bot("stranger", bot.id),
        lambda: memory.list_memories("stranger", bot.id),
        lambda: memory.delete_memory("stranger", bot.id, preference.id),
        lambda: memory.put_preference(
            "stranger", bot.id, "report_format", PreferenceRequest(value="paragraph")
        ),
        lambda: store.create(
            "stranger",
            TaskRequest(bot_id=bot.id, goal="Read a guide", completion_criteria="Save it"),
            settings,
        ),
    ]:
        with pytest.raises(MemoryNotFound):
            operation()
    other = memory.create_bot("owner", BotRequest(name="Another bot", role="Prepare guides"))
    assert memory.context("owner", other.id, "delivery")["preferences"] == []
    with pytest.raises(MemoryNotFound):
        memory.delete_memory("owner", other.id, preference.id)


def test_expired_memory_is_visible_for_management_but_not_recalled(memory_setup):
    _, store, memory, bot, _ = memory_setup
    record = memory.put_preference(
        "owner",
        bot.id,
        "temporary_style",
        PreferenceRequest(value="checklist", expires_at=datetime.now(UTC) + timedelta(days=1)),
    )
    with store.connection() as db:
        db.execute(
            "UPDATE bot_memories SET expires_at=? WHERE id=?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), record.id),
        )
    assert memory.list_memories("owner", bot.id) == []
    assert memory.context("owner", bot.id, "delivery")["preferences"] == []
    assert memory.list_memories("owner", bot.id, include_expired=True)[0].id == record.id
    with pytest.raises(ValidationError):
        PreferenceRequest(value="old", expires_at=datetime.now(UTC) - timedelta(days=1))
    with pytest.raises(ValidationError):
        PreferenceRequest(value="ambiguous", expires_at=datetime(2030, 1, 1))


def test_completion_records_have_actual_artifact_evidence_and_survive_new_jobs(memory_setup):
    settings, store, memory, bot, _ = memory_setup
    preference = memory.put_preference(
        "owner", bot.id, "report_format", PreferenceRequest(value="checklist")
    )
    first, _ = execute(memory_setup)
    assert first.status == "completed"
    outcome = memory.list_memories("owner", bot.id, kind="outcome")[0]
    assert outcome.source == "harness"
    assert outcome.source_task_id == first.id
    assert outcome.evidence["sha256"] == first.artifacts[0].sha256
    assert outcome.evidence["artifact_id"] == first.artifacts[0].id
    assert outcome.evidence["semantic_accuracy_verified"] is False
    assert "Checklist delivered" not in outcome.value
    reopened = MemoryStore(TaskStore(settings.harness_db_path))
    assert reopened.list_memories("owner", bot.id, query="DELIVERY")[0].kind == "outcome"
    second, model = execute(memory_setup)
    assert second.status == "completed"
    assert model.loaded_context["past_outcomes"][0]["source_task_id"] == first.id
    assert preference.id in second.memory_ids and outcome.id in second.memory_ids
    # Automatic retrieval stores a revision hash and IDs, not another copy of preference values.
    state = json.loads(store.row("owner", second.id)["state"])
    assert len(state["memory_revision"]) == 64
    assert not any(
        "Current stored bot context" in item.get("content", "") for item in state["messages"]
    )


def test_preference_edits_and_deletion_take_effect_on_the_next_turn(memory_setup):
    _, _, memory, bot, _ = memory_setup
    preference = memory.put_preference(
        "owner", bot.id, "report_format", PreferenceRequest(value="checklist")
    )
    seen = []

    class EditingModel(DemoModel):
        def next_turn(self, *args):
            turn = super().next_turn(*args)
            seen.append(self.loaded_context)
            if self.step == 1:
                memory.put_preference(
                    "owner", bot.id, "report_format", PreferenceRequest(value="paragraph")
                )
                memory.update_bot(
                    "owner",
                    bot.id,
                    BotRequest(
                        name="Operations",
                        role="Write delivery summaries",
                        instructions="Use plain language.",
                    ),
                )
            elif self.step == 2:
                memory.delete_memory("owner", bot.id, preference.id)
            return turn

    finished, _ = execute(memory_setup, EditingModel())
    assert finished.status == "completed"
    assert seen[0]["preferences"][0]["value"] == "checklist"
    assert seen[1]["preferences"][0]["value"] == "paragraph"
    assert seen[1]["bot"]["instructions"] == "Use plain language."
    assert seen[2]["preferences"] == []
    assert "Delivery summary" in finished.artifacts[0].content


def test_cancelled_job_cannot_publish_success_memory(memory_setup):
    settings, store, memory, bot, tools = memory_setup
    task = store.create(
        "owner",
        TaskRequest(
            bot_id=bot.id,
            goal="Prepare a delivery guide",
            completion_criteria="Save a cited guide.",
        ),
        settings,
    )

    class CancellingModel(DemoModel):
        def next_turn(self, *args):
            turn = super().next_turn(*args)
            if self.step == 4:
                store.cancel("owner", task.id)
            return turn

    Harness(store, CancellingModel(), tools, settings).run(store.claim())
    assert store.get("owner", task.id).status == "cancelled"
    assert memory.list_memories("owner", bot.id, kind="outcome") == []


def test_invalid_completion_rolls_back_task_and_memory_together(memory_setup):
    settings, store, memory, bot, _ = memory_setup
    task = store.create(
        "owner",
        TaskRequest(
            bot_id=bot.id,
            goal="Prepare a delivery guide",
            completion_criteria="Save a cited guide.",
        ),
        settings,
    )
    claimed = store.claim()
    state = json.loads(claimed["state"])
    state["completion_artifact_id"] = "invented-artifact"
    with pytest.raises(ValueError, match="saved artifact"):
        store.checkpoint(task.id, state, "completed")
    assert store.get("owner", task.id).status == "running"
    assert memory.list_memories("owner", bot.id, kind="outcome") == []


def test_duplicate_completion_checkpoints_do_not_duplicate_memories(memory_setup):
    _, store, memory, bot, _ = memory_setup
    finished, _ = execute(memory_setup)
    state = json.loads(store.row("owner", finished.id)["state"])
    assert store.checkpoint(finished.id, state, "completed") is False
    assert len(memory.list_memories("owner", bot.id, kind="outcome")) == 1


def test_memory_retrieval_and_preference_count_are_bounded(memory_setup):
    _, _, memory, bot, _ = memory_setup
    for index in range(20):
        memory.put_preference(
            "owner", bot.id, f"style_{index}", PreferenceRequest(value="Use clear language")
        )
    with pytest.raises(MemoryConflict, match="20 preferences"):
        memory.put_preference("owner", bot.id, "overflow", PreferenceRequest(value="Extra"))
    memory.put_preference("owner", bot.id, "style_0", PreferenceRequest(value="Corrected"))
    for _ in range(6):
        execute(memory_setup)
    context = memory.context("owner", bot.id, "delivery")
    assert len(context["preferences"]) == 20
    assert len(context["past_outcomes"]) == 5


def test_legacy_tasks_without_bot_fields_remain_readable(memory_setup):
    settings, store, _, _, _ = memory_setup
    task = store.create(
        "owner", TaskRequest(goal="Prepare a guide", completion_criteria="Save a guide"), settings
    )
    with store.connection() as db:
        state = json.loads(store.row("owner", task.id)["state"])
        state.pop("bot_id")
        db.execute("UPDATE tasks SET state=? WHERE id=?", (json.dumps(state), task.id))
    reopened = TaskStore(settings.harness_db_path).get("owner", task.id)
    assert reopened.bot_id is None and reopened.memory_ids == []


def test_offline_demo_runs_without_any_provider_requests(tmp_path, monkeypatch, capsys):
    import app.openai_client as provider

    def unavailable(*args, **kwargs):
        pytest.fail("The offline demo must not create an API client")

    monkeypatch.setattr(provider, "OpenAIClient", unavailable)
    path = tmp_path / "demo.sqlite3"
    run_demo(path)
    output = capsys.readouterr().out
    assert "scripted model" in output and "Reopened SQLite" in output
    assert "Second job loaded 1 prior outcome" in output
    with TaskStore(path).connection() as db:
        assert (
            db.execute("SELECT count(*) FROM bot_memories WHERE kind='outcome'").fetchone()[0] == 2
        )
        assert (
            db.execute("SELECT count(*) FROM bot_memories WHERE kind='preference'").fetchone()[0]
            == 0
        )


def test_demo_leaves_an_existing_database_untouched(memory_setup):
    settings, _, memory, bot, _ = memory_setup
    with pytest.raises(ValueError, match="existing databases"):
        run_demo(settings.harness_db_path)
    assert memory.get_bot("owner", bot.id).name == "Operations"
