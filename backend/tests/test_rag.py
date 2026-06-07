from app.rag import filter_relevant_sources
from app.schemas import SourceSnippet


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
