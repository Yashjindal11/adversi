from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from adversi.errors import (
    AuthenticationError,
    BudgetExceededError,
    ConfigurationError,
    ProviderError,
    RateLimitError,
)
from adversi.models import MemoryCache, Model, Price, parse_model_spec
from adversi.observability.usage import Budget, UsageTracker, reset_tracker, set_tracker
from adversi.providers import (
    Message,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolSpec,
    create_provider,
)
from adversi.providers.anthropic import AnthropicProvider
from adversi.providers.openai_compat import OpenAICompatibleProvider
from adversi.testing import ScriptedProvider


def _openai(handler, **kw) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://api.test/v1", api_key="k", transport=httpx.MockTransport(handler), **kw
    )


async def test_openai_payload_and_response_translation() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gpt-x",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator",
                                        "arguments": '{"expression": "1+1"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    provider = _openai(handler)
    req = ModelRequest(
        model="gpt-x",
        messages=[
            Message.system("sys"),
            Message.user("hi"),
            Message.assistant("", [ToolCall(id="c0", name="t", arguments={"a": 1})]),
            Message.tool("out", tool_call_id="c0", name="t"),
        ],
        temperature=0.2,
        tools=[ToolSpec(name="calculator", description="d", parameters={"type": "object"})],
        response_schema={"type": "object"},
        response_schema_name="Thing",
        metadata={"agent": "secret-local-info"},
    )
    resp = await provider.complete(req)
    body = seen["body"]
    assert seen["auth"] == "Bearer k"
    assert body["temperature"] == 0.2 and "max_tokens" not in body
    assert body["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c0", "content": "out"}
    assert body["response_format"]["json_schema"]["name"] == "Thing"
    assert "metadata" not in body and "secret-local-info" not in json.dumps(body)
    assert resp.tool_calls[0].arguments == {"expression": "1+1"}
    assert resp.usage.input_tokens == 11 and resp.usage.output_tokens == 7


@pytest.mark.parametrize(
    ("code", "exc", "retryable"),
    [
        (429, RateLimitError, True),
        (401, AuthenticationError, False),
        (503, ProviderError, True),
        (400, ProviderError, False),
    ],
)
async def test_openai_error_mapping(code: int, exc: type[Exception], retryable: bool) -> None:
    provider = _openai(lambda r: httpx.Response(code, text="nope"))
    with pytest.raises(exc) as info:
        await provider.complete(ModelRequest(model="m", messages=[Message.user("x")]))
    assert info.value.retryable is retryable  # type: ignore[attr-defined]


async def test_openai_streaming() -> None:
    sse = (
        "".join(
            f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}\n\n"
            for t in ["Hel", "lo"]
        )
        + "data: [DONE]\n\n"
    )
    provider = _openai(
        lambda r: httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
    )
    chunks = [
        c async for c in provider.stream(ModelRequest(model="m", messages=[Message.user("x")]))
    ]
    assert chunks == ["Hel", "lo"]


def test_missing_api_key_is_a_configuration_error(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        create_provider("openai")


def test_ollama_needs_no_key() -> None:
    p = create_provider("ollama")
    assert p.name == "ollama"


async def test_anthropic_translation() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["headers"] = request.headers
        return httpx.Response(
            200,
            json={
                "model": "claude-x",
                "content": [
                    {"type": "text", "text": "ok "},
                    {"type": "tool_use", "id": "tu1", "name": "calc", "input": {"e": "2"}},
                ],
                "usage": {"input_tokens": 5, "output_tokens": 3},
                "stop_reason": "tool_use",
            },
        )

    p = AnthropicProvider(api_key="k", transport=httpx.MockTransport(handler))
    req = ModelRequest(
        model="claude-x",
        messages=[
            Message.system("s1"),
            Message.system("s2"),
            Message.user("u"),
            Message.assistant(
                "thinking",
                [
                    ToolCall(id="a", name="calc", arguments={}),
                    ToolCall(id="b", name="calc", arguments={}),
                ],
            ),
            Message.tool("r1", tool_call_id="a", name="calc"),
            Message.tool("r2", tool_call_id="b", name="calc"),
        ],
        tools=[ToolSpec(name="calc", description="d", parameters={"type": "object"})],
    )
    resp = await p.complete(req)
    body = seen["body"]
    assert seen["headers"]["x-api-key"] == "k" and seen["headers"]["anthropic-version"]
    assert body["system"] == "s1\n\ns2"
    assert body["max_tokens"] == 4096
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in body["messages"][2]["content"]] == ["a", "b"]
    assert body["tools"][0]["input_schema"] == {"type": "object"}
    assert (
        resp.content == "ok " and resp.tool_calls[0].name == "calc" and resp.usage.input_tokens == 5
    )


