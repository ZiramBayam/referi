"use client";

import { useState } from "react";

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
      <h2>Kontrol demo — hapus memori</h2>

      <div className="card warn">
        <p style={{ marginTop: 0 }}>
          <strong>Baca dulu batasnya.</strong> Tombol di bawah menghapus{" "}
          <strong>memori DEMO</strong>: <code>agent/data/demo/memory.db</code> beserta{" "}
          <code>-wal</code> dan <code>-shm</code>-nya (menyisakan WAL membuat SQLite bisa
          memulihkan sebagian isi, jadi ketiganya wajib disapu bersama).
        </p>
        <p>
          Ia <strong>TIDAK</strong> menghapus <code>agent/data/chain-abc/memory.db</code>,
          yaitu memori yang menghasilkan verdict job 418-422 yang Anda lihat di halaman
          Timeline dan halaman verdict. Itu <strong>sengaja</strong>: berkas{" "}
          <code>chain-abc</code> adalah satu-satunya artefak yang bisa merekonstruksi ulang
          root memori yang sudah tercatat on-chain. Sebuah tombol di browser tidak diberi
          kuasa menghapus satu-satunya bukti yang menyambungkan angka on-chain dengan isi
          memorinya. Jadi: menekan tombol ini <em>tidak</em> mengubah apa pun yang tampil di{" "}
          <code>/</code> maupun <code>/verdict/[jobId]</code>.
        </p>
      </div>

      <div className="card">
        <div className="row" style={{ marginTop: 0 }}>
          <button className="danger" onClick={run} disabled={busy}>
            {busy ? "menghapus…" : "Hapus memori demo sekarang"}
          </button>
          <span className="lead" style={{ margin: 0 }}>
            POST <code>/api/demo/memory/reset</code> → <code className="mono">{resetApi}</code>
            <code>/demo/memory/reset</code>
          </span>
        </div>
        <p className="lead" style={{ marginBottom: 0 }}>
          Endpoint penghapusnya dijalankan terpisah dan hanya hidup saat{" "}
          <code>DEMO_MODE</code> menyala; halaman ini hanya meneruskan permintaan
          (browser tidak bisa memanggilnya langsung — server itu tidak mengirim header
          CORS dan menjawab preflight <code>OPTIONS</code> dengan 501).
        </p>
      </div>

      {result ? <ResetResult data={result} /> : null}
      {failure ? <ResetFailure failure={failure} command={serveCommand} /> : null}

      <div className="card note">
        <p style={{ marginTop: 0 }}>
          <strong>Kalau yang ingin Anda uji adalah mode aman</strong> — agen menolak
          memutus ketika memori yang menopang root on-chain hilang — sasarannya adalah
          berkas <code>chain-abc</code>, dan itu memang harus Anda lakukan sendiri di
          terminal, terlihat, bukan lewat tombol:
        </p>
        <pre className="proof">
          {"rm agent/data/chain-abc/memory.db\n" +
            "rm -f agent/data/chain-abc/memory.db-wal\n" +
            "rm -f agent/data/chain-abc/memory.db-shm"}
        </pre>
        <p style={{ marginBottom: 0 }}>
          Yang harus terlihat sesudahnya, pada vault yang root-nya sudah non-nol: agen
          berhenti di gerbang dengan <strong>mode aman</strong> — nol{" "}
          <code>postVerdict</code>, nol <code>finalize</code>, nonce wallet agen tidak
          berubah, job menggantung sampai <code>expiredAt</code>. Pulihkan dengan
          mengembalikan <code>memory.db</code> dari cadangan.
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
      <h3 style={{ marginTop: 0 }}>Hasil penghapusan</h3>
      <p style={{ marginTop: 0 }}>
        {deleted.length === 0 && refused.length === 0 ? (
          <strong>
            Tidak ada yang terhapus — memori demo memang sudah kosong.
          </strong>
        ) : deleted.length === 0 ? (
          <strong>Tidak ada yang terhapus panggilan ini.</strong>
        ) : (
          <strong>
            {deleted.length} berkas terhapus panggilan ini.
          </strong>
        )}{" "}
        Daftar di bawah adalah isi respons agen, tanpa tafsiran.
      </p>
      <dl className="kv">
        <dt>direktori (root)</dt>
        <dd className="mono">{data.root ? data.root : <span className="none">belum ada</span>}</dd>
        <dt>basis data (db)</dt>
        <dd className="mono">{data.db ? data.db : <span className="none">belum ada</span>}</dd>
        <dt>deleted</dt>
        <dd className="mono">
          {deleted.length ? (
            deleted.join(", ")
          ) : (
            <span className="none">kosong — tidak ada berkas yang terhapus</span>
          )}
        </dd>
        <dt>missing</dt>
        <dd className="mono">
          {missing.length ? (
            missing.join(", ")
          ) : (
            <span className="none">kosong</span>
          )}
        </dd>
        <dt>refused</dt>
        <dd className="mono">
          {refused.length ? refused.join(", ") : <span className="none">kosong</span>}
        </dd>
      </dl>
      {refused.length ? (
        <p className="lead" style={{ marginBottom: 0 }}>
          <strong>refused tidak kosong.</strong> Berkas itu ADA tetapi berupa symlink atau
          direktori, jadi agen menolak menghapusnya — isinya masih utuh. Jangan anggap
          memori demo bersih.
        </p>
      ) : (
        <p className="lead" style={{ marginBottom: 0 }}>
          Memori <code>chain-abc</code> tidak disentuh panggilan ini, dan halaman verdict
          tidak berubah.
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
      <h3 style={{ marginTop: 0 }}>Gagal — tidak ada yang terhapus</h3>
      <dl className="kv">
        <dt>status HTTP</dt>
        <dd className="mono">{failure.status === 0 ? "tidak ada respons" : failure.status}</dd>
        <dt>reason</dt>
        <dd className="mono">{reason}</dd>
      </dl>
      {unreachable ? (
        <div>
          <p>
            Server penghapus memori tidak berjalan (atau tidak di port itu). Jalankan ini
            di terminal, lalu tekan tombolnya lagi:
          </p>
          <pre className="proof">{command}</pre>
          <p style={{ marginBottom: 0 }}>
            Tanpa <code>DEMO_MODE=1</code> proses itu keluar dengan kode 1 dan tidak
            mengikat port sama sekali — itu perilaku yang diinginkan, bukan galat.
          </p>
        </div>
      ) : reason === "not_found" ? (
        <p style={{ marginBottom: 0 }}>
          Rutenya tidak terdaftar. Terjadi bila <code>DEMO_MODE</code> mati di proses yang
          menjawab — di halaman ini, atau di server penghapus memori.
        </p>
      ) : (
        <p style={{ marginBottom: 0 }}>
          Kode alasan di atas datang dari endpoint penghapus memori apa adanya. Tidak ada
          berkas yang disentuh.
        </p>
      )}
    </div>
  );
}
