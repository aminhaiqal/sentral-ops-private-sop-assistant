"""Inspect real SQLite memory with a scripted model and fictional sources. No AI key needed."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from app.config import PROJECT_ROOT, Settings
from app.harness.memory import BotRequest, MemoryStore, PreferenceRequest
from app.harness.model import ModelTurn
from app.harness.models import TaskRequest
from app.harness.runner import Harness
from app.harness.store import TaskStore
from app.harness.tools import document_tools
from app.schemas import SourceSnippet


class DemoModel:
    """Deterministic stand-in exercising the same harness protocol as a real model."""

    def __init__(self):
        self.step = 0
        self.loaded_context = {}

    def next_turn(self, instructions, messages, tools, max_tokens) -> ModelTurn:
        self.loaded_context = json.loads(messages[0]["content"].split("\n", 1)[1])
        preferences = {item["key"]: item["value"] for item in self.loaded_context["preferences"]}
        results = [
            json.loads(item["output"])
            for item in messages
            if item.get("type") == "function_call_output"
        ]
        if self.step == 0:
            name, args = "search_sops", {"query": "delivery delay escalation", "limit": 1}
        elif self.step == 1:
            content = (
                "# Delivery checklist\n\n- Contact Operations about the delay. [S1]"
                if preferences.get("report_format") == "checklist"
                else "# Delivery summary\n\nContact Operations about the delay. [S1]"
            )
            name, args = "write_artifact", {"title": "Delivery escalation", "content": content}
        elif self.step == 2:
            saved = next(item for item in results if item.get("saved"))
            name, args = "read_artifact", {"artifact_id": saved["artifact_id"]}
        else:
            saved = next(item for item in results if item.get("saved"))
            name, args = (
                "complete_task",
                {"artifact_id": saved["artifact_id"], "summary": "Saved the delivery guide."},
            )
        self.step += 1
        return ModelTurn(
            [
                {
                    "type": "function_call",
                    "call_id": f"demo-{self.step}",
                    "name": name,
                    "arguments": json.dumps(args),
                }
            ],
            tokens=50,
        )


def run_demo(path: Path) -> None:
    if path.exists():
        raise ValueError("Choose a new demo database path; existing databases are left untouched.")
    settings = Settings(
        _env_file=None, openai_api_key=None, auto_ingest_on_startup=False, harness_db_path=path
    )
    store = TaskStore(path)
    memory = MemoryStore(store)
    workspace = "demo-" + uuid.uuid4().hex
    bot = memory.create_bot(
        workspace, BotRequest(name="Operations Bot", role="Prepare SOP-backed delivery guides")
    )
    preference = memory.put_preference(
        workspace, bot.id, "report_format", PreferenceRequest(value="checklist")
    )

    def search(query, limit, workspace_id):
        return [
            SourceSnippet(
                document_id="demo-sop",
                chunk_id="demo-sop-1",
                title="Fictional delivery SOP",
                score=0.9,
                excerpt="Contact Operations about a delivery delay.",
            )
        ]

    def job():
        task = store.create(
            workspace,
            TaskRequest(
                bot_id=bot.id,
                goal="Prepare a delivery escalation guide",
                completion_criteria="Save a cited guide in the preferred format.",
            ),
            settings,
        )
        model = DemoModel()
        Harness(store, model, document_tools(settings, search=search, memory=memory), settings).run(
            store.claim()
        )
        finished = store.get(workspace, task.id)
        if finished.status != "completed":
            raise RuntimeError("Demo task did not complete.")
        return finished, model.loaded_context

    print("Offline memory demo: scripted model, fictional SOP, no provider requests.")
    print(f"Database: {path.resolve()}")
    print(f"Bot: {bot.id}")
    first, _ = job()
    print("\n1. First job used the saved 'checklist' preference:")
    print(first.artifacts[0].content)
    # Reopen the same database to prove these are durable records, not process-local variables.
    memory = MemoryStore(TaskStore(path))
    outcomes = memory.list_memories(workspace, bot.id, kind="outcome")
    print(f"\n2. Reopened SQLite: {len(outcomes)} outcome record with artifact-check evidence.")
    memory.put_preference(workspace, bot.id, "report_format", PreferenceRequest(value="paragraph"))
    second, context = job()
    print(
        f"\n3. Second job loaded {len(context['past_outcomes'])} prior outcome(s) and the edited preference:"
    )
    print(second.artifacts[0].content)
    memory.delete_memory(workspace, bot.id, preference.id)
    assert not memory.list_memories(workspace, bot.id, kind="preference")
    print("\n4. Deleted the preference; it is absent from future retrieval.")
    print(
        "Outcome records remain inspectable in the database. Their checks do not establish semantic accuracy."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=PROJECT_ROOT / "var" / f"memory-demo-{uuid.uuid4().hex[:12]}.sqlite3",
    )
    args = parser.parse_args()
    run_demo(args.db)


if __name__ == "__main__":
    main()