# -- Model --------------------------------------------------------------------------


def test_parse_model_spec_keeps_colons_in_model_name() -> None:
    assert parse_model_spec("ollama:llama3.1:8b") == ("ollama", "llama3.1:8b")
    with pytest.raises(ConfigurationError):
        parse_model_spec("gpt-4o")


class Flaky(ScriptedProvider):
    def __init__(self, errors: list[Exception]) -> None:
        super().__init__(lambda r: "ok")
        self.errors = errors

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if self.errors:
            self.requests.append(request)
            raise self.errors.pop(0)
        return await super().complete(request)


async def test_retries_retryable_errors(monkeypatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    p = Flaky([RateLimitError("slow down"), ProviderError("5xx", retryable=True)])
    resp = await Model(provider=p, model="m", max_retries=3).complete([Message.user("x")])
    assert resp.content == "ok" and len(p.requests) == 3


async def test_does_not_retry_auth_errors(monkeypatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    p = Flaky([AuthenticationError("bad key")])
    with pytest.raises(AuthenticationError):
        await Model(provider=p, model="m", max_retries=3).complete([Message.user("x")])
    assert len(p.requests) == 1


async def test_timeout_is_enforced() -> None:
    class Slow(ScriptedProvider):
        async def complete(self, request):
            await asyncio.sleep(1)
            return await super().complete(request)

    from adversi.errors import ProviderTimeoutError

    with pytest.raises(ProviderTimeoutError):
        await Model(
            provider=Slow(lambda r: "x"), model="m", timeout_s=0.01, max_retries=0
        ).complete([Message.user("x")])


async def test_cache_returns_identical_response_without_calling_provider() -> None:
    p = ScriptedProvider(lambda r: "answer")
    m = Model(provider=p, model="m", cache=MemoryCache())
    a = await m.complete([Message.user("x")], metadata={"agent": "1"})
    b = await m.complete(
        [Message.user("x")], metadata={"agent": "2"}
    )  # metadata is not part of the key
    c = await m.complete([Message.user("y")])
    assert len(p.requests) == 2 and b.cached and not a.cached and c.content == "answer"


async def test_usage_cost_and_budget() -> None:
    tracker = UsageTracker(Budget(max_model_calls=2))
    token = set_tracker(tracker)
    try:
        m = Model(
            provider=ScriptedProvider(lambda r: "x" * 400),
            model="m",
            price=Price(input_per_mtok=1.0, output_per_mtok=2.0),
        )
        await m.complete([Message.user("y" * 4000)])
        await m.complete([Message.user("y" * 4000)])
        with pytest.raises(BudgetExceededError):
            await m.complete([Message.user("y")])
    finally:
        reset_tracker(token)
    total = tracker.total()
    assert total.calls == 2
    assert total.input_tokens == 2000 and total.output_tokens == 200
    assert total.cost_usd == pytest.approx((2000 * 1 + 200 * 2) / 1e6)


def test_with_settings_rejects_unknown() -> None:
    m = Model(provider=ScriptedProvider(lambda r: ""), model="m")
    assert m.with_settings(temperature=0.0).temperature == 0.0
    with pytest.raises(TypeError):
        m.with_settings(tempurature=1)


async def _no_sleep(_: float) -> None:
    return None
