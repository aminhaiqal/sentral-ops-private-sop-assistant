from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.harness.store import TaskStore
from app.studio.models import BotConfig, RunRequest, RunSummary, RunView, StudioBot
from app.studio.registry import REGISTRY, TEMPLATES
from app.studio.safety import StudioError
from app.studio.store import StudioConflict, StudioNotFound, StudioStore
from app.workspaces import workspace_id

router = APIRouter(prefix="/api/studio", tags=["Bot Studio"])


def studio_store():
    return StudioStore(TaskStore(get_settings().harness_db_path))


def call(operation):
    try:
        return operation()
    except StudioNotFound as exc:
        raise HTTPException(
            status_code=404, detail=str(exc), headers={"Cache-Control": "private, no-store"}
        ) from exc
    except StudioConflict as exc:
        raise HTTPException(
            status_code=409, detail=str(exc), headers={"Cache-Control": "private, no-store"}
        ) from exc
    except StudioError as exc:
        raise HTTPException(
            status_code=403 if exc.code == "permission_denied" else 422,
            detail=exc.message,
            headers={"Cache-Control": "private, no-store"},
        ) from exc


@router.get("/catalog")
def catalog(workspace: str = Depends(workspace_id)):
    settings = get_settings()
    return {
        "templates": TEMPLATES,
        "skills": [skill.metadata() for skill in REGISTRY.values()],
        "tools": [
            {
                "id": "brave_search",
                "name": "Brave Search",
                "configured": bool(settings.brave_search_api_key),
                "effect": "read",
                "setup": "Create a Web Search API key at https://api-dashboard.search.brave.com. Set BRAVE_SEARCH_API_KEY on the backend and worker, then restart them.",
            },
            {
                "id": "llm",
                "name": "AI provider",
                "configured": bool(settings.openai_api_key),
                "effect": "analyze_and_draft",
                "setup": "Set OPENAI_API_KEY, OPENAI_BASE_URL and OPENAI_CHAT_MODEL on the backend and worker. The provider must support Responses structured outputs.",
            },
            {
                "id": "database",
                "name": "Axelyn database",
                "configured": True,
                "effect": "internal_write",
                "setup": "Included. Results are isolated to your account.",
            },
        ],
        "manual_only": True,
        "credentials": "Server-managed connections. Credentials are never returned to the browser or stored in bot instructions.",
        "limits": {
            "max_prospects": 8,
            "max_steps": 4,
            "max_api_calls": settings.studio_max_api_calls,
            "max_llm_calls": settings.studio_max_llm_calls,
            "max_tokens": settings.studio_max_tokens,
        },
    }


@router.get("/bots", response_model=list[StudioBot])
def bots(workspace: str = Depends(workspace_id), store: StudioStore = Depends(studio_store)):
    return store.bots(workspace)


@router.post("/bots", response_model=StudioBot, status_code=201)
def create_bot(
    request: BotConfig,
    workspace: str = Depends(workspace_id),
    store: StudioStore = Depends(studio_store),
):
    return call(lambda: store.save_bot(workspace, request))


@router.get("/bots/{bot_id}", response_model=StudioBot)
def bot(
    bot_id: str, workspace: str = Depends(workspace_id), store: StudioStore = Depends(studio_store)
):
    return call(lambda: store.bot(workspace, bot_id))


@router.put("/bots/{bot_id}", response_model=StudioBot)
def edit_bot(
    bot_id: str,
    request: BotConfig,
    workspace: str = Depends(workspace_id),
    store: StudioStore = Depends(studio_store),
):
    return call(lambda: store.save_bot(workspace, request, bot_id))


@router.delete("/bots/{bot_id}", status_code=204)
def delete_bot(
    bot_id: str, workspace: str = Depends(workspace_id), store: StudioStore = Depends(studio_store)
):
    call(lambda: store.delete_bot(workspace, bot_id))


@router.post("/bots/{bot_id}/runs", response_model=RunView, status_code=202)
def execute_bot(
    bot_id: str,
    request: RunRequest,
    workspace: str = Depends(workspace_id),
    store: StudioStore = Depends(studio_store),
):
    return call(
        lambda: store.create_run(workspace, bot_id, request.idempotency_key, get_settings())
    )


@router.get("/runs", response_model=list[RunSummary])
def runs(
    bot_id: str | None = None,
    workspace: str = Depends(workspace_id),
    store: StudioStore = Depends(studio_store),
):
    return call(lambda: store.runs(workspace, bot_id))


@router.get("/runs/{run_id}", response_model=RunView)
def run(
    run_id: str, workspace: str = Depends(workspace_id), store: StudioStore = Depends(studio_store)
):
    return call(lambda: store.run(workspace, run_id))


@router.post("/runs/{run_id}/cancel", response_model=RunView)
def cancel_run(
    run_id: str, workspace: str = Depends(workspace_id), store: StudioStore = Depends(studio_store)
):
    return call(lambda: store.control(workspace, run_id))


@router.post("/runs/{run_id}/retry", response_model=RunView, status_code=202)
def retry_run(
    run_id: str, workspace: str = Depends(workspace_id), store: StudioStore = Depends(studio_store)
):
    return call(lambda: store.control(workspace, run_id, retry=True))
