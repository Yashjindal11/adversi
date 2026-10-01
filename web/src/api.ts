import type { AdverSIResult, Meta, RunEvent, RunSummary } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export interface RunInput {
  question: string;
  context?: string;
  mode: string;
  profile: string;
  model?: string;
  documents?: { title: string; content: string }[];
}

export const api = {
  meta: () => fetch("/api/meta").then((r) => json<Meta>(r)),
  runs: () => fetch("/api/runs").then((r) => json<RunSummary[]>(r)),
  create: (input: RunInput) =>
    fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }).then((r) => json<RunSummary>(r)),
  run: (id: string) =>
    fetch(`/api/runs/${encodeURIComponent(id)}`).then((r) =>
      json<RunSummary & { result: AdverSIResult | null }>(r),
    ),
  events: (id: string, after: number) =>
    fetch(`/api/runs/${encodeURIComponent(id)}/events?after=${after}`).then((r) => json<RunEvent[]>(r)),
};

export type StreamMessage =
  | { type: "event"; event: RunEvent }
  | { type: "end"; status: string; error: string | null }
  | { type: "error"; error: string };

/** Stream run events over WebSocket, falling back to polling if the socket cannot open. */
export function streamRun(id: string, onMessage: (m: StreamMessage) => void): () => void {
  let closed = false;
  let lastSeq = 0;
  let timer: number | undefined;
  const deliver = (m: StreamMessage) => {
    if (m.type === "event") {
      if (m.event.seq <= lastSeq) return;
      lastSeq = m.event.seq;
    }
    if (!closed) onMessage(m);
  };

  const poll = async () => {
    if (closed) return;
    try {
      for (const event of await api.events(id, lastSeq)) deliver({ type: "event", event });
      const run = await api.run(id);
      if (run.status !== "queued" && run.status !== "running") {
        deliver({ type: "end", status: run.status, error: run.error });
        return;
      }
    } catch (e) {
      deliver({ type: "error", error: (e as Error).message });
      return;
    }
    timer = window.setTimeout(poll, 1000);
  };

  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/api/runs/${encodeURIComponent(id)}/stream`);
  let opened = false;
  ws.onopen = () => (opened = true);
  ws.onmessage = (e) => deliver(JSON.parse(e.data) as StreamMessage);
  ws.onclose = () => {
    if (!opened && !closed) poll();
  };
  return () => {
    closed = true;
    window.clearTimeout(timer);
    ws.close();
  };
}
