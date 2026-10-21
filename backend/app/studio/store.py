"""Studio records share the harness's SQLite connection and single-worker lock."""

import json
import uuid
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.harness.store import TaskStore, now
from app.studio.models import BotConfig, RunSummary, RunView, SavedProspect, SaveOutput, StudioBot
from app.studio.safety import StudioError, company_domain, redact


class StudioNotFound(FileNotFoundError):
    pass


class StudioConflict(ValueError):
    pass


def log_event(state, kind, message, skill_id=None):
    state["logs"].append({"at": now(), "kind": kind, "skill_id": skill_id, "message": message})
    state["logs"] = state["logs"][-100:]


def mark_cancelled(state, message):
    state["completed_at"] = now()
    for step in state["steps"]:
        if step["status"] in {"running", "pending"}:
            step.update(status="skipped", completed_at=now())
    log_event(state, "cancelled", message)


class StudioStore:
    def __init__(self, tasks: TaskStore):
        self.tasks = tasks
        with tasks.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS studio_bots (
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, configuration TEXT NOT NULL,
                    revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    deleted_at TEXT, UNIQUE(workspace,id));
                CREATE INDEX IF NOT EXISTS studio_bots_owner ON studio_bots(workspace,deleted_at);
                CREATE TABLE IF NOT EXISTS studio_runs (
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, bot_id TEXT NOT NULL,
                    request_key TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, state TEXT NOT NULL,
                    UNIQUE(workspace,bot_id,request_key),
                    FOREIGN KEY(workspace,bot_id) REFERENCES studio_bots(workspace,id));
                CREATE INDEX IF NOT EXISTS studio_runs_owner ON studio_runs(workspace,bot_id,created_at);
                CREATE INDEX IF NOT EXISTS studio_runs_queue ON studio_runs(status,created_at);
                CREATE TABLE IF NOT EXISTS studio_prospects (
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, bot_id TEXT NOT NULL,
                    domain TEXT NOT NULL, run_id TEXT NOT NULL, data TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(workspace,bot_id,domain),
                    FOREIGN KEY(workspace,bot_id) REFERENCES studio_bots(workspace,id));
            """)

    @staticmethod
    def owned_bot(db, workspace, bot_id, *, archived=False):
        row = db.execute(
            "SELECT * FROM studio_bots WHERE workspace=? AND id=?", (workspace, bot_id)
        ).fetchone()
        if row is None or (row["deleted_at"] and not archived):
            raise StudioNotFound("Bot not found.")
        return row

    def bot_view(self, db, row):
        last = db.execute(
            "SELECT * FROM studio_runs WHERE workspace=? AND bot_id=? ORDER BY created_at DESC LIMIT 1",
            (row["workspace"], row["id"]),
        ).fetchone()
        return StudioBot(
            id=row["id"],
            configuration=json.loads(row["configuration"]),
            revision=row["revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_run=self.summary(last) if last else None,
        )

    def bots(self, workspace):
        with self.tasks.connection() as db:
            return [
                self.bot_view(db, row)
                for row in db.execute(
                    "SELECT * FROM studio_bots WHERE workspace=? AND deleted_at IS NULL ORDER BY created_at DESC",
                    (workspace,),
                ).fetchall()
            ]

    def bot(self, workspace, bot_id):
        with self.tasks.connection() as db:
            return self.bot_view(db, self.owned_bot(db, workspace, bot_id))

    def save_bot(self, workspace, config: BotConfig, bot_id=None):
        config = BotConfig.model_validate(redact(config.model_dump()))
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            at = now()
            if bot_id:
                self.owned_bot(db, workspace, bot_id)
                db.execute(
                    "UPDATE studio_bots SET configuration=?,revision=revision+1,updated_at=? WHERE workspace=? AND id=?",
                    (config.model_dump_json(), at, workspace, bot_id),
                )
            else:
                if (
                    db.execute(
                        "SELECT count(*) FROM studio_bots WHERE workspace=? AND deleted_at IS NULL",
                        (workspace,),
                    ).fetchone()[0]
                    >= 50
                ):
                    raise StudioConflict(
                        "Your library has 50 bots. Delete one before creating another."
                    )
                bot_id = uuid.uuid4().hex
                db.execute(
                    "INSERT INTO studio_bots VALUES (?,?,?,1,?,?,NULL)",
                    (bot_id, workspace, config.model_dump_json(), at, at),
                )
            return self.bot_view(db, self.owned_bot(db, workspace, bot_id))

    def delete_bot(self, workspace, bot_id):
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.owned_bot(db, workspace, bot_id)
            db.execute(
                "UPDATE studio_bots SET deleted_at=?,updated_at=? WHERE workspace=? AND id=?",
                (now(), now(), workspace, bot_id),
            )
            for row in db.execute(
                "SELECT * FROM studio_runs WHERE workspace=? AND bot_id=? AND status IN ('queued','running')",
                (workspace, bot_id),
            ).fetchall():
                state = json.loads(row["state"])
                mark_cancelled(state, "Bot deleted; active execution cancelled.")
                db.execute(
                    "UPDATE studio_runs SET status='cancelled',state=?,updated_at=? WHERE id=?",
                    (json.dumps(state), now(), row["id"]),
                )

    def create_run(self, workspace, bot_id, request_key, settings: Settings):
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            bot = self.owned_bot(db, workspace, bot_id)
            existing = db.execute(
                "SELECT * FROM studio_runs WHERE workspace=? AND bot_id=? AND request_key=?",
                (workspace, bot_id, request_key),
            ).fetchone()
            if existing:
                return self.view(existing)
            config = BotConfig.model_validate_json(bot["configuration"])
            self.authorize(config)
            active = db.execute(
                "SELECT * FROM studio_runs WHERE workspace=? AND bot_id=? AND status IN ('queued','running')",
                (workspace, bot_id),
            ).fetchone()
            if active:
                return self.view(active)
            if (
                db.execute(
                    "SELECT count(*) FROM studio_runs WHERE workspace=? AND status IN ('queued','running')",
                    (workspace,),
                ).fetchone()[0]
                >= 3
            ):
                raise StudioConflict(
                    "Three runs are already queued or running. Wait for one to finish."
                )
            run_id, at = uuid.uuid4().hex, now()
            priced = (
                settings.studio_input_usd_per_million is not None
                and settings.studio_output_usd_per_million is not None
            )
            state = {
                "configuration": config.model_dump(),
                "bot_revision": bot["revision"],
                "started_at": None,
                "completed_at": None,
                "deadline_at": None,
                "steps": [
                    {
                        "skill_id": skill,
                        "status": "pending",
                        "attempts": 0,
                        "started_at": None,
                        "completed_at": None,
                        "input": None,
                        "output": None,
                        "error": None,
                    }
                    for skill in config.skills
                ],
                "result": None,
                "error": None,
                "logs": [],
                "approvals": [],
                "usage": {
                    "api_calls": 0,
                    "llm_calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "charged_token_bound": 0,
                    "estimated_cost_usd": 0.0 if priced else None,
                },
                "pricing": {
                    "input": settings.studio_input_usd_per_million,
                    "output": settings.studio_output_usd_per_million,
                },
                "limits": {
                    "max_steps": len(config.skills),
                    "max_api_calls": settings.studio_max_api_calls,
                    "max_llm_calls": settings.studio_max_llm_calls,
                    "max_tokens": settings.studio_max_tokens,
                    "max_cost_usd": settings.studio_max_cost_usd if priced else None,
                    "timeout_seconds": settings.studio_run_timeout_seconds,
                },
            }
            log_event(state, "queued", "Manual execution queued.")
            db.execute(
                "INSERT INTO studio_runs VALUES (?,?,?,?,?,?,?,?)",
                (run_id, workspace, bot_id, request_key, "queued", at, at, json.dumps(state)),
            )
            row = db.execute("SELECT * FROM studio_runs WHERE id=?", (run_id,)).fetchone()
            return self.view(row)

    @staticmethod
    def authorize(config):
        if not config.enabled:
            raise StudioError("permission_denied", "Enable this bot before running it.")
        missing = {"brave_search", "llm", "database"} - set(config.tools)
        if missing:
            raise StudioError(
                "permission_denied",
                "Grant the required tools before running: " + ", ".join(sorted(missing)),
            )

    @staticmethod
    def view(row):
        state = json.loads(row["state"])
        saved = next(
            (
                step["output"]
                for step in state["steps"]
                if step["skill_id"] == "save" and step["status"] == "completed"
            ),
            None,
        )
        return RunView(
            **{key: row[key] for key in ("id", "bot_id", "status", "created_at", "updated_at")},
            bot_name=state["configuration"]["name"],
            result_count=len(state["result"]["prospects"])
            if state["result"]
            else saved["saved_count"]
            if saved
            else 0,
            **{
                key: redact(state[key])
                for key in (
                    "configuration",
                    "started_at",
                    "completed_at",
                    "error",
                    "usage",
                    "steps",
                    "result",
                    "logs",
                    "approvals",
                    "limits",
                )
            },
        )

    @classmethod
    def summary(cls, row):
        data = cls.view(row).model_dump()
        return RunSummary(**{key: data[key] for key in RunSummary.model_fields})

    def row(self, workspace, run_id):
        with self.tasks.connection() as db:
            row = db.execute(
                "SELECT * FROM studio_runs WHERE workspace=? AND id=?", (workspace, run_id)
            ).fetchone()
            if row is None:
                raise StudioNotFound("Execution not found.")
            return dict(row)

    def run(self, workspace, run_id):
        return self.view(self.row(workspace, run_id))

    def runs(self, workspace, bot_id=None):
        with self.tasks.connection() as db:
            if bot_id:
                self.owned_bot(db, workspace, bot_id, archived=True)
            return [
                self.summary(row)
                for row in db.execute(
                    "SELECT * FROM studio_runs WHERE workspace=? AND (? IS NULL OR bot_id=?) ORDER BY created_at DESC LIMIT 100",
                    (workspace, bot_id, bot_id),
                ).fetchall()
            ]

    def claim(self):
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM studio_runs WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            state = json.loads(row["state"])
            if not state["started_at"]:
                state["started_at"] = now()
                state["deadline_at"] = (
                    datetime.now(UTC) + timedelta(seconds=state["limits"]["timeout_seconds"])
                ).isoformat()
            db.execute(
                "UPDATE studio_runs SET status='running',state=?,updated_at=? WHERE id=?",
                (json.dumps(state), now(), row["id"]),
            )
            return dict(row) | {"status": "running", "state": json.dumps(state)}

    def checkpoint(self, run_id, state, status="running"):
        with self.tasks.connection() as db:
            return (
                db.execute(
                    "UPDATE studio_runs SET state=?,status=?,updated_at=? WHERE id=? AND status='running'",
                    (json.dumps(redact(state)), status, now(), run_id),
                ).rowcount
                == 1
            )

    def recover(self):
        with self.tasks.connection() as db:
            for row in db.execute("SELECT * FROM studio_runs WHERE status='running'").fetchall():
                state = json.loads(row["state"])
                for step in state["steps"]:
                    if step["status"] == "running":
                        step["status"] = "pending"
                log_event(
                    state,
                    "recovered",
                    "Worker restarted. Completed steps are retained; uncertain API calls keep their budget reservation.",
                )
                db.execute(
                    "UPDATE studio_runs SET status='queued',state=?,updated_at=? WHERE id=?",
                    (json.dumps(state), now(), row["id"]),
                )

    def control(self, workspace, run_id, *, retry=False):
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM studio_runs WHERE workspace=? AND id=?", (workspace, run_id)
            ).fetchone()
            if row is None:
                raise StudioNotFound("Execution not found.")
            state = json.loads(row["state"])
            if retry:
                config = BotConfig.model_validate_json(
                    self.owned_bot(db, workspace, row["bot_id"])["configuration"]
                )
                self.authorize(config)
                if row["status"] != "failed" or not state["error"]["retryable"]:
                    raise StudioConflict(
                        "This run cannot be retried. Update the bot and start a new run."
                    )
                if state["deadline_at"] and datetime.fromisoformat(
                    state["deadline_at"]
                ) <= datetime.now(UTC):
                    raise StudioConflict("This run has expired. Start a new execution.")
                if any(
                    step["status"] == "failed" and step["attempts"] >= 3 for step in state["steps"]
                ):
                    raise StudioConflict(
                        "This step reached its retry limit. Start a new execution after reviewing the error."
                    )
                if (
                    db.execute(
                        "SELECT count(*) FROM studio_runs WHERE workspace=? AND status IN ('queued','running')",
                        (workspace,),
                    ).fetchone()[0]
                    >= 3
                ):
                    raise StudioConflict(
                        "Three runs are already queued or running. Wait for one to finish."
                    )
                if db.execute(
                    "SELECT 1 FROM studio_runs WHERE bot_id=? AND status IN ('queued','running')",
                    (row["bot_id"],),
                ).fetchone():
                    raise StudioConflict("This bot already has an active run.")
                for step in state["steps"]:
                    if step["status"] == "failed":
                        step.update(status="pending", error=None, completed_at=None)
                state.update(error=None, completed_at=None)
                status = "queued"
                log_event(
                    state,
                    "retry",
                    "Retry requested. Previous results and spending limits are retained.",
                )
            else:
                if row["status"] not in {"queued", "running"}:
                    raise StudioConflict("Only queued or running executions can be cancelled.")
                status = "cancelled"
                mark_cancelled(state, "Execution cancelled by its owner.")
            db.execute(
                "UPDATE studio_runs SET status=?,state=?,updated_at=? WHERE id=?",
                (status, json.dumps(state), now(), run_id),
            )
            return self.view(
                db.execute("SELECT * FROM studio_runs WHERE id=?", (run_id,)).fetchone()
            )

    def save_prospects(self, workspace, bot_id, run_id, prospects, *, state):
        saved = []
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT 1 FROM studio_runs WHERE workspace=? AND bot_id=? AND id=? AND status='running'",
                (workspace, bot_id, run_id),
            ).fetchone()
            if not active:
                raise StudioError("cancelled", "Execution was stopped before saving.")
            current = BotConfig.model_validate_json(
                self.owned_bot(db, workspace, bot_id)["configuration"]
            )
            if not current.enabled or "database" not in current.tools:
                raise StudioError("permission_denied", "Database access was revoked before saving.")
            for prospect in prospects:
                domain = company_domain(prospect.url)
                prospect_id = uuid.uuid5(
                    uuid.NAMESPACE_URL, f"studio:{workspace}:{bot_id}:{domain}"
                ).hex
                item = SavedProspect(**prospect.model_dump(), id=prospect_id)
                db.execute(
                    "INSERT INTO studio_prospects VALUES (?,?,?,?,?,?,?) ON CONFLICT(workspace,bot_id,domain) DO UPDATE SET run_id=excluded.run_id,data=excluded.data,updated_at=excluded.updated_at",
                    (
                        prospect_id,
                        workspace,
                        bot_id,
                        domain,
                        run_id,
                        json.dumps(redact(item.model_dump())),
                        now(),
                    ),
                )
                saved.append(item)
            output = SaveOutput(prospects=saved, saved_count=len(saved))
            step = next(step for step in state["steps"] if step["skill_id"] == "save")
            step.update(status="completed", completed_at=now(), output=output.model_dump())
            log_event(
                state,
                "results_saved",
                f"Committed {len(saved)} prospect records and the Save step together.",
                "save",
            )
            db.execute(
                "UPDATE studio_runs SET state=?,updated_at=? WHERE id=? AND status='running'",
                (json.dumps(redact(state)), now(), run_id),
            )
        return output
