"""Smoke tests against a real provider. Skipped unless ADVERSI_LIVE_TESTS=1.

ADVERSI_LIVE_TESTS=1 ADVERSI_MODEL=ollama:llama3.1:8b pytest -m live
"""

from __future__ import annotations

import os

import pytest

from adversi import AdverSI, Document
from adversi.protocol import RunStatus

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("ADVERSI_LIVE_TESTS") != "1", reason="set ADVERSI_LIVE_TESTS=1"
    ),
]

MODEL = os.environ.get("ADVERSI_MODEL", "openai:gpt-4o-mini")


def test_live_simple_returns_structured_answer() -> None:
    result = AdverSI(MODEL, mode="simple").run_sync("Is 17 a prime number? Answer yes or no first.")
    assert result.metadata.status == RunStatus.COMPLETED, result.metadata.errors
    assert result.answer and result.metadata.usage.calls == 1


def test_live_adversarial_with_document_produces_verified_evidence() -> None:
    doc = Document(
        title="memo.txt",
        content="The pilot program ran for 8 weeks with 40 participants. Average task time fell "
        "from 52 minutes to 47 minutes. There was no control group.",
    )
    result = AdverSI(MODEL, mode="adversarial", profile="fast").run_sync(
        "Did the pilot program cause task times to fall?", documents=[doc]
    )
    assert result.metadata.status in (RunStatus.COMPLETED, RunStatus.PARTIAL), (
        result.metadata.errors
    )
    assert result.claims
    # Any evidence that exists must have been verified against the memo.
    assert all(e.excerpt_verified for e in result.evidence if e.source_id)
