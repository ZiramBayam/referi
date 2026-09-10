"use client";

import { useRef, useState } from "react";
import { Loader2, Play, Upload, X } from "lucide-react";
import Checks from "../../components/Checks.jsx";
import { buttonClasses } from "../../components/ui/Button.jsx";
import { KeyValue, KeyValues, Notice, Tag } from "../../components/PageShell.jsx";

/**
 * @param {{ samples: { jobId: string, text: string, sha: string }[] }} props
 */
export default function PanelForm({ samples }) {
  const [text, setText] = useState("");
  const [depth, setDepth] = useState("full");
  const [result, setResult] = useState(/** @type {any} */ (null));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(/** @type {any} */ (null));

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

  /** @param {any} file */
  async function loadFile(file) {
    if (!file) return;
    setText(await file.text());
  }

  return (
    <div>
      <div className="rounded-2xl border border-border bg-surface p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-sm text-muted">Load a sample:</span>
          {samples.map((s) => (
            <button
              key={s.jobId}
              type="button"
              onClick={() => setText(s.text)}
              className={buttonClasses("secondary", "sm")}
            >
              deliverable job {s.jobId}
            </button>
          ))}
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className={buttonClasses("ghost", "sm")}
          >
            <Upload className="size-3.5" strokeWidth={2} aria-hidden />
            or upload a text file
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            onChange={(e) => loadFile(e.target.files?.[0])}
            className="sr-only"
          />
        </div>

        {/* Placeholder BUKAN label: ia hilang begitu juri mengetik, dan pembaca layar
            tidak mengumumkannya sebagai nama field (WCAG 3.3.2). */}
        <label htmlFor="deliverable" className="mt-6 block text-sm font-medium text-ink">
          Deliverable text to evaluate
        </label>
        <textarea
          id="deliverable"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="# Summary&#10;… paste deliverable text here …"
          spellCheck={false}
          rows={14}
          className="mt-2 w-full resize-y rounded-xl border border-border bg-bg px-4 py-3.5 font-mono text-xs leading-relaxed text-ink outline-none transition-colors placeholder:text-faint focus:border-primary"
        />

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-muted">
            Depth
            <select
              value={depth}
              onChange={(e) => setDepth(e.target.value)}
              className="h-9 rounded-lg border border-border bg-surface-2 px-2.5 text-sm text-ink outline-none transition-colors hover:border-border-strong focus:border-primary"
            >
              <option value="sampling">sampling (first 2 sections)</option>
              <option value="full">full (all sections)</option>
            </select>
          </label>
          <button
            type="button"
            onClick={run}
            disabled={busy || text.length === 0}
            className={buttonClasses("primary", "md")}
          >
            {busy ? (
              <>
                <Loader2 className="size-4 animate-spin" strokeWidth={2.25} aria-hidden />
                running
              </>
            ) : (
              <>
                <Play className="size-4" strokeWidth={2.25} aria-hidden />
                Run checks
              </>
            )}
          </button>
          <button
            type="button"
            onClick={() => {
              setText("");
              setResult(null);
              setError("");
            }}
            className={buttonClasses("ghost", "md")}
          >
            <X className="size-4" strokeWidth={2} aria-hidden />
            Clear
          </button>
        </div>
      </div>

      {/* Hasil dan galat muncul jauh dari tombol; tanpa live region, pengguna pembaca
          layar menekan "Run checks" lalu tidak mendengar apa pun. */}
      <div aria-live="polite">
        {error && (
          <Notice className="mt-4" tone="warn" title="Request rejected.">
            <span className="font-mono text-xs text-ink">{error}</span>
          </Notice>
        )}

        {result && (
          <div className="mt-10">
            <h2 className="font-display text-2xl font-semibold text-ink">Result</h2>
            <div className="mt-4 rounded-2xl border border-border bg-surface px-5 py-1">
              <KeyValues>
                <KeyValue label="verdict (kind)">
                  <Tag status={result.verdict === 1 ? "pass" : "fail"}>
                    {result.verdict === 1 ? "COMPLETE (kind=1)" : "REJECT (kind=2)"}
                  </Tag>
                </KeyValue>
                <KeyValue label="failed_checks">
                  <span className="font-mono text-xs">
                    {result.failed_checks.length
                      ? JSON.stringify(result.failed_checks)
                      : "[] (empty)"}
                  </span>
                </KeyValue>
                <KeyValue label="depth">
                  <span className="font-mono text-xs">{result.depth}</span>
                </KeyValue>
                <KeyValue label="sections read">
                  <span className="font-mono text-xs tnum">
                    {result.sections_read} of {result.sections}
                  </span>
                </KeyValue>
                <KeyValue label="unverified">
                  <span className="font-mono text-xs">
                    {result.unverified.length ? result.unverified.join(", ") : "none"}
                  </span>
                </KeyValue>
              </KeyValues>
            </div>
            <Notice className="mt-4">
              No transaction was sent and no memory was written by this attempt.
            </Notice>

            <h2 className="mt-10 font-display text-2xl font-semibold text-ink">
              Per-criterion evidence
            </h2>
            <div className="mt-4">
              <Checks checks={result.checks} criteria={result.criteria} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
