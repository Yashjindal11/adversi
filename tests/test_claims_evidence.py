from __future__ import annotations

from adversi.claims import ClaimStore, StatusPolicy, similarity
from adversi.evidence import EvidenceStore, verify_excerpt
from adversi.protocol import (
    Attribution,
    Challenge,
    ChallengeOutcome,
    Claim,
    ClaimStatus,
    SourceType,
)

S = ClaimStatus
TEXT = "The 2019 study found that median delay fell by 12 percent after the change."


def _att(agent: str = "a") -> Attribution:
    return Attribution(agent=agent, role="analyst", step="t", confidence=0.5)


# -- excerpt verification -----------------------------------------------------------


def test_verify_excerpt_tolerates_case_punctuation_whitespace() -> None:
    assert verify_excerpt("median delay  FELL by 12 percent", TEXT) == (True, None)
    assert verify_excerpt("\u201cThe 2019 study found\u201d", TEXT)[0]


def test_verify_excerpt_supports_ellipsis_in_order() -> None:
    assert verify_excerpt("The 2019 study ... fell by 12 percent", TEXT)[0]
    assert not verify_excerpt("fell by 12 percent ... The 2019 study", TEXT)[0]


def test_verify_excerpt_rejects_paraphrase_and_short_quotes() -> None:
    ok, reason = verify_excerpt("median delay dropped by 12 percent", TEXT)
    assert not ok and reason == "excerpt not found in source text"
    ok, reason = verify_excerpt("12", TEXT)
    assert not ok and "shorter" in (reason or "")


# -- evidence store -----------------------------------------------------------------


def test_cite_unknown_or_fabricated_is_rejected_and_recorded() -> None:
    store = EvidenceStore()
    src = store.add_source(TEXT, source_type=SourceType.DOCUMENT)
    assert store.cite(source_id="S99", excerpt="whatever text here", agent="a", step="s") is None
    assert (
        store.cite(source_id=src.id, excerpt="delay rose by 40 percent", agent="a", step="s")
        is None
    )
    assert [r.reason for r in store.rejected] == [
        "unknown source id S99",
        "excerpt not found in source text",
    ]
    assert store.all() == []


def test_model_knowledge_is_never_external() -> None:
    store = EvidenceStore()
    ev = store.cite(
        source_id=None, excerpt="Everyone knows delays fell.", agent="a", step="s", supports=["C1"]
    )
    assert ev is not None
    assert ev.provenance.source_type == SourceType.MODEL_KNOWLEDGE
    assert not ev.excerpt_verified and not ev.is_external


def test_duplicate_citations_merge_links() -> None:
    store = EvidenceStore()
    store.add_source(TEXT, source_type=SourceType.WEB, uri="https://example.org")
    e1 = store.cite(
        source_id="S1",
        excerpt="median delay fell by 12 percent",
        agent="a",
        step="s",
        supports=["C1"],
    )
    e2 = store.cite(
        source_id="S1",
        excerpt="Median delay fell by 12 percent",
        agent="b",
        step="s",
        supports=["C2"],
    )
    assert e1 is e2 and e1 is not None
    assert e1.supports == ["C1", "C2"] and e1.is_external


def test_sources_dedupe_by_uri_and_content() -> None:
    store = EvidenceStore()
    a = store.add_source(TEXT, source_type=SourceType.WEB, uri="u")
    b = store.add_source(TEXT, source_type=SourceType.WEB, uri="u")
    c = store.add_source(TEXT, source_type=SourceType.WEB, uri="v")
    assert a.id == b.id != c.id
    assert a.provenance.content_sha256 and len(a.provenance.content_sha256) == 64


# -- claims -------------------------------------------------------------------------


def test_identical_claims_share_an_id_and_accumulate_attributions() -> None:
    store = ClaimStore()
    c1 = store.add("Delays fell by 12 percent.", attribution=_att("a"))
    c2 = store.add("delays fell by 12 percent", attribution=_att("b"))
    assert c1.id == c2.id == "C1"
    assert c1.asserted_by == ["a", "b"]


