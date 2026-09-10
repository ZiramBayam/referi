/**
 * Terjemahan TAMPILAN untuk string yang tidak boleh diubah.
 *
 * KENAPA MODUL INI ADA, dan kenapa ia bukan sekadar "belum sempat menerjemahkan":
 * setiap string di sini berada DI DALAM bundel bukti yang keccak-nya diumumkan
 * on chain sebagai `reasonHash` pada transaksi `VerdictPosted`, dan teks
 * deliverable-nya sendiri keccak-nya `0x246071b3…0a51`, angka yang menjadi inti
 * klaim "teks identik, verdict berlawanan". Menerjemahkan byte-nya mengubah
 * hash-nya, dan seluruh rantai bukti itu berhenti cocok dengan chain.
 *
 * Maka byte aslinya TETAP dirender apa adanya, dan terjemahan ini muncul di
 * SEBELAHNYA, ditandai sebagai terjemahan. Yang dibaca mesin tetap yang di-hash;
 * yang dibaca juri internasional adalah keduanya.
 *
 * Kunci dicocokkan PERSIS. Kalau sebuah string tidak ada di sini, tidak ada
 * terjemahan yang ditampilkan, lebih baik hilang daripada dikarang.
 */

/** @type {Record<string, string>} */
const GLOSS = {
  // --- teks kriteria (ada di dalam bundel) ---
  "deliverable memuat seluruh bagian wajib: ['summary']":
    "the deliverable contains every required section: ['summary']",
  "tidak ada penanda pekerjaan yang belum selesai (TODO/TBD/placeholder)":
    "no unfinished-work markers (TODO/TBD/placeholder)",
  "tautan memakai skema yang diizinkan, bukan alamat internal, dan bagian sumber [] benar-benar memuat tautan":
    "links use an allowed scheme, are not internal addresses, and the source sections [] do carry links",

  // --- alasan & detail cek ---
  "seluruh 1 bagian wajib hadir": "all 1 required section present",
  "tanpa penanda pekerjaan pada 2 bagian yang dibaca":
    "no unfinished-work markers across the 2 sections read",
  "penanda pekerjaan 'TODO' pada bagian 0 (summary)":
    "unfinished-work marker 'TODO' in section 0 (summary)",
  "penanda pekerjaan 'TODO' pada bagian 2 (catatan lanjutan)":
    "unfinished-work marker 'TODO' in section 2 (follow-up notes)",
  "1 tautan lolos struktur saja (tanpa probe)":
    "1 link passed on structure alone (never probed)",
  "tidak ada tautan pada 1 bagian yang dibaca (depth=sampling)":
    "no links in the 1 section read (depth=sampling)",
  "tidak ada tautan pada 1 bagian yang dibaca (depth=full)":
    "no links in the 1 section read (depth=full)",
  "budget 2000000 melebihi cap milestone provider ini (250000; riwayat: 2 insiden terkonfirmasi)":
    "budget 2000000 exceeds this provider's milestone cap (250000; history: 2 confirmed incidents)",

  // --- catatan job & kriteria yang tidak dinilai ---
  "the-evaluator smoke job: provider menyerahkan satu deliverable, EvaluatorVault yang menilai.":
    "the-evaluator smoke job: the provider submits one deliverable and EvaluatorVault judges it.",
  "kriteria kualitatif TIDAK DINILAI di 2.3-min: rubric LLM dipotong (PM 5 Sep). Ia dicatat apa adanya, tidak pernah dianggap lolos.":
    "qualitative criteria are NOT SCORED: the LLM rubric was cut. They are recorded as-is and never treated as passed.",
};

/**
 * Terjemahan seksi deliverable, dikunci pada judul seksinya APA ADANYA seperti
 * yang dikembalikan `parseDocument`, yaitu tanpa penanda `#`, karena regex
 * judulnya hanya menangkap teks sesudah penanda.
 * @type {Record<string, string>}
 */
const SECTION_GLOSS = {
  "Summary":
    "Routine inspection report for the-evaluator demo chain. This document has three sections: summary, how it works, and follow-up notes.",
  "Cara kerja":
    "How it works. Numbers are read straight from the ACP contract on Base Sepolia, not from a copy. Every claim is checked against its on-chain value before it is written into the report. Reference link follows.",
  "Catatan lanjutan":
    "Follow-up notes. This section summarises what to carry into the next round. TODO: complete the gas-cost comparison table across rounds.",
};

/**
 * @param {string | undefined | null} original
 * @returns {string | null} terjemahan, atau null bila tidak ada padanan persis
 */
export function gloss(original) {
  if (typeof original !== "string") return null;
  return GLOSS[original.trim()] ?? null;
}

/**
 * @param {string | undefined | null} heading
 * @returns {string | null}
 */
export function glossSection(heading) {
  if (typeof heading !== "string") return null;
  return SECTION_GLOSS[heading.trim()] ?? null;
}

/**
 * Terjemahan PENUH deliverable job 422, dipakai sebagai permukaan baca UTAMA.
 *
 * Ia boleh menggantikan posisi utama HANYA karena strukturnya setia: dijalankan
 * lewat `evaluateText`, teks ini menghasilkan hasil yang IDENTIK dengan aslinya,
 * 3 seksi, `sampling` -> COMPLETE (2/3, nol gagal), `full` -> REJECT (3/3, gagal
 * `format`). Kalau terjemahan ini disunting sampai hasilnya berbeda, peraga di
 * halaman depan berhenti memperagakan mekanisme yang sebenarnya.
 *
 * Yang di-hash tetap teks aslinya. Teks ini TIDAK pernah ikut dihitung hash-nya
 * dan tidak pernah menggantikan byte yang diumumkan on chain, aslinya tetap
 * ditampilkan di bawah, bersama keccak-nya.
 */
export const DELIVERABLE_EN = `# Summary
Routine inspection report for the-evaluator demo chain. This document has three sections: summary, how it works, and follow-up notes.

## How it works
- Numbers are read straight from the ACP contract on Base Sepolia, not from a copy.
- Every claim is checked against its on-chain value before it is written into the report.
- Reference https://sepolia.basescan.org/address/0x0b93793923CD5De81850aF8604a233f3f24d461e

## Follow-up notes
- This section summarises what to carry into the next round.
- TODO: complete the gas-cost comparison table across rounds.
`;
