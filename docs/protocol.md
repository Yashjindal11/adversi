# The reasoning protocol

Everything an AdverSI run produces is a typed record in `adversi.protocol`, serialized as
`AdverSIResult` (schema version in `schema_version`).

## Claims

```python
Claim(
    id="C3",
    statement="Mandatory code review caused the drop in escaped defects",
    claim_type="causal",            # factual | causal | statistical | predictive | normative | definitional | other
    basis="assertion",              # evidence | inference | assertion | speculation
    attributions=[Attribution(agent="analyst_a", role="analyst", step="independent_analysis", confidence=0.65)],
    supporting_evidence_ids=[], contradicting_evidence_ids=["E4"],
    assumption_ids=["A1"],
    status="uncertain",             # validated, see below
    proposed_status="supported",    # what the judge said
    policy_note="no verified external evidence supports this claim",
    confidence=0.6,                 # judged confidence (None until judged)
)
```

- **Attributions** keep each agent's own confidence. They are never aggregated into a
  status: agreement is not evidence.
- **Basis** is declared by the agent but validated: `evidence` is downgraded to
  `assertion` unless the claim has at least one verified external citation.
- **Ids** are sequential per run. Identical statements (after normalization) share an id;
  `ClaimConsolidation` merges near-duplicates and records `merged_from`.

### Statuses

| Status | Meaning | Required by `StatusPolicy` |
|---|---|---|
| `supported` | Verified external evidence supports it; nothing verified contradicts it; no conceded challenge | >= 1 external supporting excerpt, 0 external contradicting, no concession |
| `partially_supported` | Some verified support | >= 1 external supporting excerpt |
| `contradicted` | Verified evidence contradicts it | >= 1 external contradicting excerpt |
| `unsupported` | Judged to lack support | no external supporting excerpt |
| `uncertain` | Mixed, insufficient, or jurors disagreed | always allowed |
| `unverified` | Never evaluated | default |

Evidence with analysed reliability below `min_reliability` (default 0.3) is ignored by the
policy. Every downgrade is explained in `policy_note`.

## Sources and evidence

A **Source** is material that entered the run from outside the agents. Only the system
creates sources: user documents (`user_provided`), tool outputs (`calculation`,
`database`, `tool`), fetched pages (`web`), search snippets (`web_search_snippet`).
Each carries **provenance**: type, URI, title, tool name and arguments, retrieval time,
SHA-256 of the content, and who caused it to be retrieved.

**Evidence** is an excerpt *from* a source, cited by an agent for or against claims:

```python
Evidence(
    id="E4", source_id="S1",
    excerpt="During the same period the company also introduced a new end-to-end test suite",
    provenance=Provenance(source_type="user_provided", title="study.txt", content_sha256="..."),
    supports=[], contradicts=["C2"],
    cited_by="researcher", excerpt_verified=True,
    reliability=0.7, reliability_rationale="Internal study; single source.",
)
```

`Evidence.is_external` is true only when the excerpt was verified against a non-model
source. Citations with `source_id=None` are recorded as `model_knowledge`: visible, but
never external. Citations that fail verification become `RejectedCitation` records with a
reason and are excluded from everything else.

### Distinguishing evidence, inference, assertion and speculation

| Kind | Representation |
|---|---|
| Evidence | `Evidence` with `is_external=True` |
| Model knowledge | `Evidence` with `source_type=model_knowledge` |
| Inference | `Claim.basis="inference"`, `derived_from=[...]` |
| Assertion | `Claim.basis="assertion"` (default) |
| Speculation | `Claim.basis="speculation"` |
| Assumption | `Assumption` linked to the claims that depend on it |
| User-provided fact | `Source` with `source_type=user_provided` |

## Perspectives, debate, challenges, critique

- `Perspective`: one agent's structured analysis (verdict, position, reasoning
  *summary*, claim ids, counterarguments, uncertainties, open questions, confidence).
  `round=0` is the independent analysis; higher rounds are revisions.
- `DebateTurn`: stance, argument, referenced claim ids, concession flag.
- `Challenge`: targets one claim id with a kind (`counterexample`, `missing_evidence`,
  `logical_flaw`, `alternative_explanation`, `hidden_assumption`, `scope`, `statistical`),
  collects `Rebuttal`s, and has an outcome (`open`, `answered`, `conceded`).
- `CritiqueFinding`: a process-level issue (`unsupported_leap`, `ignored_counterevidence`,
  `overconfidence`, `conformity`, ...) with severity and target ids.

## Chain-of-thought

AdverSI never asks for, stores or displays raw chain-of-thought. Agents are instructed to
give concise reasoning summaries; the inspectable artifacts are the structured records
above.

## Compatibility

Records ignore unknown fields when loading, so adding fields is non-breaking. Removing or
renaming fields bumps `RESULT_SCHEMA_VERSION`.
