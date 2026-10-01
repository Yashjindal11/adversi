"""Shared fixtures.

``world_handler`` scripts a complete research-mode run deterministically. It answers
each request based on ``request.metadata`` (agent, step, schema), so tests exercise
the real orchestration, ingestion, verification and policy code with no network.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from adversi.providers.base import ModelRequest
from adversi.providers.registry import register_provider, unregister_provider
from adversi.testing import ScriptedProvider
from adversi.tools.documents import Document

DOC_TEXT = (
    "At standard atmospheric pressure, water boils at 100 degrees Celsius at sea level. "
    "At high altitude it boils at lower temperatures because air pressure is lower."
)
QUESTION = "Does water always boil at 100 degrees Celsius?"


def analysis(verdict: str, claims: list[dict[str, Any]], confidence: float) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "position": f"Position: {verdict}.",
        "summary": "Short reasoning summary.",
        "claims": claims,
        "counterarguments": ["Pressure varies."],
        "uncertainties": ["Exact altitude effects."],
        "open_questions": ["What pressure is assumed?"],
        "confidence": confidence,
    }


SEA_LEVEL = {
    "statement": "Water boils at 100 degrees Celsius at sea level",
    "claim_type": "factual",
    "basis": "evidence",
    "confidence": 0.95,
    "assumptions": ["Standard atmospheric pressure"],
    "citations": [
        {"source_id": "S1", "excerpt": "water boils at 100 degrees Celsius at sea level"}
    ],
}
ALWAYS = {
    "statement": "Water always boils at 100 degrees Celsius",
    "claim_type": "factual",
    "basis": "evidence",
    "confidence": 0.6,
}
NO_ALTITUDE = {
    "statement": "Altitude has no effect on the boiling point",
    "claim_type": "causal",
    "confidence": 0.3,
}


def world_handler(request: ModelRequest) -> dict[str, Any]:
    md = request.metadata
    schema, agent = md["schema"], md["agent"]
    if schema == "Interpretation":
        return {
            "restated_question": QUESTION,
            "answer_type": "yes_no",
            "sub_questions": ["Effect of pressure?"],
        }
    if schema == "AnalysisDraft":
        if agent == "analyst_a":
            return analysis("no", [SEA_LEVEL, ALWAYS], 0.8)
        if agent == "statistician":
            dup = {
                **SEA_LEVEL,
                "statement": "Water boils at 100 degrees Celsius at sea level.",
                "citations": [],
            }
            return analysis("No", [dup, NO_ALTITUDE], 0.7)
        # near-duplicate phrasing, merged by ClaimConsolidation
        para = {
            **SEA_LEVEL,
            "statement": "At sea level, water boils at 100 degrees Celsius",
            "citations": [],
        }
        return analysis("yes", [para], 0.55)
    if schema == "AssumptionDraft":
        return {
            "assumptions": [
                {"statement": "Pure water is used", "claim_ids": ["C1", "C99"], "critical": False}
            ]
        }
    if schema == "ResearchDraft":
        return {
            "findings": [
                {
                    "source_id": "S1",
                    "excerpt": "At high altitude it boils at lower temperatures",
                    "contradicts": ["C2", "C3"],
                },
                {
                    "source_id": "S1",
                    "excerpt": "water boils at 120 degrees at sea level",
                    "supports": ["C2"],
                },
                {"source_id": "S9", "excerpt": "fabricated source text here", "supports": ["C2"]},
            ],
            "summary": "Found altitude evidence.",
            "gaps": ["No data on salt water"],
        }
    if schema == "EvidenceAssessmentDraft":
        return {
            "assessments": [
                {
                    "evidence_id": "E1",
                    "claim_id": "C1",
                    "relation": "supports",
                    "reliability": 0.9,
                    "rationale": "Direct statement.",
                }
            ]
        }
    if schema == "DebateTurnDraft":
        stance = "for" if md["role"] == "proponent" else "against"
        return {
            "stance": stance,
            "argument": f"{stance} argument citing C1",
            "claim_ids": ["C1", "C42"],
            "concedes": False,
        }
    if schema == "ChallengeDraft":
        return {
            "challenges": [
                {
                    "target_claim_id": "C2",
                    "kind": "counterexample",
                    "argument": "Altitude lowers it.",
                },
                {"target_claim_id": "C77", "argument": "bogus"},
            ]
        }
    if schema == "RebuttalDraft":
        return {"rebuttals": [{"challenge_id": "X1", "response": "Conceded.", "concedes": True}]}
    if schema == "CritiqueDraft":
        return {
            "findings": [
                {
                    "kind": "overconfidence",
                    "severity": "high",
                    "description": "C2 overstated.",
                    "target_ids": ["C2", "Z9"],
                }
            ]
        }
    if schema == "JudgmentDraft":
        return {
            "verdicts": [
                {
                    "claim_id": "C1",
                    "status": "supported",
                    "confidence": 0.95,
                    "rationale": "Verified source.",
                },
                {
                    "claim_id": "C2",
                    "status": "supported",
                    "confidence": 0.7,
                    "rationale": "Judge was wrong.",
                },
                {
                    "claim_id": "C3",
                    "status": "contradicted",
                    "confidence": 0.9,
                    "rationale": "Altitude matters.",
                },
                {"claim_id": "C55", "status": "supported", "confidence": 0.9},
            ],
            "overall_assessment": "Only at sea level.",
            "answer_confidence": 0.85,
        }
    if schema == "SynthesisDraft":
        return {
            "answer": "No. Only at sea-level pressure (C1).",
            "summary": "C1 holds; C2 does not; see C3.",
            "caveats": ["Pressure matters"],
        }
    raise AssertionError(f"unscripted request: {schema} from {agent}")


@pytest.fixture
def documents() -> list[Document]:
    return [Document(content=DOC_TEXT, title="boiling.txt")]


@pytest.fixture
def world() -> ScriptedProvider:
    return ScriptedProvider(world_handler)


@pytest.fixture
def register_scripted() -> Iterator[Callable[[Callable[[ModelRequest], Any]], ScriptedProvider]]:
    """Register a provider named 'scripted' so config/CLI code paths can use 'scripted:x'."""
    created: list[ScriptedProvider] = []

    def _register(handler: Callable[[ModelRequest], Any]) -> ScriptedProvider:
        provider = ScriptedProvider(handler)
        created.append(provider)
        register_provider("scripted", lambda **_: provider, overwrite=True)
        return provider

    yield _register
    unregister_provider("scripted")
