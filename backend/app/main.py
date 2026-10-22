from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.harness.api import router as task_router
from app.qdrant_store import QdrantStore
from app.schemas import DocumentLibrary, HealthResponse, UploadedDocument
from app.uploads import R2DocumentStore, StorageUnavailable, clean_filename, extract_document
from app.workspaces import workspace_id

logger = logging.getLogger(__name__)
settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(task_router)


@app.exception_handler(StorageUnavailable)
async def storage_error(request, exc):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Cache-Control": "private, no-store"},
    )


@app.exception_handler(FileNotFoundError)
async def missing_resource(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Resource not found."},
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        qdrant_collection=settings.qdrant_collection,
        openai_configured=bool(settings.openai_api_key),
    )


@app.get("/api/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    settings = get_settings()
    try:
        QdrantStore(settings).count()
    except Exception as exc:
        logger.exception("Readiness check failed.")
        raise HTTPException(status_code=503, detail="Qdrant is not ready.") from exc

    return HealthResponse(
        status="ready",
        app_name=settings.app_name,
        qdrant_collection=settings.qdrant_collection,
        openai_configured=bool(settings.openai_api_key),
    )


@app.get("/api/documents", response_model=DocumentLibrary)
def documents(workspace: str = Depends(workspace_id)) -> DocumentLibrary:
    settings = get_settings()
    return DocumentLibrary(
        documents=R2DocumentStore(settings).list(workspace) if settings.storage_configured else [],
        storage_configured=settings.storage_configured,
    )


@app.post("/api/documents", response_model=UploadedDocument, status_code=201)
async def upload_document(file: UploadFile, workspace: str = Depends(workspace_id)):
    settings = get_settings()
    if not settings.storage_configured:
        raise StorageUnavailable("Document uploads are temporarily unavailable.")
    try:
        filename = clean_filename(file.filename or "")
        content = bytearray()
        while block := await file.read(64 * 1024):
            content.extend(block)
            if len(content) > settings.max_upload_bytes:
                raise HTTPException(status_code=413, detail="Choose a file smaller than 10 MB.")
        text, pages = await run_in_threadpool(extract_document, filename, bytes(content))
        store = R2DocumentStore(settings)
        document = await run_in_threadpool(
            store.save, workspace, filename, bytes(content), text, pages
        )
        return await run_in_threadpool(store.index, workspace, document)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()


@app.post("/api/documents/{document_id}/index", response_model=UploadedDocument)
def index_document(document_id: str, workspace: str = Depends(workspace_id)):
    store = R2DocumentStore(get_settings())
    try:
        doc = store.get(workspace, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    return store.index(workspace, doc)


@app.get("/api/documents/{document_id}/download")
def download_document(document_id: str, workspace: str = Depends(workspace_id)):
    store = R2DocumentStore(get_settings())
    try:
        doc = store.get(workspace, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    suffix = Path(doc.filename).suffix.lower()
    body = store.call("get_object", Key=store.key(workspace, doc.id, "original" + suffix))["Body"]

    def stream():
        try:
            yield from body.iter_chunks(chunk_size=64 * 1024)
        finally:
            body.close()

    return StreamingResponse(
        stream(),
        media_type="application/pdf" if suffix == ".pdf" else "text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(doc.filename, safe=""),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: str, workspace: str = Depends(workspace_id)):
    store = R2DocumentStore(get_settings())
    try:
        doc = store.get(workspace, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    store.delete(workspace, doc)
    return Response(status_code=204, headers={"Cache-Control": "private, no-store"})
