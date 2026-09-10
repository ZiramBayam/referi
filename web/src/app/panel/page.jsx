import { loadDeliverable } from "../../lib/data.js";
import PanelForm from "./PanelForm.jsx";
import MemoryControl from "./MemoryControl.jsx";
import { demoModeEnabled } from "../../lib/demoMode.js";
import { Notice, Page, PageHeader } from "../../components/PageShell.jsx";

// Alamat server hapus memori milik `agent/` (proses terpisah, port 8010, BUKAN port
// gerbang 402). Dibaca di server pada setiap permintaan bersama gerbang DEMO_MODE,
// jadi ia bisa diubah tanpa build ulang; nilainya hanya DITAMPILKAN di panel, sedangkan
// yang benar-benar memanggilnya adalah rute `app/api/demo/memory/reset`.
const RESET_API = process.env.NEXT_PUBLIC_AGENT_RESET_API || "http://127.0.0.1:8010";

export const metadata = {
  title: "Judge panel · Referi",
  description:
    "Run the deterministic format and links checks over any deliverable text, locally, and read the evidence the agent would have written.",
};

// WAJIB: tanpa ini Next memprarender /panel saat BUILD, sehingga DEMO_MODE yang berlaku
// adalah nilai saat build, bukan saat `next start`. Gerbang DEMO_MODE harus dibaca pada
// setiap permintaan, kalau tidak ia hanya gerbang semu.
export const dynamic = "force-dynamic";

export default async function PanelPage() {
  // DEMO_MODE dibaca DI SERVER, per permintaan (bukan di lingkup modul: di sana nilainya
  // ikut beku pada `next build` meski ada `force-dynamic`). Tombol hapus memori tidak
  // pernah dikirim ke browser bila gerbangnya mati, komponennya tidak dirender sama
  // sekali, jadi tidak ada penanda apa pun di HTML yang bisa dibalik dari sisi klien.
  const demoMode = demoModeEnabled();

  const samples = [];
  for (const jobId of ["418", "421", "422"]) {
    const d = await loadDeliverable(jobId);
    if (d) samples.push({ jobId, text: d.text, sha: d.sha_keccak });
  }

  return (
    <Page>
      <PageHeader
        title="Judge panel"
        lede={
          <p>
            Paste any deliverable text, pick a depth, and run the checks. Depth decides how much of
            the document is read: <span className="font-mono text-xs">sampling</span> reads the
            first two sections, <span className="font-mono text-xs">full</span> reads all of them.
          </p>
        }
      />

      <Notice className="mt-8">
        On the real path you do not choose the depth. It is derived from the provider&apos;s memory,
        and that is why jobs 421 and 422 ended differently even though their text is identical.
      </Notice>

      <Notice className="mt-3" tone="warn" title="What this panel does not do.">
        It runs two deterministic checks (<span className="font-mono text-xs text-ink">format</span>{" "}
        and <span className="font-mono text-xs text-ink">links</span>) inside this local process. It
        does not read Sibyl memory, does not apply the provider cap gate, and sends no transaction.
        The binding verdict is still the one announced on chain.
      </Notice>

      <Notice className="mt-3">
        Results come out in Indonesian on purpose. They are produced by the same code that wrote the
        on-chain evidence bundles, and a parity test compares them character for character, so
        translating them would break the match.
      </Notice>

      <div className="mt-8">
        <PanelForm samples={samples} />
      </div>

      <MemoryControl enabled={demoMode} resetApi={RESET_API} />
    </Page>
  );
}
