"""Run-level uncertainty signals.

These are descriptive heuristics, not calibrated probabilities. They are reported so
their usefulness (e.g. "is agent disagreement predictive of error?") can be tested
with ``adversi.evaluation``.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Sequence

from adversi.claims.text import normalize
from adversi.protocol.claims import Claim, ClaimStatus
from adversi.protocol.evidence import Evidence
from adversi.protocol.outcome import Judgment, Uncertainty
from adversi.protocol.reasoning import Challenge, Perspective


def normalized_entropy(labels: Sequence[str]) -> float | None:
    if len(labels) < 2:
        return None
    counts = Counter(labels)
    if len(counts) == 1:
        return 0.0
    n = len(labels)
    h = -sum((c / n) * math.log(c / n) for c in counts.values())
    # 1.0 means every agent gave a different verdict.
    return h / math.log(n)


def compute_uncertainty(
    *,
    perspectives: Sequence[Perspective],
    claims: Sequence[Claim],
    challenges: Sequence[Challenge],
    evidence: Sequence[Evidence],
    rejected: int,
    judgment: Judgment | None,
) -> Uncertainty:
    independent = [p for p in perspectives if p.round == 0]
    verdicts = [normalize(p.verdict) for p in independent if p.verdict]
    confidences = [p.confidence for p in independent if p.confidence is not None]
    notes: list[str] = []

    n_claims = len(claims)
    contested = {c.target_claim_id for c in challenges}
    unresolved = [c for c in claims if c.status in (ClaimStatus.UNCERTAIN, ClaimStatus.UNVERIFIED)]
    externally_backed = {
        cid for e in evidence if e.is_external for cid in e.supports + e.contradicts
    }
    attempted = len(evidence) + rejected

    entropy = normalized_entropy(verdicts)
    if entropy is not None and entropy > 0.5:
        notes.append("Independent agents reached substantially different verdicts.")
    if n_claims and len(externally_backed & {c.id for c in claims}) == 0:
        notes.append(
            "No claim is backed by verified external evidence; conclusions rest on model knowledge and reasoning."
        )
    if rejected:
        notes.append(
            f"{rejected} citation(s) could not be verified against their sources and were discarded."
        )

    if judgment is not None:
        answer_confidence = judgment.answer_confidence
    elif len(independent) == 1:
        # Single-model baseline: the model's own stated confidence.
        answer_confidence = independent[0].confidence
    else:
        answer_confidence = None

    return Uncertainty(
        answer_confidence=answer_confidence,
        verdict_entropy=entropy,
        confidence_spread=statistics.pstdev(confidences) if len(confidences) >= 2 else None,
        contested_claim_ratio=len(contested) / n_claims if n_claims else None,
        unresolved_claim_ratio=len(unresolved) / n_claims if n_claims else None,
        external_evidence_coverage=(
            len(externally_backed & {c.id for c in claims}) / n_claims if n_claims else None
        ),
        citation_rejection_rate=rejected / attempted if attempted else None,
        notes=notes,
    )
