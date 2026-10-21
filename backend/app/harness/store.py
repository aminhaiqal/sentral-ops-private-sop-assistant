"""SQLite checkpoints. Only the worker mutates execution state; API controls stay separate."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.harness.memory import MemoryStore, initialize_memory, remember_completion
from app.harness.models import TaskRequest, TaskSummary, TaskView


def now() -> str:
    return datetime.now(UTC).isoformat()


def event(state: dict, kind: str, detail: str) -> None:
    state["events"].append({"kind": kind, "detail": detail, "at": now()})


class TaskConflict(ValueError):
    pass


class TaskStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS tasks ("
                "id TEXT PRIMARY KEY, workspace TEXT NOT NULL, status TEXT NOT NULL, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, state TEXT NOT NULL)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS tasks_workspace ON tasks(workspace, created_at)")
            initialize_memory(db)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, workspace: str, request: TaskRequest, settings: Settings) -> TaskView:
        task_id = uuid.uuid4().hex
        timestamp = now()
        state = {
            **request.model_dump(),
            "turns": 0,
            "tokens": 0,
            "max_turns": settings.harness_max_turns,
            "max_tokens": settings.harness_max_tokens,
            "runtime_seconds": 0.0,
            "max_runtime_seconds": settings.harness_max_runtime_seconds,
            "messages": [{"role": "user", "content": request.model_dump_json()}],
            "pending": [],
            "sources": {},
            "artifacts": {},
            "readbacks": {},
            "receipts": {},
            "summary": "",
            "exception": "",
            "events": [],
        }
        event(state, "queued", "Task accepted for autonomous execution.")
        with self.connection() as db:
            if request.bot_id:
                MemoryStore.bot_row(db, workspace, request.bot_id)
            db.execute(
                "INSERT INTO tasks VALUES (?, ?, 'queued', ?, ?, ?)",
                (task_id, workspace, timestamp, timestamp, json.dumps(state)),
            )
        return self.get(workspace, task_id)

    def row(self, workspace: str, task_id: str) -> dict:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE id=? AND workspace=?", (task_id, workspace)
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Task not found.")
        return dict(row)

    @staticmethod
    def view(row: dict) -> TaskView:
        state = json.loads(row["state"])
        return TaskView(
            **{key: row[key] for key in ("id", "status", "created_at", "updated_at")},
            **{
                key: state[key]
                for key in (
                    "goal",
                    "completion_criteria",
                    "context",
                    "turns",
                    "tokens",
                    "max_turns",
                    "max_tokens",
                    "summary",
                    "exception",
                    "events",
                )
            },
            artifacts=list(state["artifacts"].values()),
            sources=list(state["sources"].values()),
            bot_id=state.get("bot_id"),
            memory_ids=state.get("memory_ids", []),
        )

    def get(self, workspace: str, task_id: str) -> TaskView:
        return self.view(self.row(workspace, task_id))

    def list(self, workspace: str) -> list[TaskSummary]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM tasks WHERE workspace=? ORDER BY created_at DESC LIMIT 50",
                (workspace,),
            ).fetchall()
        return [TaskSummary.model_validate(self.view(dict(row)).model_dump()) for row in rows]

    def claim(self) -> dict | None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM tasks WHERE status='queued' "
                "AND COALESCE(json_extract(state, '$.retry_at'), 0) <= ? "
                "ORDER BY created_at LIMIT 1",
                (time.time(),),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE tasks SET status='running', updated_at=? WHERE id=?", (now(), row["id"])
            )
            return dict(row) | {"status": "running"}

    def checkpoint(self, task_id: str, state: dict, status: str = "running") -> bool:
        # Cancellation is authoritative, even if a model request is still returning.
        with self.connection() as db:
            result = db.execute(
                "UPDATE tasks SET state=?, status=?, updated_at=? WHERE id=? AND status='running'",
                (json.dumps(state), status, now(), task_id),
            )
            if result.rowcount == 1 and status == "completed":
                remember_completion(db, task_id, state)
        return result.rowcount == 1

    def is_running(self, task_id: str) -> bool:
        with self.connection() as db:
            row = db.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        return row is not None and row["status"] == "running"

    def recover(self) -> None:
        # Call only while holding the worker's process lock: no other worker can be alive.
        with self.connection() as db:
            db.execute(
                "UPDATE tasks SET status='queued', updated_at=? WHERE status='running'", (now(),)
            )

    def cancel(self, workspace: str, task_id: str) -> TaskView:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM tasks WHERE id=? AND workspace=?", (task_id, workspace)
            ).fetchone()
            if row is None:
                raise FileNotFoundError("Task not found.")
            if row["status"] in {"completed", "cancelled"}:
                raise TaskConflict("This task has already finished.")
            state = json.loads(row["state"])
            event(state, "cancelled", "Cancelled by the task owner.")
            db.execute(
                "UPDATE tasks SET status='cancelled', state=?, updated_at=? WHERE id=?",
                (json.dumps(state), now(), task_id),
            )
        return self.get(workspace, task_id)

    def resume(self, workspace: str, task_id: str, message: str) -> TaskView:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM tasks WHERE id=? AND workspace=?", (task_id, workspace)
            ).fetchone()
            if row is None:
                raise FileNotFoundError("Task not found.")
            if row["status"] not in {"needs_input", "failed"}:
                raise TaskConflict("Only tasks needing input or failed tasks can be resumed.")
            state = json.loads(row["state"])
            state.setdefault("inbox", []).append({"role": "user", "content": message})
            state["exception"] = ""
            state["retry_count"] = 0
            state.pop("retry_at", None)
            event(state, "resumed", "Owner supplied context; execution requeued.")
            db.execute(
                "UPDATE tasks SET status='queued', state=?, updated_at=? WHERE id=?",
                (json.dumps(state), now(), task_id),
            )
        return self.get(workspace, task_id)
