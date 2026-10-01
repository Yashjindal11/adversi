from adversi.workflows.steps.adversarial import Critique, CrossExamination, Debate
from adversi.workflows.steps.analysis import (
    AssumptionAnalysis,
    ClaimConsolidation,
    IndependentAnalysis,
    Interpret,
    PositionExchange,
)
from adversi.workflows.steps.evidence import EvidenceAnalysis, EvidenceResearch
from adversi.workflows.steps.verdict import Judgment, Synthesis, classify_claims

ClaimExtraction = ClaimConsolidation

__all__ = [
    "AssumptionAnalysis",
    "ClaimConsolidation",
    "ClaimExtraction",
    "Critique",
    "CrossExamination",
    "Debate",
    "EvidenceAnalysis",
    "EvidenceResearch",
    "IndependentAnalysis",
    "Interpret",
    "Judgment",
    "PositionExchange",
    "Synthesis",
    "call_agent",
    "call_agents",
    "classify_claims",
]
