"""Test utilities: deterministic providers for unit tests and offline workflow development."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from adversi.models.model import Model
from adversi.protocol.outcome import TokenUsage
from adversi.providers.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
)

Handler = Callable[[ModelRequest], "str | dict[str, Any] | ModelResponse"]


class ScriptedProvider(ModelProvider):
    """Answers every request with ``handler(request)``.

    The handler can branch on ``request.metadata`` (``agent``, ``role``, ``step``,
    ``schema``) to script a full workflow. All requests are kept in ``requests``.
    Token usage is approximated as characters / 4 so budget logic is exercisable.
    """

    def __init__(
        self,
        handler: Handler,
        *,
        name: str = "scripted",
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        self.name = name
        self.handler = handler
        self.capabilities = capabilities or ProviderCapabilities(
            tool_calling=True, json_mode=True, json_schema=True
        )
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        out = self.handler(request)
        if isinstance(out, ModelResponse):
            return out
        content = out if isinstance(out, str) else json.dumps(out)
        prompt_chars = sum(len(m.content) for m in request.messages)
        return ModelResponse(
            content=content,
            usage=TokenUsage(input_tokens=prompt_chars // 4, output_tokens=len(content) // 4),
            model=request.model,
            provider=self.name,
            finish_reason="stop",
        )


def scripted_model(handler: Handler, *, model: str = "scripted", **kwargs: Any) -> Model:
    kwargs.setdefault("max_retries", 0)
    return Model(provider=ScriptedProvider(handler), model=model, **kwargs)
