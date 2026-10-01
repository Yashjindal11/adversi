# Benchmarks

`smoke.jsonl` is a five-item **smoke test** that checks the benchmark pipeline runs end to
end. It is not a benchmark; do not report numbers from it.

```bash
adversi benchmark benchmarks/smoke.jsonl --modes simple,adversarial --model ollama:llama3.1:8b --profile fast
```

Real experiments, their configs, raw results and analysis scripts will live in
subdirectories here, one per experiment, following the checklist in
[docs/research.md](../docs/research.md).
