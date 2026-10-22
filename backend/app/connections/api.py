from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.config import get_settings
from app.connections.drive import DriveService
from app.connections.models import ConnectionView, DriveDocument, DriveFile
from app.connections.provider import SETUP, connection_errors
from app.connections.store import ConnectionStore
from app.harness.store import TaskStore
from app.studio.safety import StudioError
from app.workspaces import workspace_id

router = APIRouter(prefix="/api/connections", tags=["Connections"])
ConnectionId = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]
FileId = Annotated[str, Path(min_length=5, max_length=180, pattern=r"^[a-zA-Z0-9_-]+$")]


def drive_service():
    settings = get_settings()
    return DriveService(ConnectionStore(TaskStore(settings.harness_db_path), settings), settings)


async def operation(service, workspace, name, handler, connection_id=None):
    try:
        service.store.begin_operation(workspace, connection_id, name)
        async with connection_errors():
            result = await handler()
        service.store.record(workspace, connection_id, name, "completed")
        return result
    except StudioError as exc:
        service.store.record(workspace, connection_id, name, exc.code)
        status = (
            404
            if exc.code == "connection_not_found"
            else 403
            if exc.code in {"permission_denied", "connection_revoked"}
            else 429
            if exc.code == "connection_rate_limit"
            else 503
            if exc.retryable
            else 422
        )
        raise HTTPException(
            status_code=status, detail=exc.message, headers={"Cache-Control": "private, no-store"}
        ) from None


@router.get("")
def connections(workspace: str = Depends(workspace_id), service=Depends(drive_service)):
    return {
        "provider": "pipedream",
        "configured": service.settings.connections_configured,
        "environment": service.settings.pipedream_environment,
        "setup": SETUP,
        "connections": service.store.list(workspace),
        "capabilities": ["Search file names", "Read selected Google Docs and text files"],
        "activity": service.store.activity(workspace),
    }


@router.post("/google-drive/connect")
async def connect(workspace: str = Depends(workspace_id), service=Depends(drive_service)):
    return await operation(
        service, workspace, "connect", lambda: service.provider.connect_link(workspace)
    )


@router.post("/google-drive/sync", response_model=list[ConnectionView])
async def sync(workspace: str = Depends(workspace_id), service=Depends(drive_service)):
    return await operation(service, workspace, "refresh_accounts", lambda: service.sync(workspace))


@router.get("/{connection_id}/files", response_model=list[DriveFile])
async def files(
    connection_id: ConnectionId,
    query: str = Query(default="", max_length=180),
    workspace: str = Depends(workspace_id),
    service=Depends(drive_service),
):
    async def search():
        async with service.session(workspace, connection_id) as session:
            return await session.search(query.strip())

    return await operation(service, workspace, "search_files", search, connection_id)


@router.get("/{connection_id}/files/{file_id}", response_model=DriveDocument)
async def document(
    connection_id: ConnectionId,
    file_id: FileId,
    workspace: str = Depends(workspace_id),
    service=Depends(drive_service),
):
    async def read():
        async with service.session(workspace, connection_id) as session:
            return await session.read(file_id)

    return await operation(service, workspace, "read_file", read, connection_id)


@router.delete("/{connection_id}")
async def disconnect(
    connection_id: ConnectionId,
    workspace: str = Depends(workspace_id),
    service=Depends(drive_service),
):
    async def remove():
        row = service.store.disconnect(workspace, connection_id)
        try:
            async with connection_errors(15):
                await service.provider.delete_account(workspace, row["account_id"])
        except StudioError:
            # Local revocation takes effect even if the provider is offline.
            return {
                "disconnected": True,
                "provider_removed": False,
                "message": "Access is disabled in Axelyn. Provider removal could not be confirmed; retry Disconnect or revoke the account in Pipedream before reconnecting.",
            }
        return {
            "disconnected": True,
            "provider_removed": True,
            "message": "Google Drive disconnected. Saved execution history is retained.",
        }

    return await operation(service, workspace, "disconnect", remove, connection_id)


@router.post("/{connection_id}/reconnect")
async def reconnect(
    connection_id: ConnectionId,
    workspace: str = Depends(workspace_id),
    service=Depends(drive_service),
):
    async def enable():
        row = service.store.owned(workspace, connection_id, active=False)
        accounts = await service.provider.accounts(workspace)
        if not any(
            account["id"] == row["account_id"] and account["healthy"] and not account["dead"]
            for account in accounts
        ):
            raise StudioError(
                "connection_revoked",
                "This account needs fresh Google authorization. Choose Connect Google Drive, complete authorization, then refresh accounts.",
            )
        service.store.enable(workspace, connection_id)
        return {
            "message": "Google Drive access restored for this account. Bot file selections still apply."
        }

    return await operation(service, workspace, "reconnect", enable, connection_id)
