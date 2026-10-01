"""Claims, assumptions and their epistemic metadata."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from adversi.protocol.base import Record


class ClaimType(StrEnum):
    FACTUAL = "factual"
    CAUSAL = "causal"
    STATISTICAL = "statistical"
    PREDICTIVE = "predictive"
    NORMATIVE = "normative"
    DEFINITIONAL = "definitional"
    OTHER = "other"


class ClaimBasis(StrEnum):
    """What an assertion rests on, as declared by its author and validated by AdverSI.

    ``evidence`` is only kept if the claim actually links to verified evidence;
    otherwise it is downgraded to ``assertion`` during ingestion.
    """

    EVIDENCE = "evidence"
    INFERENCE = "inference"
    ASSERTION = "assertion"
    SPECULATION = "speculation"


class ClaimStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNCERTAIN = "uncertain"
    UNVERIFIED = "unverified"


class Attribution(Record):
    """One agent asserting a claim, with that agent's own stated confidence."""

    agent: str
    role: str
    step: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class Assumption(Record):
    id: str
    statement: str
    critical: bool = False
    claim_ids: list[str] = Field(default_factory=list)
    identified_by: str


class Claim(Record):
    id: str
    statement: str
    claim_type: ClaimType = ClaimType.OTHER
    basis: ClaimBasis = ClaimBasis.ASSERTION
    attributions: list[Attribution] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    assumption_ids: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    merged_from: list[str] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    proposed_status: ClaimStatus | None = None
    status_rationale: str | None = None
    policy_note: str | None = None
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Judged confidence after evaluation; None until judged.",
    )

    @property
    def asserted_by(self) -> list[str]:
        return sorted({a.agent for a in self.attributions})
