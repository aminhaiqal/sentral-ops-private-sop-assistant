import html
import secrets
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import HTMLResponse

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
CALLBACK_PATH = "/api/connections/google-drive/callback"


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
            if exc.code in {"permission_denied", "connection_revoked", "authorization_failed"}
            else 429
            if exc.code == "connection_rate_limit"
            else 503
            if exc.code == "configuration_error" or exc.retryable
            else 422
        )
        raise HTTPException(
            status_code=status, detail=exc.message, headers={"Cache-Control": "private, no-store"}
        ) from None


@router.get("")
def connections(workspace: str = Depends(workspace_id), service=Depends(drive_service)):
    return {
        "provider": "google_drive",
        "account_scope": workspace,
        "configured": service.settings.connections_configured,
        "setup": SETUP,
        "connections": service.store.list(workspace),
        "capabilities": ["Search file names", "Read selected Google Docs and text files"],
        "activity": service.store.activity(workspace),
    }


@router.post("/google-drive/connect")
async def connect(
    response: Response, workspace: str = Depends(workspace_id), service=Depends(drive_service)
):
    async def start():
        result, browser = await service.provider.start(workspace)
        response.set_cookie(
            "axelyn_drive_" + result["flow_id"],
            browser,
            max_age=600,
            path=CALLBACK_PATH,
            secure=urlsplit(service.settings.google_drive_redirect_uri).scheme == "https",
            httponly=True,
            samesite="lax",
        )
        return result

    return await operation(service, workspace, "connect", start)


def callback_page(message, success=False, cookie=None):
    nonce = secrets.token_urlsafe(24)
    title = "Google Drive authorized" if success else "Google Drive connection not completed"
    body = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{title}</title><style nonce="{nonce}">body{{font:16px/1.7 system-ui,sans-serif;max-width:480px;padding:48px 24px;margin:auto;color:#51465c}}h1{{font-size:24px}}</style></head><body><h1>{title}</h1><p>{html.escape(message)}</p><p>You can close this tab and return to Axelyn.</p>'
    if success:
        body += f'<script nonce="{nonce}">window.close();</script>'
    body += "</body></html>"
    response = HTMLResponse(
        body,
        status_code=200 if success else 400,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, nofollow",
            "Content-Security-Policy": f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        },
    )
    if cookie:
        response.delete_cookie(
            "axelyn_drive_" + cookie, path=CALLBACK_PATH, httponly=True, samesite="lax"
        )
    return response


@router.get("/google-drive/callback", include_in_schema=False)
async def google_callback(request: Request, service=Depends(drive_service)):
    # Middleware removes callback secrets from ASGI access logs after capturing them.
    pairs = getattr(request.state, "google_oauth_query", [])
    query = dict(pairs)
    flow_id = None
    try:
        if (
            len(query) != len(pairs)
            or not 32 <= len(query.get("state", "")) <= 256
            or len(query.get("code", "")) > 4096
        ):
            raise StudioError(
                "authorization_failed",
                "Invalid Google authorization response. Click Connect again.",
            )
        state = query["state"]
        flow_id = service.store.flow_for_state(state)
        browser = request.cookies.get("axelyn_drive_" + flow_id, "")
        row, verifier = service.store.consume_callback(state, browser)
        if query.get("error") or not query.get("code"):
            service.store.fail(flow_id, "authorization_cancelled")
            return callback_page(
                "Google access was not approved. No account was connected.", cookie=flow_id
            )
        async with connection_errors():
            token = await service.provider.exchange(query["code"], state, verifier)
            account = await service.provider.account(token)
            service.store.ready(row, token, account)
        return callback_page(
            "Google approved access. Axelyn will finish connecting automatically.",
            success=True,
            cookie=flow_id,
        )
    except StudioError as exc:
        # An invalid/replayed callback must not cancel a legitimate ready flow.
        if flow_id and "row" in locals():
            service.store.fail(flow_id, exc.code)
        return callback_page(exc.message, cookie=flow_id)


@router.get("/google-drive/attempts/{flow_id}")
def auth_status(
    flow_id: ConnectionId, workspace: str = Depends(workspace_id), service=Depends(drive_service)
):
    try:
        flow = service.store.flow(workspace, flow_id)
        return {"status": flow["status"], "error": flow["error"]}
    except StudioError as exc:
        raise HTTPException(
            status_code=404, detail=exc.message, headers={"Cache-Control": "private, no-store"}
        ) from None


@router.post("/google-drive/attempts/{flow_id}/complete", response_model=ConnectionView)
async def complete(
    flow_id: ConnectionId, workspace: str = Depends(workspace_id), service=Depends(drive_service)
):
    async def finalize():
        return service.store.complete_auth(workspace, flow_id)

    return await operation(service, workspace, "connect_complete", finalize)


@router.post("/google-drive/attempts/{flow_id}/cancel", status_code=204)
async def cancel(
    flow_id: ConnectionId, workspace: str = Depends(workspace_id), service=Depends(drive_service)
):
    async def stop():
        service.store.cancel_auth(workspace, flow_id)

    await operation(service, workspace, "connect_cancel", stop)


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
        encrypted = service.store.disconnect(workspace, connection_id)
        removed = False
        if encrypted:
            try:
                async with connection_errors(15):
                    token = service.store.vault.decrypt(
                        encrypted, service.store.binding("credentials", workspace, connection_id)
                    )
                    await service.provider.revoke(token)
                    removed = True
            except StudioError:
                pass
        return {
            "disconnected": True,
            "provider_removed": removed,
            "message": "Google Drive disconnected. Saved results are retained."
            if removed
            else "Google Drive is disconnected in Axelyn. Review your Google Account permissions to confirm removal of the app's access.",
        }

    return await operation(service, workspace, "disconnect", remove, connection_id)
