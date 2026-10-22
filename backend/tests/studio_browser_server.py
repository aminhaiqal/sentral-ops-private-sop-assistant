"""Browser-test server only. Production images do not include tests or fake providers."""

import argparse
import os
import threading
import time
from pathlib import Path

import jwt
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.config as configuration
from app.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--frontend-origin", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    settings = Settings(
        _env_file=None,
        harness_db_path=args.state_dir / "browser.sqlite3",
        clerk_issuer_url="https://clerk.test",
        clerk_jwt_key=public,
        backend_cors_origins=args.frontend_origin,
        clerk_authorized_parties=args.frontend_origin,
        openai_api_key="browser-test-configured",
        brave_search_api_key="browser-test-configured",
        pipedream_client_id="browser-test-configured",
        pipedream_client_secret="browser-test-configured",
        pipedream_project_id="proj_BrowserTest",
        auto_ingest_on_startup=False,
        studio_input_usd_per_million=1,
        studio_output_usd_per_million=2,
    )
    configuration.get_settings = lambda: settings
    from test_connections import FakeDriveProvider
    from test_studio import FakeProviders

    from app.connections.provider import PipedreamProvider

    # Replace only the external provider boundary, for all API/worker instances.
    drive = FakeDriveProvider()
    PipedreamProvider.connect_link = lambda self, *args, **kwargs: drive.connect_link(
        *args, **kwargs
    )
    PipedreamProvider.accounts = lambda self, *args, **kwargs: drive.accounts(*args, **kwargs)
    PipedreamProvider.delete_account = lambda self, *args, **kwargs: drive.delete_account(
        *args, **kwargs
    )
    PipedreamProvider.tools = lambda self, *args, **kwargs: drive.tools(*args, **kwargs)

    from app.harness.store import TaskStore
    from app.harness.worker import worker_lock
    from app.main import app
    from app.studio.runtime import StudioRuntime
    from app.studio.store import StudioStore

    for user in ["owner", "stranger"]:
        at = int(time.time())
        token = jwt.encode(
            {
                "iss": "https://clerk.test",
                "sub": f"user_browser_{user}",
                "sid": f"sess_browser_{user}",
                "iat": at - 1,
                "nbf": at - 1,
                "exp": at + 3600,
                "azp": args.frontend_origin,
            },
            private,
            algorithm="RS256",
            headers={"kid": "browser-test"},
        )
        fd = os.open(args.state_dir / f"{user}.token", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(token)
    tasks = TaskStore(settings.harness_db_path)
    store = StudioStore(tasks)
    stop = threading.Event()

    def work():
        with worker_lock(tasks):
            store.recover()
            while not stop.is_set():
                settings.brave_search_api_key = (
                    None
                    if (args.state_dir / "disable-search").exists()
                    else "browser-test-configured"
                )
                row = store.claim()
                if row:
                    StudioRuntime(store, settings, FakeProviders()).run(row, stop.is_set)
                stop.wait(0.1)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        stop.set()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
