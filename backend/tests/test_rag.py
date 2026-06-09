from app.rag import (
    assign_citations,
    build_retrieval_plan,
    filter_relevant_sources,
    merge_ranked_sources,
)
from app.schemas import BoundaryWarning, SourceSnippet


def source(score: float, chunk_id: str) -> SourceSnippet:
    return SourceSnippet(
        document_id="doc",
        title="Doc",
        chunk_id=chunk_id,
        score=score,
        excerpt="Approved source excerpt.",
    )


def test_filter_relevant_sources_applies_threshold_and_limit():
    sources = [
        source(0.41, "doc-001"),
        source(0.21, "doc-002"),
        source(0.36, "doc-003"),
        source(0.12, "doc-004"),
    ]

    filtered = filter_relevant_sources(sources, min_score=0.22, max_sources=2)

    assert [item.chunk_id for item in filtered] == ["doc-001", "doc-003"]


def test_filter_relevant_sources_returns_empty_for_low_confidence_context():
    sources = [source(0.10, "doc-001"), source(0.18, "doc-002")]

    assert filter_relevant_sources(sources, min_score=0.22, max_sources=5) == []


def test_build_retrieval_plan_adds_domain_specific_queries():
    plan = build_retrieval_plan("Can staff paste invoice data into ChatGPT?", warnings=[])

    assert [item.reason for item in plan] == [
        "Original user wording",
        "Focused invoice and payment follow-up lookup",
        "Focused confidential-data and AI policy lookup",
    ]


def test_build_retrieval_plan_uses_boundary_warnings_for_focused_lookup():
    warnings = [
        BoundaryWarning(
            category="live_delivery_status",
            message="Live delivery status requires an operational system check.",
        )
    ]

    plan = build_retrieval_plan("Where is order 123 now?", warnings=warnings)

    assert any("delivery delay" in item.query for item in plan)


def test_merge_ranked_sources_deduplicates_by_best_chunk_score():
    first = [source(0.30, "doc-001"), source(0.25, "doc-002")]
    second = [source(0.40, "doc-002"), source(0.20, "doc-003")]

    merged = merge_ranked_sources([first, second])

    assert [(item.chunk_id, item.score) for item in merged] == [
        ("doc-002", 0.40),
        ("doc-001", 0.30),
        ("doc-003", 0.20),
    ]


def test_assign_citations_labels_sources_in_rank_order():
    cited = assign_citations([source(0.40, "doc-001"), source(0.30, "doc-002")])

    assert [item.citation for item in cited] == ["S1", "S2"]
