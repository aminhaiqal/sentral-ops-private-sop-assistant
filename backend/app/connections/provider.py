"""Direct Google OAuth and a small, read-only MCP adapter over the stable Drive API."""

import asyncio
import json
import math
import re
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import urlencode

import httpx2
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oauth2.rfc6749.errors import OAuth2Error
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from mcp import Client
from mcp.server import MCPServer

from app.studio.safety import StudioError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DRIVE_API = "https://www.googleapis.com/drive/v3"
SCOPE = "https://www.googleapis.com/auth/drive.readonly"
APPROVED_TOOLS = frozenset(
    {"google_drive_search_files", "google_drive_get_file", "google_drive_read_file"}
)
SETUP = "Google Drive is not enabled yet. The app owner must configure Google authorization before accounts can connect."


class LimitedStream(httpx2.AsyncByteStream):
    def __init__(self, stream, maximum=512_000):
        self.stream, self.maximum = stream, maximum

    async def __aiter__(self):
        count = 0
        async for chunk in self.stream:
            count += len(chunk)
            if count > self.maximum:
                raise StudioError(
                    "connection_response_too_large",
                    "Google Drive returned too much data. Choose a smaller file.",
                )
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


async def bound_response(response):
    if 300 <= response.status_code < 400:
        raise StudioError(
            "connection_unavailable",
            "Google returned an unexpected redirect. No redirect was followed.",
        )
    response.stream = LimitedStream(response.stream)


def response_payload(result):
    if result.is_error:
        raise StudioError(
            "connection_tool_error",
            "Google Drive could not complete this read. Check the account and file permissions.",
        )
    payload = result.structured_content
    if payload is None:
        blocks = [block.text for block in result.content if block.type == "text"]
        if len(blocks) != 1:
            raise StudioError(
                "invalid_connection_output", "The Drive tool returned an unsupported response."
            )
        try:
            payload = json.loads(blocks[0])
        except (ValueError, TypeError) as exc:
            raise StudioError(
                "invalid_connection_output", "The Drive tool did not return structured data."
            ) from exc
    if isinstance(payload, dict) and set(payload) == {"error"}:
        error = payload["error"]
        raise StudioError(error["code"], error["message"], retryable=error["retryable"])
    return payload


class MCPTools:
    def __init__(self, session, tools, before_call):
        self.session, self.before_call = session, before_call
        self.tools = {tool.name: tool for tool in tools if tool.name in APPROVED_TOOLS}

    async def call(self, name, arguments):
        if name not in APPROVED_TOOLS:
            raise StudioError("permission_denied", "This Drive tool is not approved.")
        tool = self.tools.get(name)
        if not tool:
            raise StudioError(
                "connection_schema_changed", "A required Drive read tool is unavailable."
            )
        try:
            if re.search(r'"\$(?:ref|dynamicRef)"\s*:\s*"(?!#)', json.dumps(tool.input_schema)):
                raise SchemaError("External references are not permitted")
            Draft202012Validator.check_schema(tool.input_schema)
            Draft202012Validator(tool.input_schema).validate(arguments)
        except (SchemaError, ValidationError) as exc:
            raise StudioError(
                "connection_schema_changed",
                "The Drive tool input did not match its approved schema. No tool was called.",
            ) from exc
        self.before_call()
        return response_payload(await self.session.call_tool(name, arguments))


def validate_token(token, previous=None):
    if not isinstance(token, dict):
        raise StudioError(
            "authorization_failed", "Google did not return valid authorization credentials."
        )
    refresh = token.get("refresh_token") or (previous or {}).get("refresh_token")
    access = token.get("access_token")
    expiry = token.get("expires_at")
    scopes = set(str(token.get("scope", SCOPE)).split())
    if (
        not isinstance(access, str)
        or not 1 <= len(access) <= 8192
        or not isinstance(refresh, str)
        or not 1 <= len(refresh) <= 8192
        or str(token.get("token_type", "Bearer")).lower() != "bearer"
        or scopes != {SCOPE}
        or type(expiry) not in {int, float}
        or not math.isfinite(expiry)
        or not time.time() < expiry <= time.time() + 86400
    ):
        raise StudioError(
            "authorization_failed",
            "Google did not grant ongoing, read-only Drive access. Click Connect again and approve Drive access.",
        )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": expiry,
        "scope": SCOPE,
        "token_type": "Bearer",
    }


