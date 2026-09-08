"use client";

import { useState } from "react";
import Checks from "../../components/Checks.jsx";

/**
 * @param {{ samples: { jobId: string, text: string, sha: string }[] }} props
 */
export default function PanelForm({ samples }) {
  const [text, setText] = useState("");
  const [depth, setDepth] = useState("full");
  const [result, setResult] = useState(/** @type {any} */ (null));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch("/api/evaluate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, depth }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(typeof data?.error === "string" ? data.error : "request rejected");
      } else {
        setResult(data.evaluation);
      }
    } catch (e) {
      setError("could not reach the local evaluation endpoint: " + String(e));
    } finally {
      setBusy(false);
    }
  }

  /** @param {File | undefined} file */
  async function loadFile(file) {
    if (!file) return;
    setText(await file.text());
  }

  return (
    <div>
      <div className="row">
        <span>Load a sample:</span>
        {samples.map((s) => (
          <button key={s.jobId} onClick={() => setText(s.text)}>
            deliverable job {s.jobId}
          </button>
        ))}
        <label>
          or upload a text file:{" "}
          <input
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            onChange={(e) => loadFile(e.target.files?.[0])}
          />
        </label>
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="# Summary&#10;… paste deliverable text here …"
        spellCheck={false}
      />

      <div className="row">
        <label>
          Depth:{" "}
          <select value={depth} onChange={(e) => setDepth(e.target.value)}>
            <option value="sampling">sampling (first 2 sections)</option>
            <option value="full">full (all sections)</option>
          </select>
        </label>
        <button className="primary" onClick={run} disabled={busy || text.length === 0}>
          {busy ? "running…" : "Run checks"}
        </button>
        <button onClick={() => { setText(""); setResult(null); setError(""); }}>Clear</button>
      </div>

      {error ? <div className="card warn">{error}</div> : null}

      {result ? (
        <div>
          <h2>Result</h2>
          <div className="card">
            <dl className="kv">
              <dt>verdict (kind)</dt>
              <dd>
                <span className={"tag " + (result.verdict === 1 ? "pass" : "fail")}>
                  {result.verdict === 1 ? "COMPLETE (kind=1)" : "REJECT (kind=2)"}
                </span>
              </dd>
              <dt>failed_checks</dt>
              <dd className="mono">
                {result.failed_checks.length
                  ? JSON.stringify(result.failed_checks)
                  : "[] (empty)"}
              </dd>
              <dt>depth</dt>
              <dd className="mono">{result.depth}</dd>
              <dt>sections read</dt>
              <dd className="mono">
                {result.sections_read} of {result.sections}
              </dd>
              <dt>unverified</dt>
              <dd className="mono">
                {result.unverified.length ? result.unverified.join(", ") : "—"}
              </dd>
            </dl>
            <p className="lead" style={{ marginBottom: 0 }}>
              No transaction was sent and no memory was written by this attempt.
            </p>
          </div>
          <h2>Per-criterion evidence</h2>
          <Checks checks={result.checks} criteria={result.criteria} />
        </div>
      ) : null}
    </div>
  );
}
