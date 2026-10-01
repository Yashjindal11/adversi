"""Aggregate metrics with honest uncertainty."""

from __future__ import annotations

import math
from collections.abc import Sequence


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def brier_score(confidences: Sequence[float], outcomes: Sequence[bool]) -> float | None:
    """Mean squared error between stated confidence and correctness (lower is better)."""
    if not confidences or len(confidences) != len(outcomes):
        return None
    return sum((c - float(o)) ** 2 for c, o in zip(confidences, outcomes, strict=True)) / len(
        confidences
    )


def expected_calibration_error(
    confidences: Sequence[float], outcomes: Sequence[bool], bins: int = 10
) -> float | None:
    if not confidences or len(confidences) != len(outcomes):
        return None
    n = len(confidences)
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [
            i for i, c in enumerate(confidences) if (lo <= c < hi) or (b == bins - 1 and c == 1.0)
        ]
        if not idx:
            continue
        acc = sum(outcomes[i] for i in idx) / len(idx)
        conf = sum(confidences[i] for i in idx) / len(idx)
        total += len(idx) / n * abs(acc - conf)
    return total


def auroc(scores: Sequence[float], labels: Sequence[bool]) -> float | None:
    """Probability a random positive outranks a random negative (ties count half).

    Used e.g. to test whether disagreement predicts errors.
    """
    pos = [s for s, y in zip(scores, labels, strict=True) if y]
    neg = [s for s, y in zip(scores, labels, strict=True) if not y]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p in pos for q in neg)
    return wins / (len(pos) * len(neg))
