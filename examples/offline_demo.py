"""Offline demo: runs the full research workflow against a *scripted* model.

No API key or network is needed. Every model response below is hard-coded, so the
output demonstrates the machinery (claim ingestion, citation verification, status
policy, cross-examination, rendering, the web UI), NOT reasoning quality.

    python examples/offline_demo.py            # writes offline-demo-result.json
    adversi inspect offline-demo-result.json --all
"""

from __future__ import annotations

from typing import Any

from adversi import AdverSI, Document
from adversi.providers import ModelRequest
from adversi.testing import scripted_model

REPORT = (
    "Internal study, 2025: teams that adopted mandatory code review saw escaped defects fall "
    "from 4.1 to 2.9 per release over two quarters. During the same period the company also "
    "introduced a new end-to-end test suite. Median time-to-merge rose from 6 hours to 15 hours."
)


def claim(
    statement: str,
    ctype: str,
    conf: float,
    quote: str | None = None,
    assumptions: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "statement": statement,
        "claim_type": ctype,
        "confidence": conf,
        "assumptions": assumptions or [],
    }
    if quote:
        out |= {"basis": "evidence", "citations": [{"source_id": "S1", "excerpt": quote}]}
    return out


ANALYSES = {
    "analyst_a": (
        "yes, with caveats",
        0.7,
        [
            claim(
                "Escaped defects fell from 4.1 to 2.9 per release after mandatory review",
                "statistical",
                0.9,
                "escaped defects fall from 4.1 to 2.9 per release",
            ),
            claim(
                "Mandatory code review caused the drop in escaped defects",
                "causal",
                0.65,
                assumptions=["No other major quality change happened at the same time"],
            ),
        ],
    ),
    "statistician": (
        "unclear",
        0.5,
        [
            claim(
                "Escaped defects fell from 4.1 to 2.9 per release after mandatory review",
                "statistical",
                0.9,
            ),
            claim(
                "A new end-to-end test suite was introduced in the same period",
                "factual",
                0.95,
                "also introduced a new end-to-end test suite",
            ),
            claim(
                "Two quarters of data is too short to separate the effect of review from the test suite",
                "statistical",
                0.7,
            ),
        ],
    ),
    "analyst_b": (
        "yes",
        0.6,
        [
            claim(
                "Mandatory review slows delivery: median time-to-merge rose from 6 to 15 hours",
                "statistical",
                0.85,
                "Median time-to-merge rose from 6 hours to 15 hours",
            ),
            claim("Mandatory code review is worth its cost for most teams", "normative", 0.6),
        ],
    ),
}


