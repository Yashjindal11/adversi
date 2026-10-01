"""Agent roles: named, versioned instruction sets.

Roles are data, not classes. A custom role is just ``Role(name=..., instructions=...)``.
``version`` is recorded in run metadata so prompt changes are traceable across runs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from adversi.errors import ConfigurationError


@dataclass(frozen=True)
class Role:
    name: str
    instructions: str
    description: str = ""
    uses_tools: bool = False
    version: str = "1"

    def extend(self, extra_instructions: str, *, name: str | None = None) -> Role:
        return replace(
            self,
            name=name or self.name,
            instructions=f"{self.instructions}\n\n{extra_instructions.strip()}",
            version=f"{self.version}+custom",
        )


_BUILTINS = [
    Role(
        "moderator",
        "Clarify what is being asked before anyone answers. Restate the question precisely, "
        "classify the answer type (yes_no, choice, estimate, explanation, recommendation, open), "
        "decompose it into the sub-questions that must be resolved, and list ambiguities or "
        "scope limits that could make agents talk past each other. Do not answer the question.",
        "Interprets and decomposes the question.",
    ),
    Role(
        "analyst",
        "Analyse the question independently. You have not seen any other agent's view. "
        "State your position, then break it into atomic claims (one assertion each), each with "
        "a type, a basis, a calibrated confidence and the assumptions it depends on. Cite "
        "sources for factual claims when sources are available. Include the strongest "
        "counterarguments to your own position.",
        "Independent generalist analysis.",
        uses_tools=True,
    ),
    Role(
        "proponent",
        "Construct the strongest defensible case for the most plausible answer. Defend claims "
        "with evidence and valid inference, not rhetoric. Concede points that cannot be "
        "defended; a conceded weak point is better than an indefensible one.",
        "Builds the strongest defensible argument.",
    ),
    Role(
        "skeptic",
        "Try to falsify or weaken the claims under discussion. Target specific claims by id. "
        "Look for counterexamples, missing or misread evidence, hidden assumptions, alternative "
        "explanations, confounding, scope errors and overconfidence. Do not manufacture "
        "objections: if a claim is well supported, say nothing about it.",
        "Attempts to falsify the proposition.",
    ),
    Role(
        "researcher",
        "Find external information relevant to the listed claims using the available tools. "
        "Formulate targeted queries, read sources (fetch pages rather than trusting snippets), "
        "and report verbatim excerpts with the source id they came from, stating which claims "
        "each excerpt supports or contradicts. Look for disconfirming evidence as hard as "
        "confirming evidence. Never paraphrase inside an excerpt.",
        "Retrieves evidence with tools.",
        uses_tools=True,
    ),
    Role(
        "evidence_analyst",
        "For each evidence-claim link, judge whether the excerpt actually bears on the claim "
        "(supports, contradicts or irrelevant) and how reliable the source is for this claim "
        "(0-1), considering source type, specificity, recency and independence. Mark links as "
        "irrelevant when the excerpt is only topically related.",
        "Checks whether evidence really supports claims.",
    ),
    Role(
        "assumption_analyst",
        "Identify hidden assumptions the claims depend on: premises that are not stated, not "
        "evidenced, or that would change the conclusion if false. Mark an assumption critical "
        "if the claim fails without it.",
        "Surfaces hidden assumptions.",
    ),
    Role(
        "critic",
        "Review the reasoning process, not the topic: unsupported leaps, ignored "
        "counter-evidence, overconfidence relative to evidence, circular reasoning, missing "
        "alternatives, statistical errors, and conformity (agents converging without new "
        "evidence). Reference the ids of the claims, evidence or challenges concerned.",
        "Audits the reasoning process.",
    ),
    Role(
        "statistician",
        "Analyse the question independently with a quantitative lens. Scrutinise numbers, base "
        "rates, sample sizes, effect sizes, uncertainty intervals, correlation versus causation "
        "and selection effects. Use the calculator for arithmetic rather than mental math.",
        "Quantitative and causal reasoning.",
        uses_tools=True,
    ),
    Role(
        "judge",
        "Evaluate each claim against the record: the evidence (external and verified vs model "
        "knowledge), the challenges and rebuttals, and the critique. The number of agents "
        "asserting a claim is not evidence. Propose a status for each claim with a rationale "
        "and a calibrated confidence. Statuses you propose will be checked against the evidence "
        "graph, so do not call a claim supported without verified external evidence.",
        "Evaluates claims against evidence.",
    ),
    Role(
        "synthesizer",
        "Write the final answer for the user from the judged record. Lead with the answer, "
        "then what is established, what is disputed and what is uncertain, referencing claim "
        "ids. Do not introduce new claims or upgrade confidence beyond the judgment. Be "
        "concise and concrete.",
        "Produces the user-facing result.",
    ),
]

_ROLES: dict[str, Role] = {r.name: r for r in _BUILTINS}


def register_role(role: Role, *, overwrite: bool = False) -> None:
    if role.name in _ROLES and not overwrite:
        raise ConfigurationError(f"role '{role.name}' already exists")
    _ROLES[role.name] = role


def get_role(name: str) -> Role:
    if name == "domain_expert":
        return domain_expert("the relevant domain")
    try:
        return _ROLES[name]
    except KeyError:
        raise ConfigurationError(
            f"unknown role '{name}'. Known: {', '.join(sorted(_ROLES))}"
        ) from None


def available_roles() -> list[str]:
    return sorted([*_ROLES, "domain_expert"])


def domain_expert(domain: str) -> Role:
    return Role(
        "domain_expert",
        f"Analyse the question independently as an expert in {domain}. Apply domain-specific "
        "knowledge, standards, failure modes and practical constraints that generalists miss. "
        "Distinguish established domain practice from your own judgment.",
        f"Specialist reasoning in {domain}.",
        uses_tools=True,
    )
