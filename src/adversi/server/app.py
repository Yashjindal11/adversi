"""FastAPI application exposing AdverSI runs over REST + WebSocket.

The server is a thin adapter over the public Python API; the core library does not
import it. It has no authentication and binds to localhost by default.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from adversi._version import __version__
from adversi.config.loader import ConfigBuilder, load_config
from adversi.config.schema import ModelConfig
from adversi.observability.events import Event
from adversi.protocol.result import AdverSIResult
from adversi.providers.registry import available_providers
from adversi.tools.documents import Document
from adversi.tools.registry import available_tools
from adversi.workflows.base import Workflow
from adversi.workflows.presets import MODES, PROFILES, STEP_BUILDERS

STATIC_DIR = Path(__file__).parent / "static"


class DocumentIn(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    content: str = Field(max_length=200_000)


class RunRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    context: str | None = Field(default=None, max_length=20_000)
    mode: str = "research"
    profile: Literal["fast", "balanced", "deep"] = "fast"
    model: str | None = Field(default=None, max_length=200)
    models: dict[str, str] = Field(default_factory=dict)
    tools: list[str] | None = None
    documents: list[DocumentIn] = Field(default_factory=list, max_length=10)


class RunSummary(BaseModel):
    run_id: str
    question: str
    mode: str
    status: Literal["queued", "running", "completed", "partial", "failed"]
    created_at: datetime
    error: str | None = None


class RunState:
    def __init__(self, run_id: str, request: RunRequest) -> None:
        self.run_id = run_id
        self.request = request
        self.status: str = "queued"
        self.created_at = datetime.now(UTC)
        self.events: list[dict[str, Any]] = []
        self.result: AdverSIResult | None = None
        self.error: str | None = None
        self.subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()
        self.task: asyncio.Task[None] | None = None

    def summary(self) -> RunSummary:
        return RunSummary(
            run_id=self.run_id,
            question=self.request.question,
            mode=self.request.mode,
            status=self.status,
            created_at=self.created_at,
            error=self.error,
        )

    def publish(self, message: dict[str, Any] | None) -> None:
        for q in list(self.subscribers):
            q.put_nowait(message)


WorkflowFactory = Callable[[RunRequest], Workflow]


def default_workflow_factory(config_path: str | None, default_model: str | None) -> WorkflowFactory:
    base = load_config(config_path)

    def factory(req: RunRequest) -> Workflow:
        cfg = base.model_copy(deep=True)
        if req.tools is not None:
            allowed = {t.name for t in base.tools}
            disallowed = set(req.tools) - allowed
            if disallowed:
                raise HTTPException(400, f"tools not enabled on this server: {sorted(disallowed)}")
            cfg.tools = [t for t in base.tools if t.name in req.tools]
        for role, spec in req.models.items():
            cfg.models[role] = cfg.models[spec] if spec in cfg.models else ModelConfig(model=spec)
        return ConfigBuilder(cfg).workflow(
            default_model=req.model or default_model, mode=req.mode, profile=req.profile
        )

    return factory


def create_app(
    *,
    config_path: str | None = None,
    default_model: str | None = None,
    workflow_factory: WorkflowFactory | None = None,
    static_dir: Path | None = STATIC_DIR,
    max_concurrent_runs: int = 2,
    max_stored_runs: int = 200,
) -> FastAPI:
    app = FastAPI(
        title="AdverSI", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    factory = workflow_factory or default_workflow_factory(config_path, default_model)
    runs: dict[str, RunState] = {}
    gate = asyncio.Semaphore(max_concurrent_runs)

    async def execute(state: RunState, workflow: Workflow) -> None:
        def on_event(event: Event) -> None:
            payload = event.model_dump(mode="json")
            state.events.append(payload)
            state.publish({"type": "event", "event": payload})

        async with gate:
            state.status = "running"
            try:
                docs = [Document(content=d.content, title=d.title) for d in state.request.documents]
                result = await workflow.run(
                    state.request.question,
                    documents=docs,
                    context=state.request.context,
                    run_id=state.run_id,
                    on_event=on_event,
                )
                state.result = result
                state.status = result.metadata.status.value
            except Exception as exc:
                state.status = "failed"
                state.error = f"{type(exc).__name__}: {exc}"
            finally:
                state.publish({"type": "end", "status": state.status, "error": state.error})
                state.publish(None)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/meta")
    async def meta() -> dict[str, Any]:
        return {
            "version": __version__,
            "modes": list(MODES),
            "profiles": list(PROFILES),
            "steps": list(STEP_BUILDERS),
            "tools": available_tools(),
            "providers": [
                {"name": n, "configured": i.configured(), "description": i.description}
                for n, i in sorted(available_providers().items())
            ],
        }

    @app.post("/api/runs", status_code=202)
    async def create_run(req: RunRequest) -> RunSummary:
        if req.mode not in MODES:
            raise HTTPException(400, f"unknown mode '{req.mode}'")
        try:
            workflow = factory(req)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        if len(runs) >= max_stored_runs:
            for rid in [r.run_id for r in runs.values() if r.status not in ("queued", "running")][
                : len(runs) // 4 or 1
            ]:
                runs.pop(rid, None)
        state = RunState(uuid.uuid4().hex[:12], req)
        runs[state.run_id] = state
        state.task = asyncio.create_task(execute(state, workflow))
        return state.summary()

    @app.get("/api/runs")
    async def list_runs() -> list[RunSummary]:
        return [
            r.summary() for r in sorted(runs.values(), key=lambda r: r.created_at, reverse=True)
        ]

    def get_state(run_id: str) -> RunState:
        state = runs.get(run_id)
        if state is None:
            raise HTTPException(404, "run not found")
        return state

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        state = get_state(run_id)
        return {
            **state.summary().model_dump(mode="json"),
            "result": state.result.to_dict(include_trace=False) if state.result else None,
        }

    @app.get("/api/runs/{run_id}/events")
    async def get_events(run_id: str, after: int = 0) -> list[dict[str, Any]]:
        return [e for e in get_state(run_id).events if e["seq"] > after]

    @app.websocket("/api/runs/{run_id}/stream")
    async def stream(ws: WebSocket, run_id: str) -> None:
        state = runs.get(run_id)
        await ws.accept()
        if state is None:
            await ws.send_json({"type": "error", "error": "run not found"})
            await ws.close()
            return
        # Subscribe, snapshot history and check completion with no await in between, so
        # every event is delivered exactly once (duplicates are filtered by sequence).
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        state.subscribers.add(queue)
        history = list(state.events)
        finished = state.status not in ("queued", "running")
        try:
            last_seq = 0
            for e in history:
                await ws.send_json({"type": "event", "event": e})
                last_seq = e["seq"]
            if finished:
                await ws.send_json({"type": "end", "status": state.status, "error": state.error})
                return
            while (msg := await queue.get()) is not None:
                if msg.get("type") == "event":
                    if msg["event"]["seq"] <= last_seq:
                        continue
                    last_seq = msg["event"]["seq"]
                await ws.send_json(msg)
        except WebSocketDisconnect:
            pass
        finally:
            state.subscribers.discard(queue)
            with contextlib.suppress(RuntimeError):
                await ws.close()

    if static_dir is not None and (static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")

    return app
