"""Adapter for the OpenAI Chat Completions wire format.

One adapter covers OpenAI and every server that speaks the same protocol: Ollama,
vLLM, LM Studio, llama.cpp server, Hugging Face TGI / Inference Router, Google
Gemini's OpenAI-compatible endpoint, and many hosted gateways.
"""

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


class OpenAICompatibleProvider(ModelProvider):
    def __init__(
        self,
        *,
        name: str = "openai_compatible",
        base_url: str,
        api_key: str | None = None,
        api_key_env: str | None = None,
        require_api_key: bool = True,
        headers: dict[str, str] | None = None,
        timeout_s: float = 120.0,
        capabilities: ProviderCapabilities | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        key = resolve_api_key(name, api_key, api_key_env, required=require_api_key)
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        if key:
            all_headers["Authorization"] = f"Bearer {key}"
        self.capabilities = capabilities or ProviderCapabilities(
            tool_calling=True, json_mode=True, json_schema=True, streaming=True
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=all_headers,
            timeout=httpx.Timeout(timeout_s),
            transport=transport,
        )

    # -- translation -------------------------------------------------------------

    @staticmethod
    def _message(m: Message) -> dict[str, Any]:
        if m.role == "tool":
            return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
        out: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in m.tool_calls
            ]
        return out

    def build_payload(self, request: ModelRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [self._message(m) for m in request.messages],
        }
        for key in ("temperature", "max_tokens", "top_p", "seed", "stop"):
            value = getattr(request, key)
            if value is not None:
                payload[key] = value
        if request.tools and self.capabilities.tool_calling:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in request.tools
            ]
        if request.response_schema is not None:
            if self.capabilities.json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.response_schema_name or "response",
                        "schema": request.response_schema,
                        "strict": False,
                    },
                }
            elif self.capabilities.json_mode:
                payload["response_format"] = {"type": "json_object"}
        if stream:
            payload["stream"] = True
        payload.update(request.extra)
        return payload

    def parse_response(self, data: dict[str, Any], *, latency_s: float) -> ModelResponse:
        choices = data.get("choices") or [{}]
        msg = choices[0].get("message") or {}
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {"__invalid_json__": raw_args}
            tool_calls.append(
                ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args)
            )
        usage = data.get("usage") or {}
        return ModelResponse(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            usage=TokenUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
            model=data.get("model") or "",
            provider=self.name,
            finish_reason=choices[0].get("finish_reason"),
            latency_s=latency_s,
        )

    # -- calls -------------------------------------------------------------------

    async def complete(self, request: ModelRequest) -> ModelResponse:
        start = time.perf_counter()
        try:
            response = await self._client.post(
                "/chat/completions", json=self.build_payload(request)
            )
        except httpx.HTTPError as exc:
            raise translate_transport_error(self.name, exc) from exc
        raise_for_status(self.name, response)
        return self.parse_response(response.json(), latency_s=time.perf_counter() - start)

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        payload = self.build_payload(request, stream=True)
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                if not response.is_success:
                    await response.aread()
                    raise_for_status(self.name, response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    choices = json.loads(chunk).get("choices") or []
                    if choices:
                        delta = (choices[0].get("delta") or {}).get("content")
                        if delta:
                            yield delta
        except httpx.HTTPError as exc:
            raise translate_transport_error(self.name, exc) from exc

    async def aclose(self) -> None:
        await self._client.aclose()
