from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.harness.models import ResumeRequest, TaskRequest, TaskSummary, TaskView
from app.harness.store import TaskConflict, TaskStore
from app.workspaces import workspace_id

router = APIRouter(prefix="/api/tasks", tags=["Document tasks"])


def task_store() -> TaskStore:
    return TaskStore(get_settings().harness_db_path)


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
