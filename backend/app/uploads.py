from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from openai import APIStatusError

from app.chunking import chunk_markdown
from app.config import Settings
from app.openai_client import OpenAIClient, OpenAINotConfigured, provider_error_message
from app.qdrant_store import QdrantStore
from app.schemas import UploadedDocument

logger = logging.getLogger(__name__)


class StorageUnavailable(RuntimeError):
    pass


def extract_document(filename: str, data: bytes) -> tuple[str, int | None]:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".md", ".pdf"}:
        raise ValueError("Choose a PDF or Markdown (.md) file.")
    if not data:
        raise ValueError("This file is empty.")
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("This file is not a valid PDF.")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "app.pdf_extract"],
                cwd=Path(__file__).resolve().parents[1],
                input=data,
                capture_output=True,
                timeout=25,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("This PDF took too long to read. Try a smaller file.") from exc
        try:
            parsed = json.loads(result.stdout)
        except (ValueError, UnicodeError) as exc:
            raise ValueError(
                "This PDF is too complex to read. Try exporting a smaller copy."
            ) from exc
        if result.returncode or "error" in parsed:
            raise ValueError(parsed.get("error", "This PDF could not be read."))
        return parsed["text"], parsed["pages"]
    try:
        text = data.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("Save this Markdown file with UTF-8 encoding and try again.") from exc
    if "\x00" in text:
        raise ValueError("This file contains binary data. Upload a plain-text Markdown file.")
    if not text:
        raise ValueError("This file contains no text.")
    if len(text) > 200_000:
        raise ValueError("This document has too much text. Split it into smaller files.")
    return text, None


def clean_filename(value: str) -> str:
    value = value.replace("\\", "/").split("/")[-1]
    value = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
    if not value or len(value) > 200:
        raise ValueError("Use a filename with 1 to 200 characters.")
    return value


class R2DocumentStore:
    def __init__(self, settings: Settings):
        if not settings.storage_configured:
            raise StorageUnavailable("Document uploads are temporarily unavailable.")
        self.settings = settings
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                connect_timeout=5,
                read_timeout=20,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    def prefix(self, workspace: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{64}", workspace):
            raise ValueError("Invalid workspace.")
        return f"{self.settings.r2_prefix.strip('/')}/workspaces/{workspace}/"

    def key(self, workspace: str, document_id: str, filename: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{32}", document_id):
            raise ValueError("Invalid document ID.")
        return f"{self.prefix(workspace)}{document_id}/{filename}"

    def call(self, method: str, **kwargs):
        try:
            return getattr(self.client, method)(Bucket=self.settings.r2_bucket, **kwargs)
        except (BotoCoreError, ClientError) as exc:
            if isinstance(exc, ClientError) and exc.response["Error"]["Code"] in {
                "NoSuchKey",
                "404",
                "NotFound",
            }:
                raise FileNotFoundError("Document not found.") from exc
            raise StorageUnavailable(
                "Document storage is temporarily unavailable. Try again."
            ) from exc

    def read(self, key: str) -> bytes:
        response = self.call("get_object", Key=key)
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def get(self, workspace: str, document_id: str) -> UploadedDocument:
        return UploadedDocument.model_validate_json(
            self.read(self.key(workspace, document_id, "metadata.json"))
        )

    def list(self, workspace: str) -> list[UploadedDocument]:
        documents = []
        continuation = None
        while True:
            options = {"Prefix": self.prefix(workspace)}
            if continuation:
                options["ContinuationToken"] = continuation
            result = self.call("list_objects_v2", **options)
            for item in result.get("Contents", []):
                if item["Key"].endswith("/metadata.json"):
                    documents.append(UploadedDocument.model_validate_json(self.read(item["Key"])))
            if not result.get("IsTruncated"):
                break
            continuation = result["NextContinuationToken"]
        return sorted(documents, key=lambda doc: doc.uploaded_at, reverse=True)

    def save_metadata(self, workspace: str, document: UploadedDocument) -> None:
        self.call(
            "put_object",
            Key=self.key(workspace, document.id, "metadata.json"),
            Body=document.model_dump_json().encode(),
            ContentType="application/json",
            CacheControl="private, no-store",
        )

    def save(
        self, workspace: str, filename: str, data: bytes, text: str, pages: int | None
    ) -> UploadedDocument:
        document_id = hashlib.sha256(data).hexdigest()[:32]
        try:
            return self.get(workspace, document_id)
        except FileNotFoundError:
            pass
        suffix = Path(filename).suffix.lower()
        heading = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        doc = UploadedDocument(
            id=document_id,
            filename=filename,
            title=heading.group(1).strip()[:200] if heading else Path(filename).stem,
            size_bytes=len(data),
            uploaded_at=datetime.now(timezone.utc),
            pages=pages,
        )
        self.call(
            "put_object",
            Key=self.key(workspace, doc.id, "original" + suffix),
            Body=data,
            ContentType="application/pdf" if suffix == ".pdf" else "text/markdown; charset=utf-8",
            CacheControl="private, no-store",
        )
        self.call(
            "put_object",
            Key=self.key(workspace, doc.id, "content.txt"),
            Body=text.encode(),
            ContentType="text/plain; charset=utf-8",
            CacheControl="private, no-store",
        )
        self.save_metadata(workspace, doc)
        return doc

    def index(self, workspace: str, document: UploadedDocument) -> UploadedDocument:
        if document.status == "indexed":
            return document
        try:
            text = self.read(self.key(workspace, document.id, "content.txt")).decode()
            chunks = chunk_markdown("upload-" + document.id, document.title, text)
            client = OpenAIClient(self.settings)
            vectors = QdrantStore(self.settings)
            vectors.ensure_collection()
            embeddings = []
            for start in range(0, len(chunks), 32):
                batch = chunks[start : start + 32]
                embeddings.extend(client.embed_texts([chunk.text for chunk in batch]))
            vectors.upsert_chunks(chunks, embeddings, workspace_id=workspace)
            document = document.model_copy(
                update={
                    "status": "indexed",
                    "chunks": len(chunks),
                    "indexing_error": None,
                }
            )
        except APIStatusError as exc:
            logger.warning("Document indexing provider failure: status=%s", exc.status_code)
            document = document.model_copy(
                update={
                    "indexing_error": "Saved safely. " + provider_error_message(exc),
                }
            )
        except OpenAINotConfigured as exc:
            document = document.model_copy(update={"indexing_error": "Saved safely. " + str(exc)})
        except Exception as exc:
            # Saving the original is independent of embedding-provider availability.
            logger.warning("Document indexing failed: type=%s", type(exc).__name__)
            document = document.model_copy(
                update={
                    "indexing_error": "Saved safely. Search is temporarily unavailable; retry indexing later.",
                }
            )
        self.save_metadata(workspace, document)
        return document

    def delete(self, workspace: str, document: UploadedDocument) -> None:
        # A failed vector deletion must not leave searchable text from a removed document.
        QdrantStore(self.settings).delete_document("upload-" + document.id, workspace)
        for filename in [
            "original" + Path(document.filename).suffix.lower(),
            "content.txt",
            "metadata.json",
        ]:
            self.call("delete_object", Key=self.key(workspace, document.id, filename))
