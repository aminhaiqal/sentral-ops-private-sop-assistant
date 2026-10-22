import json

import httpx
import pytest
from openai import OpenAI

from app.config import Settings
from app.harness.model import ResponsesModel


@pytest.mark.parametrize(
    "model_name,effort,expected",
    [
        ("gpt-6-luna", "none", "none"),
        ("gpt-6.1-sol", "none", "low"),
        ("openai/gpt-6-luna", "low", "low"),
        ("gpt-4.1-mini", "none", None),
    ],
)
def test_responses_adapter_preserves_tool_and_reasoning_items(model_name, effort, expected):
    requests = []

    def respond(request):
        assert request.url == "https://provider.example/v1/responses"
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": model_name,
                "output": [
                    {
                        "type": "reasoning",
                        "id": "rs_test",
                        "summary": [],
                        "encrypted_content": "opaque",
                    },
                    {
                        "type": "function_call",
                        "id": "fc_test",
                        "call_id": "call_test",
                        "name": "search_documents",
                        "arguments": '{"query":"policy","limit":1}',
                    },
                ],
                "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110},
            },
        )

    settings = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        openai_chat_model=model_name,
        openai_reasoning_effort=effort,
    )
    adapter = ResponsesModel(settings)
    adapter.close()
    with OpenAI(
        api_key="sk-test",
        base_url="https://provider.example/v1",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as sdk:
        adapter.client = sdk
        history = [{"role": "user", "content": "Prepare a report"}]
        turn = adapter.next_turn("Complete the job", history, [], 1000)
        history += turn.output + [
            {"type": "function_call_output", "call_id": "call_test", "output": "{}"}
        ]
        adapter.next_turn("Complete the job", history, [], 500)
    assert turn.tokens == 110
    assert requests[0]["store"] is False
    assert requests[0]["parallel_tool_calls"] is False
    assert requests[0]["max_output_tokens"] == 1000
    assert requests[1]["input"][1]["encrypted_content"] == "opaque"
    assert requests[1]["input"][-1]["call_id"] == "call_test"
    assert requests[0]["model"] == model_name
    if expected is None:
        assert "reasoning" not in requests[0]
    else:
        assert requests[0]["reasoning"] == {"effort": expected}
    assert "temperature" not in requests[0]
