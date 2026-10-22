"""Account-owned Google grants and single-use, browser-bound OAuth attempts."""

import hashlib
import hmac
import time
import uuid
from datetime import UTC, datetime, timedelta

from app.connections.vault import TokenVault
from app.harness.store import now
from app.studio.safety import StudioError, plain_text, redact


def provider_scope(settings):
    return hashlib.sha256(
        f"google-drive:v1:{settings.google_drive_client_id}:{settings.google_drive_redirect_uri}".encode()
    ).hexdigest()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


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
                CREATE TABLE IF NOT EXISTS google_drive_credentials (
                    connection_id TEXT PRIMARY KEY REFERENCES app_connections(id),
                    ciphertext TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS google_drive_oauth (
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, scope TEXT NOT NULL,
                    state_hash TEXT UNIQUE NOT NULL, browser_hash TEXT NOT NULL,
                    status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    secrets TEXT, connection_id TEXT, error TEXT);
                CREATE INDEX IF NOT EXISTS drive_oauth_owner ON google_drive_oauth(workspace,scope,created_at);
            """)
            db.execute(
                "UPDATE google_drive_oauth SET status='expired',secrets=NULL WHERE expires_at<? AND status IN ('pending','exchanging','ready')",
                (time.time(),),
            )
            db.execute("DELETE FROM google_drive_oauth WHERE expires_at<?", (time.time() - 86400,))
        self.vault = TokenVault(tasks, settings)

    def binding(self, kind, workspace, identifier):
        return f"{kind}:{self.scope}:{workspace}:{identifier}"

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
            raise StudioError(
                "connection_not_found",
                "Connection not found. Connect your Google Drive account again.",
            )
        if active and row["status"] != "connected":
            raise StudioError(
                "connection_revoked",
                "Google Drive is disconnected or needs authorization. Open Connections to reconnect.",
            )
        return dict(row)

    def begin_auth(self, workspace, state, browser, verifier):
        flow_id = uuid.uuid4().hex
        encrypted = self.vault.encrypt(
            {"verifier": verifier}, self.binding("oauth", workspace, flow_id)
        )
        at = time.time()
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT count(*) FROM google_drive_oauth WHERE workspace=? AND created_at>?",
                (workspace, at - 600),
            ).fetchone()[0]
            if count >= 10:
                raise StudioError(
                    "connection_rate_limit",
                    "Too many Google sign-in attempts. Wait a few minutes before trying again.",
                )
            db.execute(
                "INSERT INTO google_drive_oauth VALUES (?,?,?,?,?,'pending',?,?,?,NULL,NULL)",
                (
                    flow_id,
                    workspace,
                    self.scope,
                    digest(state),
                    digest(browser),
                    at,
                    at + 600,
                    encrypted,
                ),
            )
        return flow_id

    def flow(self, workspace, flow_id):
        with self.tasks.connection() as db:
            db.execute(
                "UPDATE google_drive_oauth SET status='expired',secrets=NULL WHERE workspace=? AND scope=? AND id=? AND expires_at<? AND status IN ('pending','exchanging','ready')",
                (workspace, self.scope, flow_id, time.time()),
            )
            row = db.execute(
                "SELECT * FROM google_drive_oauth WHERE workspace=? AND scope=? AND id=?",
                (workspace, self.scope, flow_id),
            ).fetchone()
        if row is None:
            raise StudioError("connection_not_found", "Google sign-in attempt not found.")
        return dict(row)

    def consume_callback(self, state, browser):
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM google_drive_oauth WHERE scope=? AND state_hash=?",
                (self.scope, digest(state)),
            ).fetchone()
            if (
                row is None
                or row["expires_at"] <= time.time()
                or row["status"] != "pending"
                or not hmac.compare_digest(row["browser_hash"], digest(browser))
            ):
                raise StudioError(
                    "authorization_failed",
                    "This Google sign-in attempt is invalid or expired. Return to Axelyn and click Connect again.",
                )
            secrets = self.vault.decrypt(
                row["secrets"], self.binding("oauth", row["workspace"], row["id"])
            )
            db.execute("UPDATE google_drive_oauth SET status='exchanging' WHERE id=?", (row["id"],))
        return dict(row), secrets["verifier"]

    def flow_for_state(self, state):
        with self.tasks.connection() as db:
            row = db.execute(
                "SELECT id FROM google_drive_oauth WHERE scope=? AND state_hash=?",
                (self.scope, digest(state)),
            ).fetchone()
        if not row:
            raise StudioError(
                "authorization_failed", "This Google sign-in attempt is invalid or expired."
            )
        return row["id"]

    def ready(self, row, token, account):
        encrypted = self.vault.encrypt(
            {"token": token, "account": account}, self.binding("oauth", row["workspace"], row["id"])
        )
        with self.tasks.connection() as db:
            changed = db.execute(
                "UPDATE google_drive_oauth SET status='ready',secrets=? WHERE id=? AND status='exchanging' AND expires_at>?",
                (encrypted, row["id"], time.time()),
            ).rowcount
        if not changed:
            raise StudioError("authorization_failed", "This Google sign-in attempt has expired.")

    def fail(self, flow_id, error="authorization_failed"):
        with self.tasks.connection() as db:
            db.execute(
                "UPDATE google_drive_oauth SET status='failed',secrets=NULL,error=? WHERE id=? AND status IN ('pending','exchanging','ready')",
                (error, flow_id),
            )

    def cancel_auth(self, workspace, flow_id):
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            flow = db.execute(
                "SELECT status FROM google_drive_oauth WHERE workspace=? AND scope=? AND id=?",
                (workspace, self.scope, flow_id),
            ).fetchone()
            if flow is None:
                raise StudioError("connection_not_found", "Google sign-in attempt not found.")
            if flow["status"] == "complete":
                raise StudioError(
                    "authorization_completed",
                    "Google Drive is already connected. Disconnect the account to remove access.",
                )
            db.execute(
                "UPDATE google_drive_oauth SET status='failed',secrets=NULL,error='authorization_cancelled' WHERE id=?",
                (flow_id,),
            )

    def complete_auth(self, workspace, flow_id):
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            flow = db.execute(
                "SELECT * FROM google_drive_oauth WHERE workspace=? AND scope=? AND id=?",
                (workspace, self.scope, flow_id),
            ).fetchone()
            if flow is None:
                raise StudioError("connection_not_found", "Google sign-in attempt not found.")
            if flow["status"] == "complete":
                connection_id = flow["connection_id"]
            else:
                if flow["status"] != "ready" or flow["expires_at"] <= time.time():
                    raise StudioError(
                        "authorization_failed",
                        "Google authorization is not complete. Click Connect again if the sign-in attempt expired.",
                    )
                payload = self.vault.decrypt(
                    flow["secrets"], self.binding("oauth", workspace, flow_id)
                )
                account, token = payload["account"], payload["token"]
                existing = db.execute(
                    "SELECT id FROM app_connections WHERE workspace=? AND scope=? AND account_id=?",
                    (workspace, self.scope, account["id"]),
                ).fetchone()
                connection_id = existing["id"] if existing else uuid.uuid4().hex
                name = redact(plain_text(account["name"], 160)) or "Google Drive account"
                at = now()
                db.execute(
                    "INSERT INTO app_connections VALUES (?,?,?,?,?,'connected',?,?) ON CONFLICT(workspace,scope,account_id) DO UPDATE SET name=excluded.name,status='connected',checked_at=excluded.checked_at",
                    (connection_id, workspace, self.scope, account["id"], name, at, at),
                )
                encrypted = self.vault.encrypt(
                    token, self.binding("credentials", workspace, connection_id)
                )
                db.execute(
                    "INSERT INTO google_drive_credentials VALUES (?,?,1) ON CONFLICT(connection_id) DO UPDATE SET ciphertext=excluded.ciphertext,revision=revision+1",
                    (connection_id, encrypted),
                )
                db.execute(
                    "UPDATE google_drive_oauth SET status='complete',secrets=NULL,connection_id=? WHERE id=?",
                    (connection_id, flow_id),
                )
        return self.view(self.owned(workspace, connection_id, active=False))

    def tokens(self, workspace, connection_id):
        self.owned(workspace, connection_id)
        with self.tasks.connection() as db:
            row = db.execute(
                "SELECT * FROM google_drive_credentials WHERE connection_id=?", (connection_id,)
            ).fetchone()
        if row is None:
            raise StudioError(
                "connection_revoked", "Google Drive needs fresh authorization. Click Connect again."
            )
        return self.vault.decrypt(
            row["ciphertext"], self.binding("credentials", workspace, connection_id)
        ), row["revision"]

    def update_tokens(self, workspace, connection_id, token, revision):
        encrypted = self.vault.encrypt(token, self.binding("credentials", workspace, connection_id))
        with self.tasks.connection() as db:
            db.execute(
                "UPDATE google_drive_credentials SET ciphertext=?,revision=revision+1 WHERE connection_id=? AND revision=? AND EXISTS (SELECT 1 FROM app_connections WHERE id=? AND workspace=? AND scope=? AND status='connected')",
                (encrypted, connection_id, revision, connection_id, workspace, self.scope),
            )
        return self.tokens(workspace, connection_id)[0]

    def mark_reconnect(self, workspace, connection_id):
        with self.tasks.connection() as db:
            db.execute(
                "UPDATE app_connections SET status='reconnect_required',checked_at=? WHERE id=? AND workspace=? AND scope=? AND status='connected'",
                (now(), connection_id, workspace, self.scope),
            )

    def disconnect(self, workspace, connection_id):
        self.owned(workspace, connection_id, active=False)
        with self.tasks.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            credential = db.execute(
                "SELECT ciphertext FROM google_drive_credentials WHERE connection_id=?",
                (connection_id,),
            ).fetchone()
            db.execute(
                "UPDATE app_connections SET status='disconnected',checked_at=? WHERE id=? AND workspace=? AND scope=?",
                (now(), connection_id, workspace, self.scope),
            )
            db.execute(
                "DELETE FROM google_drive_credentials WHERE connection_id=?", (connection_id,)
            )
        return credential["ciphertext"] if credential else None

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
