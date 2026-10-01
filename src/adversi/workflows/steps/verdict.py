"""Judgment (with policy-validated statuses) and synthesis."""

from __future__ import annotations

import re
import statistics
from collections.abc import Sequence
from typing import Any

from adversi.agents.agent import Agent
from adversi.agents.outputs import JudgmentDraft, SynthesisDraft
from adversi.observability.events import EventType
from adversi.orchestration.context import RunContext
from adversi.protocol.claims import ClaimStatus
from adversi.protocol.outcome import ClaimVerdict
from adversi.protocol.outcome import Judgment as JudgmentRecord
from adversi.protocol.outcome import Synthesis as SynthesisRecord
from adversi.protocol.reasoning import ChallengeOutcome
from adversi.workflows.base import Step, StepError
from adversi.workflows.steps._common import call_agents, clip

_CLAIM_REF = re.compile(r"\bC\d+\b")


def _record(ctx: RunContext) -> str:
    perspectives = "\n".join(
        f"- {p.agent} (round {p.round}) verdict={p.verdict!r} confidence={p.confidence}: {clip(p.position, 500)}"
        for p in ctx.perspectives
    )
    return (
        f"{ctx.question_block(documents=False)}\n\nAgent positions:\n{perspectives or '(none)'}\n\n"
        f'Claims and evidence ("external" = verbatim excerpt verified against a non-model source):\n'
        f"{ctx.claims_block()}\n\nAssumptions:\n{ctx.assumptions_block()}\n\n"
        f"Debate:\n{ctx.debate_block()}\n\nChallenges:\n{ctx.challenges_block()}\n\n"
        f"Critique:\n{ctx.critique_block()}"
    )


