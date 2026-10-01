"""Agent perspectives, debate turns, challenges and critique findings."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from adversi.protocol.base import Record


class Perspective(Record):
    """One agent's structured analysis. ``summary`` is a reasoning summary, not raw chain-of-thought."""

    agent: str
    role: str
    model: str
    step: str
    round: int = 0
    verdict: str | None = Field(
        default=None, description="Short normalized answer, used for disagreement metrics."
    )
    position: str
    summary: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    assumption_ids: list[str] = Field(default_factory=list)
    counterarguments: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class Stance(StrEnum):
    FOR = "for"
    AGAINST = "against"
    MIXED = "mixed"


class DebateTurn(Record):
    round: int
    agent: str
    role: str
    stance: Stance
    argument: str
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    concedes: bool = False


class ChallengeKind(StrEnum):
    COUNTEREXAMPLE = "counterexample"
    MISSING_EVIDENCE = "missing_evidence"
    LOGICAL_FLAW = "logical_flaw"
    ALTERNATIVE_EXPLANATION = "alternative_explanation"
    HIDDEN_ASSUMPTION = "hidden_assumption"
    SCOPE = "scope"
    STATISTICAL = "statistical"
    OTHER = "other"


class ChallengeOutcome(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    CONCEDED = "conceded"


class Rebuttal(Record):
    agent: str
    round: int
    response: str
    concedes: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class Challenge(Record):
    id: str
    target_claim_id: str
    challenger: str
    round: int
    kind: ChallengeKind = ChallengeKind.OTHER
    argument: str
    evidence_ids: list[str] = Field(default_factory=list)
    rebuttals: list[Rebuttal] = Field(default_factory=list)
    outcome: ChallengeOutcome = ChallengeOutcome.OPEN


class CritiqueKind(StrEnum):
    UNSUPPORTED_LEAP = "unsupported_leap"
    IGNORED_COUNTEREVIDENCE = "ignored_counterevidence"
    OVERCONFIDENCE = "overconfidence"
    CIRCULAR_REASONING = "circular_reasoning"
    MISSING_ALTERNATIVE = "missing_alternative"
    ASSUMPTION_DEPENDENCY = "assumption_dependency"
    STATISTICAL_ERROR = "statistical_error"
    CONFORMITY = "conformity"
    OTHER = "other"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CritiqueFinding(Record):
    id: str
    critic: str
    kind: CritiqueKind = CritiqueKind.OTHER
    severity: Severity = Severity.MEDIUM
    description: str
    target_ids: list[str] = Field(default_factory=list)
