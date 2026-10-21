import json

import httpx
import pytest
from openai import APIConnectionError, APIStatusError

from app.config import Settings
from app.harness.model import ModelTurn
from app.harness.models import TaskRequest
from app.harness.runner import Harness
from app.harness.store import TaskConflict, TaskStore
from app.harness.tools import ToolContext, ToolError, document_tools
from app.harness.worker import worker_lock
from app.schemas import SourceSnippet


class ScriptedModel:
    def __init__(self, steps):
        self.steps = iter(steps)
        self.calls = 0
        self.inputs = []

    def next_turn(self, instructions, messages, tools, max_tokens):
        self.calls += 1
        self.inputs.append(json.loads(json.dumps(messages)))
        step = next(self.steps)
        if isinstance(step, Exception):
            raise step
        return step(messages) if callable(step) else step


def call(name, args, call_id=None):
    return ModelTurn(
        [
            {
                "type": "function_call",
                "call_id": call_id or name,
                "name": name,
                "arguments": json.dumps(args),
            },
        ],
        tokens=50,
    )


def result(messages, key):
    return next(
        data
        for item in reversed(messages)
        if item.get("type") == "function_call_output"
        and key in (data := json.loads(item["output"]))
    )


def successful_steps():
    return [
        call("search_sops", {"query": "delivery escalation", "limit": 3}),
        call(
            "write_artifact",
            {"title": "Escalation checklist", "content": "Contact Operations. [S1]"},
        ),
        lambda messages: call(
            "read_artifact", {"artifact_id": result(messages, "saved")["artifact_id"]}
        ),
        lambda messages: call(
            "complete_task",
            {
                "artifact_id": result(messages, "saved")["artifact_id"],
                "summary": "Checklist delivered.",
            },
        ),
    ]


@pytest.fixture
def setup(tmp_path):
    settings = Settings(_env_file=None, harness_db_path=tmp_path / "tasks.sqlite3")
    store = TaskStore(settings.harness_db_path)
    lookups = []

    def search(query, limit, workspace):
        lookups.append((query, limit, workspace))
        return [
            SourceSnippet(
                document_id="delivery-sop",
                chunk_id="delivery-sop-1",
                title="Delivery SOP",
                score=0.8,
                excerpt="Contact Operations when a delivery is delayed.",
            )
        ]

    tools = document_tools(settings, search=search)
    task = store.create(
        "owner",
        TaskRequest(
            goal="Prepare a delivery escalation checklist",
            completion_criteria="Save a cited Markdown checklist.",
        ),
        settings,
    )
    return settings, store, tools, task, lookups


def test_agent_executes_full_job_without_per_step_input(setup):
    settings, store, tools, task, lookups = setup
    model = ScriptedModel(successful_steps())
    Harness(store, model, tools, settings).run(store.claim())
    finished = store.get("owner", task.id)
    assert finished.status == "completed"
    assert finished.turns == 4
    assert finished.summary == "Checklist delivered."
    assert finished.exception == ""
    assert len(finished.artifacts) == 1
    assert finished.artifacts[0].content == "Contact Operations. [S1]"
    assert finished.sources[0].citation == "S1"
    assert lookups == [("delivery escalation", 3, "owner")]
    assert "messages" not in finished.model_dump()
    assert "receipts" not in finished.model_dump()


def test_unknown_tools_and_invalid_arguments_do_not_execute(setup):
    settings, store, tools, task, lookups = setup
    model = ScriptedModel(
        [
            call("run_shell", {"command": "anything"}),
            call("search_sops", {"query": "policy", "limit": "3", "workspace_id": "stranger"}),
            call("request_input", {"question": "Which document should I use?"}),
        ]
    )
    Harness(store, model, tools, settings).run(store.claim())
    assert not lookups
    assert store.get("owner", task.id).status == "needs_input"
    errors = [
        json.loads(item["output"])
        for messages in model.inputs
        for item in messages
        if item.get("type") == "function_call_output"
    ]
    assert any("not available" in item.get("error", "") for item in errors)
    assert any("Invalid tool arguments" in item.get("error", "") for item in errors)


