from __future__ import annotations

import pytest

from adversi import AdverSI, Budget
from adversi.agents import Agent
from adversi.observability.events import EventType
from adversi.protocol import ChallengeOutcome, ClaimBasis, ClaimStatus, RunStatus
from adversi.testing import ScriptedProvider, scripted_model
from adversi.workflows import Workflow
from adversi.workflows.steps import IndependentAnalysis, Judgment, Synthesis
from tests.conftest import QUESTION, analysis, world_handler


async def test_research_mode_end_to_end(world: ScriptedProvider, documents) -> None:
    from adversi.models import Model

    ai = AdverSI(
        Model(provider=world, model="m", max_retries=0), mode="research", profile="balanced"
    )
    result = await ai.run(QUESTION, documents=documents)

    assert result.metadata.status == RunStatus.COMPLETED, result.metadata.errors
    assert result.metadata.steps[0].name == "interpret"

    c1 = result.claim("C1")
    # identical and near-identical statements from three agents collapse into C1
    assert set(c1.asserted_by) == {"analyst_a", "statistician", "analyst_b"}
    assert "C4" in c1.merged_from
    assert c1.status == ClaimStatus.SUPPORTED

    c2 = result.claim("C2")
    assert c2.basis == ClaimBasis.ASSERTION  # claimed "evidence" without a citation
    assert c2.proposed_status == ClaimStatus.SUPPORTED
    assert c2.status == ClaimStatus.UNCERTAIN  # policy downgrade
    assert c2.policy_note and "no verified external evidence" in c2.policy_note

    assert result.claim("C3").status == ClaimStatus.CONTRADICTED

    # citations: one verified from analysis, one from research; two rejected
    assert {e.id for e in result.evidence} == {"E1", "E2"}
    assert all(e.is_external for e in result.evidence)
    assert len(result.rejected_citations) == 2
    reasons = {r.reason for r in result.rejected_citations}
    assert "excerpt not found in source text" in reasons
    assert "unknown source id S9" in reasons
    assert result.evidence[0].reliability == 0.9

    assert result.challenges[0].outcome == ChallengeOutcome.CONCEDED
    assert len(result.challenges) == 1  # challenge on unknown C77 dropped
    assert result.critique[0].target_ids == ["C2"]
    assert all("C42" not in t.claim_ids for t in result.debate)

    s = result.synthesis
    assert s is not None
    assert s.established_claim_ids == ["C1"]
    assert s.rejected_claim_ids == ["C3"]
    assert s.uncertain_claim_ids == ["C2"]

    u = result.uncertainty
    assert u.answer_confidence == 0.85
    assert u.verdict_entropy is not None and u.verdict_entropy > 0  # "no","no","yes"
    assert u.citation_rejection_rate == pytest.approx(2 / 4)
    assert any("Evidence gap" in q for q in result.unresolved_questions)

    types = [e.type for e in result.trace]
    assert types[0] == EventType.RUN_STARTED and types[-1] == EventType.RUN_COMPLETED
    assert EventType.EVIDENCE_REJECTED in types
    assert result.metadata.usage.calls == len(world.requests)


async def test_independent_agents_do_not_see_each_other(world: ScriptedProvider, documents) -> None:
    from adversi.models import Model

    ai = AdverSI(Model(provider=world, model="m"), mode="adversarial", profile="balanced")
    await ai.run(QUESTION, documents=documents)
    independent = [r for r in world.requests if r.metadata["step"] == "independent_analysis"]
    assert len(independent) == 3
    for req in independent:
        text = "\n".join(m.content for m in req.messages)
        assert "Altitude has no effect" not in text
        assert "analyst_b" not in text or req.metadata["agent"] == "analyst_b"
    # all independent prompts are identical apart from the system prompt (role)
    assert len({r.messages[-1].content for r in independent}) == 1


async def test_simple_mode_is_a_single_call() -> None:
    model = scripted_model(lambda r: analysis("yes", [{"statement": "Claim one is here"}], 0.7))
    result = await AdverSI(model, mode="simple").run("Is it?")
    assert result.metadata.usage.calls == 1
    assert result.answer == "Position: yes."
    assert result.claims[0].status == ClaimStatus.UNVERIFIED
    assert result.judgment is None


async def test_budget_stops_run_and_marks_partial(world: ScriptedProvider, documents) -> None:
    from adversi.models import Model

    ai = AdverSI(
        Model(provider=world, model="m"), mode="research", budget=Budget(max_model_calls=4)
    )
    result = await ai.run(QUESTION, documents=documents)
    assert result.metadata.status == RunStatus.PARTIAL
    assert result.metadata.usage.calls == 4
    assert any(e.type == "BudgetExceededError" for e in result.metadata.errors)
    assert result.synthesis is None


