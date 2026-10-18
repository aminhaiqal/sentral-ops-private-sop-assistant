from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BoundaryWarning(BaseModel):
    category: str
    message: str


class SourceSnippet(BaseModel):
    document_id: str
    title: str
    chunk_id: str
    score: float
    excerpt: str
    citation: str = ""


class AgentStep(BaseModel):
    name: str
    status: str
    detail: str


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=5000)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=800)
    top_k: int = Field(default=5, ge=1, le=8)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=6)


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceSnippet]
    warnings: list[BoundaryWarning]
    agent_steps: list[AgentStep] = Field(default_factory=list)


class IngestResponse(BaseModel):
    documents: int
    chunks: int
    collection: str


class DemoQuestion(BaseModel):
    question: str
    boundary_expected: bool = False


class HealthResponse(BaseModel):
    status: str
    app_name: str
    qdrant_collection: str
    openai_configured: bool


class UploadedDocument(BaseModel):
    id: str
    filename: str
    title: str
    size_bytes: int
    uploaded_at: datetime
    status: Literal["saved", "indexed"] = "saved"
    chunks: int = 0
    pages: int | None = None
    indexing_error: str | None = None


class DocumentLibrary(BaseModel):
    documents: list[UploadedDocument]
    storage_configured: bool
    demo_documents: int
