"""Adapter for the Anthropic Messages API."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from adversi.protocol.outcome import TokenUsage
from adversi.providers._http import raise_for_status, resolve_api_key, translate_transport_error
from adversi.providers.base import (
    Message,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ToolCall,
)

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider(ModelProvider):
    def __init__(
        self,
        *,
        name: str = "anthropic",
        base_url: str = "https://api.anthropic.com",
        api_key: str | None = None,
        api_key_env: str | None = "ANTHROPIC_API_KEY",
        headers: dict[str, str] | None = None,
        timeout_s: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        key = resolve_api_key(name, api_key, api_key_env, required=True)
        assert key is not None
        # Structured output is enforced by prompt + validation, so json_schema is False.
        self.capabilities = ProviderCapabilities(tool_calling=True, streaming=True)
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "x-api-key": key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
                **(headers or {}),
            },
            timeout=httpx.Timeout(timeout_s),
            transport=transport,
        )

    @staticmethod
    def _convert_messages(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
                continue
            if m.role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                # Consecutive tool results must share a single user turn.
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
                continue
            if m.role == "assistant" and m.tool_calls:
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                blocks.extend(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                    for tc in m.tool_calls
                )
                out.append({"role": "assistant", "content": blocks})
                continue
            out.append({"role": m.role, "content": m.content})
        return "\n\n".join(system_parts), out

    def build_payload(self, request: ModelRequest, *, stream: bool = False) -> dict[str, Any]:
        system, messages = self._convert_messages(request.messages)
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
        }
        if system:
            payload["system"] = system
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop_sequences"] = request.stop
        if request.tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in request.tools
            ]
        if stream:
            payload["stream"] = True
        payload.update(request.extra)
        return payload

    def parse_response(self, data: dict[str, Any], *, latency_s: float) -> ModelResponse:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(id=block["id"], name=block["name"], arguments=block.get("input") or {})
                )
        usage = data.get("usage") or {}
        return ModelResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            usage=TokenUsage(
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            ),
            model=data.get("model") or "",
            provider=self.name,
            finish_reason=data.get("stop_reason"),
            latency_s=latency_s,
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        start = time.perf_counter()
        try:
            response = await self._client.post("/v1/messages", json=self.build_payload(request))
        except httpx.HTTPError as exc:
            raise translate_transport_error(self.name, exc) from exc
        raise_for_status(self.name, response)
        return self.parse_response(response.json(), latency_s=time.perf_counter() - start)

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        payload = self.build_payload(request, stream=True)
        try:
            async with self._client.stream("POST", "/v1/messages", json=payload) as response:
                if not response.is_success:
                    await response.aread()
                    raise_for_status(self.name, response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:].strip())
                    if event.get("type") == "content_block_delta":
                        text = (event.get("delta") or {}).get("text")
                        if text:
                            yield text
        except httpx.HTTPError as exc:
            raise translate_transport_error(self.name, exc) from exc

    async def aclose(self) -> None:
        await self._client.aclose()