def test_completion_requires_current_readback_and_known_citations(setup):
    _, store, tools, task, _ = setup
    state = json.loads(store.row("owner", task.id)["state"])
    ctx = ToolContext(task.id, "owner", state, "test")
    saved = tools.execute(
        "write_artifact", json.dumps({"title": "Checklist", "content": "Policy. [S9]"}), ctx
    )
    complete = json.dumps({"artifact_id": saved["artifact_id"], "summary": "Done"})
    with pytest.raises(ToolError, match="Read back"):
        tools.execute("complete_task", complete, ctx)
    read = json.dumps({"artifact_id": saved["artifact_id"]})
    tools.execute("read_artifact", read, ctx)
    with pytest.raises(ToolError, match="valid"):
        tools.execute("complete_task", complete, ctx)
    tools.execute("search_sops", json.dumps({"query": "policy", "limit": 1}), ctx)
    tools.execute(
        "write_artifact", json.dumps({"title": "Checklist", "content": "Policy. [S1]"}), ctx
    )
    with pytest.raises(ToolError, match="Read back"):
        tools.execute("complete_task", complete, ctx)
    tools.execute("read_artifact", read, ctx)
    assert tools.execute("complete_task", complete, ctx)["completed"]


def test_text_does_not_complete_task_and_loop_is_bounded(setup):
    settings, store, tools, task, _ = setup
    claimed = store.claim()
    state = json.loads(claimed["state"])
    state["max_turns"] = 2
    store.checkpoint(task.id, state)
    claimed["state"] = json.dumps(state)
    model = ScriptedModel([ModelTurn([], 10), ModelTurn([], 10)])
    Harness(store, model, tools, settings).run(claimed)
    assert store.get("owner", task.id).status == "limit_reached"
    assert model.calls == 2
    with pytest.raises(TaskConflict):
        store.resume("owner", task.id, "Reset all limits")


def test_crash_replays_pending_local_write_without_regenerating_model_turn(setup, monkeypatch):
    settings, store, tools, task, _ = setup
    model = ScriptedModel(successful_steps())
    original = store.checkpoint

    def crash_after_write(task_id, state, status="running"):
        if state["artifacts"]:
            raise SystemExit("Simulated worker crash before committing the local write")
        return original(task_id, state, status)

    monkeypatch.setattr(store, "checkpoint", crash_after_write)
    with pytest.raises(SystemExit):
        Harness(store, model, tools, settings).run(store.claim())
    checkpoint = json.loads(store.row("owner", task.id)["state"])
    assert checkpoint["pending"][0]["name"] == "write_artifact"
    assert not checkpoint["artifacts"]
    assert checkpoint["turns"] == 2
    monkeypatch.setattr(store, "checkpoint", original)
    # A new process opens the persisted database, recovers the task and continues its saved call.
    recovered_store = TaskStore(settings.harness_db_path)
    with worker_lock(recovered_store):
        recovered_store.recover()
        Harness(recovered_store, model, tools, settings).run(recovered_store.claim())
    finished = recovered_store.get("owner", task.id)
    assert finished.status == "completed"
    assert len(finished.artifacts) == 1
    assert model.calls == 4


def test_cancellation_wins_over_an_inflight_model_result(setup):
    settings, store, tools, task, _ = setup

    def cancel_during_request(messages):
        store.cancel("owner", task.id)
        return call("write_artifact", {"title": "Late result", "content": "Should not be saved"})

    Harness(store, ScriptedModel([cancel_during_request]), tools, settings).run(store.claim())
    cancelled = store.get("owner", task.id)
    assert cancelled.status == "cancelled"
    assert not cancelled.artifacts


def test_exception_resumes_with_context_and_original_budget(setup):
    settings, store, tools, task, _ = setup
    Harness(
        store,
        ScriptedModel(
            [
                call("request_input", {"question": "Which team owns this incident?"}),
            ]
        ),
        tools,
        settings,
    ).run(store.claim())
    assert store.get("owner", task.id).status == "needs_input"
    store.resume("owner", task.id, "The Operations team.")
    model = ScriptedModel(successful_steps())
    Harness(store, model, tools, settings).run(store.claim())
    assert {"role": "user", "content": "The Operations team."} in model.inputs[0]
    finished = store.get("owner", task.id)
    assert finished.status == "completed"
    assert finished.turns == 5
    assert finished.exception == ""


