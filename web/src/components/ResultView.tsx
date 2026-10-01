import { useState } from "react";
import type { AdverSIResult, Claim } from "../types";
import { ClaimGraph } from "./ClaimGraph";
import { StatusPill, num, pct } from "./StatusPill";

const TABS = ["Synthesis", "Claims", "Evidence", "Perspectives", "Debate", "Critique", "Uncertainty", "Run"] as const;
type Tab = (typeof TABS)[number];

export function ResultView({ result }: { result: AdverSIResult }) {
  const [tab, setTab] = useState<Tab>("Synthesis");
  const [selected, setSelected] = useState<string | null>(null);
  const claims = new Map(result.claims.map((c) => [c.id, c]));

  const counts = {
    Claims: result.claims.length,
    Evidence: result.evidence.length,
    Perspectives: result.perspectives.length,
    Debate: result.debate.length + result.challenges.length,
    Critique: result.critique.length,
  } as Partial<Record<Tab, number>>;

  return (
    <section className="result">
      <h2 className="question">{result.question}</h2>
      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t}
            {counts[t] ? <span className="count">{counts[t]}</span> : null}
          </button>
        ))}
      </nav>

      {tab === "Synthesis" && <SynthesisTab result={result} claims={claims} />}
      {tab === "Claims" && (
        <>
          <ClaimGraph result={result} onSelect={setSelected} />
          {selected && <Detail id={selected} result={result} onClose={() => setSelected(null)} />}
          <ClaimTable claims={result.claims} onSelect={setSelected} />
        </>
      )}
      {tab === "Evidence" && <EvidenceTab result={result} />}
      {tab === "Perspectives" && <PerspectivesTab result={result} />}
      {tab === "Debate" && <DebateTab result={result} claims={claims} />}
      {tab === "Critique" && <CritiqueTab result={result} />}
      {tab === "Uncertainty" && <UncertaintyTab result={result} />}
      {tab === "Run" && <RunTab result={result} />}
    </section>
  );
}

function ClaimRef({ id, claims }: { id: string; claims: Map<string, Claim> }) {
  const c = claims.get(id);
  if (!c) return <code>{id}</code>;
  return (
    <li>
      <code>{c.id}</code> {c.statement} <StatusPill status={c.status} />
    </li>
  );
}

