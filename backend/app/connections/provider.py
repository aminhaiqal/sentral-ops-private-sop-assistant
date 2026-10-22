"""Fixed-host Pipedream control API and a narrowly permitted remote MCP client."""

import asyncio
import json
import re
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import httpx2
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.studio.safety import StudioError

API = "https://api.pipedream.com/v1"
MCP_URL = "https://remote.mcp.pipedream.net/v3"
APP = "google_drive"
APPROVED_TOOLS = frozenset(
    {"google_drive_search_files", "google_drive_get_file", "google_drive_download_file"}
)
SETUP = "Configure PIPEDREAM_CLIENT_ID, PIPEDREAM_CLIENT_SECRET, PIPEDREAM_PROJECT_ID and PIPEDREAM_ENVIRONMENT on the API and worker, then restart both. See docs/google-drive-connections.md."


def external_user(workspace):
    return "axelyn_" + workspace


def response_payload(result):
    if result.is_error:
        raise StudioError(
            "connection_tool_error",
            "Google Drive could not complete this read. Check the account connection and file permissions.",
            retryable=True,
        )
    payload = result.structured_content
    if payload is None:
        blocks = [block.text for block in result.content if block.type == "text"]
        if len(blocks) != 1:
            raise StudioError(
                "invalid_connection_output",
                "The Drive MCP server returned an unsupported response.",
            )
        try:
            payload = json.loads(blocks[0])
        except (ValueError, TypeError) as exc:
            raise StudioError(
                "invalid_connection_output",
                "The Drive MCP server did not return structured file data.",
            ) from exc
    # Pipedream action responses wrap $return_value in exports; SDK versions may
    # expose that value directly or under result/data. Never evaluate returned text.
    for _ in range(4):
        if not isinstance(payload, dict):
            break
        if (
            "exports" in payload
            and isinstance(payload["exports"], dict)
            and "$return_value" in payload["exports"]
        ):
            payload = payload["exports"]["$return_value"]
        elif "$return_value" in payload:
            payload = payload["$return_value"]
        elif len(payload) == 1 and ("result" in payload or "data" in payload):
            payload = payload.get("result", payload.get("data"))
        else:
            break
    return payload


