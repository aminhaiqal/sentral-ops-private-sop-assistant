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
            count_filter=visible_sources(None),
        )
        return int(result.count)

    def upsert_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]],
                      workspace_id: str | None = None) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length.")

        points: list[models.PointStruct] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            point_key = f"{workspace_id}:{chunk.chunk_id}" if workspace_id else chunk.chunk_id
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, point_key))
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "document_id": chunk.document_id,
                        "title": chunk.title,
                        "chunk_id": chunk.chunk_id,
                        "text": chunk.text,
                        **({"workspace_id": workspace_id} if workspace_id else {}),
                    },
                )
            )

        if points:
            self.client.upsert(
                collection_name=self.settings.qdrant_collection,
                points=points,
                wait=True,
            )

    def search(self, query_embedding: list[float], limit: int,
               workspace_id: str | None = None) -> list[SourceSnippet]:
        self.ensure_collection()
        response = self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=query_embedding,
            limit=limit,
            with_payload=True,
            query_filter=visible_sources(workspace_id),
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

    def delete_document(self, document_id: str, workspace_id: str) -> None:
        if not self.client.collection_exists(self.settings.qdrant_collection):
            return
        self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.FieldCondition(key="workspace_id", match=models.MatchValue(value=workspace_id)),
                models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)),
            ])),
            wait=True,
        )


def visible_sources(workspace_id: str | None) -> models.Filter:
    public = models.IsEmptyCondition(is_empty=models.PayloadField(key="workspace_id"))
    if not workspace_id:
        return models.Filter(must=[public])
    return models.Filter(should=[
        public,
        models.FieldCondition(key="workspace_id", match=models.MatchValue(value=workspace_id)),
    ])


def _excerpt(text: str, max_chars: int = 1800) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."
