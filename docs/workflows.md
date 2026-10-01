# Workflows, modes and profiles

A `Workflow` is an ordered list of `Step`s sharing one `RunContext`.

## Built-in steps

| Step | Calls models | What it does |
|---|---|---|
| `Interpret(agent)` | 1 | Restates and decomposes the question; lists ambiguities |
| `IndependentAnalysis(agents)` | n, concurrent | Each agent analyses alone; outputs ingested only after all finish. Required by default |
| `PositionExchange(agents, rounds)` | n per round | Agents see others' structured positions (not reasoning) and revise |
| `ClaimConsolidation(threshold)` | 0 | Merges near-duplicate claims (lexical, negation/number-safe) |
| `AssumptionAnalysis(agent)` | 1 | Adds hidden assumptions linked to claims |
| `EvidenceResearch(agent, max_claims)` | 1 + tool rounds | Researches the least-evidenced checkable claims; skipped without tools or documents |
| `EvidenceAnalysis(agent, max_links)` | 1 | Re-labels each evidence-claim link and rates reliability; cannot create links |
| `Debate(proponent, skeptic, rounds)` | 2 per round | Position-level exchange; stops when a side concedes |
| `CrossExamination(challengers, defender, rounds)` | 2 per round | Claim-level challenges and rebuttals; stops when no new challenges |
| `Critique(agent)` | 1 | Audits the reasoning process |
| `Judgment(judges)` | 1 per judge | Proposes statuses, validated by `StatusPolicy`; multiple judges = jury |
| `Synthesis(agent)` | 1 (0 with `agent=None`) | Writes the final answer; claim bins are computed in code |

## Modes

```text
simple       single_analysis -> passthrough_synthesis
debate       single_analysis -> debate -> judgment -> synthesis
adversarial  independent_analysis -> claim_consolidation -> cross_examination -> critique -> judgment -> synthesis
research     interpret -> independent_analysis -> claim_consolidation -> assumption_analysis
             -> evidence_research -> evidence_analysis -> debate -> cross_examination -> critique -> judgment -> synthesis
peer_review  independent_analysis -> claim_consolidation -> position_exchange -> critique -> judgment -> synthesis
jury         independent_analysis -> claim_consolidation -> cross_examination -> jury -> synthesis
```

These names are also valid entries in a config file's `workflow.steps` list.

## Profiles

| | fast | balanced | deep |
|---|---|---|---|
| independent analysts | 2 | 3 | 4 |
| debate rounds | 1 | 2 | 3 |
| cross-examination rounds | 1 | 1 | 2 |
| max challenges per round | 4 | 6 | 8 |
| claims researched | 3 | 6 | 10 |
| tool rounds per agent | 2 | 4 | 8 |
| jurors (jury mode) | 2 | 3 | 3 |

Override any field: `AdverSI(..., profile="fast", debate_rounds=3)` or in config.

Default analysts are deliberately diverse: a generalist, a statistician, a risk-focused
analyst (or a domain expert when `domain=` is set), and a first-principles analyst.

## Models per role

Resolution order for each agent: the agent's own `model`, then `models[agent.name]`, then
`models[role.name]`, then the default.

```python
AdverSI(
    "openai:gpt-4o-mini",
    models={"judge": "anthropic:claude-sonnet-4-5", "skeptic": "ollama:llama3.1:8b", "judge_2": "gemini:gemini-2.0-flash"},
    mode="jury",
)
```

## Failure semantics

- Agent failures inside a concurrent step are recorded as `RunError`s; the step continues
  with the remaining agents.
- A failing optional step is recorded and the workflow continues.
- A failing required step or an exhausted `Budget` stops the workflow.
- `Workflow(fail_fast=True)` raises instead.
- The returned result's `metadata.status` is `completed`, `partial` or `failed`.

## Writing a step

```python
from adversi import Step
from adversi.orchestration import RunContext

class FlagSingleSource(Step):
    kind = "flag_single_source"

    async def run(self, ctx: RunContext) -> None:
        for claim in ctx.claims.all():
            sources = {e.source_id for e in ctx.evidence.for_claim(claim.id) if e.is_external}
            if len(sources) == 1:
                ctx.unresolved_questions.append(f"{claim.id} rests on a single source.")
```

Steps can call agents with `adversi.workflows.steps.call_agent` / `call_agents` (concurrency-limited,
failures recorded) or `agent.respond(...)` directly, and should write only through `RunContext` helpers.
