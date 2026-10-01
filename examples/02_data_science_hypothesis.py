"""Data-science hypothesis review grounded in user-provided data.

The documents become citable sources. Citations are checked verbatim against them,
and the statistician uses the calculator for arithmetic.
"""

import os

from adversi import AdverSI, Document

experiment_summary = """\
A/B test: new onboarding checklist (variant B) vs current flow (A).
Run dates: 14 days. Assignment: user-level, 50/50.
A: 4,812 users, 1,203 activated within 7 days.
B: 4,790 users, 1,322 activated within 7 days.
Note: on day 6 a marketing campaign targeted at enterprise trials launched; enterprise
trials were 18% of B and 11% of A after day 6 because of a routing bug fixed on day 9.
"""

ai = AdverSI(
    os.environ.get("ADVERSI_MODEL", "openai:gpt-4o-mini"),
    mode="adversarial",
    profile="balanced",
    tools=["calculator"],
)

result = ai.run_sync(
    "Does the onboarding checklist (variant B) causally increase 7-day activation?",
    documents=[Document(content=experiment_summary, title="experiment_summary.txt")],
)

print(result.to_markdown())
print("Rejected citations:", len(result.rejected_citations))
