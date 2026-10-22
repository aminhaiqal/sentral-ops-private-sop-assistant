from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SourceSnippet(BaseModel):
    document_id: str
    title: str
    chunk_id: str
    score: float
    excerpt: str
    citation: str = ""


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
