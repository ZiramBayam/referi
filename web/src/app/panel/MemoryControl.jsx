"use client";

import { useState } from "react";

/**
 * Kontrol demo "hapus memori". Hanya dirender bila `DEMO_MODE=1` dibaca di server
 * (lihat `panel/page.jsx`); dengan DEMO_MODE mati, tidak ada satu pun byte dari komponen
 * ini yang sampai ke HTML.
 *
 * KEJUJURAN: `web/` TIDAK menghapus apa pun. Basis data memori ada di `agent/`, di luar
 * batas folder halaman ini, dan penghapusannya adalah tindakan pada mesin — bukan sesuatu
 * yang boleh dipicu diam-diam oleh sebuah halaman. Yang diberikan tombol ini adalah
 * PROSEDUR persisnya beserta hasil yang harus Anda lihat, supaya bisa dijalankan dan
 * dicek sendiri.
 *
 * @param {{ enabled: boolean }} props
 */
export default function MemoryControl({ enabled }) {
  const [shown, setShown] = useState(false);
  if (!enabled) return null;

  return (
    <div>
      <h2>Kontrol demo — hapus memori</h2>
      <div className="card warn">
        <p style={{ marginTop: 0 }}>
          Pertanyaan yang dijawab: <strong>hapus memori → apa yang berubah?</strong> Mode
          memori yang tercatat di kelima bundel job 418–422 adalah <code>normal</code>. Bila
          berkas memori hilang sementara root on-chain sudah non-nol, agen masuk{" "}
          <strong>mode aman</strong>: nol <code>postVerdict</code>, nol{" "}
          <code>finalize</code>, job menggantung sampai <code>expiredAt</code>.
        </p>
        <button className="danger" onClick={() => setShown(!shown)}>
          {shown ? "Sembunyikan prosedur hapus memori" : "Hapus memori (tampilkan prosedur)"}
        </button>
        {shown ? (
          <div>
            <p>
              Halaman ini sengaja <strong>tidak</strong> menghapus berkas apa pun: basis data
              memori milik <code>agent/</code>, dan penghapusannya harus terlihat di terminal
              Anda, bukan tersembunyi di balik sebuah tombol. Jalankan tiga perintah ini —
              ketiga berkas WAJIB disapu, menyisakan <code>-wal</code>/<code>-shm</code>{" "}
              membuat SQLite memulihkan sebagian isi:
            </p>
            <pre className="proof">
              {"rm agent/data/chain-abc/memory.db\n" +
                "rm -f agent/data/chain-abc/memory.db-wal\n" +
                "rm -f agent/data/chain-abc/memory.db-shm"}
            </pre>
            <p>
              Yang harus Anda lihat sesudahnya, pada vault Base Sepolia yang root-nya sudah
              non-nol: agen berhenti di gerbang dengan <strong>mode aman</strong>, nonce wallet
              agen TIDAK berubah, dan tidak ada transaksi baru. Pulihkan dengan mengembalikan{" "}
              <code>memory.db</code> dari cadangan.
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
