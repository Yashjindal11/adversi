from __future__ import annotations

import asyncio

import httpx
import pytest

from adversi.errors import ToolError
from adversi.protocol import SourceType
from adversi.providers.base import ToolCall
from adversi.tools import (
    SearchHit,
    StaticSearchBackend,
    Tool,
    ToolExecutor,
    ToolOutput,
    calculator_tool,
    tool,
    web_search_tool,
)
from adversi.tools.calculator import evaluate
from adversi.tools.documents import DocumentIndex
from adversi.tools.web import assert_public_url, fetch_text, html_to_text


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("2 + 3 * 4", 14),
        ("(1 + 1) ** 10", 1024),
        ("sqrt(16) + abs(-2)", 6.0),
        ("round(pi, 2)", 3.14),
        ("7 // 2 + 7 % 2", 4),
    ],
)
def test_calculator_evaluates(expr: str, expected: float) -> None:
    assert evaluate(expr) == expected


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os')",
        "().__class__",
        "open('x')",
        "9 ** 9 ** 9",
        "10 ** 400",
        "[1, 2]",
        "x + 1",
        "1 / 0",
        "a" * 600,
    ],
)
def test_calculator_rejects_unsafe_or_unbounded(expr: str) -> None:
    with pytest.raises(ToolError):
        evaluate(expr)


def test_tool_schema_from_signature_and_validation() -> None:
    @tool
    def lookup(code: str, limit: int = 5) -> str:
        """Look up an airport code."""
        return f"{code}:{limit}"

    assert isinstance(lookup, Tool)
    assert lookup.description == "Look up an airport code."
    params = lookup.spec.parameters
    assert params["required"] == ["code"]
    assert params["properties"]["limit"]["default"] == 5
    with pytest.raises(ToolError):
        lookup.validate_arguments({"code": "ORD", "unexpected": 1})
    with pytest.raises(ToolError):
        lookup.validate_arguments({"limit": 3})


def test_invalid_tool_name() -> None:
    from adversi.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        Tool("bad name!", "d", lambda: "x")


async def test_executor_reports_errors_instead_of_raising() -> None:
    async def slow() -> str:
        await asyncio.sleep(1)
        return "late"

    def boom() -> str:
        raise RuntimeError("kaput")

    ex = ToolExecutor([Tool("slow", "s", slow, timeout_s=0.01), Tool("boom", "b", boom)])
    r1 = await ex.execute(ToolCall(id="1", name="slow"))
    r2 = await ex.execute(ToolCall(id="2", name="boom"))
    r3 = await ex.execute(ToolCall(id="3", name="missing"))
    r4 = await ex.execute(ToolCall(id="4", name="boom", arguments={"x": 1}))
    assert not r1.ok and "timed out" in (r1.error or "")
    assert not r2.ok and "kaput" in (r2.error or "")
    assert not r3.ok and "unknown tool" in (r3.error or "")
    assert not r4.ok and "invalid arguments" in (r4.error or "")


async def test_executor_records_sources_and_truncates() -> None:
    recorded = []

    def recorder(draft, tool_name, args, agent):
        from adversi.evidence import EvidenceStore

        recorded.append((draft.source_type, tool_name, args, agent))
        return EvidenceStore().add_source(draft.content, source_type=draft.source_type)

    calc = calculator_tool()
    big = Tool("big", "b", lambda: ToolOutput(content="x" * 100), max_output_chars=10)
    ex = ToolExecutor([calc, big], record_source=recorder, agent="stat")
    r = await ex.execute(ToolCall(id="1", name="calculator", arguments={"expression": "6*7"}))
    assert r.ok and "42" in r.output and r.source_ids == ["S1"]
    assert recorded == [(SourceType.CALCULATION, "calculator", {"expression": "6*7"}, "stat")]
    r = await ex.execute(ToolCall(id="2", name="big"))
    assert r.output.endswith("[output truncated]")


async def test_web_search_records_snippets_as_weak_sources() -> None:
    backend = StaticSearchBackend(
        [SearchHit(title="T", url="https://e.org/a", snippet="snippet text")]
    )
    out = await web_search_tool(backend).invoke({"query": "q"})
    assert out.sources[0].source_type == SourceType.WEB_SEARCH_SNIPPET
    assert out.sources[0].uri == "https://e.org/a"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:8080/x",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest",
        "file:///etc/passwd",
        "ftp://example.com",
    ],
)
async def test_ssrf_guard_blocks_non_public_targets(url: str) -> None:
    with pytest.raises(ToolError):
        await assert_public_url(url)


async def test_fetch_follows_redirects_and_extracts_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/page"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><head><title>Hi</title><script>evil()</script></head><body><p>Hello <b>world</b></p></body></html>",
        )

    text, title, final = await fetch_text(
        "http://example.test/start", allow_private=True, transport=httpx.MockTransport(handler)
    )
    assert title == "Hi" and final.endswith("/page")
    assert "Hello world" in text and "evil" not in text


async def test_fetch_rejects_binary_content() -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")
    )
    with pytest.raises(ToolError):
        await fetch_text("http://example.test/x.pdf", allow_private=True, transport=transport)


def test_html_to_text_ignores_style() -> None:
    text, _ = html_to_text("<style>p{color:red}</style><div>A</div><div>B</div>")
    assert text == "A\nB"


def test_bm25_ranks_relevant_chunk_first() -> None:
    idx = DocumentIndex(chunk_chars=60, overlap=0)
    idx.add("S1", "Crew scheduling rules limit duty time for pilots. " * 2)
    idx.add("S2", "Weather delays at hub airports increase in winter months.")
    hits = idx.search("winter weather delays")
    assert hits and hits[0][1].source_id == "S2"
