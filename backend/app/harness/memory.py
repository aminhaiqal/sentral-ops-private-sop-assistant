"""Scoped bot profiles and durable memory, separate from task transcripts."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from app.harness.store import TaskStore


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class MemoryNotFound(FileNotFoundError):
    pass


class MemoryConflict(ValueError):
    pass


class BotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=3, max_length=500)
    instructions: str = Field(default="", max_length=4000)


class BotProfile(BotRequest):
    id: str
    created_at: datetime
    updated_at: datetime


class PreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: str = Field(min_length=1, max_length=1000)
    expires_at: AwareDatetime | None = None

    @field_validator("expires_at")
    @classmethod
    def future_expiry(cls, value):
        if value is not None:
            value = value.astimezone(UTC)
            if value <= datetime.now(UTC):
                raise ValueError("Expiry must be in the future.")
        return value


class MemoryRecord(BaseModel):
    id: str
    bot_id: str
    kind: Literal["preference", "outcome"]
    key: str
    value: str
    source: Literal["user", "harness"]
    source_task_id: str | None
    evidence: dict
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


def initialize_memory(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS bots ("
        "id TEXT PRIMARY KEY, workspace TEXT NOT NULL, name TEXT NOT NULL, "
        "role TEXT NOT NULL, instructions TEXT NOT NULL, created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL, UNIQUE(workspace, id))"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS bot_memories ("
        "id TEXT PRIMARY KEY, workspace TEXT NOT NULL, bot_id TEXT NOT NULL, "
        "kind TEXT NOT NULL CHECK(kind IN ('preference', 'outcome')), "
        "key TEXT NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL, "
        "source_task_id TEXT, evidence TEXT NOT NULL, expires_at TEXT, "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "UNIQUE(workspace, bot_id, kind, key), "
        "FOREIGN KEY(workspace, bot_id) REFERENCES bots(workspace, id) ON DELETE CASCADE)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS bot_memories_scope "
        "ON bot_memories(workspace, bot_id, kind, updated_at)"
    )


class MemoryStore:
    def __init__(self, store: TaskStore):
        self.store = store

    @staticmethod
    def bot_row(db, workspace: str, bot_id: str):
        row = db.execute(
            "SELECT * FROM bots WHERE workspace=? AND id=?", (workspace, bot_id)
        ).fetchone()
        if row is None:
            raise MemoryNotFound("Bot not found.")
        return row

    def create_bot(self, workspace: str, request: BotRequest) -> BotProfile:
        bot_id, at = uuid.uuid4().hex, timestamp()
        with self.store.connection() as db:
            db.execute(
                "INSERT INTO bots VALUES (?, ?, ?, ?, ?, ?, ?)",
                (bot_id, workspace, request.name, request.role, request.instructions, at, at),
            )
        return self.get_bot(workspace, bot_id)

    def starter_bots(self, workspace: str) -> list[BotProfile]:
        """Account-scoped, repeatable onboarding. Never overwrite a user's edits."""
        templates = [
            (
                "chief",
                "Chief of Staff",
                "Prepare briefings, plans and decision documents.",
                "Lead with the outcome. Turn the user's goal into a useful, concise document. "
                "Separate documented policy from missing live updates. End with practical next steps.",
            ),
            (
                "operations",
                "Operations",
                "Build practical checklists and operating guides.",
                "Make documents easy to act on. Include responsibilities, ordered steps and "
                "escalation points supported by the available documents.",
            ),
            (
                "research",
                "Research Analyst",
                "Research your documents and prepare cited reports.",
                "Compare the relevant sources, explain the findings and cite the evidence. "
                "Make gaps and uncertainties explicit.",
            ),
            (
                "support",
                "Customer Support",
                "Draft customer response playbooks from your policies.",
                "Write clear, considerate response drafts and escalation guides. "
                "Do not invent customer account details or claim to have sent a message.",
            ),
        ]
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for key, name, role, instructions in templates:
                bot_id = uuid.uuid5(uuid.NAMESPACE_URL, f"axelyn:{workspace}:starter:{key}").hex
                at = timestamp()
                db.execute(
                    "INSERT OR IGNORE INTO bots VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (bot_id, workspace, name, role, instructions, at, at),
                )
        return self.list_bots(workspace)

    def get_bot(self, workspace: str, bot_id: str) -> BotProfile:
        with self.store.connection() as db:
            row = self.bot_row(db, workspace, bot_id)
            return BotProfile.model_validate({key: row[key] for key in BotProfile.model_fields})

    def list_bots(self, workspace: str) -> list[BotProfile]:
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT * FROM bots WHERE workspace=? ORDER BY created_at DESC", (workspace,)
            ).fetchall()
        return [
            BotProfile.model_validate({key: row[key] for key in BotProfile.model_fields})
            for row in rows
        ]

    def update_bot(self, workspace: str, bot_id: str, request: BotRequest) -> BotProfile:
        with self.store.connection() as db:
            self.bot_row(db, workspace, bot_id)
            db.execute(
                "UPDATE bots SET name=?, role=?, instructions=?, updated_at=? "
                "WHERE workspace=? AND id=?",
                (request.name, request.role, request.instructions, timestamp(), workspace, bot_id),
            )
        return self.get_bot(workspace, bot_id)

    @staticmethod
    def record(row) -> MemoryRecord:
        return MemoryRecord.model_validate(dict(row) | {"evidence": json.loads(row["evidence"])})

    def put_preference(
        self, workspace: str, bot_id: str, key: str, request: PreferenceRequest
    ) -> MemoryRecord:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", key):
            raise MemoryConflict(
                "Use a lowercase preference key with letters, numbers, dots or dashes."
            )
        at, memory_id = timestamp(), uuid.uuid4().hex
        expiry = request.expires_at.isoformat() if request.expires_at else None
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.bot_row(db, workspace, bot_id)
            existing = db.execute(
                "SELECT id FROM bot_memories WHERE workspace=? AND bot_id=? "
                "AND kind='preference' AND key=?",
                (workspace, bot_id, key),
            ).fetchone()
            count = db.execute(
                "SELECT count(*) FROM bot_memories WHERE workspace=? AND bot_id=? "
                "AND kind='preference'",
                (workspace, bot_id),
            ).fetchone()[0]
            if existing is None and count >= 20:
                raise MemoryConflict("This bot has 20 preferences. Update or delete one first.")
            db.execute(
                "INSERT INTO bot_memories VALUES (?, ?, ?, 'preference', ?, ?, 'user', "
                "NULL, '{}', ?, ?, ?) ON CONFLICT(workspace, bot_id, kind, key) "
                "DO UPDATE SET value=excluded.value, expires_at=excluded.expires_at, "
                "updated_at=excluded.updated_at",
                (memory_id, workspace, bot_id, key, request.value, expiry, at, at),
            )
            row = db.execute(
                "SELECT * FROM bot_memories WHERE workspace=? AND bot_id=? "
                "AND kind='preference' AND key=?",
                (workspace, bot_id, key),
            ).fetchone()
            return self.record(row)

    def list_memories(
        self,
        workspace: str,
        bot_id: str,
        *,
        query: str = "",
        kind: str | None = None,
        include_expired: bool = False,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        clauses, values = ["workspace=?", "bot_id=?"], [workspace, bot_id]
        if kind is not None:
            clauses.append("kind=?")
            values.append(kind)
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at>?)")
            values.append(timestamp())
        words = list(dict.fromkeys(re.findall(r"\w{3,}", query.lower())))[:8]
        if words:
            clauses.append("(" + " OR ".join(["lower(value) LIKE ?"] * len(words)) + ")")
            values.extend(f"%{word}%" for word in words)
        with self.store.connection() as db:
            self.bot_row(db, workspace, bot_id)
            rows = db.execute(
                "SELECT * FROM bot_memories WHERE "
                + " AND ".join(clauses)
                + " ORDER BY updated_at DESC, id LIMIT ?",
                [*values, min(max(limit, 1), 50)],
            ).fetchall()
        return [self.record(row) for row in rows]

    def delete_memory(self, workspace: str, bot_id: str, memory_id: str) -> None:
        with self.store.connection() as db:
            self.bot_row(db, workspace, bot_id)
            result = db.execute(
                "DELETE FROM bot_memories WHERE workspace=? AND bot_id=? AND id=?",
                (workspace, bot_id, memory_id),
            )
            if result.rowcount != 1:
                raise MemoryNotFound("Memory not found.")

    def context(self, workspace: str, bot_id: str, query: str) -> dict:
        # Small, bounded retrieval. Preferences are exact records; outcomes use keyword lookup.
        bot = self.get_bot(workspace, bot_id)
        preferences = self.list_memories(workspace, bot_id, kind="preference", limit=20)
        outcomes = self.list_memories(workspace, bot_id, kind="outcome", query=query, limit=5)
        return {
            "bot": bot.model_dump(mode="json"),
            "preferences": [item.model_dump(mode="json") for item in preferences],
            "past_outcomes": [item.model_dump(mode="json") for item in outcomes],
            "notice": "Past outcomes are historical artifact checks, not current system state or policy.",
        }


