"""Markdown report renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adversi.protocol.claims import ClaimStatus

if TYPE_CHECKING:
    from adversi.protocol.result import AdverSIResult

STATUS_LABEL = {
    ClaimStatus.SUPPORTED: "supported",
    ClaimStatus.PARTIALLY_SUPPORTED: "partially supported",
    ClaimStatus.UNSUPPORTED: "unsupported",
    ClaimStatus.CONTRADICTED: "contradicted",
    ClaimStatus.UNCERTAIN: "uncertain",
    ClaimStatus.UNVERIFIED: "unverified",
}


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def _num(v: float | None, digits: int = 2) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def render_markdown(r: AdverSIResult) -> str:
    out: list[str] = [f"# {r.question}", ""]
    s = r.synthesis
    if s:
        out += ["## Answer", "", s.answer, ""]
        if s.summary and s.summary != s.answer:
            out += [s.summary, ""]
        if s.caveats:
            out += ["**Caveats**", "", *[f"- {c}" for c in s.caveats], ""]
        if s.recommendations:
            out += ["**Recommendations**", "", *[f"- {c}" for c in s.recommendations], ""]
    else:
        out += ["_No synthesis was produced._", ""]

    u = r.uncertainty
    out += [
        "## Uncertainty",
        "",
        f"- Judged answer confidence: {_pct(u.answer_confidence)}",
        f"- Verdict disagreement (normalized entropy): {_num(u.verdict_entropy)}",
        f"- Confidence spread across independent agents: {_num(u.confidence_spread)}",
        f"- Claims with verified external evidence: {_pct(u.external_evidence_coverage)}",
        f"- Claims left uncertain or unverified: {_pct(u.unresolved_claim_ratio)}",
        f"- Claims challenged: {_pct(u.contested_claim_ratio)}",
        f"- Citations rejected as unverifiable: {_pct(u.citation_rejection_rate)}",
        *[f"- {n}" for n in u.notes],
        "",
    ]

    if r.claims:
        out += [
            "## Claims",
            "",
            "| ID | Claim | Type | Status | Conf. | Evidence (+/-) | Asserted by |",
            "|---|---|---|---|---|---|---|",
        ]
        for c in r.claims:
            out.append(
                f"| {c.id} | {_cell(c.statement)} | {c.claim_type.value} | {STATUS_LABEL[c.status]} | "
                f"{_num(c.confidence)} | {len(c.supporting_evidence_ids)}/{len(c.contradicting_evidence_ids)} | "
                f"{', '.join(c.asserted_by)} |"
            )
        notes = [c for c in r.claims if c.policy_note]
        if notes:
            out += ["", "Status policy adjustments:", ""]
            out += [f"- {c.id}: {c.policy_note}" for c in notes]
        out.append("")

    if r.evidence:
        out += ["## Evidence", ""]
        for e in r.evidence:
            p = e.provenance
            kind = "verified external" if e.is_external else p.source_type.value.replace("_", " ")
            where = p.uri or p.title or (e.source_id or "model knowledge")
            rel = []
            if e.supports:
                rel.append(f"supports {', '.join(e.supports)}")
            if e.contradicts:
                rel.append(f"contradicts {', '.join(e.contradicts)}")
            rel_txt = "; ".join(rel) or "unlinked"
            reliability = f", reliability {e.reliability:.2f}" if e.reliability is not None else ""
            out.append(f"- **{e.id}** ({kind}{reliability}; {rel_txt}) - {where}")
            out.append(f"  > {_cell(e.excerpt)}")
        out.append("")

    if r.assumptions:
        out += ["## Assumptions", ""]
        out += [
            f"- **{a.id}**{' (critical)' if a.critical else ''}: {a.statement} - claims {', '.join(a.claim_ids)}"
            for a in r.assumptions
        ]
        out.append("")

    if r.perspectives:
        out += ["## Agent perspectives", ""]
        for pv in r.perspectives:
            label = f"{pv.agent} ({pv.role}, {pv.model})" + (
                f", revision {pv.round}" if pv.round else ""
            )
            out += [
                f"### {label}",
                "",
                f"**Verdict:** {pv.verdict} (confidence {_num(pv.confidence)})",
                "",
                pv.position,
                "",
            ]
            if pv.summary:
                out += [pv.summary, ""]
            if pv.counterarguments:
                out += [
                    "Counterarguments considered:",
                    "",
                    *[f"- {c}" for c in pv.counterarguments],
                    "",
                ]

    if r.debate:
        out += ["## Debate", ""]
        out += [
            f"- Round {t.round}, **{t.agent}** ({t.stance.value}{', concedes' if t.concedes else ''}): {t.argument}"
            for t in r.debate
        ]
        out.append("")

    if r.challenges:
        out += ["## Cross-examination", ""]
        for ch in r.challenges:
            out.append(
                f"- **{ch.id}** -> {ch.target_claim_id} ({ch.kind.value}, {ch.outcome.value}) by {ch.challenger}: {ch.argument}"
            )
            out += [
                f"  - {rb.agent}{' (concedes)' if rb.concedes else ''}: {rb.response}"
                for rb in ch.rebuttals
            ]
        out.append("")

    if r.critique:
        out += ["## Critique", ""]
        out += [
            f"- **{f.id}** [{f.severity.value}, {f.kind.value}] {f.description}"
            + (f" ({', '.join(f.target_ids)})" if f.target_ids else "")
            for f in r.critique
        ]
        out.append("")

    if r.judgment and r.judgment.overall_assessment:
        out += ["## Judgment", "", r.judgment.overall_assessment, ""]

    if r.unresolved_questions:
        out += ["## Open questions", "", *[f"- {q}" for q in r.unresolved_questions], ""]

    m = r.metadata
    usage = m.usage
    cost = (
        f"${usage.cost_usd:.4f}" if usage.cost_usd is not None else "unknown (no prices configured)"
    )
    out += [
        "## Run metadata",
        "",
        f"- Run `{m.run_id}`, workflow `{m.workflow}`, profile `{m.profile}`, status **{m.status.value}**",
        f"- {usage.calls} model calls, {usage.input_tokens:,} input / {usage.output_tokens:,} output tokens, cost {cost}",
        f"- Duration {_num(m.duration_s, 1)}s; AdverSI {m.adversi_version}, schema {m.schema_version}",
        f"- Agents: {', '.join(f'{k}={v}' for k, v in m.agents.items())}",
    ]
    if m.tools:
        out.append(f"- Tools: {', '.join(m.tools)}")
    out += [
        f"- Error in {e.step or '?'}{f' ({e.agent})' if e.agent else ''}: {e.type}: {e.message}"
        for e in m.errors
    ]
    if r.rejected_citations:
        out.append(f"- {len(r.rejected_citations)} citation(s) rejected during verification")
    out.append("")
    return "\n".join(out)
