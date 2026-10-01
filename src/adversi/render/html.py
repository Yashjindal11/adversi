"""Self-contained HTML report renderer (no template engine, everything escaped)."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from adversi.render.markdown import STATUS_LABEL

if TYPE_CHECKING:
    from adversi.protocol.result import AdverSIResult

_CSS = """
:root{--ink:#16142b;--muted:#5b5876;--line:#e3e1ef;--bg:#fbfaff;--accent:#4338ca;--amber:#d97706;--teal:#0d9488;--red:#dc2626}
*{box-sizing:border-box}body{font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);background:var(--bg);margin:0}
main{max-width:980px;margin:0 auto;padding:32px 20px 64px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
.brand{color:var(--accent);font-weight:700;letter-spacing:.02em;font-size:13px;text-transform:uppercase}
.answer{background:#fff;border:1px solid var(--line);border-left:4px solid var(--accent);padding:14px 18px;border-radius:8px}
table{border-collapse:collapse;width:100%;background:#fff}td,th{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;font-size:14px}
th{background:#f3f2fa}.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;color:#fff}
.supported{background:var(--teal)}.partially_supported{background:#14b8a6}.uncertain{background:var(--amber)}.unverified{background:#8b8aa3}
.unsupported{background:#b45309}.contradicted{background:var(--red)}blockquote{margin:4px 0 12px;padding:6px 12px;border-left:3px solid var(--line);color:var(--muted)}
.muted{color:var(--muted)}ul{padding-left:20px}
"""


def _e(text: object) -> str:
    return escape(str(text), quote=True)


def _list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>" if items else ""


def render_html(r: AdverSIResult) -> str:
    parts: list[str] = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        "<meta name=viewport content='width=device-width,initial-scale=1'>",
        f"<title>AdverSI - {_e(r.question[:80])}</title><style>{_CSS}</style></head><body><main>",
        "<div class=brand>AdverSI report</div>",
        f"<h1>{_e(r.question)}</h1>",
    ]
    s = r.synthesis
    if s:
        parts.append(f"<div class=answer><strong>{_e(s.answer)}</strong>")
        if s.summary and s.summary != s.answer:
            parts.append(f"<p>{_e(s.summary)}</p>")
        parts.append("</div>")
        if s.caveats:
            parts.append("<h2>Caveats</h2>" + _list(s.caveats))
        if s.recommendations:
            parts.append("<h2>Recommendations</h2>" + _list(s.recommendations))

    u = r.uncertainty
    rows = [
        ("Judged answer confidence", u.answer_confidence, True),
        ("Verdict disagreement (normalized entropy)", u.verdict_entropy, False),
        ("Confidence spread", u.confidence_spread, False),
        ("Claims with verified external evidence", u.external_evidence_coverage, True),
        ("Claims uncertain or unverified", u.unresolved_claim_ratio, True),
        ("Claims challenged", u.contested_claim_ratio, True),
        ("Citations rejected", u.citation_rejection_rate, True),
    ]
    parts.append("<h2>Uncertainty</h2><table>")
    for label, value, pct in rows:
        shown = "n/a" if value is None else (f"{value:.0%}" if pct else f"{value:.2f}")
        parts.append(f"<tr><th>{_e(label)}</th><td>{shown}</td></tr>")
    parts.append("</table>" + _list(u.notes))

    if r.claims:
        parts.append(
            "<h2>Claims</h2><table><tr><th>ID</th><th>Claim</th><th>Status</th><th>Conf.</th><th>Evidence +/-</th><th>By</th></tr>"
        )
        for c in r.claims:
            conf = "" if c.confidence is None else f"{c.confidence:.2f}"
            note = f"<div class=muted>{_e(c.policy_note)}</div>" if c.policy_note else ""
            parts.append(
                f"<tr><td>{_e(c.id)}</td><td>{_e(c.statement)}{note}</td>"
                f"<td><span class='pill {_e(c.status.value)}'>{_e(STATUS_LABEL[c.status])}</span></td>"
                f"<td>{conf}</td><td>{len(c.supporting_evidence_ids)}/{len(c.contradicting_evidence_ids)}</td>"
                f"<td>{_e(', '.join(c.asserted_by))}</td></tr>"
            )
        parts.append("</table>")

    if r.evidence:
        parts.append("<h2>Evidence</h2>")
        for e in r.evidence:
            p = e.provenance
            kind = "verified external" if e.is_external else p.source_type.value
            link = (
                f"<a href='{_e(p.uri)}' rel='noopener noreferrer'>{_e(p.title or p.uri)}</a>"
                if p.uri and p.uri.startswith(("http://", "https://"))
                else _e(p.title or e.source_id or "model knowledge")
            )
            rel = ", ".join(
                [
                    *(f"supports {c}" for c in e.supports),
                    *(f"contradicts {c}" for c in e.contradicts),
                ]
            )
            parts.append(
                f"<div><strong>{_e(e.id)}</strong> <span class=muted>({_e(kind)}; {_e(rel or 'unlinked')})</span> {link}<blockquote>{_e(e.excerpt)}</blockquote></div>"
            )

    if r.perspectives:
        parts.append("<h2>Agent perspectives</h2>")
        for pv in r.perspectives:
            parts.append(
                f"<h3>{_e(pv.agent)} <span class=muted>({_e(pv.role)}, {_e(pv.model)}{', revision ' + str(pv.round) if pv.round else ''})</span></h3>"
                f"<p><strong>Verdict:</strong> {_e(pv.verdict)} <span class=muted>confidence {_e(pv.confidence)}</span></p>"
                f"<p>{_e(pv.position)}</p><p class=muted>{_e(pv.summary)}</p>"
            )

    if r.challenges:
        parts.append("<h2>Cross-examination</h2><ul>")
        for ch in r.challenges:
            reb = "".join(
                f"<li>{_e(rb.agent)}{' (concedes)' if rb.concedes else ''}: {_e(rb.response)}</li>"
                for rb in ch.rebuttals
            )
            parts.append(
                f"<li><strong>{_e(ch.id)}</strong> &rarr; {_e(ch.target_claim_id)} ({_e(ch.kind.value)}, {_e(ch.outcome.value)}): {_e(ch.argument)}<ul>{reb}</ul></li>"
            )
        parts.append("</ul>")

    if r.critique:
        parts.append(
            "<h2>Critique</h2>"
            + _list([f"[{f.severity.value}, {f.kind.value}] {f.description}" for f in r.critique])
        )

    if r.unresolved_questions:
        parts.append("<h2>Open questions</h2>" + _list(r.unresolved_questions))

    m = r.metadata
    cost = f"${m.usage.cost_usd:.4f}" if m.usage.cost_usd is not None else "unknown"
    parts.append(
        "<h2>Run metadata</h2><table>"
        f"<tr><th>Run</th><td>{_e(m.run_id)} ({_e(m.workflow)}, {_e(m.profile)}, {_e(m.status.value)})</td></tr>"
        f"<tr><th>Usage</th><td>{m.usage.calls} calls, {m.usage.input_tokens:,} in / {m.usage.output_tokens:,} out tokens, cost {cost}</td></tr>"
        f"<tr><th>Agents</th><td>{_e(', '.join(f'{k}={v}' for k, v in m.agents.items()))}</td></tr>"
        f"<tr><th>Version</th><td>AdverSI {_e(m.adversi_version)}, schema {_e(m.schema_version)}</td></tr>"
        "</table>"
    )
    parts.append("</main></body></html>")
    return "".join(parts)
