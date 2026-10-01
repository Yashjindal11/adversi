# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Result schema versions are tracked
separately as `RESULT_SCHEMA_VERSION`.

## [Unreleased]

## [0.1.0] - 2026-10-01

### Added
- Reasoning protocol: claims (typed, with basis and status), assumptions, sources,
  evidence with provenance, perspectives, debate turns, challenges and rebuttals,
  critique findings, judgment, synthesis, uncertainty signals, run metadata.
  Result schema `1.0`.
- Citation verification against source text; rejected citations are recorded.
- Deterministic `StatusPolicy` validating judge-proposed claim statuses.
- Workflow engine with steps: Interpret, IndependentAnalysis, PositionExchange,
  ClaimConsolidation, AssumptionAnalysis, EvidenceResearch, EvidenceAnalysis, Debate,
  CrossExamination, Critique, Judgment (single or jury), Synthesis.
- Modes `simple`, `debate`, `adversarial`, `research`, `peer_review`, `jury`; profiles
  `fast`, `balanced`, `deep`.
- Providers: OpenAI, Anthropic, Gemini (OpenAI-compatible endpoint), Ollama, Hugging Face,
  generic OpenAI-compatible; registry with entry-point plugins.
- `Model` with retries, timeouts, concurrency and rate limits, response caching
  (memory/SQLite), token and cost accounting, budgets.
- Tools: generic `Tool`/`@tool`, executor, calculator, SSRF-guarded `fetch_url`,
  `web_search` (Brave backend), BM25 document search.
- Structured event stream with JSONL and logging sinks.
- CLI: `init`, `run`, `debate`, `inspect`, `report`, `providers`, `config`, `benchmark`,
  `evaluate`, `serve`.
- Web server (FastAPI, REST + WebSocket) and React/TypeScript UI.
- Evaluation harness: datasets, exact/contains/LLM-graded scorers, Wilson intervals, Brier,
  ECE, disagreement AUROC, re-scoring of saved results.
