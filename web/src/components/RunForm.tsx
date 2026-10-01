import { useState } from "react";
import type { RunInput } from "../api";
import type { Meta } from "../types";

const MODE_HELP: Record<string, string> = {
  simple: "One model call. The single-model baseline.",
  debate: "One analysis, then proponent vs skeptic, judge, synthesis.",
  adversarial: "Independent analysts, cross-examination, critique, judge.",
  research: "Full workflow: decomposition, analysts, research, evidence analysis, debate, cross-examination, critique, judge.",
  peer_review: "Independent analysts revise after seeing each other's structured positions.",
  jury: "Independent analysts, cross-examination, several independent judges (no majority vote).",
};

export function RunForm({ meta, busy, onSubmit }: { meta: Meta | null; busy: boolean; onSubmit: (input: RunInput) => void }) {
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState("");
  const [mode, setMode] = useState("research");
  const [profile, setProfile] = useState("fast");
  const [model, setModel] = useState("");
  const [docs, setDocs] = useState<{ title: string; content: string }[]>([]);

  const addFiles = async (files: FileList | null) => {
    if (!files) return;
    const loaded = await Promise.all([...files].map(async (f) => ({ title: f.name, content: await f.text() })));
    setDocs((d) => [...d, ...loaded].slice(0, 10));
  };

  return (
    <form
      className="card form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!question.trim()) return;
        onSubmit({ question, context: context || undefined, mode, profile, model: model || undefined, documents: docs });
      }}
    >
      <label>
        Question
        <textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={3} maxLength={4000} placeholder="Should we ...? Does X cause Y? Is design A safer than B?" required />
      </label>
      <label>
        <span>Context <span className="muted small">(optional)</span></span>
        <textarea value={context} onChange={(e) => setContext(e.target.value)} rows={2} maxLength={20000} />
      </label>
      <div className="row wrap">
        <label>
          Mode
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            {(meta?.modes ?? Object.keys(MODE_HELP)).map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
        <label>
          Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value)}>
            {(meta?.profiles ?? ["fast", "balanced", "deep"]).map((p) => <option key={p}>{p}</option>)}
          </select>
        </label>
        <label className="grow">
          <span>Model <span className="muted small">(provider:model, blank = server default)</span></span>
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="openai:gpt-4o-mini" />
        </label>
      </div>
      <p className="muted small">{MODE_HELP[mode]}</p>
      <div className="row wrap">
        <label className="file">
          Add documents
          <input type="file" multiple accept=".txt,.md,.csv,.json" onChange={(e) => addFiles(e.target.files)} />
        </label>
        {docs.map((d, i) => (
          <span key={i} className="tag">
            {d.title} <button type="button" className="link" onClick={() => setDocs(docs.filter((_, j) => j !== i))}>&times;</button>
          </span>
        ))}
      </div>
      <button className="primary" disabled={busy || !question.trim()}>{busy ? "Running\u2026" : "Run"}</button>
    </form>
  );
}
