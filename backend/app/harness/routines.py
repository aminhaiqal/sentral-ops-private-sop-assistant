"""Calendar routines dispatched transactionally by the existing harness worker."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings
from app.harness.memory import MemoryConflict, MemoryNotFound, MemoryStore
from app.harness.models import TaskRequest, TaskView
from app.harness.store import TaskStore


class RoutineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bot_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    goal: str = Field(min_length=3, max_length=4000)
    completion_criteria: str = Field(
        default="Save a useful Markdown document with source citations and check the saved file.",
        min_length=3,
        max_length=2000,
    )
    recurrence: Literal["daily", "weekdays", "weekly"] = "weekdays"
    timezone: str = Field(max_length=80)
    local_time: str = "08:00"
    weekday: int = Field(default=0, ge=0, le=6)
    enabled: bool = True

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Choose a valid IANA timezone.") from exc
        return value

    @field_validator("local_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Use a time in HH:MM format.")
        return value


class RoutineView(RoutineRequest):
    id: str
    next_run_at: datetime
    last_task_id: str | None
    created_at: datetime
    updated_at: datetime


def next_occurrence(request: RoutineRequest, after: datetime) -> datetime:
    """One run per local date; spring gaps move forward, autumn folds run once."""
    zone = ZoneInfo(request.timezone)
    local = after.astimezone(zone)
    hour, minute = map(int, request.local_time.split(":"))
    for offset in range(15):
        day = local.date() + timedelta(days=offset)
        if request.recurrence == "weekdays" and day.weekday() >= 5:
            continue
        if request.recurrence == "weekly" and day.weekday() != request.weekday:
            continue
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone, fold=0)
        candidate = candidate.astimezone(UTC)
        if candidate > after:
            return candidate
    raise ValueError("Could not find the next routine date.")


class RoutineStore:
    def __init__(self, store: TaskStore, settings: Settings):
        self.store, self.settings = store, settings
        with store.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS routines ("
                "id TEXT PRIMARY KEY, workspace TEXT NOT NULL, bot_id TEXT NOT NULL, "
                "settings TEXT NOT NULL, enabled INTEGER NOT NULL, next_run_at TEXT NOT NULL, "
                "last_task_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                "FOREIGN KEY(workspace, bot_id) REFERENCES bots(workspace, id))"
            )
            db.execute("CREATE INDEX IF NOT EXISTS routines_due ON routines(enabled, next_run_at)")
            db.execute("CREATE INDEX IF NOT EXISTS routines_owner ON routines(workspace, bot_id)")

    @staticmethod
    def view(row) -> RoutineView:
        return RoutineView(
            **json.loads(row["settings"]),
            **{
                key: row[key]
                for key in ("id", "next_run_at", "last_task_id", "created_at", "updated_at")
            },
        )

    @staticmethod
    def owned(db, workspace, routine_id):
        row = db.execute(
            "SELECT * FROM routines WHERE id=? AND workspace=?", (routine_id, workspace)
        ).fetchone()
        if row is None:
            raise MemoryNotFound("Routine not found.")
        return row

    def list(self, workspace: str) -> list[RoutineView]:
        with self.store.connection() as db:
            return [
                self.view(row)
                for row in db.execute(
                    "SELECT * FROM routines WHERE workspace=? ORDER BY created_at", (workspace,)
                ).fetchall()
            ]

    def save(self, workspace: str, request: RoutineRequest, routine_id: str | None = None):
        at = datetime.now(UTC)
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            MemoryStore.bot_row(db, workspace, request.bot_id)
            if routine_id:
                self.owned(db, workspace, routine_id)
                db.execute(
                    "UPDATE routines SET bot_id=?, settings=?, enabled=?, next_run_at=?, "
                    "updated_at=? WHERE id=? AND workspace=?",
                    (
                        request.bot_id,
                        request.model_dump_json(),
                        int(request.enabled),
                        next_occurrence(request, at).isoformat(),
                        at.isoformat(),
                        routine_id,
                        workspace,
                    ),
                )
            else:
                count = db.execute(
                    "SELECT count(*) FROM routines WHERE workspace=?", (workspace,)
                ).fetchone()[0]
                if count >= 20:
                    raise MemoryConflict("Your workspace has 20 routines. Remove one first.")
                routine_id = uuid.uuid4().hex
                db.execute(
                    "INSERT INTO routines VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
                    (
                        routine_id,
                        workspace,
                        request.bot_id,
                        request.model_dump_json(),
                        int(request.enabled),
                        next_occurrence(request, at).isoformat(),
                        at.isoformat(),
                        at.isoformat(),
                    ),
                )
            return self.view(self.owned(db, workspace, routine_id))

    def delete(self, workspace: str, routine_id: str) -> None:
        with self.store.connection() as db:
            self.owned(db, workspace, routine_id)
            db.execute("DELETE FROM routines WHERE id=? AND workspace=?", (routine_id, workspace))

    def enqueue(self, db, row) -> TaskView:
        # A blocked run must be resolved before a new scheduled run is started.
        active = db.execute(
            "SELECT * FROM tasks WHERE workspace=? "
            "AND json_extract(state, '$.routine_id')=? "
            "AND status IN ('queued', 'running', 'needs_input') ORDER BY created_at LIMIT 1",
            (row["workspace"], row["id"]),
        ).fetchone()
        if active:
            return self.store.view(active)
        request = RoutineRequest.model_validate_json(row["settings"])
        task = self.store.create_in(
            db,
            row["workspace"],
            TaskRequest(
                bot_id=request.bot_id,
                goal=request.goal,
                completion_criteria=request.completion_criteria,
            ),
            self.settings,
            routine_id=row["id"],
        )
        db.execute("UPDATE routines SET last_task_id=? WHERE id=?", (task.id, row["id"]))
        return task

    def run_now(self, workspace: str, routine_id: str) -> TaskView:
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            return self.enqueue(db, self.owned(db, workspace, routine_id))

    def dispatch(self, at: datetime | None = None) -> list[str]:
        at = at or datetime.now(UTC)
        dispatched = []
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM routines WHERE enabled=1 AND next_run_at<=?", (at.isoformat(),)
            ).fetchall()
            for row in rows:
                task = self.enqueue(db, row)
                request = RoutineRequest.model_validate_json(row["settings"])
                db.execute(
                    "UPDATE routines SET next_run_at=?, updated_at=? WHERE id=?",
                    (next_occurrence(request, at).isoformat(), at.isoformat(), row["id"]),
                )
                dispatched.append(task.id)
        return dispatched