class Judgment(Step):
    """One or more judges propose claim statuses; :class:`StatusPolicy` validates them.

    With several judges (jury mode) there is no majority vote: a claim keeps a status
    only if every juror's validated status agrees; otherwise it becomes ``uncertain``
    and the split is recorded.
    """

    kind = "judgment"

    def __init__(self, judges: Agent | Sequence[Agent] | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        if judges is None:
            judges = [Agent("judge")]
        self.judges = [judges] if isinstance(judges, Agent) else list(judges)
        names = [j.name for j in self.judges]
        if len(set(names)) != len(names):
            raise ValueError(f"judge names must be unique, got {names}")

    @property
    def agents(self) -> list[Agent]:
        return self.judges

    def config(self) -> dict[str, Any]:
        return {"n_judges": len(self.judges)}

    async def run(self, ctx: RunContext) -> None:
        if not len(ctx.claims):
            raise StepError("nothing to judge: no claims were produced")
        task = _record(ctx) + "\n\nGive a verdict for every claim id, then an overall assessment."
        drafts = await call_agents(
            ctx,
            self.judges,
            [task] * len(self.judges),
            step=self.name,
            schema=JudgmentDraft,
            allow_tools=False,
        )
        pairs = [(j, d) for j, d in zip(self.judges, drafts, strict=True) if d is not None]
        if not pairs:
            raise StepError("no judge produced a judgment")

        evidence = ctx.evidence.all()
        challenges = list(ctx.challenges.values())
        verdicts: list[ClaimVerdict] = []
        per_claim: dict[str, list[ClaimVerdict]] = {}
        for judge, draft in pairs:
            seen: set[str] = set()
            for v in draft.verdicts:
                if v.claim_id not in ctx.claims or v.claim_id in seen:
                    continue
                seen.add(v.claim_id)
                claim = ctx.claims.get(v.claim_id)
                status, note = ctx.policy.validate(v.status, claim, evidence, challenges)
                cv = ClaimVerdict(
                    claim_id=v.claim_id,
                    judge=judge.name,
                    proposed_status=v.status,
                    status=status,
                    confidence=v.confidence,
                    rationale=v.rationale,
                    policy_note=note,
                )
                verdicts.append(cv)
                per_claim.setdefault(v.claim_id, []).append(cv)

        for claim_id, cvs in per_claim.items():
            claim = ctx.claims.get(claim_id)
            statuses = {cv.status for cv in cvs}
            if len(statuses) == 1:
                claim.status = cvs[0].status
                notes = [cv.policy_note for cv in cvs if cv.policy_note]
                claim.policy_note = notes[0] if notes else None
            else:
                claim.status = ClaimStatus.UNCERTAIN
                split = ", ".join(f"{cv.judge}={cv.status.value}" for cv in cvs)
                claim.policy_note = f"jurors disagreed ({split})"
            claim.proposed_status = cvs[0].proposed_status if len(cvs) == 1 else None
            claim.status_rationale = " | ".join(cv.rationale for cv in cvs if cv.rationale) or None
            confs = [cv.confidence for cv in cvs if cv.confidence is not None]
            claim.confidence = statistics.fmean(confs) if confs else None
            ctx.events.emit(
                EventType.CLAIM_STATUS,
                step=self.name,
                claim_id=claim_id,
                status=claim.status.value,
                proposed=[cv.proposed_status.value for cv in cvs],
                policy_note=claim.policy_note,
            )

        answer_confs = [d.answer_confidence for _, d in pairs]
        ctx.judgment = JudgmentRecord(
            judges=[j.name for j, _ in pairs],
            verdicts=verdicts,
            overall_assessment="\n\n".join(
                d.overall_assessment if len(pairs) == 1 else f"[{j.name}] {d.overall_assessment}"
                for j, d in pairs
            ),
            key_considerations=list(
                dict.fromkeys(k for _, d in pairs for k in d.key_considerations)
            ),
            answer_confidence=statistics.fmean(answer_confs),
            juror_answer_confidences=answer_confs,
        )
        ctx.events.emit(
            EventType.JUDGMENT_COMPLETED,
            step=self.name,
            verdicts=len(verdicts),
            answer_confidence=ctx.judgment.answer_confidence,
        )


def classify_claims(ctx: RunContext) -> dict[str, list[str]]:
    S = ClaimStatus
    contested = {
        ch.target_claim_id
        for ch in ctx.challenges.values()
        if ch.outcome != ChallengeOutcome.CONCEDED
    }
    bins: dict[str, list[str]] = {
        "established": [],
        "rejected": [],
        "disputed": [],
        "uncertain": [],
    }
    for c in ctx.claims.all():
        if c.status in (S.SUPPORTED, S.PARTIALLY_SUPPORTED):
            bins["established"].append(c.id)
        elif c.status in (S.CONTRADICTED, S.UNSUPPORTED):
            bins["rejected"].append(c.id)
        elif c.id in contested:
            bins["disputed"].append(c.id)
        else:
            bins["uncertain"].append(c.id)
    return bins


class Synthesis(Step):
    """Writes the final answer from the judged record.

    Claim bins (established / disputed / uncertain / rejected) are computed
    deterministically from validated statuses; the synthesizer only writes prose.
    With ``agent=None`` no model is called and the single perspective is reported
    as-is (used by the ``simple`` single-model baseline).
    """

    kind = "synthesis"

    def __init__(self, agent: Agent | bool | None = True, **kw: Any) -> None:
        super().__init__(**kw)
        self.agent: Agent | None = Agent("synthesizer") if agent is True else (agent or None)

    @property
    def agents(self) -> list[Agent]:
        return [self.agent] if self.agent else []

    def config(self) -> dict[str, Any]:
        return {"llm": self.agent is not None}

    async def run(self, ctx: RunContext) -> None:
        bins = classify_claims(ctx)
        if self.agent is None:
            self._passthrough(ctx, bins)
        else:
            await self._synthesize(ctx, bins)
        ctx.events.emit(
            EventType.SYNTHESIS_COMPLETED,
            step=self.name,
            counts={k: len(v) for k, v in bins.items()},
        )

    def _passthrough(self, ctx: RunContext, bins: dict[str, list[str]]) -> None:
        if not ctx.perspectives:
            raise StepError("nothing to synthesize: no perspectives")
        p = ctx.perspectives[-1]
        ctx.synthesis = SynthesisRecord(
            answer=p.position,
            summary=p.summary,
            established_claim_ids=bins["established"],
            disputed_claim_ids=bins["disputed"],
            uncertain_claim_ids=bins["uncertain"],
            rejected_claim_ids=bins["rejected"],
            caveats=p.uncertainties,
        )

    async def _synthesize(self, ctx: RunContext, bins: dict[str, list[str]]) -> None:
        assert self.agent is not None
        judged = ctx.judgment is not None
        statuses = "\n".join(
            f"{c.id} [{c.status.value}{f'; conf {c.confidence:.2f}' if c.confidence is not None else ''}] {c.statement}"
            + (f" (policy: {c.policy_note})" if c.policy_note else "")
            for c in ctx.claims.all()
        )
        task = (
            f"{_record(ctx)}\n\nJudgment:\n{ctx.judgment.overall_assessment if ctx.judgment else '(no judgment step ran; claims are unverified)'}\n"
            f"Answer confidence from judgment: {ctx.judgment.answer_confidence if ctx.judgment else 'n/a'}\n\n"
            f"Final claim statuses:\n{statuses or '(none)'}\n\n"
            f"Established: {bins['established']}\nDisputed: {bins['disputed']}\n"
            f"Uncertain: {bins['uncertain']}\nRejected: {bins['rejected']}\n\n"
            "Write the final answer. Reference claim ids. Do not present uncertain or disputed claims as established."
            + ("" if judged else " No claims were verified, so make that limitation explicit.")
        )
        drafts = await call_agents(
            ctx, [self.agent], [task], step=self.name, schema=SynthesisDraft, allow_tools=False
        )
        draft = drafts[0]
        if draft is None:
            raise StepError("synthesizer failed")
        unknown = sorted(
            {m for m in _CLAIM_REF.findall(draft.summary + draft.answer) if m not in ctx.claims}
        )
        if unknown:
            ctx.events.emit(
                EventType.WARNING,
                step=self.name,
                agent=self.agent.name,
                message=f"synthesis referenced unknown claims {unknown}",
            )
        ctx.synthesis = SynthesisRecord(
            answer=draft.answer,
            summary=draft.summary,
            established_claim_ids=bins["established"],
            disputed_claim_ids=bins["disputed"],
            uncertain_claim_ids=bins["uncertain"],
            rejected_claim_ids=bins["rejected"],
            caveats=draft.caveats,
            recommendations=draft.recommendations,
        )
        ctx.unresolved_questions.extend(draft.unresolved_questions)
