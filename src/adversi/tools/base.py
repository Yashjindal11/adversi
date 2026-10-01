"""Tool abstraction.

A tool is a validated, timeout-bounded function an agent may call. Tools that
retrieve information declare a ``source_type``; their outputs are then recorded as
:class:`~adversi.protocol.Source` objects that agents can cite as evidence.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Awaitable, Callable
from typing import Any, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from adversi.errors import ConfigurationError, ToolError
from adversi.protocol.evidence import SourceType
from adversi.providers.base import ToolSpec

_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SourceDraft(BaseModel):
    """Material a tool retrieved that should become a citable Source."""

    content: str
    source_type: SourceType
    uri: str | None = None
    title: str | None = None


class ToolOutput(BaseModel):
    """Rich return value for tools. Plain strings / JSON-able values are also accepted."""

    content: str
    sources: list[SourceDraft] = Field(default_factory=list)
    data: Any = None


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        function: Callable[..., Any] | Callable[..., Awaitable[Any]],
        *,
        parameters: type[BaseModel] | None = None,
        source_type: SourceType | None = None,
        timeout_s: float = 30.0,
        max_output_chars: int = 20_000,
    ) -> None:
        if not _NAME.match(name):
            raise ConfigurationError(f"invalid tool name {name!r}: use [A-Za-z0-9_-], max 64 chars")
        self.name = name
        self.description = description
        self.function = function
        self.args_model = parameters or _model_from_signature(name, function)
        self.source_type = source_type
        self.timeout_s = timeout_s
        self.max_output_chars = max_output_chars

    def __repr__(self) -> str:
        return f"Tool({self.name!r})"

    @property
    def spec(self) -> ToolSpec:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return ToolSpec(name=self.name, description=self.description, parameters=schema)

    def validate_arguments(self, arguments: dict[str, Any]) -> BaseModel:
        try:
            return self.args_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolError(
                f"invalid arguments for {self.name}: {exc.errors(include_url=False)}"
            ) from exc

    async def invoke(self, arguments: dict[str, Any]) -> Any:
        validated = self.validate_arguments(arguments)
        kwargs = {k: getattr(validated, k) for k in type(validated).model_fields}
        coro: Awaitable[Any]
        if inspect.iscoroutinefunction(self.function):
            coro = self.function(**kwargs)
        else:
            # Note: a timed-out sync function keeps running in its worker thread.
            coro = asyncio.to_thread(self.function, **kwargs)
        return await asyncio.wait_for(coro, self.timeout_s)


def _model_from_signature(name: str, fn: Callable[..., Any]) -> type[BaseModel]:
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    fields: dict[str, Any] = {}
    for pname, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            raise ConfigurationError(f"tool {name}: *args/**kwargs are not supported")
        annotation = hints.get(pname, Any)
        default = param.default if param.default is not inspect.Parameter.empty else ...
        fields[pname] = (annotation, default)
    model: type[BaseModel] = create_model(
        f"{name}_args", __config__=ConfigDict(extra="forbid"), **fields
    )
    return model


def tool(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    source_type: SourceType | None = None,
    timeout_s: float = 30.0,
) -> Any:
    """Decorator turning a typed function into a :class:`Tool`.

    The docstring becomes the description; the signature becomes the JSON schema.
    """

    def wrap(f: Callable[..., Any]) -> Tool:
        return Tool(
            name or f.__name__,
            description or inspect.getdoc(f) or f.__name__,
            f,
            source_type=source_type,
            timeout_s=timeout_s,
        )

    return wrap(fn) if fn is not None else wrap
