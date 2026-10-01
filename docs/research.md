# Research agenda

The core question:

> Does structured adversarial multi-agent reasoning improve the reliability of AI systems
> compared with a single model, and at what cost?

AdverSI does not assume the answer is yes. Prior work on multi-agent debate reports mixed
results: gains on some reasoning tasks, little or none on others, and sensitivity to
model strength, prompt design and aggregation. AdverSI's contribution is
infrastructure for testing this under controlled, reproducible conditions, with
explicit claim/evidence structure that most debate setups lack.

## Questions and how to test them with AdverSI

| # | Question | Experimental handle |
|---|---|---|
| 1 | Does adversarial reasoning improve factuality? | `simple` vs `adversarial` vs `research` on a fact-verification set; accuracy + CI |
| 2 | Does independent reasoning reduce correlated errors? | `peer_review` (exchange) vs `adversarial` (no exchange); measure verdict changes in `position_exchange` toward the majority without new evidence (conformity) |
| 3 | Does model diversity improve robustness? | Same workflow with homogeneous vs heterogeneous `models=` maps |
| 4 | When does multi-agent reasoning hurt? | Per-item comparison: items `simple` gets right and `research` gets wrong; inspect traces |
| 5 | How many agents are useful? | Sweep `analysts=1..6` at fixed rounds |
| 6 | How many debate rounds? | Sweep `debate_rounds`, `cross_examination_rounds`; early-stop statistics from events |
| 7 | Does a dedicated skeptic reduce hallucination? | Ablate `cross_examination`; measure `citation_rejection_rate` and contradicted-claim rates |
| 8 | Does evidence verification improve judgment? | `StatusPolicy(require_external_evidence=False)` vs default; calibration (Brier/ECE) |
| 9 | Improvement per unit cost? | Accuracy vs total tokens/cost across modes and profiles (Pareto frontier) |
| 10 | Is disagreement an uncertainty signal? | AUROC of `verdict_entropy` (and `confidence_spread`) for predicting errors |

## Reproducibility checklist

- Pin `adversi` version; each result records it, the schema version and role versions.
- Record full configuration (stored in `metadata.config`).
- Use `temperature=0` and `seed` where supported; report remaining nondeterminism by
  repeating runs.
- Enable the SQLite cache to make re-analysis free and exact.
- Publish datasets, configs, raw result JSON and the analysis script.

## Known limitations of the current implementation

- Claim consolidation is lexical; paraphrased duplicates stay separate.
- Verdict entropy compares short verdict strings lexically.
- Citation verification checks that a quote exists, not that it supports the claim; the
  latter is delegated to `EvidenceAnalysis` (a model).
- The status policy is a small rule set and has not been validated against human labels.

Results will be added here only after experiments are run and can be reproduced.
