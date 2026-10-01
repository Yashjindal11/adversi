"""Judgment, synthesis, uncertainty and run metadata."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from adversi.protocol.base import Record
from adversi.protocol.claims import ClaimStatus


class Interpretation(Record):
    restated_question: str
    answer_type: str = "open"
    sub_questions: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    scope_notes: list[str] = Field(default_factory=list)


class ClaimVerdict(Record):
    claim_id: str
    judge: str
    proposed_status: ClaimStatus
    status: ClaimStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str = ""
    policy_note: str | None = None


class Judgment(Record):
    judges: list[str]
    verdicts: list[ClaimVerdict] = Field(default_factory=list)
    overall_assessment: str = ""
    key_considerations: list[str] = Field(default_factory=list)
    answer_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    juror_answer_confidences: list[float] = Field(default_factory=list)


class Synthesis(Record):
    answer: str
    summary: str = ""
    established_claim_ids: list[str] = Field(default_factory=list)
    disputed_claim_ids: list[str] = Field(default_factory=list)
    uncertain_claim_ids: list[str] = Field(default_factory=list)
    rejected_claim_ids: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class Uncertainty(Record):
    """Uncertainty signals. These are heuristics, reported so they can be studied, not trusted blindly."""

    answer_confidence: float | None = None
    verdict_entropy: float | None = Field(
        default=None, description="Normalized entropy of independent agents' verdicts (0=agree)."
    )
    confidence_spread: float | None = Field(
        default=None, description="Std-dev of independent agents' self-reported confidence."
    )
    contested_claim_ratio: float | None = None
    unresolved_claim_ratio: float | None = None
    external_evidence_coverage: float | None = None
    citation_rejection_rate: float | None = None
    notes: list[str] = Field(default_factory=list)


class TokenUsage(Record):
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class UsageSummary(Record):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    latency_s: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class RunStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class RunError(Record):
    step: str | None = None
    agent: str | None = None
    type: str
    message: str


class StepRecord(Record):
    name: str
    kind: str
    config: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    duration_s: float | None = None
    ok: bool = True


class RunMetadata(Record):
    run_id: str
    adversi_version: str
    schema_version: str
    workflow: str
    mode: str | None = None
    profile: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_s: float | None = None
    status: RunStatus = RunStatus.COMPLETED
    steps: list[StepRecord] = Field(default_factory=list)
    agents: dict[str, str] = Field(default_factory=dict, description="agent name -> model id")
    tools: list[str] = Field(default_factory=list)
    usage: UsageSummary = Field(default_factory=UsageSummary)
    usage_by_model: dict[str, UsageSummary] = Field(default_factory=dict)
    errors: list[RunError] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