function SynthesisTab({ result, claims }: { result: AdverSIResult; claims: Map<string, Claim> }) {
  const s = result.synthesis;
  if (!s) return <p className="muted">No synthesis was produced. See the Run tab for errors.</p>;
  const groups: [string, string[]][] = [
    ["Established", s.established_claim_ids],
    ["Disputed", s.disputed_claim_ids],
    ["Uncertain", s.uncertain_claim_ids],
    ["Rejected", s.rejected_claim_ids],
  ];
  return (
    <div className="stack">
      <div className="answer">
        <p className="answer-text">{s.answer}</p>
        {s.summary && s.summary !== s.answer && <p className="whitespace">{s.summary}</p>}
        <p className="muted">
          Judged confidence {pct(result.uncertainty.answer_confidence)} &middot; external evidence coverage{" "}
          {pct(result.uncertainty.external_evidence_coverage)}
        </p>
      </div>
      <div className="grid2">
        {groups.map(([label, ids]) =>
          ids.length ? (
            <div key={label} className="card">
              <h4>{label}</h4>
              <ul className="plain">{ids.map((id) => <ClaimRef key={id} id={id} claims={claims} />)}</ul>
            </div>
          ) : null,
        )}
      </div>
      {s.caveats.length > 0 && (
        <div className="card">
          <h4>Caveats</h4>
          <ul>{s.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}
      {s.recommendations.length > 0 && (
        <div className="card">
          <h4>Recommendations</h4>
          <ul>{s.recommendations.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function ClaimTable({ claims, onSelect }: { claims: Claim[]; onSelect: (id: string) => void }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Claim</th>
          <th>Type</th>
          <th>Status</th>
          <th>Conf.</th>
          <th>+/-</th>
          <th>Asserted by</th>
        </tr>
      </thead>
      <tbody>
        {claims.map((c) => (
          <tr key={c.id} onClick={() => onSelect(c.id)} className="clickable">
            <td><code>{c.id}</code></td>
            <td>
              {c.statement}
              {c.policy_note && <div className="note">policy: {c.policy_note}</div>}
            </td>
            <td>{c.claim_type}<div className="muted small">{c.basis}</div></td>
            <td><StatusPill status={c.status} /></td>
            <td>{num(c.confidence)}</td>
            <td>{c.supporting_evidence_ids.length}/{c.contradicting_evidence_ids.length}</td>
            <td>{[...new Set(c.attributions.map((a) => a.agent))].join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Detail({ id, result, onClose }: { id: string; result: AdverSIResult; onClose: () => void }) {
  const claim = result.claims.find((c) => c.id === id);
  const ev = result.evidence.find((e) => e.id === id);
  const ch = result.challenges.find((c) => c.id === id);
  const as = result.assumptions.find((a) => a.id === id);
  return (
    <div className="card detail">
      <button className="close" onClick={onClose} aria-label="Close">&times;</button>
      {claim && (
        <>
          <h4><code>{claim.id}</code> {claim.statement}</h4>
          <p><StatusPill status={claim.status} />{" "}
            {claim.proposed_status && claim.proposed_status !== claim.status && (
              <span className="muted">judge proposed {claim.proposed_status}; adjusted by policy</span>
            )}
          </p>
          {claim.status_rationale && <p>{claim.status_rationale}</p>}
          <p className="muted small">
            {claim.attributions.map((a) => `${a.agent} (${a.step}, conf ${num(a.confidence)})`).join(" \u00b7 ")}
          </p>
        </>
      )}
      {ev && (
        <>
          <h4><code>{ev.id}</code> {ev.provenance.source_type}</h4>
          <blockquote>{ev.excerpt}</blockquote>
          <SourceLink uri={ev.provenance.uri} title={ev.provenance.title} />
        </>
      )}
      {ch && (
        <>
          <h4><code>{ch.id}</code> {ch.kind} &rarr; {ch.target_claim_id} ({ch.outcome})</h4>
          <p>{ch.argument}</p>
          {ch.rebuttals.map((r, i) => <p key={i} className="muted">{r.agent}: {r.response}</p>)}
        </>
      )}
      {as && (
        <>
          <h4><code>{as.id}</code> {as.critical ? "critical assumption" : "assumption"}</h4>
          <p>{as.statement}</p>
        </>
      )}
    </div>
  );
}

function SourceLink({ uri, title }: { uri: string | null; title: string | null }) {
  if (uri && /^https?:\/\//.test(uri)) {
    return <a href={uri} target="_blank" rel="noopener noreferrer">{title || uri}</a>;
  }
  return <span className="muted">{title || uri || "no external source"}</span>;
}

function EvidenceTab({ result }: { result: AdverSIResult }) {
  if (!result.evidence.length && !result.rejected_citations.length)
    return <p className="muted">No evidence was cited.</p>;
  return (
    <div className="stack">
      {result.evidence.map((e) => {
        const external = e.excerpt_verified && e.provenance.source_type !== "model_knowledge";
        return (
          <div key={e.id} className={`card ev ${external ? "external" : "model"}`}>
            <div className="row">
              <code>{e.id}</code>
              <span className={`tag ${external ? "tag-ext" : "tag-model"}`}>
                {external ? "verified external" : e.provenance.source_type.replace(/_/g, " ")}
              </span>
              {e.supports.length > 0 && <span className="tag tag-sup">supports {e.supports.join(", ")}</span>}
              {e.contradicts.length > 0 && <span className="tag tag-con">contradicts {e.contradicts.join(", ")}</span>}
              {e.reliability != null && <span className="muted small">reliability {num(e.reliability)}</span>}
            </div>
            <blockquote>{e.excerpt}</blockquote>
            <div className="small">
              <SourceLink uri={e.provenance.uri} title={e.provenance.title} />
              <span className="muted"> &middot; cited by {e.cited_by}{e.provenance.tool_name ? ` via ${e.provenance.tool_name}` : ""}</span>
            </div>
            {e.reliability_rationale && <p className="muted small">{e.reliability_rationale}</p>}
          </div>
        );
      })}
      {result.rejected_citations.length > 0 && (
        <div className="card warn">
          <h4>Rejected citations ({result.rejected_citations.length})</h4>
          <p className="muted small">Excerpts that could not be found in the cited source. They are excluded from all judgments.</p>
          <ul>{result.rejected_citations.map((r, i) => <li key={i}>{r.agent} &rarr; {r.source_id ?? "?"}: {r.reason}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function PerspectivesTab({ result }: { result: AdverSIResult }) {
  return (
    <div className="grid2">
      {result.perspectives.map((p, i) => (
        <div key={i} className="card">
          <div className="row">
            <strong>{p.agent}</strong>
            <span className="muted small">{p.role} &middot; {p.model}{p.round ? ` \u00b7 revision ${p.round}` : ""}</span>
          </div>
          <p><span className="tag">{p.verdict}</span> <span className="muted small">confidence {num(p.confidence)}</span></p>
          <p>{p.position}</p>
          <p className="muted">{p.summary}</p>
          {p.claim_ids.length > 0 && <p className="small">Claims: {p.claim_ids.join(", ")}</p>}
          {p.counterarguments.length > 0 && (
            <>
              <h5>Counterarguments considered</h5>
              <ul>{p.counterarguments.map((c, j) => <li key={j}>{c}</li>)}</ul>
            </>
          )}
          {p.uncertainties.length > 0 && (
            <>
              <h5>Uncertainties</h5>
              <ul>{p.uncertainties.map((c, j) => <li key={j}>{c}</li>)}</ul>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

function DebateTab({ result, claims }: { result: AdverSIResult; claims: Map<string, Claim> }) {
  return (
    <div className="stack">
      {result.debate.length > 0 && (
        <div className="card">
          <h4>Debate</h4>
          {result.debate.map((t, i) => (
            <div key={i} className={`turn ${t.stance}`}>
              <div className="row">
                <strong>{t.agent}</strong>
                <span className="muted small">round {t.round} &middot; {t.stance}{t.concedes ? " \u00b7 concedes" : ""}</span>
              </div>
              <p>{t.argument}</p>
            </div>
          ))}
        </div>
      )}
      {result.challenges.length > 0 && (
        <div className="card">
          <h4>Cross-examination</h4>
          {result.challenges.map((c) => (
            <div key={c.id} className="challenge">
              <div className="row">
                <code>{c.id}</code>
                <span className="tag">{c.kind.replace(/_/g, " ")}</span>
                <span className={`tag out-${c.outcome}`}>{c.outcome}</span>
                <span className="muted small">{c.challenger} &rarr; {c.target_claim_id}</span>
              </div>
              <p className="muted small">{claims.get(c.target_claim_id)?.statement}</p>
              <p>{c.argument}</p>
              {c.rebuttals.map((r, i) => (
                <p key={i} className="rebuttal"><strong>{r.agent}{r.concedes ? " (concedes)" : ""}:</strong> {r.response}</p>
              ))}
            </div>
          ))}
        </div>
      )}
      {!result.debate.length && !result.challenges.length && <p className="muted">This workflow had no debate step.</p>}
    </div>
  );
}

function CritiqueTab({ result }: { result: AdverSIResult }) {
  return (
    <div className="stack">
      {result.critique.map((f) => (
        <div key={f.id} className={`card sev-${f.severity}`}>
          <div className="row">
            <code>{f.id}</code>
            <span className="tag">{f.kind.replace(/_/g, " ")}</span>
            <span className={`tag sev`}>{f.severity}</span>
            {f.target_ids.length > 0 && <span className="muted small">{f.target_ids.join(", ")}</span>}
          </div>
          <p>{f.description}</p>
        </div>
      ))}
      {result.judgment?.overall_assessment && (
        <div className="card">
          <h4>Judgment</h4>
          <p className="whitespace">{result.judgment.overall_assessment}</p>
        </div>
      )}
      {!result.critique.length && !result.judgment && <p className="muted">No critique or judgment in this workflow.</p>}
    </div>
  );
}

function UncertaintyTab({ result }: { result: AdverSIResult }) {
  const u = result.uncertainty;
  const rows: [string, string, string][] = [
    ["Judged answer confidence", pct(u.answer_confidence), "Judge's stated probability; not calibrated by AdverSI."],
    ["Verdict disagreement", num(u.verdict_entropy), "Normalized entropy of independent agents' verdicts (0 = all agree)."],
    ["Confidence spread", num(u.confidence_spread), "Std-dev of independent agents' self-reported confidence."],
    ["External evidence coverage", pct(u.external_evidence_coverage), "Claims with at least one verified external excerpt."],
    ["Unresolved claims", pct(u.unresolved_claim_ratio), "Claims left uncertain or unverified."],
    ["Challenged claims", pct(u.contested_claim_ratio), "Claims targeted in cross-examination."],
    ["Rejected citations", pct(u.citation_rejection_rate), "Citations whose excerpt was not found in the source."],
  ];
  return (
    <div className="stack">
      <table className="table">
        <tbody>
          {rows.map(([k, v, hint]) => (
            <tr key={k}>
              <th>{k}</th>
              <td className="mono">{v}</td>
              <td className="muted small">{hint}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {u.notes.length > 0 && <div className="card warn"><ul>{u.notes.map((n, i) => <li key={i}>{n}</li>)}</ul></div>}
      {result.unresolved_questions.length > 0 && (
        <div className="card">
          <h4>Open questions</h4>
          <ul>{result.unresolved_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function RunTab({ result }: { result: AdverSIResult }) {
  const m = result.metadata;
  return (
    <div className="stack">
      <table className="table">
        <tbody>
          <tr><th>Run</th><td className="mono">{m.run_id} &middot; {m.workflow} &middot; {m.profile} &middot; {m.status}</td></tr>
          <tr><th>Usage</th><td>{m.usage.calls} calls &middot; {m.usage.input_tokens.toLocaleString()} in / {m.usage.output_tokens.toLocaleString()} out tokens &middot; cost {m.usage.cost_usd == null ? "unknown (no prices configured)" : `$${m.usage.cost_usd.toFixed(4)}`}</td></tr>
          <tr><th>Duration</th><td>{num(m.duration_s, 1)}s</td></tr>
          <tr><th>Version</th><td>AdverSI {m.adversi_version}, schema {m.schema_version}</td></tr>
          <tr><th>Tools</th><td>{m.tools.join(", ") || "none"}</td></tr>
        </tbody>
      </table>
      <div className="grid2">
        <div className="card">
          <h4>Agents</h4>
          <ul className="plain">{Object.entries(m.agents).map(([a, model]) => <li key={a}><strong>{a}</strong> <span className="muted">{model}</span></li>)}</ul>
        </div>
        <div className="card">
          <h4>Steps</h4>
          <ul className="plain">{m.steps.map((s) => <li key={s.name}>{s.ok ? "\u2713" : "\u2717"} {s.name} <span className="muted">{num(s.duration_s, 1)}s</span></li>)}</ul>
        </div>
      </div>
      {m.errors.length > 0 && (
        <div className="card warn">
          <h4>Errors</h4>
          <ul>{m.errors.map((e, i) => <li key={i}>[{e.step}{e.agent ? `/${e.agent}` : ""}] {e.type}: {e.message}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
