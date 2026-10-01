"""General decision analysis with the jury mode and different models per role.

Jury mode runs several judges independently. AdverSI does not take a majority vote:
a claim keeps a status only if every juror agrees after policy validation.
"""

import os

from adversi import AdverSI

default = os.environ.get("ADVERSI_MODEL", "openai:gpt-4o-mini")

ai = AdverSI(
    default,
    # Model diversity among jurors reduces correlated errors (a hypothesis you can test
    # with `adversi benchmark`). Any judge without an entry uses the default model.
    models={
        "judge_1": default,
        "judge_2": os.environ.get("ADVERSI_JUDGE_2", default),
        "judge_3": os.environ.get("ADVERSI_JUDGE_3", default),
    },
    mode="jury",
    profile="balanced",
)

result = ai.run_sync(
    "Should a 40-person startup migrate from a monolith to microservices this year?",
    context="Team: 12 engineers. Product: B2B SaaS with ~300 customers. Deploys weekly. "
    "Main pain points: slow CI (35 min) and one module with frequent incidents.",
)

print(result.to_markdown())
for claim in result.claims:
    print(f"{claim.id:<4} {claim.status.value:<20} {claim.statement}")
