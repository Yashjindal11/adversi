"""Aviation operations: a hub disruption decision with operational data.

Shows a custom workflow (no web research, documents only), an airline-operations
domain expert, a dedicated skeptic focused on safety and crew legality, and per-role
models. The data below is illustrative, not real operational data.
"""

import os

from adversi import Agent, Budget, Document, Workflow, domain_expert, steps

ops_snapshot = """\
Hub: ORD. Time: 14:10 local. Thunderstorm cell forecast 15:30-17:30, ground stop likely.
Departures 15:00-18:00: 142 scheduled. Average load factor 87%.
Crew: 23 crews would exceed FAA Part 117 flight duty period limits if delayed > 2h45m.
Reserve crews available at ORD: 9.
Option A: proactively cancel 28 short-haul departures now and re-accommodate.
Option B: hold schedule and delay as needed; cancel reactively after the ground stop.
Historical: on 6 comparable storm days, reactive handling produced 31-44 cancellations,
with 2 of 6 days requiring next-day crew repositioning.
"""

default = os.environ.get("ADVERSI_MODEL", "openai:gpt-4o-mini")
judge_model = os.environ.get("ADVERSI_JUDGE_MODEL", default)

ops_expert = Agent(
    domain_expert("airline operations control, crew scheduling and FAA Part 117"), name="ops_expert"
)
workflow = Workflow(
    [
        steps.Interpret(),
        steps.IndependentAnalysis(
            [Agent("analyst", name="network_planner"), ops_expert, Agent("statistician")]
        ),
        steps.ClaimConsolidation(),
        steps.AssumptionAnalysis(),
        steps.CrossExamination(
            [
                Agent(
                    "skeptic",
                    name="safety_skeptic",
                    instructions="Prioritise safety, crew legality and passenger impact.",
                )
            ],
            defender=Agent("proponent"),
            rounds=2,
        ),
        steps.Critique(),
        steps.Judgment(Agent("judge")),
        steps.Synthesis(),
    ],
    name="ops_decision",
    model=default,
    models={"judge": judge_model},
    budget=Budget(max_model_calls=30),
)

result = workflow.run_sync(
    "Should we choose Option A (proactive cancellations) or Option B (reactive) for this afternoon?",
    documents=[Document(content=ops_snapshot, title="ops_snapshot_1410.txt")],
)
print(result.to_markdown())
