from __future__ import annotations

from dataclasses import dataclass
import re

from app.config import Settings, get_settings
from app.guardrails import boundary_prompt, evaluate_question
from app.openai_client import OpenAIClient
from app.qdrant_store import QdrantStore
from app.schemas import AgentStep, AskResponse, BoundaryWarning, SourceSnippet


SYSTEM_PROMPT = """You are the Sentral Ops Private SOP Assistant for Axelyn's proof demo.

Use only the provided source excerpts. Do not use outside knowledge.
If the sources do not answer the question, say that the approved documents do not contain enough information.
Do not invent live delivery status, payment confirmation, stock availability, customer-specific facts, or approval decisions.
For approval questions, explain the approval matrix and state that the assistant cannot approve the action.
For confidential data or public AI questions, explain the boundary clearly and direct staff to approved internal systems.
Keep the answer practical and concise.
Every factual answer sentence should cite one or more source IDs like [S1]."""


@dataclass(frozen=True)
class RetrievalQuery:
    query: str
    reason: str


@dataclass(frozen=True)
class QueryRule:
    pattern: re.Pattern[str]
    query: str
    reason: str
    warning_categories: tuple[str, ...] = ()


QUERY_RULES = [
    QueryRule(
        pattern=re.compile(r"\b(refund|credit note|damaged|return)\b", re.I),
        query="refund credit note approval damaged goods required information",
        reason="Focused refund and credit-note SOP lookup",
    ),
    QueryRule(
        pattern=re.compile(r"\b(delivery|delay|eta|arrival|driver|dispatch)\b", re.I),
        query="delivery delay escalation operations manager ETA live status SOP",
        reason="Focused delivery-delay escalation lookup",
        warning_categories=("live_delivery_status",),
    ),
    QueryRule(
        pattern=re.compile(r"\b(stock|substitut|alternative|inventory|out of stock)\b", re.I),
        query="stock exception substitution customer approval manager approval SOP",
        reason="Focused stock exception and substitution lookup",
        warning_categories=("stock_availability", "substitution_approval"),
    ),
    QueryRule(
        pattern=re.compile(r"\b(invoice|payment|overdue|receipt|ledger|finance)\b", re.I),
        query="invoice handling payment follow up finance overdue payment confirmation",
        reason="Focused invoice and payment follow-up lookup",
        warning_categories=("payment_confirmation",),
    ),
    QueryRule(
        pattern=re.compile(
            r"\b(chatgpt|public ai|external ai|confidential|customer data|personal data)\b",
            re.I,
        ),
        query="data handling AI usage policy confidential customer data external AI",
        reason="Focused confidential-data and AI policy lookup",
        warning_categories=("confidential_data", "external_ai"),
    ),
    QueryRule(
        pattern=re.compile(r"\b(onboarding|new employee|week one|training)\b", re.I),
        query="new employee onboarding week one support staff training guide",
        reason="Focused onboarding guide lookup",
    ),
    QueryRule(
        pattern=re.compile(r"\b(leave|attendance|shift|absence|medical certificate)\b", re.I),
        query="leave attendance shift policy absence medical certificate",
        reason="Focused leave and attendance policy lookup",
    ),
    QueryRule(
        pattern=re.compile(r"\b(support|troubleshoot|missing item|escalat)\b", re.I),
        query="internal support troubleshooting missing item escalation checklist",
        reason="Focused support troubleshooting lookup",
    ),
]


