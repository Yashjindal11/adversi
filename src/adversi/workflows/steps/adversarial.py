"""Adversarial steps: debate, cross-examination and critique."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from adversi.agents.agent import Agent
from adversi.agents.outputs import ChallengeDraft, CritiqueDraft, DebateTurnDraft, RebuttalDraft
from adversi.observability.events import EventType
from adversi.orchestration.context import RunContext
from adversi.protocol.reasoning import (
    Challenge,
    ChallengeOutcome,
    CritiqueFinding,
    DebateTurn,
    Rebuttal,
)
from adversi.workflows.base import Step
from adversi.workflows.steps._common import call_agent, call_agents, clip

_ID = re.compile(r"^[CEXAS]\d+$")


class Debate(Step):
    """Position-level exchange between a proponent and a skeptic.

    Each round the proponent argues, then the skeptic responds, both seeing the full
    claim/evidence record and prior turns. Stops early when either side concedes.
    """

    kind = "debate"

    def __init__(
        self,
        proponent: Agent | None = None,
        skeptic: Agent | None = None,
        *,
        rounds: int = 2,
        **kw: Any,
    ) -> None:
        super().__init__(**kw)
        self.proponent = proponent or Agent("proponent")
        self.skeptic = skeptic or Agent("skeptic")
        self.rounds = rounds

    @property
    def agents(self) -> list[Agent]:
        return [self.proponent, self.skeptic]

    def config(self) -> dict[str, Any]:
        return {"rounds": self.rounds}

    def _task(self, ctx: RunContext, side: str) -> str:
        verdicts = "\n".join(
            f"- {p.agent}: verdict={p.verdict!r} confidence={p.confidence}"
            for p in ctx.perspectives
            if p.round == 0
        )
        return (
            f"{ctx.question_block(documents=False)}\n\nIndependent verdicts:\n{verdicts or '(none)'}\n\n"
            f"Claims and evidence:\n{ctx.claims_block()}\n\nDebate so far:\n{ctx.debate_block()}\n\n"
            f"You argue {side}. Reference claim ids. Add new claims only if needed and atomic. "
            "Set concedes=true if you can no longer defend your side."
        )

    async def run(self, ctx: RunContext) -> None:
        for r in range(1, self.rounds + 1):
            for agent, side in (
                (self.proponent, "for the most plausible answer"),
                (self.skeptic, "against it"),
            ):
                draft = await call_agent(
                    ctx,
                    agent,
                    step=self.name,
                    task=self._task(ctx, side),
                    schema=DebateTurnDraft,
                    allow_tools=False,
                )
                new_ids = ctx.ingest_claims(draft.new_claims, agent=agent, step=self.name)
                turn = DebateTurn(
                    round=r,
                    agent=agent.name,
                    role=agent.role.name,
                    stance=draft.stance,
                    argument=draft.argument,
                    claim_ids=ctx.valid_claim_ids([*draft.claim_ids, *new_ids]),
                    concedes=draft.concedes,
                )
                ctx.debate.append(turn)
                ctx.events.emit(
                    EventType.DEBATE_TURN,
                    step=self.name,
                    agent=agent.name,
                    round=r,
                    stance=turn.stance.value,
                    concedes=turn.concedes,
                )
                if draft.concedes:
                    return


class CrossExamination(Step):
    """Claim-level challenges and rebuttals.

    Challengers attack specific claims; the defender answers or concedes each
    challenge. Stops early when a round produces no new challenges.
    """

    kind = "cross_examination"

    def __init__(
        self,
        challengers: Sequence[Agent] | None = None,
        defender: Agent | None = None,
        *,
        rounds: int = 1,
        max_challenges_per_round: int = 6,
        **kw: Any,
    ) -> None:
        super().__init__(**kw)
        self.challengers = list(challengers) if challengers else [Agent("skeptic")]
        self.defender = defender or Agent("proponent")
        self.rounds = rounds
        self.max_challenges_per_round = max_challenges_per_round

    @property
    def agents(self) -> list[Agent]:
        return [*self.challengers, self.defender]

    def config(self) -> dict[str, Any]:
        return {"rounds": self.rounds, "max_challenges_per_round": self.max_challenges_per_round}

    async def run(self, ctx: RunContext) -> None:
        if not len(ctx.claims):
            return
        for r in range(1, self.rounds + 1):
            task = (
                f"{ctx.question_block(documents=False)}\n\nClaims and evidence:\n{ctx.claims_block()}\n\n"
                f"Assumptions:\n{ctx.assumptions_block()}\n\nExisting challenges:\n{ctx.challenges_block()}\n\n"
                f"Raise up to {self.max_challenges_per_round} new, substantive challenges against specific "
                "claims. Do not repeat existing challenges. Return an empty list if none are warranted."
            )
            drafts = await call_agents(
                ctx,
                self.challengers,
                [task] * len(self.challengers),
                step=self.name,
                schema=ChallengeDraft,
                allow_tools=False,
            )
            new: list[Challenge] = []
            for agent, draft in zip(self.challengers, drafts, strict=True):
                for item in draft.challenges if draft else []:
                    if (
                        item.target_claim_id not in ctx.claims
                        or len(new) >= self.max_challenges_per_round
                    ):
                        continue
                    ch = Challenge(
                        id=f"X{len(ctx.challenges) + 1}",
                        target_claim_id=item.target_claim_id,
                        challenger=agent.name,
                        round=r,
                        kind=item.kind,
                        argument=item.argument,
                        evidence_ids=[e for e in item.evidence_ids if e in ctx.evidence],
                    )
                    ctx.challenges[ch.id] = ch
                    new.append(ch)
                    ctx.events.emit(
                        EventType.CHALLENGE_CREATED,
                        step=self.name,
                        agent=agent.name,
                        challenge_id=ch.id,
                        target=ch.target_claim_id,
                        kind=ch.kind.value,
                    )
            if not new:
                return
            await self._rebut(ctx, new, r)

    async def _rebut(self, ctx: RunContext, challenges: list[Challenge], round: int) -> None:
        listing = "\n".join(
            f"{ch.id} against {ch.target_claim_id} ({ctx.claims.get(ch.target_claim_id).statement}) "
            f"[{ch.kind.value}]: {ch.argument}"
            for ch in challenges
        )
        task = (
            f"{ctx.question_block()}\n\nClaims and evidence:\n{ctx.claims_block()}\n\n"
            f"Challenges to answer:\n{listing}\n\n"
            "Answer each challenge by id. Concede when the challenge is correct. You may cite "
            "sources in support of the challenged claim."
        )
        draft = await call_agent(
            ctx, self.defender, step=self.name, task=task, schema=RebuttalDraft, allow_tools=False
        )
        by_id = {ch.id: ch for ch in challenges}
        for item in draft.rebuttals:
            ch = by_id.get(item.challenge_id)
            if ch is None:
                continue
            evidence_ids = []
            for c in item.citations:
                ev = ctx.cite(
                    c, agent=self.defender.name, step=self.name, supports=[ch.target_claim_id]
                )
                if ev is not None:
                    evidence_ids.append(ev.id)
            ch.rebuttals.append(
                Rebuttal(
                    agent=self.defender.name,
                    round=round,
                    response=item.response,
                    concedes=item.concedes,
                    evidence_ids=evidence_ids,
                )
            )
            ch.outcome = ChallengeOutcome.CONCEDED if item.concedes else ChallengeOutcome.ANSWERED
            ctx.events.emit(
                EventType.REBUTTAL_CREATED,
                step=self.name,
                agent=self.defender.name,
                challenge_id=ch.id,
                concedes=item.concedes,
            )


class Critique(Step):
    """A critic audits the reasoning process recorded so far."""

    kind = "critique"

    def __init__(self, agent: Agent | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.agent = agent or Agent("critic")

    @property
    def agents(self) -> list[Agent]:
        return [self.agent]

    async def run(self, ctx: RunContext) -> None:
        perspectives = "\n".join(
            f"- {p.agent} (round {p.round}) verdict={p.verdict!r} confidence={p.confidence}: {clip(p.summary, 600)}"
            for p in ctx.perspectives
        )
        task = (
            f"{ctx.question_block(documents=False)}\n\nAgent perspectives:\n{perspectives or '(none)'}\n\n"
            f"Claims and evidence:\n{ctx.claims_block()}\n\nAssumptions:\n{ctx.assumptions_block()}\n\n"
            f"Debate:\n{ctx.debate_block()}\n\nChallenges:\n{ctx.challenges_block()}\n\n"
            f"Rejected citations (could not be verified): {len(ctx.evidence.rejected)}\n\n"
            "Report problems with the reasoning process."
        )
        draft = await call_agent(
            ctx, self.agent, step=self.name, task=task, schema=CritiqueDraft, allow_tools=False
        )
        known = (
            {c.id for c in ctx.claims.all()}
            | {e.id for e in ctx.evidence.all()}
            | set(ctx.challenges)
            | {a.id for a in ctx.claims.assumptions()}
        )
        for item in draft.findings:
            finding = CritiqueFinding(
                id=f"K{len(ctx.critique) + 1}",
                critic=self.agent.name,
                kind=item.kind,
                severity=item.severity,
                description=item.description,
                target_ids=[t for t in item.target_ids if _ID.match(t) and t in known],
            )
            ctx.critique.append(finding)
            ctx.events.emit(
                EventType.CRITIQUE_CREATED,
                step=self.name,
                agent=self.agent.name,
                finding_id=finding.id,
                kind=finding.kind.value,
                severity=finding.severity.value,
            )
