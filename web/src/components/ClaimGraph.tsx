import { useMemo, useState } from "react";
import type { AdverSIResult } from "../types";

type Kind = "evidence" | "claim" | "challenge" | "assumption";
interface Node {
  id: string;
  kind: Kind;
  label: string;
  x: number;
  y: number;
  cls: string;
}
interface Edge {
  from: string;
  to: string;
  cls: "supports" | "contradicts" | "challenge" | "assumes";
}

const COL = { evidence: 110, claim: 420, challenge: 730, assumption: 730 };
const ROW = 46;
const short = (s: string, n = 42) => (s.length > n ? `${s.slice(0, n - 1)}\u2026` : s);

/**
 * Layered claim graph: evidence (left) -> claims (centre) <- challenges / assumptions (right).
 * A fixed layered layout keeps it deterministic and readable without a graph library.
 */
export function ClaimGraph({ result, onSelect }: { result: AdverSIResult; onSelect: (id: string) => void }) {
  const [hover, setHover] = useState<string | null>(null);

  const { nodes, edges, height } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];
    const place = (items: { id: string; label: string; cls: string }[], kind: Kind, offset = 0) =>
      items.forEach((it, i) => nodes.push({ ...it, kind, x: COL[kind], y: 40 + offset + i * ROW }));

    place(
      result.claims.map((c) => ({ id: c.id, label: short(c.statement), cls: `s-${c.status}` })),
      "claim",
    );
    place(
      result.evidence.map((e) => ({
        id: e.id,
        label: short(e.excerpt, 24),
        cls: e.excerpt_verified && e.provenance.source_type !== "model_knowledge" ? "ev-ext" : "ev-model",
      })),
      "evidence",
    );
    place(
      result.challenges.map((c) => ({ id: c.id, label: short(c.argument, 24), cls: `ch-${c.outcome}` })),
      "challenge",
    );
    place(
      result.assumptions.map((a) => ({ id: a.id, label: short(a.statement, 24), cls: a.critical ? "as-crit" : "as" })),
      "assumption",
      result.challenges.length * ROW + (result.challenges.length ? 24 : 0),
    );

    for (const e of result.evidence) {
      e.supports.forEach((c) => edges.push({ from: e.id, to: c, cls: "supports" }));
      e.contradicts.forEach((c) => edges.push({ from: e.id, to: c, cls: "contradicts" }));
    }
    result.challenges.forEach((c) => edges.push({ from: c.id, to: c.target_claim_id, cls: "challenge" }));
    result.assumptions.forEach((a) => a.claim_ids.forEach((c) => edges.push({ from: a.id, to: c, cls: "assumes" })));
    const height = Math.max(...nodes.map((n) => n.y), 0) + 40;
    return { nodes, edges, height };
  }, [result]);

  const byId = new Map(nodes.map((n) => [n.id, n]));
  const linked = new Set<string>();
  if (hover) {
    linked.add(hover);
    edges.forEach((e) => {
      if (e.from === hover || e.to === hover) {
        linked.add(e.from);
        linked.add(e.to);
      }
    });
  }

  if (!nodes.length) return <p className="muted">No claims were recorded.</p>;

  return (
    <div className="graph-wrap">
      <div className="legend">
        <span className="lg lg-supports">supports</span>
        <span className="lg lg-contradicts">contradicts</span>
        <span className="lg lg-challenge">challenge</span>
        <span className="lg lg-assumes">assumes</span>
        <span className="muted">Filled evidence = verified external excerpt; dashed = model knowledge. Hover to trace, click for details.</span>
      </div>
      <svg className="graph" viewBox={`0 0 840 ${height}`} role="img" aria-label="Claim graph">
        <text x={COL.evidence} y={16} className="col-h">Evidence</text>
        <text x={COL.claim} y={16} className="col-h">Claims</text>
        <text x={COL.challenge} y={16} className="col-h">Challenges / assumptions</text>
        {edges.map((e, i) => {
          const a = byId.get(e.from);
          const b = byId.get(e.to);
          if (!a || !b) return null;
          const x1 = a.x < b.x ? a.x + 95 : a.x - 95;
          const x2 = a.x < b.x ? b.x - 140 : b.x + 140;
          const dim = hover && !(linked.has(e.from) && linked.has(e.to));
          return (
            <path
              key={i}
              d={`M${x1},${a.y} C${(x1 + x2) / 2},${a.y} ${(x1 + x2) / 2},${b.y} ${x2},${b.y}`}
              className={`edge ${e.cls}${dim ? " dim" : ""}`}
            />
          );
        })}
        {nodes.map((n) => {
          const w = n.kind === "claim" ? 280 : 190;
          return (
            <g
              key={n.id}
              className={`node ${n.kind} ${n.cls}${hover && !linked.has(n.id) ? " dim" : ""}`}
              transform={`translate(${n.x - w / 2},${n.y - 16})`}
              onMouseEnter={() => setHover(n.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect(n.id)}
            >
              <rect width={w} height={32} rx={8} />
              <text x={10} y={20}>
                <tspan className="nid">{n.id}</tspan> {n.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