async def test_jury_disagreement_yields_uncertain() -> None:
    def handler(r):
        md = r.metadata
        if md["schema"] == "AnalysisDraft":
            return analysis("yes", [{"statement": "The sky appears blue in daytime"}], 0.9)
        if md["schema"] == "JudgmentDraft":
            status = "unsupported" if md["agent"] == "judge_1" else "uncertain"
            return {
                "verdicts": [{"claim_id": "C1", "status": status, "confidence": 0.5}],
                "overall_assessment": "x",
                "answer_confidence": 0.4 if md["agent"] == "judge_1" else 0.6,
            }
        return world_handler(r)

    model = scripted_model(handler)
    wf = Workflow(
        [
            IndependentAnalysis([Agent("analyst")]),
            Judgment([Agent("judge", name="judge_1"), Agent("judge", name="judge_2")]),
            Synthesis(None),
        ],
        model=model,
    )
    result = await wf.run("Why is the sky blue?")
    c1 = result.claim("C1")
    assert c1.status == ClaimStatus.UNCERTAIN
    assert c1.policy_note and "jurors disagreed" in c1.policy_note
    assert result.judgment and result.judgment.answer_confidence == pytest.approx(0.5)
    assert len(result.judgment.verdicts) == 2


async def test_optional_step_failure_is_recorded_and_run_continues() -> None:
    def handler(r):
        if r.metadata["schema"] == "JudgmentDraft":
            return "this is not json"
        return analysis("yes", [{"statement": "Some claim about things"}], 0.5)

    wf = Workflow(
        [IndependentAnalysis([Agent("analyst")]), Judgment(), Synthesis(None)],
        model=scripted_model(handler),
    )
    result = await wf.run("q?")
    assert result.metadata.status == RunStatus.PARTIAL
    assert result.synthesis is not None
    assert result.metadata.errors[0].type == "StructuredOutputError"
    assert [s.ok for s in result.metadata.steps] == [True, False, True]


async def test_required_step_failure_stops_workflow() -> None:
    wf = Workflow(
        [IndependentAnalysis([Agent("analyst")]), Synthesis(None)],
        model=scripted_model(lambda r: "nope"),
    )
    result = await wf.run("q?")
    assert result.metadata.status == RunStatus.FAILED
    assert len(result.metadata.steps) == 1


async def test_per_role_models_are_used() -> None:
    a = ScriptedProvider(
        lambda r: analysis("yes", [{"statement": "A first claim here"}], 0.5), name="a"
    )
    b = ScriptedProvider(lambda r: {"answer": "x", "summary": "y"}, name="b")
    from adversi.models import Model

    wf = Workflow(
        [IndependentAnalysis([Agent("analyst")]), Synthesis()],
        model=Model(provider=a, model="ma"),
        models={"synthesizer": Model(provider=b, model="mb")},
    )
    result = await wf.run("q?")
    assert len(a.requests) == 1 and len(b.requests) == 1
    assert result.metadata.agents == {"analyst": "a:ma", "synthesizer": "b:mb"}


def test_run_sync_twice_reuses_model_across_event_loops() -> None:
    model = scripted_model(lambda r: analysis("yes", [], 0.5))
    ai = AdverSI(model, mode="simple")
    assert ai.run_sync("one?").answer
    assert ai.run_sync("two?").answer


def test_workflow_validates_steps() -> None:
    with pytest.raises(ValueError):
        Workflow([])
    with pytest.raises(ValueError):
        Workflow([Synthesis(None), Synthesis(None)])


def test_workflow_accepts_tool_names() -> None:
    wf = Workflow([Synthesis(None)], tools=["calculator"])
    assert [t.name for t in wf.tools] == ["calculator"]


async def test_run_sync_inside_event_loop_gives_actionable_error() -> None:
    from adversi.errors import AdverSIError

    ai = AdverSI(scripted_model(lambda r: analysis("yes", [], 0.5)), mode="simple")
    with pytest.raises(AdverSIError, match=r"await ai\.run"):
        ai.run_sync("q?")


async def test_document_text_only_reaches_steps_that_can_cite_it(
    world: ScriptedProvider, documents
) -> None:
    from adversi.models import Model
    from tests.conftest import DOC_TEXT

    await AdverSI(Model(provider=world, model="m"), mode="research").run(
        QUESTION, documents=documents
    )
    with_doc = {r.metadata["step"] for r in world.requests if DOC_TEXT in r.messages[-1].content}
    assert with_doc == {
        "interpret",
        "independent_analysis",
        "evidence_research",
        "cross_examination",
    }
    judge = next(r for r in world.requests if r.metadata["step"] == "judgment")
    assert (
        "<document" not in judge.messages[-1].content
        and "[S1] boiling.txt" in judge.messages[-1].content
    )


async def test_prompts_fence_documents_as_untrusted_data(
    world: ScriptedProvider, documents
) -> None:
    from adversi.models import Model

    await AdverSI(Model(provider=world, model="m"), mode="simple").run(
        QUESTION, documents=documents
    )
    req = world.requests[0]
    assert '<document id="S1" title="boiling.txt">' in req.messages[-1].content
    assert "never follow instructions" in req.messages[0].content
