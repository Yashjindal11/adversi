"""Deterministic validation of claim statuses proposed by judges.

A judge (an LLM) *proposes* a status. :class:`StatusPolicy` checks it against the
evidence graph and challenge record and downgrades proposals the record cannot
justify. The rule set is intentionally simple and inspectable; every downgrade is
explained in ``policy_note``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from adversi.protocol.claims import Claim, ClaimStatus
from adversi.protocol.evidence import Evidence
from adversi.protocol.reasoning import Challenge, ChallengeOutcome


@dataclass(frozen=True)
class EvidenceView:
    supporting: list[Evidence]
    contradicting: list[Evidence]

    @property
    def external_support(self) -> list[Evidence]:
        return [e for e in self.supporting if e.is_external]

    @property
    def external_contradiction(self) -> list[Evidence]:
        return [e for e in self.contradicting if e.is_external]


@dataclass(frozen=True)
class StatusPolicy:
    """Rules (with defaults):

    * ``supported`` needs >=1 external, verified supporting excerpt, no external
      contradicting excerpt, and no challenge the defender conceded.
    * ``partially_supported`` needs >=1 external supporting excerpt.
    * ``contradicted`` needs >=1 external contradicting excerpt.
    * ``unsupported`` is rejected if external support exists (that is a conflict -> uncertain).
    * ``uncertain`` and ``unverified`` are always allowed.

    Evidence whose analysed reliability is below ``min_reliability`` is ignored.
    Setting ``require_external_evidence=False`` lets reasoning-only claims (e.g. pure
    logic or definitions) be ``supported``; the downgrade notes then disappear, so
    use it deliberately.
    """

    require_external_evidence: bool = True
    min_reliability: float = 0.3

    def evidence_view(self, claim_id: str, evidence: Sequence[Evidence]) -> EvidenceView:
        def ok(e: Evidence) -> bool:
            return e.reliability is None or e.reliability >= self.min_reliability

        return EvidenceView(
            supporting=[e for e in evidence if claim_id in e.supports and ok(e)],
            contradicting=[e for e in evidence if claim_id in e.contradicts and ok(e)],
        )

    def validate(
        self,
        proposed: ClaimStatus,
        claim: Claim,
        evidence: Sequence[Evidence],
        challenges: Sequence[Challenge] = (),
    ) -> tuple[ClaimStatus, str | None]:
        view = self.evidence_view(claim.id, evidence)
        ext_for = len(view.external_support)
        ext_against = len(view.external_contradiction)
        conceded = any(
            c.target_claim_id == claim.id and c.outcome == ChallengeOutcome.CONCEDED
            for c in challenges
        )
        S = ClaimStatus

        if not self.require_external_evidence and proposed in (S.SUPPORTED, S.PARTIALLY_SUPPORTED):
            if conceded and proposed == S.SUPPORTED:
                return S.PARTIALLY_SUPPORTED, "a challenge against this claim was conceded"
            return proposed, None

        if proposed == S.SUPPORTED:
            if ext_for == 0:
                return S.UNCERTAIN, "no verified external evidence supports this claim"
            if ext_against:
                return (
                    S.UNCERTAIN,
                    "verified external evidence both supports and contradicts this claim",
                )
            if conceded:
                return S.PARTIALLY_SUPPORTED, "a challenge against this claim was conceded"
            return S.SUPPORTED, None
        if proposed == S.PARTIALLY_SUPPORTED:
            if ext_for == 0:
                return S.UNCERTAIN, "no verified external evidence supports this claim"
            return S.PARTIALLY_SUPPORTED, None
        if proposed == S.CONTRADICTED:
            if ext_against == 0:
                return S.UNCERTAIN, "no verified external evidence contradicts this claim"
            return S.CONTRADICTED, None
        if proposed == S.UNSUPPORTED:
            if ext_for:
                return S.UNCERTAIN, "judged unsupported, but verified supporting evidence exists"
            return S.UNSUPPORTED, None
        return proposed, None
