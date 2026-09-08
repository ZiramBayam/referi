// Tes PARITAS: `src/lib/checks.js` (port JavaScript) vs bundel bukti yang SUDAH mendarat
// di chain (`public/verdicts/<jobId>.json`).
//
// KENAPA ADA: README dan post build-in-public mengklaim port ini menghasilkan array
// `checks` yang IDENTIK dengan bundel agen — termasuk string `detail` dan `proof`, bukan
// hanya `failed_checks`. Tanpa tes ini klaim itu hanya "pernah diperiksa sekali dengan
// tangan"; sekali `checks.js` disentuh, paritasnya bisa patah diam-diam dan klaim di
// README berubah jadi klaim palsu.
//
// Yang dibandingkan BUKAN keluaran port dengan keluaran port. Sisi "harapan" seluruhnya
// dibaca dari artefak: teks dari `public/deliverables/<jobId>.json` (salinan apa adanya
// `demo/deliverables/`), harapan dari `public/verdicts/<jobId>.json` (salinan apa adanya
// bundel yang hash-nya diumumkan `EvaluatorVault`). Tidak ada satu pun string harapan
// yang diketik ulang di berkas ini.
//
// Runner: `node:test` bawaan Node (docs/versions.md memin Node 24) — nol dependensi baru.
// Jalankan: `pnpm --filter web test`  atau  `node --test web/test/`

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { evaluateText, DEPTH_SAMPLING, DEPTH_FULL } from "../src/lib/checks.js";

/** @param {string} rel */
function readJson(rel) {
  return JSON.parse(readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8"));
}

// Kedalaman ditulis di sini, TIDAK diambil dari bundel: bundelnya justru ikut diperiksa
// terhadap daftar ini, supaya bundel yang tertukar (mis. 421 sampling ditimpa salinan
// full) jatuh sebagai galat, bukan lolos karena tes memakai nilainya sendiri.
const JOBS = [
  { jobId: "418", depth: DEPTH_SAMPLING },
  { jobId: "419", depth: DEPTH_FULL },
  { jobId: "421", depth: DEPTH_SAMPLING },
  { jobId: "422", depth: DEPTH_FULL },
];

// Bundel menulis setiap int sebagai `{"$u":"-1"}` (encoding kanonik v3/v4). Keluaran port
// memakai angka JS biasa, jadi sisi PORT yang dinaikkan ke bentuk kanonik — bukan bundel
// yang diturunkan — supaya perbedaan bentuk tidak bisa menyembunyikan perbedaan nilai.
/** @param {number} n */
const u = (n) => ({ $u: String(n) });

test("keempat bundel bukti punya blok evaluation yang bisa dipakai", () => {
  for (const { jobId } of JOBS) {
    const bundle = readJson(`../public/verdicts/${jobId}.json`);
    assert.ok(bundle.evaluation, `bundel ${jobId} tanpa blok evaluation`);
    assert.ok(Array.isArray(bundle.evaluation.checks), `bundel ${jobId} tanpa array checks`);
    assert.equal(bundle.evaluation.checks.length, 3, `bundel ${jobId}: jumlah cek berubah`);
  }
});

for (const { jobId, depth } of JOBS) {
  test(`job ${jobId} (depth=${depth}): port checks.js == bundel bukti on-chain`, () => {
    const bundle = readJson(`../public/verdicts/${jobId}.json`);
    const deliverable = readJson(`../public/deliverables/${jobId}.json`);
    const expected = bundle.evaluation;

    // Ikatan teks <-> bundel. Kalau berkas deliverable ditukar, hash yang ia bawa tidak
    // lagi sama dengan hash yang dicatat bundel, dan tes berhenti di sini — bukan
    // diam-diam membandingkan teks lain dengan bundel ini.
    assert.equal(deliverable.jobId, jobId, `deliverable ${jobId}: jobId tidak cocok`);
    assert.equal(
      deliverable.sha_keccak,
      expected.deliverable,
      `job ${jobId}: teks deliverable bukan teks yang dinilai bundel ini`,
    );
    assert.equal(expected.depth, depth, `job ${jobId}: depth bundel bukan ${depth}`);

    const actual = evaluateText(deliverable.text, depth);

    // Inti klaim: SELURUH array `checks`, field demi field, termasuk `detail` & `proof`.
    assert.equal(actual.checks.length, expected.checks.length, `job ${jobId}: jumlah cek`);
    actual.checks.forEach((got, i) => {
      const want = expected.checks[i];
      assert.deepEqual(
        {
          check: got.check,
          criterion: got.criterion,
          depth: got.depth,
          detail: got.detail,
          pattern: got.pattern,
          proof: got.proof,
          section: u(got.section),
          status: got.status,
        },
        want,
        `job ${jobId}: cek ke-${i} (${want.criterion}) berbeda dari bundel`,
      );
    });

    assert.deepEqual(actual.failed_checks, expected.failed_checks, `job ${jobId}: failed_checks`);
    assert.deepEqual(actual.unverified, expected.unverified, `job ${jobId}: unverified`);
    assert.equal(actual.category, expected.category, `job ${jobId}: category`);
    assert.equal(actual.depth, expected.depth, `job ${jobId}: depth`);
    assert.deepEqual(actual.verdict, Number(expected.verdict.$u), `job ${jobId}: verdict`);

    // Katalog kriteria deterministik juga bagian dari yang ditampilkan panel juri. Kriteria
    // kualitatif bundel (`qualitative.0`) memang TIDAK diport — rubric LLM dipotong.
    const wantCriteria = expected.criteria.filter(
      (/** @type {{ kind: string }} */ c) => c.kind === "deterministic",
    );
    assert.deepEqual(
      actual.criteria.map((c) => ({ check: c.check, id: c.id, kind: c.kind, text: c.text })),
      wantCriteria,
      `job ${jobId}: katalog kriteria deterministik berbeda dari bundel`,
    );
  });
}
