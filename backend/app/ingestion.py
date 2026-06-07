from __future__ import annotations

from app.chunking import DocumentChunk, chunk_markdown
from app.config import Settings, get_settings
from app.documents import load_documents
from app.openai_client import OpenAIClient
from app.qdrant_store import QdrantStore
from app.schemas import IngestResponse


def ingest_all(settings: Settings | None = None) -> IngestResponse:
    settings = settings or get_settings()
    documents = load_documents(settings.data_dir)

    chunks: list[DocumentChunk] = []
    for document in documents:
        chunks.extend(
            chunk_markdown(
                document_id=document.document_id,
                title=document.title,
                markdown=document.text,
            )
        )

    openai_client = OpenAIClient(settings)
    store = QdrantStore(settings)
    store.ensure_collection()

    batch_size = 64
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        embeddings = openai_client.embed_texts([chunk.text for chunk in batch])
        store.upsert_chunks(batch, embeddings)

    return IngestResponse(
        documents=len(documents),
        chunks=len(chunks),
        collection=settings.qdrant_collection,
    )


if __name__ == "__main__":
    result = ingest_all()
    print(result.model_dump_json(indent=2))
