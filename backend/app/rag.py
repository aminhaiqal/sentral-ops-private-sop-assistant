from __future__ import annotations

from app.config import Settings, get_settings
from app.guardrails import boundary_prompt, evaluate_question
from app.openai_client import OpenAIClient
from app.qdrant_store import QdrantStore
from app.schemas import AskResponse, BoundaryWarning, SourceSnippet


SYSTEM_PROMPT = """You are the Sentral Ops Private SOP Assistant for Axelyn's proof demo.

Use only the provided source excerpts. Do not use outside knowledge.
If the sources do not answer the question, say that the approved documents do not contain enough information.
Do not invent live delivery status, payment confirmation, stock availability, customer-specific facts, or approval decisions.
For approval questions, explain the approval matrix and state that the assistant cannot approve the action.
For confidential data or public AI questions, explain the boundary clearly and direct staff to approved internal systems.
Keep the answer practical and concise. Cite relevant source titles in square brackets when useful."""


class RagAssistant:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.openai_client = OpenAIClient(self.settings)
        self.store = QdrantStore(self.settings)

    def ask(self, question: str, top_k: int = 5) -> AskResponse:
        warnings = evaluate_question(question)
        question_embedding = self.openai_client.embed_texts([question])[0]
        raw_sources = self.store.search(query_embedding=question_embedding, limit=top_k)
        sources = filter_relevant_sources(
            raw_sources,
            min_score=self.settings.min_source_score,
            max_sources=self.settings.max_context_sources,
        )

        if not sources:
            warning = BoundaryWarning(
                category="outside_scope",
                message=(
                    "No sufficiently relevant approved source was found. The assistant should not "
                    "answer this as Sentral Ops policy."
                ),
            )
            answer = (
                "I could not find a sufficiently relevant approved Sentral Ops source for that question. "
                "Please check the correct internal owner, SOP document, or specialist team before acting."
            )
            return AskResponse(
                answer=answer,
                sources=[],
                warnings=[*warnings, warning],
            )

        user_prompt = build_user_prompt(question, sources, boundary_prompt(warnings))
        answer = self.openai_client.generate_answer(SYSTEM_PROMPT, user_prompt)
        return AskResponse(answer=answer, sources=sources, warnings=warnings)


def filter_relevant_sources(
    sources: list[SourceSnippet],
    min_score: float,
    max_sources: int,
) -> list[SourceSnippet]:
    return [source for source in sources if source.score >= min_score][:max_sources]


def build_user_prompt(question: str, sources: list[SourceSnippet], boundary_notes: str) -> str:
    source_blocks = []
    for index, source in enumerate(sources, start=1):
        source_blocks.append(
            "\n".join(
                [
                    f"Source {index}",
                    f"Document: {source.title}",
                    f"Document ID: {source.document_id}",
                    f"Chunk ID: {source.chunk_id}",
                    f"Excerpt: {source.excerpt}",
                ]
            )
        )

    return "\n\n".join(
        [
            f"Question: {question}",
            boundary_notes,
            "Approved source excerpts:",
            "\n\n".join(source_blocks),
            "Answer from these sources only.",
        ]
    )
