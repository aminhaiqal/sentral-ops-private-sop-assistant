import json

import httpx
from openai import OpenAI
import pytest

from app.config import Settings
from app.openai_client import OpenAIClient


@pytest.mark.parametrize("model,effort,expected_effort,temperature", [
    ("gpt-6-luna", "none", "none", 0.1),
    ("gpt-6-luna", "low", "low", None),
    ("gpt-6.1-sol", "none", "low", None),
    ("gpt-4.1-mini", "none", None, 0.1),
    ("openai/gpt-6-luna", "none", "none", 0.1),
    ("openai/gpt-6-luna", "low", "low", None),
    ("openai/gpt-6.1-sol", "none", "low", None),
])
def test_answer_request_uses_supported_reasoning_and_sampling_parameters(
    model, effort, expected_effort, temperature
):
    requests = []

    def respond(request):
        assert request.url.path == "/v1/chat/completions"
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "completion-test", "object": "chat.completion", "created": 1,
            "model": model,
            "choices": [{"index": 0, "message": {
                "role": "assistant", "content": "The SOP requires approval. [S1]",
            }, "finish_reason": "stop"}],
        })

    settings = Settings(_env_file=None, openai_api_key="sk-test", openai_chat_model=model,
                        openai_reasoning_effort=effort)
    client = OpenAIClient(settings)
    client.client.close()
    with OpenAI(api_key="sk-test", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(respond))) as sdk:
        client.client = sdk
        answer = client.generate_answer("Answer only from the provided SOP.", "What is required?")

    assert answer == "The SOP requires approval. [S1]"
    assert requests[0]["model"] == model
    assert requests[0].get("reasoning_effort") == expected_effort
    assert requests[0].get("temperature") == temperature
    if temperature is None:
        assert "temperature" not in requests[0]


def test_configured_provider_routes_both_embeddings_and_answers(monkeypatch):
    import app.openai_client as module

    requests = []

    def respond(request):
        assert request.url.host == "openrouter.ai"
        assert request.headers["authorization"] == "Bearer sk-or-test"
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path == "/api/v1/embeddings":
            return httpx.Response(200, json={
                "object": "list", "model": body["model"],
                "data": [{"index": 0, "object": "embedding", "embedding": [1.0, 0.0, 0.0]}],
                "usage": {"prompt_tokens": 3, "total_tokens": 3},
            })
        assert request.url.path == "/api/v1/chat/completions"
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 1, "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Sign in. [S1]"},
                         "finish_reason": "stop"}],
        })

    def sdk(**kwargs):
        return OpenAI(**kwargs, max_retries=0,
                      http_client=httpx.Client(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(module, "OpenAI", sdk)
    settings = Settings(_env_file=None, openai_api_key="sk-or-test",
                        openai_base_url="https://openrouter.ai/api/v1",
                        openai_chat_model="openai/gpt-6-luna",
                        openai_embedding_model="openai/text-embedding-3-small")
    client = OpenAIClient(settings)
    with client.client:
        assert client.embed_texts(["Visitor policy"]) == [[1.0, 0.0, 0.0]]
        assert client.generate_answer("Use the source.", "Where do I sign in?") == "Sign in. [S1]"
    assert requests[0][1]["model"] == "openai/text-embedding-3-small"
    assert requests[0][1]["encoding_format"] == "float"
    assert requests[1][1]["model"] == "openai/gpt-6-luna"
    assert requests[1][1]["reasoning_effort"] == "none"
