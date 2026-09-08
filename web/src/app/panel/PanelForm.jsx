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
        setError(typeof data?.error === "string" ? data.error : "permintaan ditolak");
      } else {
        setResult(data.evaluation);
      }
    } catch (e) {
      setError("gagal menghubungi endpoint evaluasi lokal: " + String(e));
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
        <span>Muat contoh:</span>
        {samples.map((s) => (
          <button key={s.jobId} onClick={() => setText(s.text)}>
            deliverable job {s.jobId}
          </button>
        ))}
        <label>
          atau unggah berkas teks:{" "}
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
        placeholder="# Summary&#10;… tempel teks deliverable di sini …"
        spellCheck={false}
      />

      <div className="row">
        <label>
          Kedalaman:{" "}
          <select value={depth} onChange={(e) => setDepth(e.target.value)}>
            <option value="sampling">sampling (2 bagian pertama)</option>
            <option value="full">full (seluruh bagian)</option>
          </select>
        </label>
        <button className="primary" onClick={run} disabled={busy || text.length === 0}>
          {busy ? "menjalankan…" : "Jalankan cek"}
        </button>
        <button onClick={() => { setText(""); setResult(null); setError(""); }}>Bersihkan</button>
      </div>

      {error ? <div className="card warn">{error}</div> : null}

      {result ? (
        <div>
          <h2>Hasil</h2>
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
                  : "[] (kosong)"}
              </dd>
              <dt>kedalaman</dt>
              <dd className="mono">{result.depth}</dd>
              <dt>bagian dibaca</dt>
              <dd className="mono">
                {result.sections_read} dari {result.sections}
              </dd>
              <dt>tidak diverifikasi</dt>
              <dd className="mono">
                {result.unverified.length ? result.unverified.join(", ") : "—"}
              </dd>
            </dl>
            <p className="lead" style={{ marginBottom: 0 }}>
              Tidak ada transaksi yang dikirim dan tidak ada memori yang ditulis oleh
              percobaan ini.
            </p>
          </div>
          <h2>Bukti per-kriteria</h2>
          <Checks checks={result.checks} criteria={result.criteria} />
        </div>
      ) : null}
    </div>
  );
}
