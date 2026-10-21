from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.harness.memory import BotProfile, BotRequest, MemoryRecord, MemoryStore, PreferenceRequest
from app.harness.models import ResumeRequest, TaskRequest, TaskSummary, TaskView
from app.harness.routines import RoutineRequest, RoutineStore, RoutineView
from app.harness.store import TaskConflict, TaskStore
from app.workspaces import workspace_id

router = APIRouter(prefix="/api/tasks", tags=["Autopilot tasks"])
bots_router = APIRouter(prefix="/api/bots", tags=["Bot profiles and memory"])
routines_router = APIRouter(prefix="/api/routines", tags=["Scheduled bot routines"])


def task_store() -> TaskStore:
    return TaskStore(get_settings().harness_db_path)


def memory_store(store: TaskStore = Depends(task_store)) -> MemoryStore:
    return MemoryStore(store)


def routine_store(store: TaskStore = Depends(task_store)) -> RoutineStore:
    return RoutineStore(store, get_settings())


@routines_router.get("", response_model=list[RoutineView])
def list_routines(
    workspace: str = Depends(workspace_id), routines: RoutineStore = Depends(routine_store)
):
    return routines.list(workspace)


@routines_router.post("", response_model=RoutineView, status_code=201)
def create_routine(
    request: RoutineRequest,
    workspace: str = Depends(workspace_id),
    routines: RoutineStore = Depends(routine_store),
):
    return routines.save(workspace, request)


@routines_router.put("/{routine_id}", response_model=RoutineView)
def update_routine(
    routine_id: str,
    request: RoutineRequest,
    workspace: str = Depends(workspace_id),
    routines: RoutineStore = Depends(routine_store),
):
    return routines.save(workspace, request, routine_id)


@routines_router.delete("/{routine_id}", status_code=204, response_model=None)
def delete_routine(
    routine_id: str,
    workspace: str = Depends(workspace_id),
    routines: RoutineStore = Depends(routine_store),
):
    routines.delete(workspace, routine_id)


@routines_router.post("/{routine_id}/run", response_model=TaskView, status_code=202)
def run_routine(
    routine_id: str,
    workspace: str = Depends(workspace_id),
    routines: RoutineStore = Depends(routine_store),
):
    return routines.run_now(workspace, routine_id)


@bots_router.post("", response_model=BotProfile, status_code=201)
def create_bot(
    request: BotRequest,
    workspace: str = Depends(workspace_id),
    memory: MemoryStore = Depends(memory_store),
) -> BotProfile:
    return memory.create_bot(workspace, request)


@bots_router.get("", response_model=list[BotProfile])
def list_bots(
    workspace: str = Depends(workspace_id), memory: MemoryStore = Depends(memory_store)
) -> list[BotProfile]:
    return memory.list_bots(workspace)


@bots_router.post("/starter", response_model=list[BotProfile])
def starter_bots(
    workspace: str = Depends(workspace_id), memory: MemoryStore = Depends(memory_store)
) -> list[BotProfile]:
    return memory.starter_bots(workspace)


@bots_router.get("/{bot_id}", response_model=BotProfile)
def get_bot(
    bot_id: str, workspace: str = Depends(workspace_id), memory: MemoryStore = Depends(memory_store)
) -> BotProfile:
    return memory.get_bot(workspace, bot_id)


@bots_router.put("/{bot_id}", response_model=BotProfile)
def update_bot(
    bot_id: str,
    request: BotRequest,
    workspace: str = Depends(workspace_id),
    memory: MemoryStore = Depends(memory_store),
) -> BotProfile:
    return memory.update_bot(workspace, bot_id, request)


@bots_router.put("/{bot_id}/preferences/{key}", response_model=MemoryRecord)
def put_preference(
    bot_id: str,
    key: str,
    request: PreferenceRequest,
    workspace: str = Depends(workspace_id),
    memory: MemoryStore = Depends(memory_store),
) -> MemoryRecord:
    return memory.put_preference(workspace, bot_id, key, request)


@bots_router.get("/{bot_id}/memories", response_model=list[MemoryRecord])
def list_memories(
    bot_id: str,
    q: str = Query(default="", max_length=800),
    kind: Literal["preference", "outcome"] | None = None,
    include_expired: bool = False,
    limit: int = Query(default=50, ge=1, le=50),
    workspace: str = Depends(workspace_id),
    memory: MemoryStore = Depends(memory_store),
) -> list[MemoryRecord]:
    return memory.list_memories(
        workspace, bot_id, query=q, kind=kind, include_expired=include_expired, limit=limit
    )


@bots_router.delete("/{bot_id}/memories/{memory_id}", status_code=204, response_model=None)
def delete_memory(
    bot_id: str,
    memory_id: str,
    workspace: str = Depends(workspace_id),
    memory: MemoryStore = Depends(memory_store),
) -> None:
    memory.delete_memory(workspace, bot_id, memory_id)


@router.post("", response_model=TaskView, status_code=202)
def create_task(
    request: TaskRequest,
    workspace: str = Depends(workspace_id),
    store: TaskStore = Depends(task_store),
) -> TaskView:
    return store.create(workspace, request, get_settings())


@router.get("", response_model=list[TaskSummary])
def list_tasks(
    workspace: str = Depends(workspace_id), store: TaskStore = Depends(task_store)
) -> list[TaskSummary]:
    return store.list(workspace)


@router.get("/{task_id}", response_model=TaskView)
def get_task(
    task_id: str, workspace: str = Depends(workspace_id), store: TaskStore = Depends(task_store)
) -> TaskView:
    return store.get(workspace, task_id)


@router.post("/{task_id}/cancel", response_model=TaskView)
def cancel_task(
    task_id: str, workspace: str = Depends(workspace_id), store: TaskStore = Depends(task_store)
) -> TaskView:
    try:
        return store.cancel(workspace, task_id)
    except TaskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{task_id}/resume", response_model=TaskView, status_code=202)
def resume_task(
    task_id: str,
    request: ResumeRequest,
    workspace: str = Depends(workspace_id),
    store: TaskStore = Depends(task_store),
) -> TaskView:
    try:
        return store.resume(workspace, task_id, request.message)
    except TaskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
