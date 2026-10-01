# Evaluation

The evaluation harness exists to test, not to advertise. No results are published with
this release because no experiments have been run.

## Datasets

JSONL, one item per line:

```json
{"id": "q1", "question": "...", "answer": "Paris", "accepted_answers": ["paris, france"], "context": "optional", "metadata": {"source": "..."}}
```

`benchmarks/smoke.jsonl` contains a handful of items to check that the pipeline runs. It is
not a benchmark and its numbers mean nothing. For real experiments use established
datasets with clear licenses (e.g. TruthfulQA, StrategyQA, FEVER-style claim
verification, GSM8K for arithmetic reasoning), keeping a held-out split you never tune
prompts on.

## Running

```bash
adversi benchmark data.jsonl --modes simple,adversarial,research \
  --model openai:gpt-4o-mini --profile fast --scorer contains --output-dir out/
adversi evaluate out/ data.jsonl --scorer llm_grader --grader anthropic:claude-sonnet-4-5
```

```python
from adversi import AdverSI
from adversi.evaluation import ContainsAnswer, load_dataset, run_benchmark

items = load_dataset("data.jsonl")
systems = {mode: AdverSI("openai:gpt-4o-mini", mode=mode, profile="fast").workflow
           for mode in ("simple", "adversarial")}
report = await run_benchmark(items, systems, ContainsAnswer(), output_dir="out")
print(report.to_markdown())
```

Every run's full `AdverSIResult` is saved under `out/results/<system>/<item>.json`, so
results can be re-scored with a different scorer without new model calls.

## Metrics

| Metric | Definition | Caveat |
|---|---|---|
| Accuracy + 95% CI | Wilson score interval | Small n gives wide intervals; overlapping intervals are not evidence of a difference |
| Brier score | mean (confidence - correct)^2 using `uncertainty.answer_confidence` | Judged confidence for multi-agent modes; the model's self-stated confidence in `simple` mode, so the two are not the same kind of number |
| ECE | 10-bin expected calibration error | Unstable below a few hundred items |
| Disagreement AUROC | Does `verdict_entropy` rank wrong answers above right ones? | Verdicts are compared lexically |
| Tokens, cost, latency | From run metadata | Cost requires configured prices |

## Scorers

- `exact_match`, `contains` (normalized, whole-word)
- `llm_grader`: model-graded; reported as `model_graded` in the report. Use a different
  model family from the systems under test and spot-check its judgments.

## Pitfalls

- Compare at equal budget where possible (e.g. `simple` with a larger model vs `research`
  with a smaller one); report cost alongside accuracy.
- Fix seeds/temperature where providers allow it and record config (it is in each
  result's metadata).
- Watch for contamination: models may have memorized public benchmarks.
- Report failures (`failures` column); do not silently drop them.
