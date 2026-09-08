import { loadDeliverable } from "../../lib/data.js";
import PanelForm from "./PanelForm.jsx";
import MemoryControl from "./MemoryControl.jsx";

// DEMO_MODE dibaca DI SERVER. Tombol hapus memori tidak pernah dikirim ke browser bila
// nilainya bukan "1": komponennya tidak dirender sama sekali, jadi tidak ada penanda apa
// pun di HTML yang bisa dibalik dari sisi klien.
const DEMO_MODE = process.env.DEMO_MODE === "1";

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
  const samples = [];
  for (const jobId of ["418", "421", "422"]) {
    const d = await loadDeliverable(jobId);
    if (d) samples.push({ jobId, text: d.text, sha: d.sha_keccak });
  }

  return (
    <div>
      <h2>Panel juri — coba sendiri</h2>
      <p className="lead">
        Tempel teks deliverable apa pun (atau muat salah satu contoh), pilih kedalaman, lalu
        jalankan cek. Kedalamannya di sini Anda pilih SENDIRI; di jalur sungguhan kedalaman itu
        yang diturunkan dari memori provider — itulah yang membuat job 421 (
        <code>sampling</code>) dan job 422 (<code>full</code>) berakhir berbeda meski teksnya
        identik.
      </p>

      <div className="card warn">
        <strong>Batas yang wajib dibaca.</strong> Panel menjalankan cek deterministik{" "}
        <code>format</code> dan <code>links</code> saja, di proses Next.js lokal ini —
        port dari <code>agent/agent/checks/</code>. Ia TIDAK menjalankan gerbang cap
        provider, TIDAK membaca memori Sibyl, TIDAK memanggil gerbang 402, dan TIDAK
        mengirim transaksi. Verdict yang mengikat tetap yang diumumkan on-chain oleh{" "}
        <code>EvaluatorVault</code>.
      </div>

      <PanelForm samples={samples} />

      <MemoryControl enabled={DEMO_MODE} resetApi={RESET_API} />
    </div>
  );
}
