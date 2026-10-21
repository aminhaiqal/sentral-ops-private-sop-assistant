from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import APIStatusError
from starlette.concurrency import run_in_threadpool

from app.auth import require_user
from app.config import get_settings
from app.demo_questions import DEMO_QUESTIONS
from app.harness.api import bots_router, routines_router
from app.harness.api import router as task_router
from app.harness.memory import MemoryConflict, MemoryNotFound
from app.ingestion import ingest_all
from app.openai_client import OpenAINotConfigured, provider_error_message
from app.qdrant_store import QdrantStore
from app.rag import RagAssistant
from app.schemas import (
    AskRequest,
    AskResponse,
    DemoQuestion,
    DocumentLibrary,
    HealthResponse,
    IngestResponse,
    UploadedDocument,
)
from app.studio.api import router as studio_router
from app.studio.safety import redact
from app.uploads import R2DocumentStore, StorageUnavailable, clean_filename, extract_document
from app.workspaces import workspace_id

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auto_ingest_on_startup and settings.openai_api_key:
        try:
            store = QdrantStore(settings)
            if store.count() == 0:
                logger.info("Qdrant collection is empty; ingesting demo documents.")
                ingest_all(settings)
        except APIStatusError as exc:
            logger.warning(
                "Startup indexing unavailable: status=%s code=%s", exc.status_code, exc.code
            )
        except Exception:
            logger.exception(
                "Automatic ingestion failed. Use POST /api/ingest after fixing config."
            )
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(task_router)
app.include_router(bots_router)
app.include_router(routines_router)
app.include_router(studio_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    if not request.url.path.startswith("/api/studio/"):
        return await request_validation_exception_handler(request, exc)
    from fastapi.responses import JSONResponse

    # Do not echo rejected credential fields or arbitrary input values in API errors.
    messages = [str(error["msg"]) for error in exc.errors()[:5]]
    return JSONResponse(
        status_code=422,
        content={"detail": redact("Check the bot configuration: " + "; ".join(messages))},
        headers={"Cache-Control": "private, no-store"},
    )


@app.exception_handler(MemoryNotFound)
async def missing_memory(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
        headers={"Cache-Control": "private, no-store"},
    )


@app.exception_handler(MemoryConflict)
async def memory_conflict(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=409,
        content={"detail": str(exc)},
        headers={"Cache-Control": "private, no-store"},
    )


@app.exception_handler(StorageUnavailable)
async def storage_error(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Cache-Control": "private, no-store"},
    )


@app.exception_handler(FileNotFoundError)
async def missing_document(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=404,
        content={"detail": "Document not found."},
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


@app.post("/api/ingest", response_model=IngestResponse, dependencies=[Depends(require_user)])
def ingest() -> IngestResponse:
    try:
        return ingest_all(get_settings())
    except APIStatusError as exc:
        logger.warning("SOP indexing unavailable: status=%s code=%s", exc.status_code, exc.code)
        raise HTTPException(status_code=503, detail=provider_error_message(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ingestion failed.")
        raise HTTPException(status_code=502, detail="Document ingestion failed.") from exc


@app.get("/api/demo-questions", response_model=list[DemoQuestion])
def demo_questions() -> list[DemoQuestion]:
    return DEMO_QUESTIONS


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest, workspace: str = Depends(workspace_id)) -> AskResponse:
    try:
        assistant = RagAssistant(get_settings(), workspace_id=workspace)
        return assistant.ask(request.question, request.top_k, request.history)
    except APIStatusError as exc:
        logger.warning(
            "Answer provider rejected request: status=%s code=%s", exc.status_code, exc.code
        )
        raise HTTPException(
            status_code=503, detail=provider_error_message(exc) + " Your documents are still saved."
        ) from exc
    except OpenAINotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail="The assistant is not available yet. Try again later."
        ) from exc
    except Exception as exc:
        logger.exception("Question answering failed.")
        raise HTTPException(status_code=502, detail="Question answering failed.") from exc


@app.get("/api/documents", response_model=DocumentLibrary)
def documents(workspace: str = Depends(workspace_id)) -> DocumentLibrary:
    settings = get_settings()
    return DocumentLibrary(
        documents=R2DocumentStore(settings).list(workspace) if settings.storage_configured else [],
        storage_configured=settings.storage_configured,
        demo_documents=len(list(settings.data_dir.glob("*.md"))),
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
