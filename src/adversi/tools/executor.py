"""Executes tool calls with validation, timeouts, output limits and source capture."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel

from adversi.errors import ToolError
from adversi.protocol.evidence import Source
from adversi.providers.base import ToolCall
from adversi.tools.base import SourceDraft, Tool, ToolOutput


class ToolResult(BaseModel):
    call_id: str
    tool: str
    arguments: dict[str, Any]
    ok: bool
    output: str
    error: str | None = None
    source_ids: list[str] = []
    latency_s: float = 0.0


SourceRecorder = Callable[[SourceDraft, str, dict[str, Any], str], Source]
"""(draft, tool_name, arguments, agent) -> registered Source"""


class ToolExecutor:
    def __init__(
        self,
        tools: Sequence[Tool],
        *,
        record_source: SourceRecorder | None = None,
        agent: str = "",
    ) -> None:
        self.tools = {t.name: t for t in tools}
        self.record_source = record_source
        self.agent = agent

    async def execute(self, call: ToolCall) -> ToolResult:
        start = time.perf_counter()
        tool = self.tools.get(call.name)
        if tool is None:
            return self._error(call, f"unknown tool '{call.name}'", start)
        try:
            raw = await tool.invoke(call.arguments)
        except TimeoutError:
            return self._error(call, f"tool timed out after {tool.timeout_s}s", start)
        except ToolError as exc:
            return self._error(call, str(exc), start)
        except Exception as exc:  # tool bugs are reported to the model, not raised
            return self._error(call, f"{type(exc).__name__}: {exc}", start)

        output = _coerce_output(raw)
        drafts = list(output.sources)
        if not drafts and tool.source_type is not None:
            drafts.append(SourceDraft(content=output.content, source_type=tool.source_type))
        source_ids: list[str] = []
        if self.record_source:
            for draft in drafts:
                source_ids.append(
                    self.record_source(draft, tool.name, call.arguments, self.agent).id
                )
        text = output.content
        if len(text) > tool.max_output_chars:
            text = text[: tool.max_output_chars] + "\n[output truncated]"
        if source_ids:
            text = f"[recorded as source(s): {', '.join(source_ids)}]\n{text}"
        return ToolResult(
            call_id=call.id,
            tool=call.name,
            arguments=call.arguments,
            ok=True,
            output=text,
            source_ids=source_ids,
            latency_s=time.perf_counter() - start,
        )

    @staticmethod
    def _error(call: ToolCall, message: str, start: float) -> ToolResult:
        return ToolResult(
            call_id=call.id,
            tool=call.name,
            arguments=call.arguments,
            ok=False,
            output=f"ERROR: {message}",
            error=message,
            latency_s=time.perf_counter() - start,
        )


def _coerce_output(raw: Any) -> ToolOutput:
    if isinstance(raw, ToolOutput):
        return raw
    if isinstance(raw, str):
        return ToolOutput(content=raw)
    if isinstance(raw, BaseModel):
        return ToolOutput(content=raw.model_dump_json(), data=raw)
    try:
        return ToolOutput(content=json.dumps(raw, default=str), data=raw)
    except (TypeError, ValueError):
        return ToolOutput(content=str(raw))
