"""Interpretation, independent analysis, position exchange, claim consolidation, assumptions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from adversi.agents.agent import Agent
from adversi.agents.outputs import AnalysisDraft, AssumptionDraft
from adversi.orchestration.context import RunContext
from adversi.protocol.outcome import Interpretation
from adversi.protocol.reasoning import Perspective
from adversi.workflows.base import Step, StepError
from adversi.workflows.steps._common import call_agent, call_agents, clip

INDEPENDENT_TASK = """\
{question}

Analyse this question on your own. You cannot see other agents' work and they cannot \
see yours. Produce your verdict, position, atomic claims (with citations where sources \
exist), assumptions, counterarguments to your own view, uncertainties and open questions."""

EXCHANGE_TASK = """\
{question}

Your previous analysis:
verdict: {verdict}
position: {position}

Other agents' independent analyses (structured summaries only):
{others}

Current claims:
{claims}

Revise your analysis. Change your view only for reasons you can name (new evidence, a flaw \
in your argument); agreement by others is not itself a reason. Return a full analysis."""


class Interpret(Step):
    """Restate and decompose the question before analysis (problem decomposition)."""

    kind = "interpret"

    def __init__(self, agent: Agent | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.agent = agent or Agent("moderator")

    @property
    def agents(self) -> list[Agent]:
        return [self.agent]

    async def run(self, ctx: RunContext) -> None:
        ctx.interpretation = await call_agent(
            ctx,
            self.agent,
            step=self.name,
            task=ctx.question_block(),
            schema=Interpretation,
            allow_tools=False,
        )


class IndependentAnalysis(Step):
    """Agents analyse in parallel, each seeing only the question material.

    Independence is structural: the task text is built from the question block alone,
    and outputs are ingested only after every agent has finished.
    """

    kind = "independent_analysis"

    def __init__(self, agents: Sequence[Agent], *, min_successful: int = 1, **kw: Any) -> None:
        kw.setdefault("required", True)
        super().__init__(**kw)
        if not agents:
            raise ValueError("IndependentAnalysis needs at least one agent")
        names = [a.name for a in agents]
        if len(set(names)) != len(names):
            raise ValueError(f"agent names must be unique within a step, got {names}")
        self._agents = list(agents)
        self.min_successful = min_successful

    @property
    def agents(self) -> list[Agent]:
        return self._agents

    def config(self) -> dict[str, Any]:
        return {"n_agents": len(self._agents), "min_successful": self.min_successful}

    async def run(self, ctx: RunContext) -> None:
        task = INDEPENDENT_TASK.format(question=ctx.question_block())
        drafts = await call_agents(
            ctx, self._agents, [task] * len(self._agents), step=self.name, schema=AnalysisDraft
        )
        ok = 0
        for agent, draft in zip(self._agents, drafts, strict=True):
            if draft is None:
                continue
            ok += 1
            ctx.perspectives.append(_perspective(ctx, agent, draft, step=self.name, round=0))
        if ok < self.min_successful:
            raise StepError(f"only {ok} of {len(self._agents)} agents produced an analysis")


class PositionExchange(Step):
    """Agents see each other's structured positions and may revise (peer review)."""

    kind = "position_exchange"

    def __init__(self, agents: Sequence[Agent], *, rounds: int = 1, **kw: Any) -> None:
        super().__init__(**kw)
        self._agents = list(agents)
        self.rounds = rounds

    @property
    def agents(self) -> list[Agent]:
        return self._agents

    def config(self) -> dict[str, Any]:
        return {"rounds": self.rounds}

    async def run(self, ctx: RunContext) -> None:
        for r in range(1, self.rounds + 1):
            latest = _latest_by_agent(ctx.perspectives)
            participants = [a for a in self._agents if a.name in latest]
            tasks = []
            for agent in participants:
                own = latest[agent.name]
                others = "\n".join(
                    f"- {p.agent} ({p.role}) verdict={p.verdict!r} confidence={p.confidence}: {clip(p.position, 500)} "
                    f"claims={', '.join(p.claim_ids)}"
                    for name, p in latest.items()
                    if name != agent.name
                )
                tasks.append(
                    EXCHANGE_TASK.format(
                        question=ctx.question_block(),
                        verdict=own.verdict,
                        position=own.position,
                        others=others or "(none)",
                        claims=ctx.claims_block(),
                    )
                )
            drafts = await call_agents(
                ctx, participants, tasks, step=self.name, schema=AnalysisDraft
            )
            for agent, draft in zip(participants, drafts, strict=True):
                if draft is not None:
                    ctx.perspectives.append(
                        _perspective(ctx, agent, draft, step=self.name, round=r)
                    )


class ClaimConsolidation(Step):
    """Deterministically merge near-duplicate claims asserted by different agents.

    Agents emit atomic claims as structured output at generation time; this step
    consolidates them. It never calls a model.
    """

    kind = "claim_consolidation"

    def __init__(self, *, threshold: float = 0.85, **kw: Any) -> None:
        super().__init__(**kw)
        self.threshold = threshold

    def config(self) -> dict[str, Any]:
        return {"threshold": self.threshold}

    async def run(self, ctx: RunContext) -> None:
        ctx.remap_claims(ctx.claims.consolidate(self.threshold))


class AssumptionAnalysis(Step):
    kind = "assumption_analysis"

    def __init__(self, agent: Agent | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.agent = agent or Agent("assumption_analyst")

    @property
    def agents(self) -> list[Agent]:
        return [self.agent]

    async def run(self, ctx: RunContext) -> None:
        if not len(ctx.claims):
            return
        task = (
            f"{ctx.question_block(documents=False)}\n\nClaims:\n{ctx.claims_block(with_evidence=False)}\n\n"
            f"Assumptions already identified:\n{ctx.assumptions_block()}\n\n"
            "Identify additional hidden assumptions, linking each to the claim ids that depend on it."
        )
        draft = await call_agent(
            ctx, self.agent, step=self.name, task=task, schema=AssumptionDraft, allow_tools=False
        )
        for item in draft.assumptions:
            ids = ctx.valid_claim_ids(item.claim_ids)
            if ids:
                ctx.claims.add_assumption(
                    item.statement,
                    identified_by=self.agent.name,
                    claim_ids=ids,
                    critical=item.critical,
                )


def _perspective(
    ctx: RunContext, agent: Agent, draft: AnalysisDraft, *, step: str, round: int
) -> Perspective:
    claim_ids = ctx.ingest_claims(draft.claims, agent=agent, step=step)
    assumption_ids = sorted({a for cid in claim_ids for a in ctx.claims.get(cid).assumption_ids})
    return Perspective(
        agent=agent.name,
        role=agent.role.name,
        model=ctx.agents_used.get(agent.name, ""),
        step=step,
        round=round,
        verdict=draft.verdict,
        position=draft.position,
        summary=draft.summary,
        claim_ids=claim_ids,
        assumption_ids=assumption_ids,
        counterarguments=draft.counterarguments,
        uncertainties=draft.uncertainties,
        open_questions=draft.open_questions,
        confidence=draft.confidence,
    )


def _latest_by_agent(perspectives: Sequence[Perspective]) -> dict[str, Perspective]:
    latest: dict[str, Perspective] = {}
    for p in perspectives:
        if p.agent not in latest or p.round >= latest[p.agent].round:
            latest[p.agent] = p
    return latest
