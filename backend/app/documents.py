from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    title: str
    path: Path
    text: str
    owner: str | None = None
    version: str | None = None
    last_reviewed: str | None = None
    classification: str | None = None


def _first_heading(markdown: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _metadata(markdown: str, key: str) -> str | None:
    pattern = rf"^\*\*{re.escape(key)}:\*\*\s*(.+)$"
    match = re.search(pattern, markdown, flags=re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else None


def load_documents(data_dir: Path) -> list[SourceDocument]:
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    documents: list[SourceDocument] = []
    for path in sorted(data_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = _first_heading(text, path.stem)
        documents.append(
            SourceDocument(
                document_id=path.stem,
                title=title,
                path=path,
                text=text,
                owner=_metadata(text, "Owner"),
                version=_metadata(text, "Version"),
                last_reviewed=_metadata(text, "Last Reviewed"),
                classification=_metadata(text, "Classification"),
            )
        )
    return documents
