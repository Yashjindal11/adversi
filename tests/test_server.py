from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from adversi import AdverSI
from adversi.models import Model
from adversi.server.app import RunRequest, create_app
from adversi.testing import ScriptedProvider, scripted_model
from tests.conftest import QUESTION, world_handler


def test_server_run_lifecycle_and_stream(documents) -> None:
    def factory(req: RunRequest):
        return AdverSI(
            Model(provider=ScriptedProvider(world_handler), model="m"),
            mode=req.mode,
            profile=req.profile,
        ).workflow

    app = create_app(workflow_factory=factory, static_dir=None)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        meta = client.get("/api/meta").json()
        assert "research" in meta["modes"] and any(p["name"] == "ollama" for p in meta["providers"])

        r = client.post(
            "/api/runs",
            json={
                "question": QUESTION,
                "mode": "research",
                "profile": "balanced",
                "documents": [{"title": "b", "content": documents[0].content}],
            },
        )
        assert r.status_code == 202
        run_id = r.json()["run_id"]

        messages = []
        with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "end":
                    break
        seqs = [m["event"]["seq"] for m in messages if m["type"] == "event"]
        stored = client.get(f"/api/runs/{run_id}/events").json()
        assert seqs == [e["seq"] for e in stored]  # every event exactly once, in order
        assert seqs[0] == 1 and stored[-1]["type"] == "run.completed"
        assert messages[-1]["status"] == "completed"

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["result"]["synthesis"]["established_claim_ids"] == ["C1"]
        assert "trace" not in run["result"] or run["result"]["trace"] == []
        after = client.get(f"/api/runs/{run_id}/events", params={"after": seqs[-2]}).json()
        assert [e["seq"] for e in after] == [seqs[-1]]
        assert client.get("/api/runs/missing").status_code == 404


def test_server_rejects_bad_requests() -> None:
    app = create_app(
        workflow_factory=lambda req: AdverSI(scripted_model(lambda r: ""), mode="simple").workflow,
        static_dir=None,
    )
    with TestClient(app) as client:
        assert client.post("/api/runs", json={"question": "", "mode": "simple"}).status_code == 422
        assert client.post("/api/runs", json={"question": "q", "mode": "nope"}).status_code == 400
        assert client.post("/api/runs", json={"question": "x" * 5000}).status_code == 422
        too_many_docs = [{"content": "d"}] * 11
        assert (
            client.post("/api/runs", json={"question": "q", "documents": too_many_docs}).status_code
            == 422
        )


def test_server_tool_allowlist_and_no_default_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("ADVERSI_MODEL", raising=False)
    cfg = tmp_path / "adversi.toml"
    cfg.write_text('tools = ["calculator"]\n[models]\ndefault = "openai:m"\n')
    with TestClient(create_app(config_path=str(cfg), static_dir=None)) as client:
        r = client.post(
            "/api/runs", json={"question": "q", "mode": "simple", "tools": ["fetch_url"]}
        )
        assert r.status_code == 400 and "not enabled" in r.json()["detail"]

    empty = tmp_path / "empty.toml"
    empty.write_text("version = 1\n")
    with TestClient(create_app(config_path=str(empty), static_dir=None)) as client:
        r = client.post("/api/runs", json={"question": "q", "mode": "simple"})
        assert r.status_code == 400 and "no default model" in r.json()["detail"]
