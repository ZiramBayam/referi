"use client";

import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { buttonClasses } from "../../components/ui/Button.jsx";
import { KeyValue, KeyValues, Notice, NotAvailable } from "../../components/PageShell.jsx";

/**
 * Kontrol demo "hapus memori". Hanya dirender bila `DEMO_MODE=1` dibaca di server
 * (lihat `panel/page.jsx`); dengan DEMO_MODE mati, tidak ada satu pun byte dari komponen
 * ini yang sampai ke HTML, dan rute proksinya menjawab 404.
 *
 * BATAS YANG TIDAK BOLEH DIPERHALUS: tombol ini menghapus memori DEMO
 * (`agent/data/demo/memory.db`). Ia TIDAK menyentuh `agent/data/chain-abc/memory.db`,
 * memori yang menghasilkan verdict 418-422 yang dipajang di `/timeline` dan
 * `/verdict/[jobId]`. Batas itu disengaja dan dinyatakan di layar, supaya tidak ada juri
 * yang mengira ia baru saja menghapus memori di balik verdict yang sedang ia lihat.
 *
 * @param {{ enabled: boolean, resetApi: string }} props
 */
export default function MemoryControl({ enabled, resetApi }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(/** @type {any} */ (null));
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
    <section className="mt-16 border-t border-border pt-12">
      <h2 className="font-display text-2xl font-semibold text-ink">Demo control: wipe memory</h2>

      <Notice className="mt-5" tone="warn" title="Read the limits first.">
        <p>
          The button below deletes the <span className="font-medium text-ink">demo memory</span>:{" "}
          <span className="font-mono text-xs text-ink">agent/data/demo/memory.db</span> together
          with its <span className="font-mono text-xs">-wal</span> and{" "}
          <span className="font-mono text-xs">-shm</span> files (leaving the WAL behind would let
          SQLite recover part of the contents, so all three must go together).
        </p>
        <p className="mt-3">
          It does <span className="font-medium text-ink">not</span> delete{" "}
          <span className="font-mono text-xs text-ink">agent/data/chain-abc/memory.db</span>, the
          memory that produced the job 418–422 verdicts you see on the on-chain record and verdict
          pages. That is deliberate: the <span className="font-mono text-xs">chain-abc</span> file
          is the only artifact that can reconstruct the memory roots already recorded on chain. A
          button in a browser is not given the power to erase the only evidence tying the on-chain
          numbers to the memory behind them. So: pressing this button changes{" "}
          <em>nothing</em> shown on <span className="font-mono text-xs">/timeline</span> or{" "}
          <span className="font-mono text-xs">/verdict/[jobId]</span>.
        </p>
      </Notice>

      <div className="mt-4 rounded-2xl border border-border bg-surface p-5">
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className={buttonClasses(
              "secondary",
              "md",
              "border-proof-block/45 bg-proof-block/10 text-proof-block hover:border-proof-block hover:bg-proof-block/15"
            )}
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" strokeWidth={2.25} aria-hidden />
            ) : (
              <Trash2 className="size-4" strokeWidth={2} aria-hidden />
            )}
            {busy ? "deleting" : "Wipe demo memory now"}
          </button>
          <span className="text-sm text-muted">
            POST <span className="font-mono text-xs text-ink">/api/demo/memory/reset</span> →{" "}
            <span className="font-mono text-xs text-ink">{resetApi}/demo/memory/reset</span>
          </span>
        </div>
        <p className="mt-4 max-w-3xl text-[13px] leading-relaxed text-muted">
          The delete endpoint runs as a separate process and is only alive while{" "}
          <span className="font-mono text-xs">DEMO_MODE</span> is on; this page merely forwards the
          request. What keeps other callers out is not CORS (deleting is a side effect, and the
          side effect happens even when the response cannot be read) but three things: the delete
          server refuses non-loopback peers, this page&apos;s server is bound to{" "}
          <span className="font-mono text-xs">127.0.0.1</span>, and the proxy route rejects
          requests that are not same-origin.
        </p>
      </div>

      {/* Aksi merusak: hasilnya wajib terdengar, bukan hanya terlihat. */}
      <div aria-live="polite">
        {result ? <ResetResult data={result} /> : null}
        {failure ? <ResetFailure failure={failure} command={serveCommand} /> : null}
      </div>

      <div className="mt-4 rounded-2xl border border-border bg-surface p-5">
        <p className="max-w-3xl text-sm leading-relaxed text-muted">
          <span className="font-medium text-ink">If what you want to test is safe mode</span>, the
          agent refusing to decide once the memory backing the on-chain root is gone, the target
          is the <span className="font-mono text-xs text-ink">chain-abc</span> file, and that is
          something you must do yourself in a terminal, in the open, not through a button:
        </p>
        <pre className="mt-3 overflow-x-auto rounded-xl border border-border bg-bg px-4 py-3.5 font-mono text-xs leading-relaxed text-ink">
          {"rm agent/data/chain-abc/memory.db\n" +
            "rm -f agent/data/chain-abc/memory.db-wal\n" +
            "rm -f agent/data/chain-abc/memory.db-shm"}
        </pre>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
          What you should see afterwards, against a vault whose root is already non-zero: the agent
          stops at the gate in <span className="font-medium text-ink">safe mode</span>, zero{" "}
          <span className="font-mono text-xs">postVerdict</span>, zero{" "}
          <span className="font-mono text-xs">finalize</span>, the agent wallet nonce unchanged,
          the job hanging until <span className="font-mono text-xs">expiredAt</span>. Recover by
          restoring <span className="font-mono text-xs">memory.db</span> from a backup.
        </p>
      </div>
    </section>
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
    <div className="mt-4 overflow-hidden rounded-2xl border border-border bg-surface">
      <header className="border-b border-border px-5 py-3.5">
        <h3 className="text-sm font-medium text-ink">Deletion result</h3>
      </header>
      <div className="px-5 py-4">
        <p className="text-sm leading-relaxed text-muted">
          <span className="font-medium text-ink">
            {deleted.length === 0 && refused.length === 0
              ? "Nothing was deleted. The demo memory was already empty."
              : deleted.length === 0
                ? "Nothing was deleted by this call."
                : `${deleted.length} file(s) deleted by this call.`}
          </span>{" "}
          The list below is the agent&apos;s response, uninterpreted.
        </p>
        <div className="mt-3">
          <KeyValues>
            <KeyValue label="directory (root)">
              <span className="break-all font-mono text-xs">
                {data.root ? data.root : <NotAvailable />}
              </span>
            </KeyValue>
            <KeyValue label="database (db)">
              <span className="break-all font-mono text-xs">
                {data.db ? data.db : <NotAvailable />}
              </span>
            </KeyValue>
            <KeyValue label="deleted">
              <span className="break-all font-mono text-xs">
                {deleted.length ? (
                  deleted.join(", ")
                ) : (
                  <span className="text-faint">empty, no file was deleted</span>
                )}
              </span>
            </KeyValue>
            <KeyValue label="missing">
              <span className="break-all font-mono text-xs">
                {missing.length ? missing.join(", ") : <span className="text-faint">empty</span>}
              </span>
            </KeyValue>
            <KeyValue label="refused">
              <span className="break-all font-mono text-xs">
                {refused.length ? refused.join(", ") : <span className="text-faint">empty</span>}
              </span>
            </KeyValue>
          </KeyValues>
        </div>
        {refused.length ? (
          <p className="mt-4 text-sm leading-relaxed text-muted">
            <span className="font-medium text-proof-review">refused is not empty.</span> Those
            files exist but are symlinks or directories, so the agent refused to delete them,
            their contents are intact. Do not treat the demo memory as clean.
          </p>
        ) : (
          <p className="mt-4 text-sm leading-relaxed text-muted">
            The <span className="font-mono text-xs">chain-abc</span> memory was not touched by this
            call, and the verdict pages did not change.
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Kegagalan, dilaporkan dengan kode alasan asli, tanpa hijau palsu.
 * @param {{ failure: { status: number, body: any }, command: string }} props
 */
function ResetFailure({ failure, command }) {
  const reason = typeof failure.body?.reason === "string" ? failure.body.reason : "not available";
  const unreachable = reason === "reset_server_unreachable" || reason === "proxy_unreachable";

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-proof-block/35 bg-proof-block/[0.06]">
      <header className="border-b border-proof-block/25 px-5 py-3.5">
        <h3 className="text-sm font-medium text-ink">Failed. Nothing was deleted</h3>
      </header>
      <div className="px-5 py-4">
        <KeyValues>
          <KeyValue label="HTTP status">
            <span className="font-mono text-xs tnum">
              {failure.status === 0 ? "no response" : failure.status}
            </span>
          </KeyValue>
          <KeyValue label="reason">
            <span className="font-mono text-xs">{reason}</span>
          </KeyValue>
        </KeyValues>

        {unreachable ? (
          <div className="mt-4">
            <p className="text-sm leading-relaxed text-muted">
              The memory delete server is not running (or not on that port). Run this in a
              terminal, then press the button again:
            </p>
            <pre className="mt-3 overflow-x-auto rounded-xl border border-border bg-bg px-4 py-3.5 font-mono text-xs leading-relaxed text-ink">
              {command}
            </pre>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              Without <span className="font-mono text-xs">DEMO_MODE=1</span> that process exits
              with code 1 and binds no port at all, that is the intended behaviour, not an error.
            </p>
          </div>
        ) : reason === "cross_site_request" ||
          reason === "missing_fetch_metadata" ||
          reason === "missing_origin" ||
          reason === "bad_origin" ||
          reason === "origin_host_mismatch" ? (
          <p className="mt-4 text-sm leading-relaxed text-muted">
            The request was rejected by this page&apos;s proxy route, before it reached the memory
            delete server: only the panel on the same origin may trigger it. If you see this while
            pressing the button on this very page, the panel was most likely opened on a different
            host/port than the one Next is serving.
          </p>
        ) : reason === "not_found" ? (
          <p className="mt-4 text-sm leading-relaxed text-muted">
            The route is not registered. This happens when{" "}
            <span className="font-mono text-xs">DEMO_MODE</span> is off in the process that
            answered, either this page, or the memory delete server.
          </p>
        ) : (
          <p className="mt-4 text-sm leading-relaxed text-muted">
            The reason code above comes from the memory delete endpoint verbatim. No file was
            touched.
          </p>
        )}
      </div>
    </div>
  );
}
