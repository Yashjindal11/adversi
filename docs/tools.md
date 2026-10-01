# Tools

## Defining tools

```python
from adversi import Tool, ToolOutput, SourceType, tool

@tool
def convert(amount: float, rate: float = 1.0) -> str:
    """Convert an amount at a given rate."""
    return f"{amount * rate:.2f}"

lookup = Tool(
    "fleet_lookup",
    "Look up aircraft by tail number.",
    my_function,                # sync or async
    source_type=SourceType.DATABASE,   # results become citable sources
    timeout_s=10,
    max_output_chars=10_000,
)
```

- The JSON schema is derived from type hints (or pass a Pydantic model as
  `parameters=`). Unknown arguments are rejected.
- Tool names: `[A-Za-z0-9_-]{1,64}`.
- Exceptions, validation errors and timeouts are returned to the model as
  `ERROR: ...` tool results and recorded as `tool.result` events; they do not crash runs.
- Sync functions run in a worker thread. A timed-out sync function cannot be cancelled
  and keeps running; prefer async for network I/O.

### Producing evidence

A tool's output becomes a citable `Source` when either:

- the tool declares `source_type=...` (the whole output is one source), or
- it returns `ToolOutput(content=..., sources=[SourceDraft(...), ...])` for multiple
  sources (e.g. search results), each with its own URI and title.

The tool result shown to the model is prefixed with the new source ids (`S4`, `S5`), and
agents cite those ids with verbatim excerpts.

## Built-in tools

| Name | Source type | Notes |
|---|---|---|
| `calculator` | `calculation` | AST whitelist: arithmetic, `pi`, `e`, common math functions; bounded exponent and magnitude; no `eval` |
| `fetch_url` | `web` | http(s) only; refuses private/loopback/link-local/reserved hosts on every redirect; 2 MB cap; text/HTML/JSON only; HTML reduced to text |
| `web_search` | `web_search_snippet` per hit | Pluggable `SearchBackend`; `BraveSearchBackend` (needs `BRAVE_API_KEY`) and `StaticSearchBackend` for tests |
| `search_documents` | (existing `user_provided` sources) | BM25 over chunks of user documents; added automatically when documents are too long to inline |

Snippets are weak evidence by design: they get their own source type so researchers and
evidence analysts can discount them, and the researcher is instructed to fetch pages.

## Which agents get tools

Tools passed to `AdverSI(tools=...)` / `Workflow(tools=...)` are *run tools*. Roles with
`uses_tools=True` (analyst, statistician, domain expert, researcher) receive them;
others (judge, critic, skeptic, ...) do not, so evaluators cannot go fetch new material
mid-judgment. Override per agent with `Agent(..., tools=[...], use_run_tools=False)`.

## Registering tools by name

```python
from adversi.tools import register_tool
register_tool("fleet_lookup", lambda **opts: lookup)
```

Registered names can be used in `adversi.toml` (`tools = ["fleet_lookup"]`) and on the
CLI (`--tool fleet_lookup`).

## Python execution

There is intentionally no Python execution tool in the core. Running model-written code
safely requires real isolation (container, gVisor, Firecracker, a remote sandbox
service). Wrap such a service as a normal `Tool`.
