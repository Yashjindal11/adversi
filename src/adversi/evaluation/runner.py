"""Benchmark runner: compare workflows on the same dataset with the same scorer."""

from __future__ import annotations

import asyncio
import re
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from adversi.evaluation.dataset import EvalItem, Score, Scorer
from adversi.evaluation.metrics import (
    auroc,
    brier_score,
    expected_calibration_error,
    wilson_interval,
)
from adversi.protocol.result import AdverSIResult
from adversi.workflows.base import Workflow


class BenchmarkRow(BaseModel):
    system: str
    item_id: str
    correct: bool | None = None
    answer: str | None = None
    answer_confidence: float | None = None
    verdict_entropy: float | None = None
    total_tokens: int = 0
    cost_usd: float | None = None
    duration_s: float | None = None
    status: str = "completed"
    error: str | None = None
    model_graded: bool = False


class SystemSummary(BaseModel):
    system: str
    n: int
    scored: int
    failures: int
    accuracy: float | None = None
    accuracy_ci95: tuple[float, float] | None = None
    brier: float | None = None
    ece: float | None = None
    disagreement_error_auroc: float | None = Field(
        default=None, description="AUROC of verdict entropy for predicting an incorrect answer."
    )
    mean_tokens: float | None = None
    total_cost_usd: float | None = None
    mean_duration_s: float | None = None


class BenchmarkReport(BaseModel):
    scorer: str
    model_graded: bool
    n_items: int
    summaries: list[SystemSummary]
    rows: list[BenchmarkRow]

    def to_markdown(self) -> str:
        lines = [
            f"Scorer: `{self.scorer}`{' (model-graded)' if self.model_graded else ''}; items: {self.n_items}",
            "",
            "| System | Scored | Accuracy | 95% CI | Brier | ECE | Disagreement AUROC | Mean tokens | Cost | Mean s | Failures |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]

        def f(v: float | None, d: int = 3) -> str:
            return "n/a" if v is None else f"{v:.{d}f}"

        for s in self.summaries:
            ci = (
                f"[{s.accuracy_ci95[0]:.2f}, {s.accuracy_ci95[1]:.2f}]"
                if s.accuracy_ci95
                else "n/a"
            )
            cost = f"${s.total_cost_usd:.4f}" if s.total_cost_usd is not None else "n/a"
            lines.append(
                f"| {s.system} | {s.scored}/{s.n} | {f(s.accuracy)} | {ci} | {f(s.brier)} | {f(s.ece)} | "
                f"{f(s.disagreement_error_auroc)} | {f(s.mean_tokens, 0)} | {cost} | {f(s.mean_duration_s, 1)} | {s.failures} |"
            )
        lines += [
            "",
            "Small samples give wide intervals; overlapping intervals are not evidence of a difference.",
        ]
        return "\n".join(lines)


def summarize(system: str, rows: Sequence[BenchmarkRow]) -> SystemSummary:
    scored = [r for r in rows if r.correct is not None]
    correct = sum(1 for r in scored if r.correct)
    calib = [
        (r.answer_confidence, bool(r.correct)) for r in scored if r.answer_confidence is not None
    ]
    dis = [(r.verdict_entropy, not r.correct) for r in scored if r.verdict_entropy is not None]
    costs = [r.cost_usd for r in rows if r.cost_usd is not None]
    durations = [r.duration_s for r in rows if r.duration_s is not None]
    return SystemSummary(
        system=system,
        n=len(rows),
        scored=len(scored),
        failures=sum(1 for r in rows if r.status == "failed" or r.error),
        accuracy=correct / len(scored) if scored else None,
        accuracy_ci95=wilson_interval(correct, len(scored)),
        brier=brier_score([c for c, _ in calib], [o for _, o in calib]),
        ece=expected_calibration_error([c for c, _ in calib], [o for _, o in calib]),
        disagreement_error_auroc=auroc([s for s, _ in dis], [y for _, y in dis]) if dis else None,
        mean_tokens=statistics.fmean(r.total_tokens for r in rows) if rows else None,
        total_cost_usd=sum(costs) if costs else None,
        mean_duration_s=statistics.fmean(durations) if durations else None,
    )


def _safe(name: str) -> str:
    """Filesystem-safe component: dataset ids must not be able to escape the output dir."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")
    return cleaned[:120] or "_"


def _row(
    system: str,
    item: EvalItem,
    result: AdverSIResult | None,
    score: Score | None,
    error: str | None,
) -> BenchmarkRow:
    if result is None:
        return BenchmarkRow(system=system, item_id=item.id, status="failed", error=error)
    m = result.metadata
    return BenchmarkRow(
        system=system,
        item_id=item.id,
        correct=score.correct if score else None,
        answer=result.answer,
        answer_confidence=result.uncertainty.answer_confidence,
        verdict_entropy=result.uncertainty.verdict_entropy,
        total_tokens=m.usage.total_tokens,
        cost_usd=m.usage.cost_usd,
        duration_s=m.duration_s,
        status=m.status.value,
        error=error,
        model_graded=bool(score and score.model_graded),
    )


async def run_benchmark(
    items: Sequence[EvalItem],
    systems: Mapping[str, Workflow],
    scorer: Scorer,
    *,
    concurrency: int = 2,
    output_dir: str | Path | None = None,
) -> BenchmarkReport:
    """Run every system on every item. Per-run results are saved for later re-scoring."""
    out = Path(output_dir) if output_dir else None
    sem = asyncio.Semaphore(concurrency)
    rows: list[BenchmarkRow] = []

    async def one(system: str, wf: Workflow, item: EvalItem) -> BenchmarkRow:
        async with sem:
            try:
                result = await wf.run(
                    item.question, context=item.context, run_id=f"{system}-{item.id}"
                )
            except Exception as exc:
                return _row(system, item, None, None, f"{type(exc).__name__}: {exc}")
            if out:
                result.save(out / "results" / _safe(system) / f"{_safe(item.id)}.json")
            score = await scorer.score(item, result)
            return _row(system, item, result, score, None)

    tasks: list[Any] = [one(name, wf, item) for name, wf in systems.items() for item in items]
    rows = list(await asyncio.gather(*tasks))
    report = BenchmarkReport(
        scorer=scorer.name,
        model_graded=any(r.model_graded for r in rows),
        n_items=len(items),
        summaries=[summarize(name, [r for r in rows if r.system == name]) for name in systems],
        rows=rows,
    )
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        (out / "report.md").write_text(report.to_markdown(), encoding="utf-8")
    return report


async def rescore(
    results_dir: str | Path, items: Sequence[EvalItem], scorer: Scorer
) -> BenchmarkReport:
    """Re-score saved results (``<dir>/results/<system>/<item>.json``) without re-running models."""
    base = Path(results_dir) / "results"
    by_id = {_safe(i.id): i for i in items}
    rows: list[BenchmarkRow] = []
    systems = sorted(p.name for p in base.iterdir() if p.is_dir())
    for system in systems:
        for path in sorted((base / system).glob("*.json")):
            item = by_id.get(path.stem)
            if item is None:
                continue
            result = AdverSIResult.load(path)
            rows.append(_row(system, item, result, await scorer.score(item, result), None))
    return BenchmarkReport(
        scorer=scorer.name,
        model_graded=any(r.model_graded for r in rows),
        n_items=len(items),
        summaries=[summarize(s, [r for r in rows if r.system == s]) for s in systems],
        rows=rows,
    )
