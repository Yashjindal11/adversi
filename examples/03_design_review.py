"""Software design review as a peer-review workflow with a domain expert.

Peer review: independent analysts, then each revises after seeing the others'
structured positions (not their reasoning text), then critique, judgment, synthesis.
Comparing round-0 and revised verdicts lets you measure conformity.
"""

import os

from adversi import AdverSI, Agent, domain_expert

design_doc = """\
Proposal: replace the nightly batch export with change-data-capture (CDC) from Postgres
logical replication into Kafka, consumed by the analytics warehouse loader.
- Expected freshness: < 5 minutes (today: 24 hours).
- Schema changes: handled by a schema registry with backward compatibility.
- Failure handling: consumer restarts from last committed offset.
- Replication slot retention: default settings.
- Team has no prior Kafka operations experience.
"""

model = os.environ.get("ADVERSI_MODEL", "openai:gpt-4o-mini")
ai = AdverSI(
    model,
    mode="peer_review",
    agents=[
        Agent("analyst", name="architect"),
        Agent(domain_expert("PostgreSQL operations and data infrastructure"), name="db_expert"),
        Agent(
            "statistician",
            name="reliability",
            instructions="Focus on failure rates, recovery time and operational load.",
        ),
    ],
)

result = ai.run_sync("Is this CDC design safe to roll out next quarter?", context=design_doc)
print(result.to_markdown())

before = {p.agent: p.verdict for p in result.perspectives if p.round == 0}
after = {p.agent: p.verdict for p in result.perspectives if p.round == 1}
print("Verdict changes after peer exchange:", {a: (before[a], after.get(a)) for a in before})
