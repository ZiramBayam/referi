// Pembaca artefak statis. SEMUA data halaman berasal dari berkas di `public/`, yang
// merupakan SALINAN APA ADANYA dari artefak yang sudah mendarat di repo:
//
//   public/verdicts/<jobId>.json      <- agent/data/chain-abc/verdicts/<jobId>-<keccak>.json
//   public/deliverables/<jobId>.json  <- demo/deliverables/<jobId>.json
//   public/deployment.json            <- deployments/84532.json
//   public/jobs.json                  <- indeks; field `source` menyebut asal tiap kolom
//
// Berkasnya diimpor sebagai modul JSON, bukan dibaca lewat `fs` saat permintaan masuk:
// dengan begitu tidak ada satu pun path yang dirakit dari masukan pihak, dan seluruh
// halaman bisa dipraproduksi saat build. Nol RPC, nol wallet, nol panggilan jaringan.

import index from "../../public/jobs.json" with { type: "json" };
import deployment from "../../public/deployment.json" with { type: "json" };

import verdict418 from "../../public/verdicts/418.json" with { type: "json" };
import verdict419 from "../../public/verdicts/419.json" with { type: "json" };
import verdict420 from "../../public/verdicts/420.json" with { type: "json" };
import verdict421 from "../../public/verdicts/421.json" with { type: "json" };
import verdict422 from "../../public/verdicts/422.json" with { type: "json" };

import deliverable418 from "../../public/deliverables/418.json" with { type: "json" };
import deliverable419 from "../../public/deliverables/419.json" with { type: "json" };
import deliverable421 from "../../public/deliverables/421.json" with { type: "json" };
import deliverable422 from "../../public/deliverables/422.json" with { type: "json" };

/** @type {Record<string, any>} */
const BUNDLES = {
  418: verdict418,
  419: verdict419,
  420: verdict420,
  421: verdict421,
  422: verdict422,
};

// Job 420 sengaja TIDAK ada di sini: ia ditolak di gerbang sebelum provider sempat
// `submit()`, jadi memang tidak pernah ada teks deliverable untuknya.
/** @type {Record<string, any>} */
const DELIVERABLES = {
  418: deliverable418,
  419: deliverable419,
  421: deliverable421,
  422: deliverable422,
};

export async function loadIndex() {
  return index;
}

export async function loadJobs() {
  return index.jobs;
}

/** @param {string} jobId */
export async function loadJob(jobId) {
  return index.jobs.find((j) => j.jobId === jobId) ?? null;
}

/**
 * Bundel bukti mentah. `null` bila jobId tidak dikenal, halaman WAJIB menampilkan
 * "belum ada", bukan mengarang isi.
 * @param {string} jobId
 */
export async function loadBundle(jobId) {
  return BUNDLES[jobId] ?? null;
}

/** @param {string} jobId */
export async function loadDeliverable(jobId) {
  return DELIVERABLES[jobId] ?? null;
}

export async function loadDeployment() {
  return deployment;
}