def test_transient_errors_retry_with_backoff_and_do_not_expose_credentials(setup, monkeypatch):
    settings, store, tools, task, _ = setup
    moment = [1000.0]
    monkeypatch.setattr("app.harness.store.time.time", lambda: moment[0])
    secret = "sk-private-never-return"
    error = APIStatusError(
        secret,
        response=httpx.Response(
            503,
            request=httpx.Request("POST", "https://example.test/responses"),
        ),
        body={"message": secret},
    )
    model = ScriptedModel([error, *successful_steps()])
    Harness(store, model, tools, settings).run(store.claim())
    retry = store.get("owner", task.id)
    assert retry.status == "queued"
    assert secret not in retry.model_dump_json()
    assert store.claim() is None
    moment[0] += 2
    Harness(store, model, tools, settings).run(store.claim())
    assert store.get("owner", task.id).status == "completed"
    assert store.get("owner", task.id).exception == ""


def test_transient_retry_count_is_bounded(setup, monkeypatch):
    settings, store, tools, task, _ = setup
    moment = [1000.0]
    monkeypatch.setattr("app.harness.store.time.time", lambda: moment[0])
    error = APIConnectionError(request=httpx.Request("POST", "https://example.test/responses"))
    model = ScriptedModel([error] * 4)
    for _ in range(4):
        Harness(store, model, tools, settings).run(store.claim())
        moment[0] += 30
    assert store.get("owner", task.id).status == "failed"
    assert model.calls == 4


def test_provider_parallel_calls_cannot_bypass_sequential_execution(setup):
    settings, store, tools, task, lookups = setup
    batch = call("search_sops", {"query": "policy", "limit": 1})
    batch.output += call("write_artifact", {"title": "Untested", "content": "Unverified"}).output
    model = ScriptedModel([batch, call("request_input", {"question": "Need a document"})])
    Harness(store, model, tools, settings).run(store.claim())
    assert not lookups
    assert not store.get("owner", task.id).artifacts


def test_incomplete_response_is_counted_but_does_not_execute_tools(setup):
    settings, store, tools, task, lookups = setup
    turn = call("search_sops", {"query": "policy", "limit": 1})
    turn.completed = False
    Harness(store, ScriptedModel([turn]), tools, settings).run(store.claim())
    assert not lookups
    assert store.get("owner", task.id).status == "failed"
    assert store.get("owner", task.id).tokens == 50


def test_only_one_worker_can_recover_the_same_database(setup):
    _, store, _, _, _ = setup
    with worker_lock(store):
        with pytest.raises(RuntimeError, match="already running"):
            with worker_lock(store):
                pytest.fail("A second worker must not enter")


@pytest.mark.parametrize("limit", ["tokens", "runtime", "context"])
def test_resource_limits_stop_before_dispatching_more_work(setup, limit):
    settings, store, tools, task, lookups = setup
    claimed = store.claim()
    state = json.loads(claimed["state"])
    if limit == "tokens":
        state["tokens"] = state["max_tokens"]
    elif limit == "runtime":
        state["runtime_seconds"] = state["max_runtime_seconds"]
    else:
        state["messages"] = [{"role": "user", "content": "x" * settings.harness_max_context_chars}]
    store.checkpoint(task.id, state)
    claimed["state"] = json.dumps(state)
    model = ScriptedModel([])
    Harness(store, model, tools, settings).run(claimed)
    assert store.get("owner", task.id).status == "limit_reached"
    assert not lookups and model.calls == 0


def test_resume_waits_for_pending_call_output_before_adding_user_context(setup):
    settings, store, tools, task, _ = setup
    claimed = store.claim()
    state = json.loads(claimed["state"])
    pending = call("search_sops", {"query": "policy", "limit": 1}).output
    state["pending"] = pending
    state["messages"].extend(pending)
    store.checkpoint(task.id, state, "failed")
    store.resume("owner", task.id, "Focus on Operations.")
    model = ScriptedModel([call("request_input", {"question": "Need a case number"})])
    Harness(store, model, tools, settings).run(store.claim())
    history = model.inputs[0]
    assert history[-2]["type"] == "function_call_output"
    assert history[-1] == {"role": "user", "content": "Focus on Operations."}


def test_worker_once_processes_a_real_persistent_queue(setup, monkeypatch):
    import app.harness.worker as worker

    settings, store, tools, task, _ = setup
    model = ScriptedModel(successful_steps())
    model.close = lambda: None
    monkeypatch.setattr("sys.argv", ["worker", "--once"])
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "ResponsesModel", lambda _: model)
    monkeypatch.setattr(worker, "document_tools", lambda _, **kwargs: tools)
    worker.main()
    assert store.get("owner", task.id).status == "completed"
