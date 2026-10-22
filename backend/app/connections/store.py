import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from app.harness.store import now
from app.studio.safety import StudioError, plain_text, redact


def provider_scope(settings):
    return hashlib.sha256(
        f"{settings.pipedream_project_id}:{settings.pipedream_environment}:{settings.pipedream_client_id}".encode()
    ).hexdigest()


class ConnectionStore:
    def __init__(self, tasks, settings):
        self.tasks, self.scope = tasks, provider_scope(settings)
        with tasks.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS app_connections (
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, scope TEXT NOT NULL,
                    account_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, checked_at TEXT NOT NULL,
                    UNIQUE(workspace,scope,account_id));
                CREATE INDEX IF NOT EXISTS connections_owner ON app_connections(workspace,scope);
                CREATE TABLE IF NOT EXISTS connection_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, workspace TEXT NOT NULL,
                    connection_id TEXT, operation TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS connection_activity_owner ON connection_activity(workspace,created_at);
            """)

    @staticmethod
    def view(row):
        return {
            "provider": "google_drive",
            **{key: row[key] for key in ("id", "name", "status", "created_at", "checked_at")},
        }

    def list(self, workspace):
        with self.tasks.connection() as db:
            return [
                self.view(row)
                for row in db.execute(
                    "SELECT * FROM app_connections WHERE workspace=? AND scope=? ORDER BY created_at DESC",
                    (workspace, self.scope),
                )
            ]

    def owned(self, workspace, connection_id, *, active=True):
        with self.tasks.connection() as db:
            row = db.execute(
                "SELECT * FROM app_connections WHERE workspace=? AND scope=? AND id=?",
                (workspace, self.scope, connection_id),
            ).fetchone()
        if row is None:
            raise StudioError("connection_not_found", "Connection not found.")
        if active and row["status"] != "connected":
            raise StudioError(
                "connection_revoked",
                "Google Drive is disconnected or needs authorization. Open Connections to reconnect.",
            )
        return dict(row)

    def sync(self, workspace, accounts):
        at = now()
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # A local disconnect remains authoritative, including when provider deletion failed.
            db.execute(
                "UPDATE app_connections SET status='reconnect_required',checked_at=? WHERE workspace=? AND scope=? AND status='connected'",
                (at, workspace, self.scope),
            )
            for account in accounts:
                status = (
                    "connected"
                    if account["healthy"] and not account["dead"]
                    else "reconnect_required"
                )
                name = redact(plain_text(account["name"], 160)) or "Google Drive account"
                db.execute(
                    "INSERT INTO app_connections VALUES (?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(workspace,scope,account_id) DO UPDATE SET name=excluded.name,"
                    "status=CASE WHEN app_connections.status='disconnected' THEN 'disconnected' ELSE excluded.status END,checked_at=excluded.checked_at",
                    (uuid.uuid4().hex, workspace, self.scope, account["id"], name, status, at, at),
                )
        return self.list(workspace)

    def disconnect(self, workspace, connection_id):
        row = self.owned(workspace, connection_id, active=False)
        with self.tasks.connection() as db:
            db.execute(
                "UPDATE app_connections SET status='disconnected',checked_at=? WHERE id=? AND workspace=?",
                (now(), connection_id, workspace),
            )
        return row

    def enable(self, workspace, connection_id):
        self.owned(workspace, connection_id, active=False)
        with self.tasks.connection() as db:
            db.execute(
                "UPDATE app_connections SET status='connected',checked_at=? WHERE workspace=? AND id=?",
                (now(), workspace, connection_id),
            )

    def record(self, workspace, connection_id, operation, status):
        with self.tasks.connection() as db:
            db.execute(
                "INSERT INTO connection_activity(workspace,connection_id,operation,status,created_at) VALUES (?,?,?,?,?)",
                (workspace, connection_id, operation, status, now()),
            )
            db.execute(
                "DELETE FROM connection_activity WHERE workspace=? AND id NOT IN (SELECT id FROM connection_activity WHERE workspace=? ORDER BY id DESC LIMIT 200)",
                (workspace, workspace),
            )

    def begin_operation(self, workspace, connection_id, operation):
        since = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT count(*) FROM connection_activity WHERE workspace=? AND status='started' AND created_at>?",
                (workspace, since),
            ).fetchone()[0]
            if count >= 30:
                raise StudioError(
                    "connection_rate_limit",
                    "Too many connection requests. Wait a minute before trying again.",
                    retryable=True,
                )
            db.execute(
                "INSERT INTO connection_activity(workspace,connection_id,operation,status,created_at) VALUES (?,?,?,?,?)",
                (workspace, connection_id, operation, "started", now()),
            )

    def activity(self, workspace):
        with self.tasks.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT connection_id,operation,status,created_at FROM connection_activity WHERE workspace=? ORDER BY id DESC LIMIT 30",
                    (workspace,),
                )
            ]