class GoogleDriveProvider:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store

    def require_configuration(self):
        if not self.settings.connections_configured:
            raise StudioError("configuration_error", SETUP)

    def oauth_client(self, **kwargs):
        self.require_configuration()
        return AsyncOAuth2Client(
            self.settings.google_drive_client_id,
            self.settings.google_drive_client_secret,
            token_endpoint_auth_method="client_secret_post",
            scope=SCOPE,
            redirect_uri=self.settings.google_drive_redirect_uri,
            code_challenge_method="S256",
            timeout=15,
            trust_env=False,
            follow_redirects=False,
            event_hooks={"response": [bound_response]},
            **kwargs,
        )

    async def start(self, workspace):
        state, browser, verifier = (
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(64),
        )
        async with self.oauth_client() as client:
            url, _ = client.create_authorization_url(
                AUTH_URL,
                state=state,
                code_verifier=verifier,
                access_type="offline",
                prompt="consent select_account",
            )
        flow_id = self.store.begin_auth(workspace, state, browser, verifier)
        return {"url": url, "flow_id": flow_id, "expires_in": 600}, browser

    async def exchange(self, code, state, verifier):
        try:
            async with self.oauth_client(state=state) as client:
                response = (
                    self.settings.google_drive_redirect_uri
                    + "?"
                    + urlencode({"code": code, "state": state})
                )
                token = await client.fetch_token(
                    TOKEN_URL,
                    authorization_response=response,
                    code_verifier=verifier,
                    grant_type="authorization_code",
                )
            return validate_token(token)
        except (OAuthError, OAuth2Error) as exc:
            raise StudioError(
                "authorization_failed",
                "Google authorization failed. Return to Axelyn and click Connect again.",
            ) from exc

    async def access_token(self, workspace, connection_id):
        self.require_configuration()
        token, revision = self.store.tokens(workspace, connection_id)
        if token["expires_at"] <= time.time() + 60:
            try:
                async with self.oauth_client() as client:
                    refreshed = await client.refresh_token(
                        TOKEN_URL, refresh_token=token["refresh_token"]
                    )
                token = self.store.update_tokens(
                    workspace, connection_id, validate_token(refreshed, token), revision
                )
            except (OAuthError, OAuth2Error) as exc:
                self.store.mark_reconnect(workspace, connection_id)
                raise StudioError(
                    "connection_revoked",
                    "Google Drive authorization expired or was revoked. Click Connect to authorize it again.",
                ) from exc
        self.store.owned(workspace, connection_id)
        return token["access_token"]

    async def request(self, token, path, *, params=None, text=False):
        maximum = 128_000 if text else 512_000
        async with httpx2.AsyncClient(
            timeout=15, trust_env=False, follow_redirects=False
        ) as client:
            async with client.stream(
                "GET", DRIVE_API + path, headers={"Authorization": f"Bearer {token}"}, params=params
            ) as response:
                if response.status_code == 401:
                    raise StudioError(
                        "connection_revoked",
                        "Google Drive access was revoked. Click Connect again.",
                    )
                if response.status_code == 404:
                    raise StudioError(
                        "drive_file_unavailable",
                        "This Drive file was deleted or is no longer shared with your account.",
                    )
                if response.status_code != 200:
                    raise StudioError(
                        "connection_provider_error",
                        "Google Drive could not complete this read. Check account permissions and the app's Drive API configuration.",
                        retryable=response.status_code == 429 or response.status_code >= 500,
                    )
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    data.extend(chunk)
                    if len(data) > maximum:
                        raise StudioError(
                            "connection_response_too_large",
                            "This Drive file is too large. Choose a text document under 128 KB.",
                        )
        if text:
            try:
                return data.decode("utf-8-sig")
            except UnicodeError as exc:
                raise StudioError(
                    "unsupported_drive_content", "Choose a Google Doc or UTF-8 text file."
                ) from exc
        try:
            return json.loads(data)
        except ValueError as exc:
            raise StudioError(
                "invalid_connection_output", "Google Drive returned invalid data."
            ) from exc

    async def account(self, token):
        payload = await self.request(
            token["access_token"],
            "/about",
            params={"fields": "user(displayName,emailAddress,permissionId)"},
        )
        user = payload.get("user", {}) if isinstance(payload, dict) else {}
        identifier = user.get("permissionId", "")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{5,200}", identifier):
            raise StudioError(
                "invalid_connection_output", "Google Drive did not identify the authorized account."
            )
        return {
            "id": identifier,
            "name": str(
                user.get("emailAddress") or user.get("displayName") or "Google Drive account"
            )[:160],
        }

    async def revoke(self, token):
        async with httpx2.AsyncClient(
            timeout=10, trust_env=False, follow_redirects=False
        ) as client:
            async with client.stream(
                "POST", REVOKE_URL, data={"token": token["refresh_token"]}
            ) as response:
                # An already-revoked token is equivalent to successful revocation.
                if response.status_code not in {200, 400}:
                    raise StudioError(
                        "connection_unavailable", "Google revocation could not be confirmed."
                    )

    @asynccontextmanager
    async def tools(self, workspace, connection_id, before_call=lambda: None):
        self.require_configuration()
        self.store.owned(workspace, connection_id)
        server = MCPServer("Axelyn Google Drive", log_level="ERROR")

        async def run(operation):
            try:
                token = await self.access_token(workspace, connection_id)
                result = await operation(token)
                self.store.owned(workspace, connection_id)
                return result
            except StudioError as exc:
                if exc.code == "connection_revoked":
                    self.store.mark_reconnect(workspace, connection_id)
                return {
                    "error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}
                }
            except Exception:
                # SDK error logs must not include tokens or provider response bodies.
                return {
                    "error": {
                        "code": "connection_unavailable",
                        "message": "Google Drive could not be reached. Try again later.",
                        "retryable": True,
                    }
                }

        @server.tool(name="google_drive_search_files")
        async def search_files(name: str) -> dict:
            literal = name.replace("\\", "\\\\").replace("'", "\\'")
            query = "trashed = false and mimeType != 'application/vnd.google-apps.folder'"
            if literal:
                query += f" and name contains '{literal}'"
            return await run(
                lambda token: self.request(
                    token,
                    "/files",
                    params={
                        "q": query,
                        "pageSize": 20,
                        "fields": "files(id,name,mimeType,modifiedTime,trashed),nextPageToken",
                        "corpora": "user",
                    },
                )
            )

        @server.tool(name="google_drive_get_file")
        async def get_file(file_id: str) -> dict:
            if not re.fullmatch(r"[a-zA-Z0-9_-]{5,180}", file_id):
                raise ValueError("Invalid file identifier")
            return await run(
                lambda token: self.request(
                    token,
                    f"/files/{file_id}",
                    params={"fields": "id,name,mimeType,modifiedTime,size,trashed"},
                )
            )

        @server.tool(name="google_drive_read_file")
        async def read_file(file_id: str, mime_type: str) -> dict:
            if not re.fullmatch(r"[a-zA-Z0-9_-]{5,180}", file_id) or mime_type not in {
                "application/vnd.google-apps.document",
                "text/plain",
                "text/markdown",
                "text/csv",
            }:
                raise ValueError("Unsupported Drive text file")

            async def content(token):
                path = f"/files/{file_id}"
                params = {"alt": "media"}
                if mime_type == "application/vnd.google-apps.document":
                    path += "/export"
                    params = {"mimeType": "text/plain"}
                return {
                    "fileId": file_id,
                    "content": await self.request(token, path, params=params, text=True),
                }

            return await run(content)

        async with Client(
            server, raise_exceptions=True, mode="legacy", read_timeout_seconds=20
        ) as client:
            listing = await client.list_tools()
            yield MCPTools(client, listing.tools, before_call)


@asynccontextmanager
async def connection_errors(timeout=30):
    try:
        async with asyncio.timeout(timeout):
            yield
    except StudioError:
        raise
    except TimeoutError as exc:
        raise StudioError(
            "connection_timeout",
            "Google Drive took too long to respond. Try again.",
            retryable=True,
        ) from exc
    except Exception as exc:
        pending = [exc]
        while pending:
            cause = pending.pop()
            if isinstance(cause, StudioError):
                raise cause from None
            if isinstance(cause, BaseExceptionGroup):
                pending.extend(cause.exceptions)
        raise StudioError(
            "connection_unavailable",
            "Google Drive could not complete the request. Try reconnecting your account.",
            retryable=True,
        ) from exc
