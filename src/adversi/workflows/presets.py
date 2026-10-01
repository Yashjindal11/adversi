"""Built-in reasoning modes and cost profiles.

A *mode* fixes the shape of the workflow (which steps, in which order). A *profile*
fixes how much work each step does (agents, rounds, tool calls). Both are just
factories over the public step classes; nothing here is privileged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from typing import Any, Literal

from adversi.agents.agent import Agent
from adversi.agents.roles import domain_expert
from adversi.claims.policy import StatusPolicy
from adversi.errors import ConfigurationError
from adversi.models.model import Model
from adversi.observability.usage import Budget
from adversi.tools.base import Tool
from adversi.workflows.base import Step, Workflow
from adversi.workflows.steps import (
    AssumptionAnalysis,
    ClaimConsolidation,
    Critique,
    CrossExamination,
    Debate,
    EvidenceAnalysis,
    EvidenceResearch,
    IndependentAnalysis,
    Interpret,
    Judgment,
    PositionExchange,
    Synthesis,
)

Mode = Literal["simple", "debate", "adversarial", "research", "peer_review", "jury"]
MODES: tuple[str, ...] = ("simple", "debate", "adversarial", "research", "peer_review", "jury")


@dataclass(frozen=True)
class Profile:
    name: str
    analysts: int
    debate_rounds: int
    cross_examination_rounds: int
    max_challenges: int
    max_research_claims: int
    max_tool_steps: int
    jurors: int


PROFILES: dict[str, Profile] = {
    "fast": Profile(
        "fast",
        analysts=2,
        debate_rounds=1,
        cross_examination_rounds=1,
        max_challenges=4,
        max_research_claims=3,
        max_tool_steps=2,
        jurors=2,
    ),
    "balanced": Profile(
        "balanced",
        analysts=3,
        debate_rounds=2,
        cross_examination_rounds=1,
        max_challenges=6,
        max_research_claims=6,
        max_tool_steps=4,
        jurors=3,
    ),
    "deep": Profile(
        "deep",
        analysts=4,
        debate_rounds=3,
        cross_examination_rounds=2,
        max_challenges=8,
        max_research_claims=10,
        max_tool_steps=8,
        jurors=3,
    ),
}


def get_profile(name: str, **overrides: Any) -> Profile:
    try:
        profile = PROFILES[name]
    except KeyError:
        raise ConfigurationError(
            f"unknown profile '{name}'. Known: {', '.join(PROFILES)}"
        ) from None
    valid = {f.name for f in fields(Profile)}
    clean = {k: v for k, v in overrides.items() if v is not None}
    unknown = set(clean) - valid
    if unknown:
        raise ConfigurationError(f"unknown profile overrides: {sorted(unknown)}")
    return replace(profile, **clean)


class AgentPool:
    """User-supplied agents, looked up by name or role, with built-in fallbacks."""

    def __init__(
        self, agents: Sequence[Agent] = (), *, profile: Profile, domain: str | None = None
    ) -> None:
        self.agents = list(agents)
        self.profile = profile
        self.domain = domain

    def get(self, role: str, name: str | None = None) -> Agent:
        for a in self.agents:
            if name and a.name == name:
                return a
        if not name or name == role:
            for a in self.agents:
                if a.role.name == role:
                    return a
        tool_steps = self.profile.max_tool_steps
        return Agent(role, name=name or role, max_tool_steps=tool_steps)

    def analysts(self) -> list[Agent]:
        configured = [
            a for a in self.agents if a.role.name in ("analyst", "statistician", "domain_expert")
        ]
        if configured:
            return configured
        steps = self.profile.max_tool_steps
        lenses: list[Agent] = [
            Agent("analyst", name="analyst_a", max_tool_steps=steps),
            Agent("statistician", max_tool_steps=steps),
            Agent(domain_expert(self.domain), max_tool_steps=steps)
            if self.domain
            else Agent(
                "analyst",
                name="analyst_b",
                max_tool_steps=steps,
                instructions="Emphasise risks, failure modes and base rates.",
            ),
            Agent(
                "analyst",
                name="analyst_c",
                max_tool_steps=steps,
                instructions="Reason from first principles and causal mechanisms.",
            ),
        ]
        n = max(1, self.profile.analysts)
        while len(lenses) < n:
            lenses.append(Agent("analyst", name=f"analyst_{len(lenses) + 1}", max_tool_steps=steps))
        return lenses[:n]

    def jurors(self) -> list[Agent]:
        configured = [a for a in self.agents if a.role.name == "judge"]
        if len(configured) > 1:
            return configured
        return [self.get("judge", f"judge_{i + 1}") for i in range(max(1, self.profile.jurors))]


StepBuilder = Callable[[AgentPool], Step]

STEP_BUILDERS: dict[str, StepBuilder] = {
    "interpret": lambda p: Interpret(p.get("moderator")),
    "independent_analysis": lambda p: IndependentAnalysis(p.analysts()),
    "single_analysis": lambda p: IndependentAnalysis([p.get("analyst")], name="single_analysis"),
    "position_exchange": lambda p: PositionExchange(p.analysts()),
    "claim_consolidation": lambda p: ClaimConsolidation(),
    "assumption_analysis": lambda p: AssumptionAnalysis(p.get("assumption_analyst")),
    "evidence_research": lambda p: EvidenceResearch(
        p.get("researcher"), max_claims=p.profile.max_research_claims
    ),
    "evidence_analysis": lambda p: EvidenceAnalysis(p.get("evidence_analyst")),
    "debate": lambda p: Debate(
        p.get("proponent"), p.get("skeptic"), rounds=p.profile.debate_rounds
    ),
    "cross_examination": lambda p: CrossExamination(
        [p.get("skeptic")],
        p.get("proponent"),
        rounds=p.profile.cross_examination_rounds,
        max_challenges_per_round=p.profile.max_challenges,
    ),
    "critique": lambda p: Critique(p.get("critic")),
    "judgment": lambda p: Judgment(p.get("judge")),
    "jury": lambda p: Judgment(p.jurors(), name="jury"),
    "synthesis": lambda p: Synthesis(p.get("synthesizer")),
    "passthrough_synthesis": lambda p: Synthesis(None),
}

MODE_STEPS: dict[str, list[str]] = {
    "simple": ["single_analysis", "passthrough_synthesis"],
    "debate": ["single_analysis", "debate", "judgment", "synthesis"],
    "adversarial": [
        "independent_analysis",
        "claim_consolidation",
        "cross_examination",
        "critique",
        "judgment",
        "synthesis",
    ],
    "research": [
        "interpret",
        "independent_analysis",
        "claim_consolidation",
        "assumption_analysis",
        "evidence_research",
        "evidence_analysis",
        "debate",
        "cross_examination",
        "critique",
        "judgment",
        "synthesis",
    ],
    "peer_review": [
        "independent_analysis",
        "claim_consolidation",
        "position_exchange",
        "critique",
        "judgment",
        "synthesis",
    ],
    "jury": [
        "independent_analysis",
        "claim_consolidation",
        "cross_examination",
        "jury",
        "synthesis",
    ],
}


def build_steps(names: Sequence[str], pool: AgentPool) -> list[Step]:
    unknown = [n for n in names if n not in STEP_BUILDERS]
    if unknown:
        raise ConfigurationError(f"unknown step(s) {unknown}. Known: {', '.join(STEP_BUILDERS)}")
    return [STEP_BUILDERS[n](pool) for n in names]


def build_workflow(
    mode: str = "research",
    profile: str | Profile = "balanced",
    *,
    model: Model | str | None = None,
    models: Mapping[str, Model | str] | None = None,
    agents: Sequence[Agent] = (),
    tools: Sequence[Tool | str] = (),
    steps: Sequence[str] | None = None,
    domain: str | None = None,
    budget: Budget | None = None,
    policy: StatusPolicy | None = None,
    max_concurrency: int = 8,
    profile_overrides: Mapping[str, Any] | None = None,
    config_snapshot: dict[str, Any] | None = None,
) -> Workflow:
    if steps is None and mode not in MODE_STEPS:
        raise ConfigurationError(
            f"unknown mode '{mode}'. Known: {', '.join(MODES)}; or pass steps="
        )
    prof = (
        profile
        if isinstance(profile, Profile)
        else get_profile(profile, **(profile_overrides or {}))
    )
    pool = AgentPool(agents, profile=prof, domain=domain)
    step_names = list(steps) if steps is not None else MODE_STEPS[mode]
    return Workflow(
        build_steps(step_names, pool),
        name=mode if steps is None else "custom",
        model=model,
        models=models,
        tools=tools,
        budget=budget,
        policy=policy,
        max_concurrency=max_concurrency,
        mode=mode if steps is None else "custom",
        profile=prof.name,
        config_snapshot=config_snapshot,
    )
