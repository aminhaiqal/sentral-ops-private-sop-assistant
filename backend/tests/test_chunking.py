import pytest

from app.chunking import chunk_markdown, slugify, word_count


def test_slugify_creates_stable_ids():
    assert slugify("Customer Refund & Credit Note SOP") == "customer-refund-credit-note-sop"


def test_chunk_markdown_returns_deterministic_chunk_ids():
    markdown = "# Test SOP\n\n" + "\n\n".join(
        f"## Section {index}\n\nThis section has a short operational rule."
        for index in range(1, 12)
    )

    first = chunk_markdown("test-doc", "Test SOP", markdown, max_words=90, overlap_words=10)
    second = chunk_markdown("test-doc", "Test SOP", markdown, max_words=90, overlap_words=10)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert len(first) > 1


def test_chunk_markdown_respects_max_words_with_reasonable_overlap():
    markdown = "# Long SOP\n\n" + " ".join(f"word{index}" for index in range(310))

    chunks = chunk_markdown("long-doc", "Long SOP", markdown, max_words=100, overlap_words=10)

    assert len(chunks) >= 3
    assert all(word_count(chunk.text) <= 110 for chunk in chunks)


def test_chunk_markdown_rejects_too_small_chunk_size():
    with pytest.raises(ValueError):
        chunk_markdown("bad", "Bad", "# Bad", max_words=20)
