# Design decisions

Short records of choices where reasonable alternatives existed.

### D1. Pydantic records + separate LLM draft schemas
**Alternatives:** dataclasses; one schema for both model output and storage.
**Choice:** Pydantic v2 for validation and JSON Schema generation. Separate draft schemas
so the model never supplies ids, statuses or verification flags.
**Trade-off:** some mapping code in steps.

### D2. No agent framework dependency
**Alternatives:** LangChain, LlamaIndex, AutoGen, LiteLLM.
**Choice:** a 150-line `ModelProvider` interface and one OpenAI-compatible adapter
(covering OpenAI, Gemini, Ollama, vLLM, HF, LM Studio) plus Anthropic.
**Why:** small, stable surface for a single maintainer; no transitive dependency churn;
the interesting logic (claims, evidence, policy) is ours anyway.
**Trade-off:** fewer providers out of the box; mitigated by the plugin entry point.

### D3. Async-first core, sync wrappers
Model and tool calls are I/O bound and independent agents must run concurrently.
`run_sync()` wraps `asyncio.run`. Event handlers are synchronous (cheap, non-blocking) so
the bus never needs an event loop; async consumers push to a queue.

### D4. Citation verification by normalized substring
**Alternatives:** semantic similarity; LLM-checked entailment.
**Choice:** case/punctuation/whitespace-insensitive substring match with ellipsis support
and a minimum length.
**Why:** deterministic, explainable, cannot be talked into accepting a paraphrase.
**Trade-off:** rejects legitimate paraphrases (by design; agents are told to quote).
Whether the excerpt *supports* the claim is a separate question handled by
`EvidenceAnalysis` and visible in the record.

### D5. Rule-based status policy instead of trusting the judge
The judge proposes; code disposes. Rules are deliberately few and documented in
`StatusPolicy`. A configurable switch allows reasoning-only support for domains (logic,
definitions) where external evidence is not meaningful.

### D6. No majority voting
Agreement among models that share training data is weak evidence. Attribution counts are
recorded (useful for research) but never used to set status. Jury disagreement yields
`uncertain`.

### D7. Lexical claim consolidation
**Alternatives:** embeddings; LLM clustering.
**Choice:** Jaccard over content words, refusing to merge when negations or numbers
differ. Errs toward keeping duplicates, the safe failure mode (a wrong merge hides a
disagreement). Semantic consolidation is on the roadmap as an optional step.

### D8. Standard-library CLI
argparse instead of Click/Typer keeps the core at two dependencies. The CLI is thin; all
behaviour lives in the library.

### D9. Server as an optional subpackage
`adversi.server` ships in the wheel but its dependencies are an extra. The core never
imports it. The built UI is bundled so `adversi serve` needs no Node toolchain.

### D10. No bundled price table
Prices change and silently wrong cost numbers are worse than none. Cost is `None` unless
prices are configured.

### D11. Sequential, human-readable ids (C1, E2, X3)
Easier for models to reference and for humans to read than UUIDs; unique within a run,
which is the scope that matters. Run ids are random.
