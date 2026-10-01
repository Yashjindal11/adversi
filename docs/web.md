# Web application

```bash
pip install "adversi[server]"
adversi serve --model openai:gpt-4o-mini       # http://127.0.0.1:8765
```

The server is a thin FastAPI adapter over the public API. The UI is a React +
TypeScript single-page app (Vite, no UI framework dependency) bundled into the Python
package at release time.

## What the UI shows

| Tab | Content |
|---|---|
| Synthesis | Answer, summary, established / disputed / uncertain / rejected claims, caveats, recommendations |
| Claims | Claim graph (evidence -> claims <- challenges, assumptions) with hover tracing and details; claim table with policy notes |
| Evidence | Excerpts with provenance, verified vs model-knowledge labels, reliability, rejected citations |
| Perspectives | Each agent's verdict, position, reasoning summary, counterarguments, uncertainties |
| Debate | Debate turns; cross-examination challenges, rebuttals and outcomes |
| Critique | Process critique findings and the judge's overall assessment |
| Uncertainty | All uncertainty signals with explanations; open questions |
| Run | Run id, mode, profile, usage, cost, duration, agents and models, steps, errors |

Raw chain-of-thought is never requested or displayed. "Open result JSON" renders any saved
result without a server.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness and version |
| GET | `/api/meta` | Modes, profiles, steps, tools, providers and whether credentials are set |
| POST | `/api/runs` | Start a run: `{question, context?, mode, profile, model?, models?, tools?, documents?}` -> 202 + run summary |
| GET | `/api/runs` | Run summaries, newest first |
| GET | `/api/runs/{id}` | Summary + result (without trace) |
| GET | `/api/runs/{id}/events?after=N` | Events after sequence N (polling) |
| WS | `/api/runs/{id}/stream` | Replays past events, streams new ones, then `{"type": "end"}` |

OpenAPI docs are at `/api/docs`.

## Limits and security

- Binds to `127.0.0.1`. **No authentication**: put it behind an authenticating proxy
  before exposing it.
- Question <= 4,000 chars, context <= 20,000, <= 10 documents of <= 200,000 chars each.
- Tools requested by a client must be in the server config's tool list.
- At most 2 concurrent runs by default; up to 200 runs kept in memory.
- Provider credentials come from the server's environment; clients cannot pass keys or
  base URLs.

## Development

```bash
python scripts/demo_server.py   # scripted backend on :8765, no API keys
cd web && npm install && npm run dev   # http://127.0.0.1:5173, proxies /api
npm run build                          # writes src/adversi/server/static
```
