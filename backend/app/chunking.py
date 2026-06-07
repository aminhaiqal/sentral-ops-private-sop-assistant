from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    title: str
    text: str


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "document"


def word_count(value: str) -> int:
    return len(re.findall(r"\S+", value))


def _blocks(markdown: str) -> list[str]:
    cleaned = markdown.replace("\r\n", "\n").strip()
    return [block.strip() for block in re.split(r"\n\s*\n", cleaned) if block.strip()]


def _overlap_text(text: str, overlap_words: int) -> str:
    if overlap_words <= 0:
        return ""
    words = re.findall(r"\S+", text)
    return " ".join(words[-overlap_words:])


def chunk_markdown(
    document_id: str,
    title: str,
    markdown: str,
    max_words: int = 280,
    overlap_words: int = 35,
) -> list[DocumentChunk]:
    if max_words < 80:
        raise ValueError("max_words must be at least 80 for useful SOP chunks.")
    if overlap_words >= max_words:
        raise ValueError("overlap_words must be smaller than max_words.")

    chunks: list[DocumentChunk] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        text = "\n\n".join(current).strip()
        if not text:
            return
        index = len(chunks) + 1
        chunks.append(
            DocumentChunk(
                chunk_id=f"{document_id}-{index:03d}",
                document_id=document_id,
                title=title,
                text=text,
            )
        )
        overlap = _overlap_text(text, overlap_words)
        current = [overlap] if overlap else []

    for block in _blocks(markdown):
        block_words = word_count(block)
        current_words = word_count("\n\n".join(current))

        if current and current_words + block_words > max_words:
            flush()

        if block_words > max_words:
            words = re.findall(r"\S+", block)
            for start in range(0, len(words), max_words - overlap_words):
                part = " ".join(words[start : start + max_words])
                if current:
                    flush()
                current = [part]
                flush()
            current = []
            continue

        current.append(block)

    final_text = "\n\n".join(current).strip()
    if final_text:
        index = len(chunks) + 1
        chunks.append(
            DocumentChunk(
                chunk_id=f"{document_id}-{index:03d}",
                document_id=document_id,
                title=title,
                text=final_text,
            )
        )

    return chunks
