from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI

from app.config import Settings
from app.openai_client import OpenAINotConfigured


@dataclass
class ModelTurn:
    output: list[dict]
    tokens: int
    completed: bool = True


class AgentModel(Protocol):
    def next_turn(
        self, instructions: str, messages: list[dict], tools: list[dict], max_tokens: int
    ) -> ModelTurn: ...


class ResponsesModel:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise OpenAINotConfigured(
                "An administrator needs to configure the server's AI API key."
            )
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.harness_request_timeout_seconds,
            max_retries=0,
        )

    def next_turn(
        self, instructions: str, messages: list[dict], tools: list[dict], max_tokens: int
    ) -> ModelTurn:
        parameters = {}
        name = self.settings.openai_chat_model.removeprefix("openai/")
        if name.startswith("gpt-6"):
            effort = self.settings.openai_reasoning_effort
            if effort == "none" and name.startswith(("gpt-6-astra", "gpt-6.1-sol")):
                effort = "low"
            parameters["reasoning"] = {"effort": effort}
        response = self.client.responses.create(
            model=self.settings.openai_chat_model,
            instructions=instructions,
            input=messages,
            tools=tools,
            parallel_tool_calls=False,
            store=False,
            include=["reasoning.encrypted_content"],
            max_output_tokens=min(4000, max_tokens),
            **parameters,
        )
        return ModelTurn(
            output=[item.model_dump(mode="json", exclude_none=True) for item in response.output],
            tokens=response.usage.total_tokens if response.usage else max_tokens,
            completed=response.status == "completed",
        )

    def close(self) -> None:
        self.client.close()
