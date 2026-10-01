"""Evidence research (tool-driven) and evidence analysis."""

from __future__ import annotations

from typing import Any

from adversi.agents.agent import Agent
from adversi.agents.outputs import Citation, EvidenceAssessmentDraft, ResearchDraft
from adversi.observability.events import EventType
from adversi.orchestration.context import RunContext
from adversi.protocol.claims import Claim, ClaimType
from adversi.protocol.evidence import EvidenceRelation
from adversi.workflows.base import Step
from adversi.workflows.steps._common import call_agent

_CHECKABLE = {
    ClaimType.FACTUAL,
    ClaimType.CAUSAL,
    ClaimType.STATISTICAL,
    ClaimType.PREDICTIVE,
    ClaimType.OTHER,
}


class EvidenceResearch(Step):
    """A researcher gathers external evidence for and against the most important claims.

    Findings must quote a source that exists in the run (tool output or user document);
    the step refuses to run without any retrieval capability rather than letting a
    model "research" from memory.
    """

    kind = "evidence_research"

    def __init__(self, agent: Agent | None = None, *, max_claims: int = 6, **kw: Any) -> None:
        super().__init__(**kw)
        self.agent = agent or Agent("researcher")
        self.max_claims = max_claims

    @property
    def agents(self) -> list[Agent]:
        return [self.agent]

    def config(self) -> dict[str, Any]:
        return {"max_claims": self.max_claims}

    def select_claims(self, ctx: RunContext) -> list[Claim]:
        """Prioritise checkable claims with little external evidence and many proponents."""
        candidates = [c for c in ctx.claims.all() if c.claim_type in _CHECKABLE]
        challenged = {ch.target_claim_id for ch in ctx.challenges.values()}

        def key(c: Claim) -> tuple[int, int, int]:
            external = sum(1 for e in ctx.evidence.for_claim(c.id) if e.is_external)
            return (external, -int(c.id in challenged), -len(c.attributions))

        return sorted(candidates, key=key)[: self.max_claims]

    async def run(self, ctx: RunContext) -> None:
        if not ctx.tools_for(self.agent) and not ctx.document_sources:
            ctx.events.emit(
                EventType.WARNING,
                step=self.name,
                agent=self.agent.name,
                message="evidence research skipped: no retrieval tools or documents configured",
            )
            return
        targets = self.select_claims(ctx)
        if not targets:
            return
        task = (
            f"{ctx.question_block()}\n\nClaims to research:\n"
            f"{ctx.claims_block([c.id for c in targets])}\n\n"
            f"Sources already in this run:\n{ctx.sources_block()}\n\n"
            "Find evidence that supports AND evidence that contradicts these claims. Report each "
            "finding as a verbatim excerpt with its source id and the claim ids it bears on. "
            "List what you searched for but could not find under gaps."
        )
        draft = await call_agent(ctx, self.agent, step=self.name, task=task, schema=ResearchDraft)
        for f in draft.findings:
            ctx.cite(
                Citation(source_id=f.source_id, excerpt=f.excerpt),
                agent=self.agent.name,
                step=self.name,
                supports=f.supports,
                contradicts=f.contradicts,
            )
        ctx.unresolved_questions.extend(f"Evidence gap: {g}" for g in draft.gaps)


class EvidenceAnalysis(Step):
    """Re-examines each evidence-claim link: relation and source reliability.

    The analyst may reclassify or drop existing links but cannot create new ones.
    """

    kind = "evidence_analysis"

    def __init__(self, agent: Agent | None = None, *, max_links: int = 40, **kw: Any) -> None:
        super().__init__(**kw)
        self.agent = agent or Agent("evidence_analyst")
        self.max_links = max_links

    @property
    def agents(self) -> list[Agent]:
        return [self.agent]

    def config(self) -> dict[str, Any]:
        return {"max_links": self.max_links}

    async def run(self, ctx: RunContext) -> None:
        links: list[tuple[str, str, str]] = []
        for e in ctx.evidence.all():
            links += [(e.id, c, "supports") for c in e.supports]
            links += [(e.id, c, "contradicts") for c in e.contradicts]
        links = links[: self.max_links]
        if not links:
            return
        lines = []
        for eid, cid, rel in links:
            e = ctx.evidence.get(eid)
            p = e.provenance
            lines.append(
                f"- {eid} -> {cid} (currently {rel})\n  claim: {ctx.claims.get(cid).statement}\n"
                f'  source: {p.source_type.value} {p.title or ""} {p.uri or ""}\n  excerpt: "{e.excerpt}"'
            )
        task = (
            f"Question: {ctx.question}\n\nEvidence links to assess:\n"
            + "\n".join(lines)
            + "\n\nAssess every link."
        )
        draft = await call_agent(
            ctx,
            self.agent,
            step=self.name,
            task=task,
            schema=EvidenceAssessmentDraft,
            allow_tools=False,
        )
        known = {(eid, cid) for eid, cid, _ in links}
        reliability: dict[str, list[float]] = {}
        rationale: dict[str, str] = {}
        for a in draft.assessments:
            if (a.evidence_id, a.claim_id) not in known:
                continue
            relation = None if a.relation == "irrelevant" else EvidenceRelation(a.relation)
            ctx.evidence.link(a.evidence_id, a.claim_id, relation)
            reliability.setdefault(a.evidence_id, []).append(a.reliability)
            if a.rationale:
                rationale[a.evidence_id] = a.rationale
        for eid, values in reliability.items():
            e = ctx.evidence.get(eid)
            e.reliability = min(values)
            e.reliability_rationale = rationale.get(eid)
