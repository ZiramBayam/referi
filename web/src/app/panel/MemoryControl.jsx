"use client";

import { useState } from "react";
import Icon from "../../components/Icon.jsx";

/**
 * Kontrol demo "hapus memori". Hanya dirender bila `DEMO_MODE=1` dibaca di server
 * (lihat `panel/page.jsx`); dengan DEMO_MODE mati, tidak ada satu pun byte dari komponen
 * ini yang sampai ke HTML, dan rute proksinya menjawab 404.
 *
 * BATAS YANG TIDAK BOLEH DIPERHALUS: tombol ini menghapus memori DEMO
 * (`agent/data/demo/memory.db`). Ia TIDAK menyentuh `agent/data/chain-abc/memory.db` —
 * memori yang menghasilkan verdict 418-422 yang dipajang di `/` dan `/verdict/[jobId]`.
 * Batas itu disengaja dan dinyatakan di layar, supaya tidak ada juri yang mengira ia baru
 * saja menghapus memori di balik verdict yang sedang ia lihat.
 *
 * @param {{ enabled: boolean, resetApi: string }} props
 */
export default function MemoryControl({ enabled, resetApi }) {
  const [busy, setBusy] = useState(false);
  /** @type {[any, (v: any) => void]} */
  const [result, setResult] = useState(/** @type {any} */ (null));
  /** @type {[any, (v: any) => void]} */
  const [failure, setFailure] = useState(/** @type {any} */ (null));

  if (!enabled) return null;

  const serveCommand =
    "cd agent && DEMO_MODE=1 uv run python -m agent.demo_reset --host 127.0.0.1 --port 8010";

  async function run() {
    setBusy(true);
    setResult(null);
    setFailure(null);
    try {
      const res = await fetch("/api/demo/memory/reset", { method: "POST" });
      const data = await res.json();
      if (res.ok && data?.ok === true) setResult(data);
      else setFailure({ status: res.status, body: data });
    } catch (e) {
      // Rute proksi kami sendiri tidak terjangkau (server Next mati / dev-server restart).
      setFailure({ status: 0, body: { reason: "proxy_unreachable", detail: String(e) } });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2>Demo control — wipe memory</h2>

      <div className="card warn">
        <p style={{ marginTop: 0 }}>
          <Icon name="triangle-alert" size={15} />{" "}
          <strong>Read the limits first.</strong> The button below deletes the{" "}
          <strong>DEMO memory</strong>: <code>agent/data/demo/memory.db</code> together with its{" "}
          <code>-wal</code> and <code>-shm</code> files (leaving the WAL behind would let SQLite
          recover part of the contents, so all three must go together).
        </p>
        <p>
          It does <strong>NOT</strong> delete <code>agent/data/chain-abc/memory.db</code>, the
          memory that produced the job 418-422 verdicts you see on the timeline and verdict
          pages. That is <strong>deliberate</strong>: the <code>chain-abc</code> file is the only
          artifact that can reconstruct the memory roots already recorded on chain. A button in a
          browser is not given the power to erase the only evidence tying the on-chain numbers to
          the memory behind them. So: pressing this button changes <em>nothing</em> shown on{" "}
          <code>/</code> or <code>/verdict/[jobId]</code>.
        </p>
      </div>

      <div className="card">
        <div className="row" style={{ marginTop: 0 }}>
          <button className="danger" onClick={run} disabled={busy}>
            <Icon name="trash" size={14} />
            {busy ? "deleting…" : "Wipe demo memory now"}
          </button>
          <span className="lead" style={{ margin: 0 }}>
            POST <code>/api/demo/memory/reset</code> → <code className="mono">{resetApi}</code>
            <code>/demo/memory/reset</code>
          </span>
        </div>
        <p className="lead" style={{ marginBottom: 0 }}>
          The delete endpoint runs as a separate process and is only alive while{" "}
          <code>DEMO_MODE</code> is on; this page merely forwards the request. What keeps other
          callers out is not CORS (deleting is a side effect, and the side effect happens even
          when the response cannot be read) but three things: the delete server refuses
          non-loopback peers, this page&apos;s server is bound to <code>127.0.0.1</code>, and the
          proxy route rejects requests that are not same-origin.
        </p>
      </div>

      {/* Aksi merusak: hasilnya wajib terdengar, bukan hanya terlihat. */}
      <div aria-live="polite">
        {result ? <ResetResult data={result} /> : null}
        {failure ? <ResetFailure failure={failure} command={serveCommand} /> : null}
      </div>

      <div className="card note">
        <p style={{ marginTop: 0 }}>
          <strong>If what you want to test is safe mode</strong> — the agent refusing to decide
          once the memory backing the on-chain root is gone — the target is the{" "}
          <code>chain-abc</code> file, and that is something you must do yourself in a terminal,
          in the open, not through a button:
        </p>
        <pre className="proof">
          {"rm agent/data/chain-abc/memory.db\n" +
            "rm -f agent/data/chain-abc/memory.db-wal\n" +
            "rm -f agent/data/chain-abc/memory.db-shm"}
        </pre>
        <p style={{ marginBottom: 0 }}>
          What you should see afterwards, against a vault whose root is already non-zero: the
          agent stops at the gate in <strong>safe mode</strong> — zero <code>postVerdict</code>,
          zero <code>finalize</code>, the agent wallet nonce unchanged, the job hanging until{" "}
          <code>expiredAt</code>. Recover by restoring <code>memory.db</code> from a backup.
        </p>
      </div>
    </div>
  );
}

/**
 * Hasil sukses, ditampilkan APA ADANYA dari respons agen.
 * @param {{ data: { root?: string, db?: string, deleted?: string[], missing?: string[],
 *   refused?: string[] } }} props
 */
function ResetResult({ data }) {
  const deleted = data.deleted ?? [];
  const missing = data.missing ?? [];
  const refused = data.refused ?? [];

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Deletion result</h3>
      <p style={{ marginTop: 0 }}>
        {deleted.length === 0 && refused.length === 0 ? (
          <strong>Nothing was deleted — the demo memory was already empty.</strong>
        ) : deleted.length === 0 ? (
          <strong>Nothing was deleted by this call.</strong>
        ) : (
          <strong>{deleted.length} file(s) deleted by this call.</strong>
        )}{" "}
        The list below is the agent&apos;s response, uninterpreted.
      </p>
      <dl className="kv">
        <dt>directory (root)</dt>
        <dd className="mono">
          {data.root ? data.root : <span className="none">not available</span>}
        </dd>
        <dt>database (db)</dt>
        <dd className="mono">{data.db ? data.db : <span className="none">not available</span>}</dd>
        <dt>deleted</dt>
        <dd className="mono">
          {deleted.length ? (
            deleted.join(", ")
          ) : (
            <span className="none">empty — no file was deleted</span>
          )}
        </dd>
        <dt>missing</dt>
        <dd className="mono">
          {missing.length ? (
            missing.join(", ")
          ) : (
            <span className="none">empty</span>
          )}
        </dd>
        <dt>refused</dt>
        <dd className="mono">
          {refused.length ? refused.join(", ") : <span className="none">empty</span>}
        </dd>
      </dl>
      {refused.length ? (
        <p className="lead" style={{ marginBottom: 0 }}>
          <strong>refused is not empty.</strong> Those files EXIST but are symlinks or
          directories, so the agent refused to delete them — their contents are intact. Do not
          treat the demo memory as clean.
        </p>
      ) : (
        <p className="lead" style={{ marginBottom: 0 }}>
          The <code>chain-abc</code> memory was not touched by this call, and the verdict pages
          did not change.
        </p>
      )}
    </div>
  );
}