class LimitedStream(httpx2.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        count = 0
        async for chunk in self.stream:
            count += len(chunk)
            if count > 1_000_000:
                raise StudioError(
                    "connection_response_too_large",
                    "Drive returned too much data. Choose a smaller file.",
                )
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


async def bound_response(response):
    if response.status_code >= 300 and response.status_code != 405:
        raise StudioError(
            "connection_unavailable",
            "The Drive MCP connection was rejected. Refresh or reconnect the account.",
            retryable=True,
        )
    response.stream = LimitedStream(response.stream)


class MCPTools:
    def __init__(self, session, tools, before_call):
        self.session, self.before_call = session, before_call
        self.tools = {}
        for tool in tools:
            canonical = tool.name.replace("-", "_")
            if canonical in APPROVED_TOOLS:
                if canonical in self.tools:
                    raise StudioError(
                        "connection_schema_changed",
                        "Drive exposed ambiguous tool names. Ask the administrator to review the connector.",
                    )
                self.tools[canonical] = tool

    async def call(self, name, arguments):
        if name not in APPROVED_TOOLS:
            raise StudioError(
                "permission_denied", "This MCP tool is not approved for Google Drive."
            )
        tool = self.tools.get(name)
        if not tool:
            raise StudioError(
                "connection_schema_changed",
                "A required Drive read tool is unavailable. Ask the administrator to check the MCP connector.",
            )
        try:
            # No remote JSON Schema references: validating a server's schema must
            # never initiate another network request.
            serialized = json.dumps(tool.input_schema)
            if re.search(r'"\$(?:ref|dynamicRef)"\s*:\s*"(?!#)', serialized):
                raise SchemaError("Remote schema references are not permitted")
            Draft202012Validator.check_schema(tool.input_schema)
            Draft202012Validator(tool.input_schema).validate(arguments)
        except (SchemaError, ValidationError) as exc:
            raise StudioError(
                "connection_schema_changed",
                "The Drive tool's input schema changed. No tool was called; ask the administrator to review the connector.",
            ) from exc
        self.before_call()
        result = await self.session.call_tool(tool.name, arguments)
        return response_payload(result)


class PipedreamProvider:
    def __init__(self, settings):
        self.settings = settings

    def require_configuration(self):
        if not self.settings.connections_configured:
            raise StudioError("configuration_error", SETUP, retryable=True)

    async def request(self, method, path, *, token=None, **kwargs):
        self.require_configuration()
        headers = {"x-pd-environment": self.settings.pipedream_environment}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(
                timeout=15, trust_env=False, follow_redirects=False
            ) as client:
                async with client.stream(method, API + path, headers=headers, **kwargs) as response:
                    if response.status_code >= 300:
                        raise StudioError(
                            "connection_provider_error",
                            "Pipedream rejected the connection request. Check project credentials, environment, account authorization and service limits.",
                            retryable=True,
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > 512_000:
                            raise StudioError(
                                "connection_response_too_large",
                                "The connection provider returned too much data.",
                            )
                    return json.loads(body) if body else None
        except httpx.HTTPError as exc:
            raise StudioError(
                "connection_unavailable",
                "The connection provider could not be reached. Try again later.",
                retryable=True,
            ) from exc
        except ValueError as exc:
            raise StudioError(
                "invalid_connection_output", "The connection provider returned an invalid response."
            ) from exc

    async def access_token(self):
        payload = await self.request(
            "POST",
            "/oauth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": self.settings.pipedream_client_id,
                "client_secret": self.settings.pipedream_client_secret,
                "scope": "connect:accounts:read connect:accounts:write connect:apps:* connect:actions:* connect:tokens:create",
            },
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise StudioError(
                "invalid_connection_output", "Pipedream did not issue a valid access token."
            )
        return token

    async def connect_link(self, workspace):
        token = await self.access_token()
        body = {
            "external_user_id": external_user(workspace),
            "app_id": APP,
            "expires_in": 600,
            "scope": "connect:accounts:read connect:accounts:write connect:apps:*",
            "allowed_origins": self.settings.cors_origins,
        }
        if self.settings.pipedream_drive_oauth_app_id:
            body["oauth_app_id"] = self.settings.pipedream_drive_oauth_app_id
        payload = await self.request(
            "POST", f"/connect/{self.settings.pipedream_project_id}/tokens", token=token, json=body
        )
        url = urlsplit(payload.get("connect_link_url", "") if isinstance(payload, dict) else "")
        host = url.hostname or ""
        if (
            url.scheme != "https"
            or not (host == "pipedream.com" or host.endswith(".pipedream.com"))
            or url.username
            or url.password
            or url.port not in {None, 443}
            or url.path != "/_static/connect.html"
        ):
            raise StudioError(
                "invalid_connection_output", "Pipedream returned an unexpected authorization link."
            )
        query = dict(parse_qsl(url.query))
        if not re.fullmatch(r"ctok_[0-9a-f]{32}", query.get("token", "")):
            raise StudioError(
                "invalid_connection_output", "Pipedream returned an invalid connection link."
            )
        query = {"token": query["token"], "connectLink": "true", "app": APP}
        return {
            "url": urlunsplit(("https", url.netloc, url.path, urlencode(query), "")),
            "expires_in": 600,
        }

    async def accounts(self, workspace, token=None):
        token = token or await self.access_token()
        payload = await self.request(
            "GET",
            f"/connect/{self.settings.pipedream_project_id}/users/{external_user(workspace)}/accounts",
            token=token,
            params={"app": APP, "include_credentials": "false"},
        )
        if not isinstance(payload, list) or len(payload) > 100:
            raise StudioError(
                "invalid_connection_output", "Pipedream returned an invalid account list."
            )
        accounts = []
        for row in payload:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("app"), dict)
                or row["app"].get("name_slug") != APP
            ):
                continue
            if not re.fullmatch(r"apn_[a-zA-Z0-9]+", str(row.get("id", ""))):
                continue
            accounts.append(
                {
                    "id": row["id"],
                    "name": str(row.get("name") or "Google Drive account")[:160],
                    "healthy": row.get("healthy") is True,
                    "dead": row.get("dead") is True,
                }
            )
        return accounts

    async def delete_account(self, workspace, account_id):
        token = await self.access_token()
        # Verify ownership from a user-scoped listing before account-level deletion.
        if any(account["id"] == account_id for account in await self.accounts(workspace, token)):
            await self.request(
                "DELETE",
                f"/connect/{self.settings.pipedream_project_id}/accounts/{account_id}",
                token=token,
            )

    @asynccontextmanager
    async def tools(self, workspace, account_id, before_call=lambda: None):
        token = await self.access_token()
        accounts = await self.accounts(workspace, token)
        if not any(
            row["id"] == account_id and row["healthy"] and not row["dead"] for row in accounts
        ):
            raise StudioError(
                "connection_revoked",
                "The Google Drive account is no longer authorized. Open Connections and reconnect.",
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "x-pd-project-id": self.settings.pipedream_project_id,
            "x-pd-environment": self.settings.pipedream_environment,
            "x-pd-external-user-id": external_user(workspace),
            "x-pd-app-slug": APP,
            "x-pd-account-id": account_id,
            "x-pd-registry": "public",
        }
        async with httpx2.AsyncClient(
            headers=headers,
            timeout=20,
            trust_env=False,
            follow_redirects=False,
            event_hooks={"response": [bound_response]},
        ) as client:
            async with streamable_http_client(
                MCP_URL, http_client=client, max_sse_event_size=1_000_000
            ) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=20) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    yield MCPTools(session, listing.tools, before_call)


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
            "Google Drive took too long to respond. Try again with a smaller file.",
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
        # SDK exception groups may contain provider bodies and authorization headers.
        # Return a fixed message and never log the original exception text.
        raise StudioError(
            "connection_unavailable",
            "Google Drive could not complete the request. Refresh the connection and try again.",
            retryable=True,
        ) from exc
