"""Custom agent roles and a custom step.

Roles are plain data (name + instructions). Steps are small classes operating on the
shared RunContext. Neither requires changes to the library.
"""

import os

from adversi import Agent, Role, Step, Workflow, register_role, steps
from adversi.orchestration import RunContext
from adversi.protocol import ClaimStatus

# 1. A custom role. Register it to make it available by name in config files.
red_team = Role(
    "red_team",
    "Assume the proposal fails badly within a year. Work backwards: list the most plausible "
    "causes of failure as atomic claims, each with a confidence and the assumption it attacks.",
    description="Pre-mortem analyst",
)
register_role(red_team, overwrite=True)


# 2. A custom deterministic step: flag high-confidence claims that ended uncertain.
class OverconfidenceAudit(Step):
    kind = "overconfidence_audit"

    def __init__(self, threshold: float = 0.8) -> None:
        super().__init__()
        self.threshold = threshold

    def config(self) -> dict[str, float]:
        return {"threshold": self.threshold}

    async def run(self, ctx: RunContext) -> None:
        for claim in ctx.claims.all():
            stated = max((a.confidence or 0.0) for a in claim.attributions)
            if stated >= self.threshold and claim.status in (
                ClaimStatus.UNCERTAIN,
                ClaimStatus.UNVERIFIED,
            ):
                ctx.unresolved_questions.append(
                    f"{claim.id} was asserted with confidence {stated:.2f} but could not be verified."
                )


workflow = Workflow(
    [
        steps.IndependentAnalysis([Agent("analyst"), Agent("red_team")]),
        steps.ClaimConsolidation(),
        steps.CrossExamination(),
        steps.Judgment(),
        OverconfidenceAudit(threshold=0.8),
        steps.Synthesis(),
    ],
    model=os.environ.get("ADVERSI_MODEL", "openai:gpt-4o-mini"),
)

result = workflow.run_sync("Should our team adopt a monorepo for 30 services?")
print(result.to_markdown())
