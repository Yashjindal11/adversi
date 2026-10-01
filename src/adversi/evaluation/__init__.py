"""Experimental evaluation framework. See docs/evaluation.md before drawing conclusions."""

from adversi.evaluation.dataset import (
    ContainsAnswer,
    EvalItem,
    ExactMatch,
    LLMGrader,
    Score,
    Scorer,
    load_dataset,
    make_scorer,
)
from adversi.evaluation.metrics import (
    auroc,
    brier_score,
    expected_calibration_error,
    wilson_interval,
)
from adversi.evaluation.runner import (
    BenchmarkReport,
    BenchmarkRow,
    SystemSummary,
    rescore,
    run_benchmark,
)

__all__ = [
    "BenchmarkReport",
    "BenchmarkRow",
    "ContainsAnswer",
    "EvalItem",
    "ExactMatch",
    "LLMGrader",
    "Score",
    "Scorer",
    "SystemSummary",
    "auroc",
    "brier_score",
    "expected_calibration_error",
    "load_dataset",
    "make_scorer",
    "rescore",
    "run_benchmark",
    "wilson_interval",
]
