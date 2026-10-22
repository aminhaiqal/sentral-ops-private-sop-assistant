import json

import httpx
from openai import OpenAI

from app.config import Settings
from app.openai_client import OpenAIClient


def test_configured_provider_routes_embeddings(monkeypatch):
    import app.openai_client as module

    requests = []

    def respond(request):
        assert request.url.host == "openrouter.ai"
        assert request.url.path == "/api/v1/embeddings"
        assert request.headers["authorization"] == "Bearer sk-or-test"
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": body["model"],
                "data": [{"index": 0, "object": "embedding", "embedding": [1.0, 0.0, 0.0]}],
                "usage": {"prompt_tokens": 3, "total_tokens": 3},
            },
        )

    def sdk(**kwargs):
        return OpenAI(
            **kwargs,
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        )

    monkeypatch.setattr(module, "OpenAI", sdk)
    client = OpenAIClient(
        Settings(
            _env_file=None,
            openai_api_key="sk-or-test",
            openai_base_url="https://openrouter.ai/api/v1",
            openai_embedding_model="openai/text-embedding-3-small",
        )
    )
    with client.client:
        assert client.embed_texts(["Visitor policy"]) == [[1.0, 0.0, 0.0]]
    assert requests[0]["model"] == "openai/text-embedding-3-small"
    assert requests[0]["encoding_format"] == "float"