class RagAssistant:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.openai_client = OpenAIClient(self.settings)
        self.store = QdrantStore(self.settings)

    def ask(self, question: str, top_k: int = 5) -> AskResponse:
        warnings = evaluate_question(question)
        agent_steps = [
            AgentStep(
                name="Boundary check",
                status="warning" if warnings else "done",
                detail=(
                    f"Detected {len(warnings)} boundary warning(s)."
                    if warnings
                    else "No boundary-sensitive wording detected."
                ),
            )
        ]

        retrieval_plan = build_retrieval_plan(question, warnings)
        agent_steps.append(
            AgentStep(
                name="Query planning",
                status="done",
                detail=format_retrieval_plan(retrieval_plan),
            )
        )

        query_embeddings = self.openai_client.embed_texts([item.query for item in retrieval_plan])
        source_batches = [
            self.store.search(query_embedding=embedding, limit=top_k) for embedding in query_embeddings
        ]
        raw_sources = merge_ranked_sources(source_batches)
        agent_steps.append(
            AgentStep(
                name="Retrieval",
                status="done",
                detail=(
                    f"Ran {len(retrieval_plan)} vector search(es), then deduplicated "
                    f"{sum(len(batch) for batch in source_batches)} candidate chunk(s) "
                    f"to {len(raw_sources)} unique chunk(s)."
                ),
            )
        )

        sources = filter_relevant_sources(
            raw_sources,
            min_score=self.settings.min_source_score,
            max_sources=self.settings.max_context_sources,
        )
        sources = assign_citations(sources)
        agent_steps.append(
            AgentStep(
                name="Grounding check",
                status="done" if sources else "warning",
                detail=(
                    f"{len(sources)} source chunk(s) passed the "
                    f"{self.settings.min_source_score:.2f} relevance threshold."
                ),
            )
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
                agent_steps=agent_steps,
            )

        user_prompt = build_user_prompt(question, sources, boundary_prompt(warnings))
        answer = self.openai_client.generate_answer(SYSTEM_PROMPT, user_prompt)
        agent_steps.append(
            AgentStep(
                name="Answer synthesis",
                status="done",
                detail="Generated a response constrained to the approved cited source excerpts.",
            )
        )
        return AskResponse(answer=answer, sources=sources, warnings=warnings, agent_steps=agent_steps)


def build_retrieval_plan(
    question: str,
    warnings: list[BoundaryWarning],
    max_queries: int = 3,
) -> list[RetrievalQuery]:
    plan = [RetrievalQuery(query=normalize_query(question), reason="Original user wording")]
    warning_categories = {warning.category for warning in warnings}

    for rule in QUERY_RULES:
        if len(plan) >= max_queries:
            break

        matches_question = bool(rule.pattern.search(question))
        matches_warning = bool(warning_categories.intersection(rule.warning_categories))
        if not matches_question and not matches_warning:
            continue

        candidate = RetrievalQuery(query=rule.query, reason=rule.reason)
        if normalize_query(candidate.query) not in {item.query for item in plan}:
            plan.append(candidate)

    return plan


def normalize_query(query: str) -> str:
    return " ".join(query.split())


def format_retrieval_plan(plan: list[RetrievalQuery]) -> str:
    return "; ".join(f"{index}. {item.reason}: {item.query}" for index, item in enumerate(plan, 1))


def merge_ranked_sources(source_batches: list[list[SourceSnippet]]) -> list[SourceSnippet]:
    best_by_chunk: dict[str, SourceSnippet] = {}

    for batch in source_batches:
        for source in batch:
            current = best_by_chunk.get(source.chunk_id)
            if current is None or source.score > current.score:
                best_by_chunk[source.chunk_id] = source

    return sorted(best_by_chunk.values(), key=lambda source: source.score, reverse=True)


def filter_relevant_sources(
    sources: list[SourceSnippet],
    min_score: float,
    max_sources: int,
) -> list[SourceSnippet]:
    return [source for source in sources if source.score >= min_score][:max_sources]


def assign_citations(sources: list[SourceSnippet]) -> list[SourceSnippet]:
    return [
        source.model_copy(update={"citation": f"S{index}"})
        for index, source in enumerate(sources, start=1)
    ]


def build_user_prompt(question: str, sources: list[SourceSnippet], boundary_notes: str) -> str:
    source_blocks = []
    for index, source in enumerate(sources, start=1):
        citation = source.citation or f"S{index}"
        source_blocks.append(
            "\n".join(
                [
                    f"Source {index}",
                    f"Citation: [{citation}]",
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
            "Answer from these sources only. Use citation IDs such as [S1] for factual claims.",
        ]
    )
