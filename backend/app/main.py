from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.demo_questions import DEMO_QUESTIONS
from app.ingestion import ingest_all
from app.qdrant_store import QdrantStore
from app.rag import RagAssistant
from app.schemas import AskRequest, AskResponse, DemoQuestion, HealthResponse, IngestResponse

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
        except Exception:
            logger.exception("Automatic ingestion failed. Use POST /api/ingest after fixing config.")
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.post("/api/ingest", response_model=IngestResponse)
def ingest() -> IngestResponse:
    try:
        return ingest_all(get_settings())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ingestion failed.")
        raise HTTPException(status_code=502, detail="Document ingestion failed.") from exc


@app.get("/api/demo-questions", response_model=list[DemoQuestion])
def demo_questions() -> list[DemoQuestion]:
    return DEMO_QUESTIONS


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    try:
        assistant = RagAssistant(get_settings())
        return assistant.ask(request.question, request.top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Question answering failed.")
        raise HTTPException(status_code=502, detail="Question answering failed.") from exc