/**
 * Kegagalan — dilaporkan dengan kode alasan asli, tanpa hijau palsu.
 * @param {{ failure: { status: number, body: any }, command: string }} props
 */
function ResetFailure({ failure, command }) {
  const reason = typeof failure.body?.reason === "string" ? failure.body.reason : "—";
  const unreachable =
    reason === "reset_server_unreachable" || reason === "proxy_unreachable";

  return (
    <div className="card warn">
      <h3 style={{ marginTop: 0 }}>Failed — nothing was deleted</h3>
      <dl className="kv">
        <dt>HTTP status</dt>
        <dd className="mono">{failure.status === 0 ? "no response" : failure.status}</dd>
        <dt>reason</dt>
        <dd className="mono">{reason}</dd>
      </dl>
      {unreachable ? (
        <div>
          <p>
            The memory delete server is not running (or not on that port). Run this in a
            terminal, then press the button again:
          </p>
          <pre className="proof">{command}</pre>
          <p style={{ marginBottom: 0 }}>
            Without <code>DEMO_MODE=1</code> that process exits with code 1 and binds no port
            at all — that is the intended behaviour, not an error.
          </p>
        </div>
      ) : reason === "cross_site_request" ||
        reason === "missing_fetch_metadata" ||
        reason === "missing_origin" ||
        reason === "bad_origin" ||
        reason === "origin_host_mismatch" ? (
        <p style={{ marginBottom: 0 }}>
          The request was rejected by this page&apos;s proxy route, before it reached the
          memory delete server: only the panel on the same origin may trigger it. If you see this
          while pressing the button on this very page, the panel was most likely opened on a
          different host/port than the one Next is serving.
        </p>
      ) : reason === "not_found" ? (
        <p style={{ marginBottom: 0 }}>
          The route is not registered. This happens when <code>DEMO_MODE</code> is off in the
          process that answered — either this page, or the memory delete server.
        </p>
      ) : (
        <p style={{ marginBottom: 0 }}>
          The reason code above comes from the memory delete endpoint verbatim. No file was
          touched.
        </p>
      )}
    </div>
  );
}
