import type { RunEvent } from "../types";

const SHOWN = new Set([
  "step.started",
  "step.completed",
  "step.failed",
  "agent.completed",
  "agent.failed",
  "tool.call",
  "evidence.created",
  "evidence.rejected",
  "challenge.created",
  "claim.status",
  "budget.exceeded",
  "warning",
  "run.completed",
  "run.failed",
]);

function describe(e: RunEvent): string {
  const d = e.data as Record<string, string | number | boolean | null>;
  switch (e.type) {
    case "step.started":
      return `${e.step}`;
    case "step.completed":
      return `${e.step} done in ${d.duration_s}s`;
    case "agent.completed":
      return `${e.agent} finished (${d.duration_s}s)`;
    case "tool.call":
      return `${e.agent} called ${d.tool}`;
    case "evidence.created":
      return `${d.evidence_id} from ${d.source_id ?? "model knowledge"}${d.external ? " (verified)" : ""}`;
    case "evidence.rejected":
      return `citation by ${e.agent} rejected: ${d.reason}`;
    case "challenge.created":
      return `${d.challenge_id} ${d.kind} against ${d.target}`;
    case "claim.status":
      return `${d.claim_id} -> ${d.status}${d.policy_note ? ` (${d.policy_note})` : ""}`;
    case "run.completed":
      return `completed: ${d.calls} calls, ${Number(d.input_tokens) + Number(d.output_tokens)} tokens`;
    default:
      return String(d.error ?? d.message ?? "");
  }
}

export function EventLog({ events, live }: { events: RunEvent[]; live: boolean }) {
  const shown = events.filter((e) => SHOWN.has(e.type));
  return (
    <div className="card events">
      <h4>
        Trace {live && <span className="pulse" aria-label="live" />}
        <span className="muted small"> {events.length} events</span>
      </h4>
      <ol>
        {shown.map((e) => (
          <li key={e.seq} className={`ev-${e.type.replace(".", "-")}`}>
            <span className="mono muted">{e.type}</span> {describe(e)}
          </li>
        ))}
      </ol>
    </div>
  );
}
