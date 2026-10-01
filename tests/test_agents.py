from __future__ import annotations

import pytest

from adversi.agents import Agent, Role
from adversi.agents.outputs import AnalysisDraft
from adversi.errors import StructuredOutputError
from adversi.models import Model, extract_json
from adversi.observability.events import EventBus, EventType
from adversi.observability.usage import UsageTracker
from adversi.orchestration import ModelMap, RunContext
from adversi.providers import ModelResponse, ProviderCapabilities, ToolCall
from adversi.testing import ScriptedProvider
from adversi.tools import calculator_tool


def test_extract_json_variants() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Here you go:\n```json\n{"a": "}"}\n```') == {"a": "}"}
    assert extract_json('prefix {"a": {"b": [1, 2]}} suffix') == {"a": {"b": [1, 2]}}
    with pytest.raises(StructuredOutputError):
        extract_json("no json at all")


def _ctx(provider: ScriptedProvider, **kw) -> RunContext:
    return RunContext(
        run_id="r",
        question="q",
        models=ModelMap(Model(provider=provider, model="m", max_retries=0)),
        events=EventBus("r"),
        usage=UsageTracker(),
        **kw,
    )


VALID = {"verdict": "yes", "position": "p", "summary": "s", "confidence": 0.6}


async def test_agent_repairs_invalid_output_once() -> None:
    replies = iter(["not json", VALID])
    provider = ScriptedProvider(lambda r: next(replies))
    out = await Agent("analyst").respond(_ctx(provider), step="s", task="t", schema=AnalysisDraft)
    assert out.verdict == "yes"
    assert "invalid" in provider.requests[1].messages[-1].content


async def test_agent_tool_loop_records_sources_and_events() -> None:
    def handler(req):
        if not any(m.role == "tool" for m in req.messages):
            return ModelResponse(
                content="",
                tool_calls=[
                    ToolCall(id="t1", name="calculator", arguments={"expression": "365*24"})
                ],
                model="m",
                provider="scripted",
            )
        tool_msg = next(m for m in req.messages if m.role == "tool")
        assert "8760" in tool_msg.content and "S1" in tool_msg.content
        return {
            **VALID,
            "claims": [
                {
                    "statement": "A year has 8760 hours",
                    "citations": [{"source_id": "S1", "excerpt": "365*24 = 8760"}],
                }
            ],
        }

    provider = ScriptedProvider(handler)
    ctx = _ctx(provider, tools=[calculator_tool()])
    agent = Agent("statistician")
    draft = await agent.respond(ctx, step="s", task="t", schema=AnalysisDraft)
    ids = ctx.ingest_claims(draft.claims, agent=agent, step="s")
    evidence = ctx.evidence.for_claim(ids[0])
    assert evidence and evidence[0].is_external
    assert evidence[0].provenance.tool_name == "calculator"
    types = [e.type for e in ctx.events.history]
    assert EventType.TOOL_CALL in types and EventType.TOOL_RESULT in types
    assert provider.requests[0].tools[0].name == "calculator"


async def test_tool_steps_are_bounded() -> None:
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if req.tools:
            return ModelResponse(
                content="",
                tool_calls=[
                    ToolCall(id=str(calls["n"]), name="calculator", arguments={"expression": "1+1"})
                ],
                model="m",
                provider="x",
            )
        return VALID

    ctx = _ctx(ScriptedProvider(handler), tools=[calculator_tool()])
    await Agent("analyst", max_tool_steps=2).respond(ctx, step="s", task="t", schema=AnalysisDraft)
    assert calls["n"] == 3  # 2 tool rounds + forced final answer without tools


async def test_tools_dropped_for_providers_without_tool_calling() -> None:
    provider = ScriptedProvider(
        lambda r: VALID, capabilities=ProviderCapabilities(tool_calling=False)
    )
    ctx = _ctx(provider, tools=[calculator_tool()])
    await Agent("analyst").respond(ctx, step="s", task="t", schema=AnalysisDraft)
    assert provider.requests[0].tools == []
    assert any(e.type == EventType.WARNING for e in ctx.events.history)


def test_non_tool_roles_do_not_receive_run_tools() -> None:
    ctx = _ctx(ScriptedProvider(lambda r: VALID), tools=[calculator_tool()])
    assert ctx.tools_for(Agent("judge")) == []
    assert [t.name for t in ctx.tools_for(Agent("researcher"))] == ["calculator"]


def test_custom_role_prompt_contains_instructions_and_schema() -> None:
    role = Role("safety_officer", "Check FAA regulatory compliance.")
    prompt = Agent(role, instructions="Be terse.").system_prompt(
        AnalysisDraft, tools_available=False
    )
    assert "Check FAA regulatory compliance." in prompt and "Be terse." in prompt
    assert '"verdict"' in prompt and "Never invent sources" in prompt
