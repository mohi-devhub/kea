"""OpenAI adapter contract tests. No network: httpx is mocked with recorded payload shapes."""

import json
from typing import Any

import httpx2 as httpx
import pytest
from openai import AsyncOpenAI

from app.config import Settings
from app.llm.base import LLMError
from app.llm.factory import UnavailableProvider, provider_for_settings
from app.llm.models import LLMRequest, Message, ToolCall, ToolSpec
from app.llm.openai_adapter import OpenAIProvider
from app.llm.safety import SafeProvider, find_secret


def _settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, **kw)


KEY = "sk-test-0123456789abcdef0123456789abcdef"


def _response(output: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": "gpt-5.6-terra",
        "status": "completed",
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
        **extra,
    }


def _provider(handler: Any) -> tuple[OpenAIProvider, list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append({"body": json.loads(request.content), "auth": request.headers["authorization"]})
        response: httpx.Response = handler(request)
        return response

    client = AsyncOpenAI(
        api_key=KEY,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)),
        max_retries=0,
    )
    return OpenAIProvider(KEY, "gpt-5.6-terra", client=client), seen


def _request() -> LLMRequest:
    return LLMRequest(
        model="gpt-5.6-terra",
        messages=[
            Message(role="system", content="Be brief."),
            Message(role="user", content="Investigate."),
        ],
        tools=[ToolSpec(name="get_incident", description="Read the incident.")],
    )


@pytest.mark.asyncio
async def test_request_shape_is_stateless_and_carries_no_key_in_the_body() -> None:
    call = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "get_incident",
            "arguments": "{}", "status": "completed"}  # fmt: skip
    provider, seen = _provider(lambda _: httpx.Response(200, json=_response([call])))
    result = await provider.generate(_request())
    body = seen[0]["body"]
    assert body["store"] is False
    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["instructions"] == "Be brief."
    assert body["input"] == [{"role": "user", "content": "Investigate."}]
    assert body["tools"][0]["type"] == "function" and body["tools"][0]["name"] == "get_incident"
    assert "temperature" not in body
    assert KEY not in json.dumps(body)  # the key travels only in the Authorization header
    assert result.tool_calls[0].name == "get_incident"
    assert result.finish_reason == "tool_calls"
    assert result.usage["total_tokens"] == 120
    assert result.message.raw and result.message.raw[0]["call_id"] == "call_1"


@pytest.mark.asyncio
async def test_native_items_are_echoed_back_on_the_next_turn() -> None:
    reasoning = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "abc"}
    call = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "get_incident",
            "arguments": "{}", "status": "completed"}  # fmt: skip
    text = {"type": "message", "id": "m", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": "done", "annotations": []}]}  # fmt: skip
    provider, seen = _provider(lambda _: httpx.Response(200, json=_response([reasoning, call])))
    first = await provider.generate(_request())
    provider2, seen2 = _provider(lambda _: httpx.Response(200, json=_response([text])))
    follow = _request().model_copy(
        update={
            "messages": [
                *_request().messages,
                first.message,
                Message(role="tool", tool_call_id="call_1", content='{"ok": true}'),
            ]
        }
    )
    final = await provider2.generate(follow)
    items = seen2[0]["body"]["input"]
    assert [i.get("type") or i.get("role") for i in items] == [
        "user", "reasoning", "function_call", "function_call_output",
    ]  # fmt: skip
    assert items[1]["encrypted_content"] == "abc"
    assert items[3] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"ok": true}',
    }
    assert final.message.content == "done" and final.finish_reason == "stop"
    assert seen[0]["auth"] == f"Bearer {KEY}"


@pytest.mark.asyncio
async def test_errors_never_leak_the_key() -> None:
    leaky = {"error": {"message": f"Incorrect API key provided: {KEY[:12]}...", "type": "x"}}
    provider, _ = _provider(lambda _: httpx.Response(401, json=leaky))
    with pytest.raises(LLMError) as raised:
        await provider.generate(_request())
    assert "401" in str(raised.value)
    assert KEY[:12] not in str(raised.value)


@pytest.mark.asyncio
async def test_rate_limit_becomes_llm_error() -> None:
    provider, _ = _provider(lambda _: httpx.Response(429, json={"error": {"message": "slow down"}}))
    with pytest.raises(LLMError, match="429"):
        await provider.generate(_request())


def test_raw_items_stay_out_of_dumps_and_cache_keys() -> None:
    message = Message(
        role="assistant", content="x", raw=[{"type": "reasoning", "encrypted_content": "z"}]
    )
    assert (
        "raw" not in message.model_dump() and "encrypted_content" not in message.model_dump_json()
    )


def test_secret_guard_blocks_keys_paths_and_tokens() -> None:
    assert find_secret(f"key is {KEY}", []) == "api key (sk-...)"
    assert find_secret("my token abc123", ["abc123"]) == "a configured API key"
    assert find_secret("open /Users/alex/project/file", []) == "home directory path"
    assert find_secret("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123", [])
    assert find_secret("payment latency_p95_ms reached 14.1x baseline", [KEY]) is None


@pytest.mark.asyncio
async def test_safe_provider_refuses_to_send_a_secret() -> None:
    provider, seen = _provider(lambda _: httpx.Response(200, json=_response([])))
    safe = SafeProvider(provider, [KEY])
    bad = _request().model_copy(update={"messages": [Message(role="user", content=f"oops {KEY}")]})
    with pytest.raises(LLMError, match="blocked outbound"):
        await safe.generate(bad)
    assert seen == []  # nothing was sent


def test_factory_only_activates_with_provider_model_and_key() -> None:
    base = {"llm_provider": "openai", "llm_model": "gpt-5.6-terra"}
    assert provider_for_settings(_settings(llm_provider="template")) is None
    no_key = provider_for_settings(_settings(**base))
    assert isinstance(no_key, UnavailableProvider) and "OPENAI_API_KEY" in no_key.reason
    no_model = provider_for_settings(_settings(llm_provider="openai", openai_api_key=KEY))
    assert isinstance(no_model, UnavailableProvider) and "LLM_MODEL" in no_model.reason
    live = provider_for_settings(_settings(openai_api_key=KEY, **base))
    assert (
        isinstance(live, SafeProvider) and live.name == "openai" and live.model == "gpt-5.6-terra"
    )
    other = provider_for_settings(_settings(llm_provider="anthropic", llm_model="m"))
    assert isinstance(other, UnavailableProvider)


def test_role_overrides_win_over_the_global_setting() -> None:
    settings = _settings(llm_provider="openai", llm_model="a", openai_api_key=KEY,
                        baseline_llm_model="b")  # fmt: skip
    assert provider_for_settings(settings, "agent").model == "a"  # type: ignore[union-attr]
    assert provider_for_settings(settings, "baseline").model == "b"  # type: ignore[union-attr]


def test_tool_call_model_is_neutral() -> None:
    assert ToolCall(id="c", name="n").arguments == {}
