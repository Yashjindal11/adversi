import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamRun, type RunInput } from "./api";
import { EventLog } from "./components/EventLog";
import { Logo } from "./components/Logo";
import { ResultView } from "./components/ResultView";
import { RunForm } from "./components/RunForm";
import type { AdverSIResult, Meta, RunEvent, RunSummary } from "./types";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [offline, setOffline] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [result, setResult] = useState<AdverSIResult | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closeStream = useRef<(() => void) | null>(null);

  const refreshRuns = useCallback(() => api.runs().then(setRuns).catch(() => undefined), []);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setOffline(true));
    refreshRuns();
    return () => closeStream.current?.();
  }, [refreshRuns]);

  const open = useCallback(
    (id: string) => {
      closeStream.current?.();
      setActiveId(id);
      setEvents([]);
      setResult(null);
      setError(null);
      setLive(true);
      closeStream.current = streamRun(id, (msg) => {
        if (msg.type === "event") setEvents((ev) => [...ev, msg.event]);
        else if (msg.type === "end") {
          setLive(false);
          if (msg.error) setError(msg.error);
          api.run(id).then((r) => setResult(r.result)).catch((e: Error) => setError(e.message));
          refreshRuns();
        } else {
          setLive(false);
          setError(msg.error);
        }
      });
    },
    [refreshRuns],
  );

  const submit = async (input: RunInput) => {
    setError(null);
    try {
      const run = await api.create(input);
      await refreshRuns();
      open(run.run_id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const loadFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as AdverSIResult;
      if (!parsed.metadata || !Array.isArray(parsed.claims)) throw new Error("not an AdverSI result file");
      closeStream.current?.();
      setActiveId(null);
      setEvents([]);
      setResult(parsed);
      setError(null);
    } catch (e) {
      setError(`Could not open file: ${(e as Error).message}`);
    }
  };

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <Logo />
          <div>
            <strong>AdverSI</strong>
            <span className="muted small"> Independent reasoning. Adversarial critique. Evidence. Synthesis.</span>
          </div>
        </div>
        <label className="file small">
          Open result JSON
          <input type="file" accept="application/json,.json" onChange={(e) => loadFile(e.target.files?.[0])} />
        </label>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <button className="primary block" onClick={() => { setActiveId(null); setResult(null); setEvents([]); }}>
            New run
          </button>
          <h5>Runs</h5>
          {runs.length === 0 && <p className="muted small">No runs yet.</p>}
          <ul className="runs">
            {runs.map((r) => (
              <li key={r.run_id} className={r.run_id === activeId ? "active" : ""}>
                <button className="link" onClick={() => open(r.run_id)}>
                  <span className={`dot st-${r.status}`} /> {r.question.slice(0, 60)}
                  <div className="muted small">{r.mode} &middot; {r.status}</div>
                </button>
              </li>
            ))}
          </ul>
          {meta && (
            <>
              <h5>Providers</h5>
              <ul className="plain small">
                {meta.providers.map((p) => (
                  <li key={p.name}><span className={`dot ${p.configured ? "st-completed" : "st-queued"}`} /> {p.name}</li>
                ))}
              </ul>
            </>
          )}
        </aside>

        <main className="main">
          {offline && (
            <div className="card warn small">
              No AdverSI server detected. Start one with <code>adversi serve</code>, or open a saved result JSON to explore it offline.
            </div>
          )}
          {error && <div className="card error">{error}</div>}
          {!activeId && !result && <RunForm meta={meta} busy={false} onSubmit={submit} />}
          {(activeId || events.length > 0) && !result && <EventLog events={events} live={live} />}
          {result && <ResultView result={result} />}
        </main>
      </div>
    </div>
  );
}