def test_similarity_refuses_to_merge_negations_or_different_numbers() -> None:
    assert (
        similarity("Remote work improves productivity", "Remote work does not improve productivity")
        == 0
    )
    assert similarity("Delays fell by 12 percent", "Delays fell by 15 percent") == 0
    assert similarity("At sea level water boils at 100 C", "Water boils at 100 C at sea level") == 1


def test_consolidate_merges_and_returns_mapping() -> None:
    store = ClaimStore()
    store.add("Water boils at 100 C at sea level", attribution=_att("a"))
    store.add("Altitude matters for boiling", attribution=_att("a"))
    store.add("At sea level, water boils at 100 C", attribution=_att("b"))
    store.add_assumption("Pure water", identified_by="x", claim_ids=["C3"])
    mapping = store.consolidate(0.85)
    assert mapping == {"C3": "C1"}
    assert [c.id for c in store.all()] == ["C1", "C2"]
    assert store.get("C1").asserted_by == ["a", "b"]
    assert store.assumptions()[0].claim_ids == ["C1"]


# -- status policy ------------------------------------------------------------------


def _setup(supports: bool = False, contradicts: bool = False, model_only: bool = False):
    store = EvidenceStore()
    store.add_source(TEXT, source_type=SourceType.DOCUMENT)
    if supports:
        store.cite(
            source_id=None if model_only else "S1",
            excerpt="median delay fell by 12 percent",
            agent="a",
            step="s",
            supports=["C1"],
        )
    if contradicts:
        store.cite(
            source_id="S1", excerpt="The 2019 study found", agent="a", step="s", contradicts=["C1"]
        )
    return Claim(id="C1", statement="x"), store.all()


def test_policy_supported_requires_external_evidence() -> None:
    policy = StatusPolicy()
    claim, ev = _setup()
    assert policy.validate(S.SUPPORTED, claim, ev)[0] == S.UNCERTAIN
    claim, ev = _setup(supports=True, model_only=True)
    assert policy.validate(S.SUPPORTED, claim, ev)[0] == S.UNCERTAIN
    claim, ev = _setup(supports=True)
    assert policy.validate(S.SUPPORTED, claim, ev) == (S.SUPPORTED, None)


def test_policy_mixed_evidence_and_concessions() -> None:
    policy = StatusPolicy()
    claim, ev = _setup(supports=True, contradicts=True)
    assert policy.validate(S.SUPPORTED, claim, ev)[0] == S.UNCERTAIN
    assert policy.validate(S.CONTRADICTED, claim, ev)[0] == S.CONTRADICTED
    assert policy.validate(S.UNSUPPORTED, claim, ev)[0] == S.UNCERTAIN
    claim, ev = _setup(supports=True)
    conceded = Challenge(
        id="X1",
        target_claim_id="C1",
        challenger="s",
        round=1,
        argument="a",
        outcome=ChallengeOutcome.CONCEDED,
    )
    assert policy.validate(S.SUPPORTED, claim, ev, [conceded])[0] == S.PARTIALLY_SUPPORTED


def test_policy_contradicted_requires_external_contradiction() -> None:
    claim, ev = _setup(supports=True)
    assert StatusPolicy().validate(S.CONTRADICTED, claim, ev)[0] == S.UNCERTAIN


def test_policy_ignores_low_reliability_evidence() -> None:
    claim, ev = _setup(supports=True)
    ev[0].reliability = 0.1
    assert StatusPolicy().validate(S.SUPPORTED, claim, ev)[0] == S.UNCERTAIN
    assert StatusPolicy(min_reliability=0.05).validate(S.SUPPORTED, claim, ev)[0] == S.SUPPORTED


def test_policy_can_allow_reasoning_only_support() -> None:
    claim, ev = _setup()
    assert (
        StatusPolicy(require_external_evidence=False).validate(S.SUPPORTED, claim, ev)[0]
        == S.SUPPORTED
    )


def test_uncertain_and_unverified_always_allowed() -> None:
    claim, ev = _setup()
    for s in (S.UNCERTAIN, S.UNVERIFIED):
        assert StatusPolicy().validate(s, claim, ev) == (s, None)
