import base64
from contextlib import asynccontextmanager

from app.connections.models import DriveDocument, DriveFile
from app.connections.provider import PipedreamProvider, connection_errors
from app.studio.safety import StudioError, plain_text, redact

SUPPORTED_TYPES = frozenset(
    {"application/vnd.google-apps.document", "text/plain", "text/markdown", "text/csv"}
)


def file_view(item):
    if not isinstance(item, dict) or item.get("trashed") is True:
        raise StudioError(
            "invalid_connection_output", "Drive returned invalid or trashed file metadata."
        )
    file_id = item.get("id", "")
    mime = item.get("mimeType", "")
    return DriveFile(
        id=file_id,
        name=redact(plain_text(str(item.get("name", "")), 240)),
        mime_type=mime,
        url=f"https://drive.google.com/file/d/{file_id}/view",
        modified_at=str(item["modifiedTime"])[:64] if item.get("modifiedTime") else None,
        readable=mime in SUPPORTED_TYPES,
    )


def document_view(metadata, payload, limit=8000):
    if (
        not isinstance(payload, dict)
        or payload.get("fileId") != metadata.id
        or payload.get("resolvedFromShortcut") is True
    ):
        raise StudioError(
            "invalid_connection_output",
            "Drive returned content for a different file or shortcut. Choose the original document.",
        )
    content = payload.get("content")
    raw = None
    if isinstance(content, dict) and content.get("type") == "Buffer":
        data = content.get("data")
        if (
            isinstance(data, list)
            and len(data) <= 128_000
            and all(type(value) is int and 0 <= value <= 255 for value in data)
        ):
            raw = bytes(data)
    elif (
        isinstance(content, dict)
        and content.get("encoding") == "base64"
        and isinstance(content.get("data"), str)
        and len(content["data"]) <= 172_000
    ):
        try:
            raw = base64.b64decode(content["data"], validate=True)
        except ValueError:
            pass
    elif isinstance(content, str) and len(content.encode()) <= 128_000:
        raw = content.encode()
    if raw is None or len(raw) > 128_000:
        raise StudioError(
            "unsupported_drive_content",
            "Drive did not return a small text document. Use a Google Doc or a UTF-8 text file under 128 KB.",
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise StudioError(
            "unsupported_drive_content",
            "This file is not UTF-8 text. Choose a Google Doc or plain text file.",
        ) from exc
    if "\0" in text:
        raise StudioError(
            "unsupported_drive_content",
            "Binary documents are not supported yet. Choose a Google Doc or plain text file.",
        )
    return DriveDocument(
        file=metadata, text=redact(plain_text(text, limit)), truncated=len(text) > limit
    )


class DriveSession:
    def __init__(self, tools):
        self.tools = tools

    async def search(self, query):
        # Only a bounded literal name search; the browser cannot submit Drive query code.
        literal = query.replace("\\", "\\\\").replace("'", "\\'")
        condition = "trashed = false and mimeType != 'application/vnd.google-apps.folder'"
        if literal:
            condition += f" and name contains '{literal}'"
        payload = await self.tools.call(
            "google_drive_search_files",
            {"query": condition, "maxResults": 20, "includeItemsFromAllDrives": False},
        )
        items = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) > 20:
            raise StudioError("invalid_connection_output", "Drive returned an invalid file list.")
        return [file_view(item) for item in items]

    async def read(self, file_id, limit=8000):
        payload = await self.tools.call(
            "google_drive_get_file",
            {"fileId": file_id, "fields": "id,name,mimeType,modifiedTime,size,trashed"},
        )
        metadata = file_view(payload)
        if metadata.id != file_id:
            raise StudioError(
                "invalid_connection_output", "Drive returned metadata for a different file."
            )
        if not metadata.readable:
            raise StudioError(
                "unsupported_drive_content",
                "Preview supports Google Docs and UTF-8 plain text, Markdown and CSV files. Other file types are not read.",
            )
        size = payload.get("size")
        if size is not None and (not str(size).isdigit() or int(size) > 128_000):
            raise StudioError(
                "unsupported_drive_content",
                "This text file is too large. Choose a file under 128 KB.",
            )
        payload = await self.tools.call(
            "google_drive_download_file",
            {"fileId": file_id, "mimeType": "text/plain", "getBufferResponse": True},
        )
        return document_view(metadata, payload, limit)


class DriveService:
    def __init__(self, store, settings, provider=None):
        self.store, self.settings = store, settings
        self.provider = provider or PipedreamProvider(settings)

    async def sync(self, workspace):
        return self.store.sync(workspace, await self.provider.accounts(workspace))

    @asynccontextmanager
    async def session(self, workspace, connection_id, before_call=lambda: None):
        row = self.store.owned(workspace, connection_id)

        def check():
            self.store.owned(workspace, connection_id)
            before_call()

        async with self.provider.tools(workspace, row["account_id"], check) as tools:
            yield DriveSession(tools)
            self.store.owned(workspace, connection_id)

    async def context(self, workspace, source, before_call=lambda: None, timeout=30):
        async with connection_errors(timeout):
            async with self.session(workspace, source.connection_id, before_call) as session:
                documents = []
                for file_id in source.file_ids:
                    documents.append(await session.read(file_id, limit=2000))
                return documents
