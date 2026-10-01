"""Provider-neutral request/response types and the ``ModelProvider`` interface.

Providers translate these types to and from a vendor API. Nothing above this layer
knows which vendor is in use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from adversi.protocol.outcome import TokenUsage


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str, tool_calls: list[ToolCall] | None = None) -> Message:
        return cls(role="assistant", content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool(cls, content: str, *, tool_call_id: str, name: str) -> Message:
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class ModelRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model: str
    messages: list[Message]
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    seed: int | None = None
    stop: list[str] | None = None
    tools: list[ToolSpec] = Field(default_factory=list)
    response_schema: dict[str, Any] | None = None
    response_schema_name: str | None = None
    extra: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific body parameters, passed through."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Local tracing info (agent, step). Never sent."
    )


class ModelResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    model: str
    provider: str
    finish_reason: str | None = None
    latency_s: float = 0.0
    cached: bool = False


class ProviderCapabilities(BaseModel):
    tool_calling: bool = False
    json_mode: bool = False
    json_schema: bool = False
    streaming: bool = False


class ModelProvider(ABC):
    """Interface every model backend implements.

    Implementations must be safe to call concurrently from one event loop and must
    raise :class:`adversi.errors.ProviderError` subclasses with an accurate
    ``retryable`` flag; retries, timeouts, caching and accounting are handled by
    :class:`adversi.models.Model`, not by providers.
    """

    name: str = "custom"
    capabilities: ProviderCapabilities = ProviderCapabilities()

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse: ...

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """Yield text deltas. Default: a single chunk from :meth:`complete`."""
        response = await self.complete(request)
        yield response.content

    async def aclose(self) -> None:
        return None
