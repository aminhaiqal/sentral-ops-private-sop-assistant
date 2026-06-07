from __future__ import annotations

import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.chunking import DocumentChunk
from app.config import Settings
from app.schemas import SourceSnippet


class QdrantStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = QdrantClient(url=settings.qdrant_url)

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.settings.qdrant_collection):
            return

        self.client.create_collection(
            collection_name=self.settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=self.settings.openai_embedding_dimensions,
                distance=models.Distance.COSINE,
            ),
        )

    def count(self) -> int:
        if not self.client.collection_exists(self.settings.qdrant_collection):
            return 0
        result = self.client.count(
            collection_name=self.settings.qdrant_collection,
            exact=True,
        )
        return int(result.count)

    def upsert_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length.")

        points: list[models.PointStruct] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id))
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "document_id": chunk.document_id,
                        "title": chunk.title,
                        "chunk_id": chunk.chunk_id,
                        "text": chunk.text,
                    },
                )
            )

        if points:
            self.client.upsert(
                collection_name=self.settings.qdrant_collection,
                points=points,
                wait=True,
            )

    def search(self, query_embedding: list[float], limit: int) -> list[SourceSnippet]:
        self.ensure_collection()
        response = self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=query_embedding,
            limit=limit,
            with_payload=True,
        )

        snippets: list[SourceSnippet] = []
        for result in response.points:
            payload = result.payload or {}
            text = str(payload.get("text", ""))
            snippets.append(
                SourceSnippet(
                    document_id=str(payload.get("document_id", "")),
                    title=str(payload.get("title", "")),
                    chunk_id=str(payload.get("chunk_id", "")),
                    score=float(result.score),
                    excerpt=_excerpt(text),
                )
            )
        return snippets


def _excerpt(text: str, max_chars: int = 1800) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."
