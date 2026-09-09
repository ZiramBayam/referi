import { loadDeliverable } from "../../lib/data.js";
import PanelForm from "./PanelForm.jsx";
import MemoryControl from "./MemoryControl.jsx";
import { demoModeEnabled } from "../../lib/demoMode.js";

// Alamat server hapus memori milik `agent/` (proses terpisah, port 8010 — BUKAN port
// gerbang 402). Dibaca di server pada setiap permintaan bersama gerbang DEMO_MODE,
// jadi ia bisa diubah tanpa build ulang; nilainya hanya DITAMPILKAN di panel, sedangkan
// yang benar-benar memanggilnya adalah rute `app/api/demo/memory/reset`.
const RESET_API = process.env.NEXT_PUBLIC_AGENT_RESET_API || "http://127.0.0.1:8010";

// WAJIB: tanpa ini Next memprarender /panel saat BUILD, sehingga DEMO_MODE yang berlaku
// adalah nilai saat build — bukan saat `next start`. Gerbang DEMO_MODE harus dibaca pada
// setiap permintaan, kalau tidak ia hanya gerbang semu.
export const dynamic = "force-dynamic";

export default async function PanelPage() {
  // DEMO_MODE dibaca DI SERVER, per permintaan (bukan di lingkup modul: di sana nilainya
  // ikut beku pada `next build` meski ada `force-dynamic`). Tombol hapus memori tidak
  // pernah dikirim ke browser bila gerbangnya mati — komponennya tidak dirender sama
  // sekali, jadi tidak ada penanda apa pun di HTML yang bisa dibalik dari sisi klien.
  const demoMode = demoModeEnabled();

  const samples = [];
  for (const jobId of ["418", "421", "422"]) {
    const d = await loadDeliverable(jobId);
    if (d) samples.push({ jobId, text: d.text, sha: d.sha_keccak });
  }

  return (
    <div>
      <h1>Judge panel — try it yourself</h1>
      <p className="lead">
        Paste any deliverable text (or load one of the samples), pick a depth, then run the
        checks. Here YOU choose the depth; on the real path that depth is derived from the
        provider&apos;s memory — that is what made job 421 (<code>sampling</code>) and job 422
        (<code>full</code>) end differently even though their text is identical.
      </p>

      <div className="card warn">
        <strong>Limits you must read first.</strong> The panel runs the deterministic{" "}
        <code>format</code> and <code>links</code> checks only, inside this local Next.js
        process — a port of <code>agent/agent/checks/</code>. It does NOT run the provider cap
        gate, does NOT read Sibyl memory, does NOT call the 402 gate, and does NOT send any
        transaction. The binding verdict is still the one announced on-chain by{" "}
        <code>EvaluatorVault</code>.
      </div>

      <p className="lead">
        The check results below are produced by the same code that wrote the on-chain bundles,
        so their <code>reason</code> and <code>proof</code> strings come out in Indonesian —
        untranslated on purpose, because the parity test compares them character for character
        against the bundles that were hashed into <code>reasonHash</code>.
      </p>

      <PanelForm samples={samples} />

      <MemoryControl enabled={demoMode} resetApi={RESET_API} />
    </div>
  );
}
