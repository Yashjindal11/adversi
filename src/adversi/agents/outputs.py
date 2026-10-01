"""LLM-facing output schemas.

These are deliberately separate from the protocol records. Agents produce *drafts*
(no ids, no statuses, no verification flags); AdverSI assigns ids, verifies
citations and computes statuses. Changing a draft schema changes prompts, not the
public result format.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from adversi.protocol.claims import ClaimBasis, ClaimStatus, ClaimType
from adversi.protocol.reasoning import ChallengeKind, CritiqueKind, Severity, Stance


class Citation(BaseModel):
    source_id: str | None = Field(
        default=None,
        description="Id (S#) of a source in this run. null means your own background knowledge.",
    )
    excerpt: str = Field(
        description="Verbatim quote from the source. With source_id null, the fact you rely on."
    )


class ClaimDraft(BaseModel):
    statement: str = Field(description="One atomic, checkable assertion.")
    claim_type: ClaimType = ClaimType.OTHER
    basis: ClaimBasis = Field(
        default=ClaimBasis.ASSERTION,
        description="evidence (cited), inference (from other claims), assertion, or speculation",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class AnalysisDraft(BaseModel):
    verdict: str = Field(
        description="Your answer in at most 6 words, e.g. 'yes', 'no', 'option B'."
    )
    position: str = Field(description="Your position in 1-3 sentences.")
    summary: str = Field(description="Concise summary of your reasoning (not a transcript).")
    claims: list[ClaimDraft] = Field(default_factory=list, description="3-7 atomic claims.")
    counterarguments: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="P(your verdict is right)")


class Finding(BaseModel):
    source_id: str = Field(description="S# the excerpt was taken from.")
    excerpt: str = Field(description="Verbatim quote, copied exactly.")
    supports: list[str] = Field(default_factory=list, description="Claim ids (C#) supported.")
    contradicts: list[str] = Field(default_factory=list, description="Claim ids (C#) contradicted.")
    note: str | None = None


class ResearchDraft(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""
    gaps: list[str] = Field(
        default_factory=list, description="What you looked for but could not find."
    )


class EvidenceAssessment(BaseModel):
    evidence_id: str
    claim_id: str
    relation: Literal["supports", "contradicts", "irrelevant"]
    reliability: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class EvidenceAssessmentDraft(BaseModel):
    assessments: list[EvidenceAssessment] = Field(default_factory=list)


class AssumptionItem(BaseModel):
    statement: str
    claim_ids: list[str] = Field(default_factory=list)
    critical: bool = False


class AssumptionDraft(BaseModel):
    assumptions: list[AssumptionItem] = Field(default_factory=list)


class DebateTurnDraft(BaseModel):
    stance: Stance
    argument: str = Field(description="Your argument this round, referencing claim ids.")
    claim_ids: list[str] = Field(
        default_factory=list, description="Existing claims you rely on or attack."
    )
    new_claims: list[ClaimDraft] = Field(default_factory=list)
    concedes: bool = Field(
        default=False, description="True if you no longer contest the other side."
    )


class ChallengeItem(BaseModel):
    target_claim_id: str
    kind: ChallengeKind = ChallengeKind.OTHER
    argument: str
    evidence_ids: list[str] = Field(default_factory=list)


class ChallengeDraft(BaseModel):
    challenges: list[ChallengeItem] = Field(
        default_factory=list, description="Empty list if you have no substantive challenge."
    )


class RebuttalItem(BaseModel):
    challenge_id: str
    response: str
    concedes: bool = False
    citations: list[Citation] = Field(default_factory=list)


class RebuttalDraft(BaseModel):
    rebuttals: list[RebuttalItem] = Field(default_factory=list)


class CritiqueItem(BaseModel):
    kind: CritiqueKind = CritiqueKind.OTHER
    severity: Severity = Severity.MEDIUM
    description: str
    target_ids: list[str] = Field(default_factory=list)


class CritiqueDraft(BaseModel):
    findings: list[CritiqueItem] = Field(default_factory=list)


class VerdictItem(BaseModel):
    claim_id: str
    status: ClaimStatus
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class JudgmentDraft(BaseModel):
    verdicts: list[VerdictItem] = Field(default_factory=list)
    overall_assessment: str
    key_considerations: list[str] = Field(default_factory=list)
    answer_confidence: float = Field(ge=0.0, le=1.0)


class SynthesisDraft(BaseModel):
    answer: str = Field(description="Direct answer to the question, 1-3 sentences.")
    summary: str = Field(description="Short markdown summary referencing claim ids.")
    caveats: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