def remember_completion(db: sqlite3.Connection, task_id: str, state: dict) -> None:
    """Commit an evidence record in the SAME transaction as the completed task checkpoint."""
    bot_id = state.get("bot_id")
    if not bot_id:
        return
    row = db.execute("SELECT workspace FROM tasks WHERE id=?", (task_id,)).fetchone()
    workspace = row["workspace"]
    MemoryStore.bot_row(db, workspace, bot_id)
    artifact_id = state.get("completion_artifact_id")
    artifact = state["artifacts"].get(artifact_id)
    if artifact is None:
        raise ValueError("A completion memory needs a saved artifact.")
    digest = hashlib.sha256(artifact["content"].encode()).hexdigest()
    citations = sorted(set(re.findall(r"\[(S\d+)\]", artifact["content"])))
    if (
        digest != artifact["sha256"]
        or state["readbacks"].get(artifact_id) != digest
        or not citations
        or not set(citations).issubset(state["sources"])
    ):
        raise ValueError("Completion memory verification failed.")
    evidence = {
        "artifact_id": artifact_id,
        "sha256": digest,
        "citations": citations,
        "checks": ["saved_artifact", "latest_content_readback", "citation_labels"],
        "semantic_accuracy_verified": False,
    }
    at = timestamp()
    db.execute(
        "INSERT INTO bot_memories VALUES (?, ?, ?, 'outcome', ?, ?, 'harness', ?, ?, NULL, ?, ?) "
        "ON CONFLICT(workspace, bot_id, kind, key) DO NOTHING",
        (
            uuid.uuid5(uuid.NAMESPACE_URL, f"{workspace}:{bot_id}:{task_id}").hex,
            workspace,
            bot_id,
            f"task:{task_id}",
            f"Saved artifact '{artifact['title']}' for task: {state['goal']}",
            task_id,
            json.dumps(evidence),
            at,
            at,
        ),
    )