def respond(req: ModelRequest) -> dict[str, Any]:
    md = req.metadata
    s = md["schema"]
    if s == "Interpretation":
        return {
            "restated_question": "Did mandatory code review reduce escaped defects, and is it worth the slower merges?",
            "answer_type": "yes_no",
            "sub_questions": [
                "Is the defect drop real?",
                "Is it attributable to review?",
                "What does it cost?",
            ],
            "ambiguities": ["'Worth it' depends on how defects and delay are valued."],
        }
    if s == "AnalysisDraft":
        verdict, conf, claims = ANALYSES[md["agent"]]
        return {
            "verdict": verdict,
            "position": f"{verdict.capitalize()}.",
            "summary": "Structured summary of this agent's analysis.",
            "claims": claims,
            "counterarguments": ["Confounding by the test suite."],
            "uncertainties": ["Short observation window."],
            "open_questions": ["Was review adoption staggered across teams?"],
            "confidence": conf,
        }
    if s == "AssumptionDraft":
        return {
            "assumptions": [
                {
                    "statement": "Defect counting did not change during the period",
                    "claim_ids": ["C1"],
                    "critical": True,
                }
            ]
        }
    if s == "ResearchDraft":
        return {
            "findings": [
                {
                    "source_id": "S1",
                    "excerpt": "During the same period the company also introduced a new end-to-end test suite",
                    "contradicts": ["C2"],
                },
                {"source_id": "S1", "excerpt": "review cut defects in half", "supports": ["C2"]},
            ],
            "gaps": ["No team-level breakdown by adoption date."],
        }
    if s == "EvidenceAssessmentDraft":
        return {
            "assessments": [
                {
                    "evidence_id": "E1",
                    "claim_id": "C1",
                    "relation": "supports",
                    "reliability": 0.7,
                    "rationale": "Internal study; single source.",
                },
                {
                    "evidence_id": "E4",
                    "claim_id": "C2",
                    "relation": "contradicts",
                    "reliability": 0.7,
                    "rationale": "Concurrent change is a confounder, weakening the causal claim.",
                },
            ]
        }
    if s == "DebateTurnDraft":
        if md["role"] == "proponent":
            return {
                "stance": "for",
                "argument": "C1 is well supported and review is a plausible mechanism for C2.",
                "claim_ids": ["C1", "C2"],
            }
        return {
            "stance": "against",
            "argument": "C3 is a direct confounder for C2; the data cannot attribute the drop to review.",
            "claim_ids": ["C2", "C3"],
        }
    if s == "ChallengeDraft":
        return {
            "challenges": [
                {
                    "target_claim_id": "C2",
                    "kind": "alternative_explanation",
                    "argument": "The end-to-end suite (C3) could explain the drop.",
                },
                {
                    "target_claim_id": "C6",
                    "kind": "missing_evidence",
                    "argument": "No cost-benefit data supports this normative claim.",
                },
            ]
        }
    if s == "RebuttalDraft":
        return {
            "rebuttals": [
                {
                    "challenge_id": "X1",
                    "response": "Conceded: the design cannot separate the two changes.",
                    "concedes": True,
                },
                {
                    "challenge_id": "X2",
                    "response": "The 9-hour merge delay is real but defect cost data is missing.",
                    "concedes": False,
                },
            ]
        }
    if s == "CritiqueDraft":
        return {
            "findings": [
                {
                    "kind": "unsupported_leap",
                    "severity": "high",
                    "description": "Agents moved from a before/after difference to a causal claim.",
                    "target_ids": ["C2"],
                },
                {
                    "kind": "conformity",
                    "severity": "low",
                    "description": "Two analysts reached 'yes' without addressing the confounder.",
                    "target_ids": [],
                },
            ]
        }
    if s == "JudgmentDraft":
        return {
            "verdicts": [
                {
                    "claim_id": "C1",
                    "status": "supported",
                    "confidence": 0.85,
                    "rationale": "Directly stated in the study.",
                },
                {
                    "claim_id": "C2",
                    "status": "supported",
                    "confidence": 0.6,
                    "rationale": "Plausible mechanism.",
                },
                {
                    "claim_id": "C3",
                    "status": "supported",
                    "confidence": 0.95,
                    "rationale": "Stated in the study.",
                },
                {
                    "claim_id": "C4",
                    "status": "uncertain",
                    "confidence": 0.6,
                    "rationale": "Reasonable but untested.",
                },
                {
                    "claim_id": "C5",
                    "status": "supported",
                    "confidence": 0.9,
                    "rationale": "Stated in the study.",
                },
                {
                    "claim_id": "C6",
                    "status": "uncertain",
                    "confidence": 0.4,
                    "rationale": "Normative; depends on values.",
                },
            ],
            "overall_assessment": "The defect drop is documented, but attribution to review is confounded.",
            "answer_confidence": 0.55,
        }
    if s == "SynthesisDraft":
        return {
            "answer": "The data shows fewer escaped defects (C1) but cannot attribute the drop to code review, because a new test suite arrived at the same time (C3). Review did slow merges (C5).",
            "summary": "Established: C1, C3, C5. The causal claim C2 was conceded under cross-examination and remains uncertain.",
            "caveats": ["Single internal study", "Two quarters only"],
            "recommendations": [
                "Compare teams by review adoption date",
                "Track defect severity, not just counts",
            ],
        }
    raise ValueError(s)


if __name__ == "__main__":
    print("NOTE: scripted demo, no real model is called.\n")
    ai = AdverSI(scripted_model(respond), mode="research", profile="balanced")
    result = ai.run_sync(
        "Did mandatory code review reduce escaped defects, and is it worth it?",
        documents=[Document(content=REPORT, title="code_review_study_2025.txt")],
    )
    print(result.to_markdown())
    result.save("offline-demo-result.json")
