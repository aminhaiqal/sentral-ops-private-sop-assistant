"""Fixed-host search and schema-constrained AI. No user-controlled request endpoints."""

import json
from dataclasses import dataclass

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from app.config import Settings
from app.studio.safety import StudioError

SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


@dataclass
class Generated:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    completed: bool = True


class Providers:
    def __init__(self, settings: Settings):
        self.settings = settings

    def search(self, query: str, limit: int, timeout: float) -> list[dict]:
        if not self.settings.brave_search_api_key:
            raise StudioError(
                "configuration_error",
                "Brave Search is not configured. Create a Web Search API key at https://api-dashboard.search.brave.com and set BRAVE_SEARCH_API_KEY on the backend and worker, then restart them.",
                retryable=True,
            )
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "GET",
                    SEARCH_ENDPOINT,
                    headers={
                        "X-Subscription-Token": self.settings.brave_search_api_key,
                        "Accept": "application/json",
                    },
                    params={
                        "q": query,
                        "count": limit,
                        "result_filter": "web",
                        "text_decorations": "false",
                        "safesearch": "moderate",
                    },
                ) as response:
                    if response.status_code != 200:
                        self.http_error("Brave Search", response.status_code)
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > 512_000:
                            raise StudioError(
                                "provider_response_too_large",
                                "Search returned too much data. Use a narrower target.",
                            )
            payload = json.loads(body)
            results = payload.get("web", {}).get("results", [])
            if not isinstance(results, list) or not all(isinstance(item, dict) for item in results):
                raise ValueError()
            return results[:limit]
        except httpx.TimeoutException as exc:
            raise StudioError(
                "provider_timeout",
                "Brave Search timed out. Retry within this run's remaining budget.",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise StudioError(
                "provider_unavailable", "Brave Search could not be reached.", retryable=True
            ) from exc
        except (ValueError, AttributeError) as exc:
            if isinstance(exc, StudioError):
                raise
            raise StudioError(
                "invalid_provider_response", "Brave Search returned an invalid response."
            ) from exc

    @staticmethod
    def http_error(provider, status):
        configuration = status in {400, 401, 402, 403, 404}
        raise StudioError(
            "configuration_error" if configuration else "provider_error",
            f"{provider} returned HTTP {status}. Check the server API key, API plan and configured model. No provider response body is logged.",
            retryable=configuration or status in {408, 429} or status >= 500,
        )

    def generate(
        self, schema, instructions: str, data: dict, timeout: float, max_output_tokens: int
    ) -> Generated:
        if not self.settings.openai_api_key:
            raise StudioError(
                "configuration_error",
                "The AI provider is not configured. Set OPENAI_API_KEY, OPENAI_BASE_URL and OPENAI_CHAT_MODEL on the backend and worker. The model must support Responses structured outputs.",
                retryable=True,
            )
        parameters = {}
        name = self.settings.openai_chat_model.removeprefix("openai/")
        if name.startswith("gpt-6"):
            effort = self.settings.openai_reasoning_effort
            if effort == "none" and name.startswith(("gpt-6-astra", "gpt-6.1-sol")):
                effort = "low"
            parameters["reasoning"] = {"effort": effort}
        try:
            with httpx.Client(
                timeout=timeout, follow_redirects=False, trust_env=False
            ) as transport:
                with OpenAI(
                    api_key=self.settings.openai_api_key,
                    base_url=self.settings.openai_base_url,
                    http_client=transport,
                    max_retries=0,
                ) as client:
                    response = client.responses.create(
                        model=self.settings.openai_chat_model,
                        store=False,
                        instructions=instructions,
                        input=[{"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
                        text={
                            "format": {
                                "type": "json_schema",
                                "name": schema.__name__,
                                "strict": True,
                                "schema": schema.model_json_schema(),
                            }
                        },
                        max_output_tokens=max_output_tokens,
                        **parameters,
                    )
            return Generated(
                response.output_text,
                response.usage.input_tokens if response.usage else None,
                response.usage.output_tokens if response.usage else None,
                response.status == "completed",
            )
        except APITimeoutError as exc:
            raise StudioError(
                "provider_timeout",
                "The AI request timed out. Its reserved usage remains charged to this run's budget.",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise StudioError(
                "provider_unavailable", "The AI provider could not be reached.", retryable=True
            ) from exc
        except APIStatusError as exc:
            self.http_error("AI provider", exc.status_code)
