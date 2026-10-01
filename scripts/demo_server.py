"""Serve the web UI backed by the scripted offline-demo model (no API keys needed).

For frontend development and demos only; answers are hard-coded.

    python scripts/demo_server.py          # http://127.0.0.1:8765
    cd web && npm run dev                  # http://127.0.0.1:5173 with hot reload
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

from offline_demo import REPORT, respond

from adversi import AdverSI
from adversi.server.app import DocumentIn, RunRequest, create_app
from adversi.testing import scripted_model
from adversi.workflows import Workflow


def factory(req: RunRequest) -> Workflow:
    # The scripted answers cite this document, so always attach it.
    if not req.documents:
        req.documents.append(DocumentIn(title="code_review_study_2025.txt", content=REPORT))
    return AdverSI(scripted_model(respond), mode="research", profile="balanced").workflow


if __name__ == "__main__":
    uvicorn.run(create_app(workflow_factory=factory), host="127.0.0.1", port=8765)
