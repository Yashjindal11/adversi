from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from adversi import AdverSI
from adversi.evaluation import (
    ContainsAnswer,
    EvalItem,
    ExactMatch,
    auroc,
    brier_score,
    expected_calibration_error,
    load_dataset,
    rescore,
    run_benchmark,
    wilson_interval,
)
from adversi.protocol import AdverSIResult, Claim, RunMetadata, Synthesis
from adversi.testing import scripted_model
from tests.conftest import analysis


def _result(answer: str = "Paris", question: str = "<script>alert(1)</script>") -> AdverSIResult:
    return AdverSIResult(
        question=question,
        claims=[Claim(id="C1", statement="A | pipe <b>claim</b>")],
        synthesis=Synthesis(answer=answer),
        metadata=RunMetadata(
            run_id="r",
            adversi_version="0",
            schema_version="1.0",
            workflow="w",
            started_at=datetime.now(UTC),
        ),
    )


# -- schema & rendering -------------------------------------------------------------


def test_result_round_trip_and_forward_compatibility() -> None:
    r = _result()
    data = json.loads(r.to_json())
    data["future_field"] = {"x": 1}
    data["claims"][0]["new_claim_field"] = True
    loaded = AdverSIResult.model_validate(data)
    assert loaded.claims[0].statement == r.claims[0].statement


def test_html_escapes_untrusted_text() -> None:
    html = _result().to_html()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html and "&lt;b&gt;claim" in html


def test_markdown_escapes_table_pipes() -> None:
    md = _result().to_markdown()
    assert "A \\| pipe" in md and "## Answer" in md and "## Run metadata" in md


# -- evaluation ---------------------------------------------------------------------


def test_metrics() -> None:
    lo, hi = wilson_interval(8, 10) or (0, 0)
    assert 0.49 < lo < 0.5 and 0.94 < hi < 0.95
    assert wilson_interval(0, 0) is None
    assert brier_score([1.0, 0.0], [True, False]) == 0
    assert brier_score([0.5], [True]) == 0.25
    assert auroc([0.9, 0.8, 0.1], [True, True, False]) == 1.0
    assert auroc([0.5, 0.5], [True, False]) == 0.5
    assert expected_calibration_error([0.9] * 10, [True] * 9 + [False]) == pytest.approx(0.0)


async def test_scorers() -> None:
    item = EvalItem(id="1", question="Capital?", answer="Paris", accepted_answers=["paris france"])
    assert (await ExactMatch().score(item, _result("paris."))).correct
    assert (await ContainsAnswer().score(item, _result("It is Paris."))).correct
    assert not (await ContainsAnswer().score(item, _result("Parisian food"))).correct
    assert (await ContainsAnswer().score(EvalItem(id="2", question="q"), _result())).correct is None


async def test_contains_scorer_handles_yes_no_by_leading_word() -> None:
    item = EvalItem(id="1", question="Is it?", answer="no")
    assert (await ContainsAnswer().score(item, _result("No. It is not."))).correct
    # "no" appears later in the text, but the answer is "yes"
    assert not (
        await ContainsAnswer().score(item, _result("Yes, although there is no proof."))
    ).correct


async def test_benchmark_and_rescore(tmp_path) -> None:
    ds = tmp_path / "d.jsonl"
    ds.write_text(
        '{"id": "a", "question": "Capital of France?", "answer": "Paris"}\n'
        '{"id": "../../escape", "question": "2+2?", "answer": "4"}\n'
    )
    items = load_dataset(ds)

    def answers(r):
        q = r.messages[-1].content
        return {**analysis("x", [], 0.8), "position": "Paris" if "France" in q else "5"}

    systems = {"simple": AdverSI(scripted_model(answers), mode="simple").workflow}
    report = await run_benchmark(items, systems, ContainsAnswer(), output_dir=tmp_path / "out")
    s = report.summaries[0]
    assert (s.n, s.scored, s.accuracy, s.failures) == (2, 2, 0.5, 0)
    # simple mode reports the single model's own stated confidence (0.8) for calibration
    assert s.brier == pytest.approx(((0.8 - 1) ** 2 + 0.8**2) / 2)
    saved = sorted(p.name for p in (tmp_path / "out" / "results" / "simple").iterdir())
    assert saved == ["_.._escape.json", "a.json"]  # dataset ids cannot escape the output dir
    assert "Small samples" in report.to_markdown()

    again = await rescore(tmp_path / "out", items, ContainsAnswer())
    assert again.summaries[0].accuracy == 0.5 and again.summaries[0].scored == 2
