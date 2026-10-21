"""Run with python -m app.harness.worker. One worker per local SQLite database."""

from __future__ import annotations

import argparse
import fcntl
import signal
import threading
import time
from contextlib import contextmanager

from app.config import get_settings
from app.harness.memory import MemoryStore
from app.harness.model import ResponsesModel
from app.harness.routines import RoutineStore
from app.harness.runner import Harness
from app.harness.store import TaskStore
from app.harness.tools import document_tools
from app.studio.runtime import StudioRuntime
from app.studio.store import StudioStore


@contextmanager
def worker_lock(store: TaskStore):
    with store.path.with_suffix(".worker.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("A harness worker is already running for this database.") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Process at most one queued task and exit."
    )
    args = parser.parse_args()
    settings = get_settings()
    store = TaskStore(settings.harness_db_path.resolve())
    routines = RoutineStore(store, settings)
    studio = StudioStore(store)
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    with worker_lock(store):
        store.recover()
        studio.recover()
        next_dispatch = 0.0
        prefer_studio = True
        while not stop.is_set():
            if time.monotonic() >= next_dispatch:
                routines.dispatch()
                next_dispatch = time.monotonic() + 30
            studio_run = studio.claim() if prefer_studio else None
            task = store.claim() if studio_run is None else None
            if studio_run is None and task is None:
                studio_run = studio.claim()
            if studio_run is not None:
                StudioRuntime(studio, settings).run(studio_run, stop.is_set)
                prefer_studio = False
                if args.once:
                    return
                continue
            prefer_studio = True
            if task is None:
                if args.once:
                    return
                stop.wait(1)
                continue
            model = None
            try:
                model = ResponsesModel(settings)
                Harness(
                    store, model, document_tools(settings, memory=MemoryStore(store)), settings
                ).run(task, stop.is_set)
            except Exception as exc:
                import json

                state = json.loads(store.row(task["workspace"], task["id"])["state"])
                Harness.fail(state, exc, lambda status: store.checkpoint(task["id"], state, status))
            finally:
                if model is not None:
                    model.close()
            if args.once:
                return
            # Give API controls a chance to run even when tasks repeatedly fail immediately.
            time.sleep(0.05)


if __name__ == "__main__":
    main()
