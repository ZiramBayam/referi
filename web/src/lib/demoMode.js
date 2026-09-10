// Gerbang DEMO_MODE untuk sisi `web/`. SATU tempat, dipakai oleh SEMUA permukaan
// (halaman `/panel` dan rute proksi `api/demo/memory/reset`).
//
// KENAPA SATU BERKAS: sebelumnya kedua permukaan menuliskan sendiri
// `process.env.DEMO_MODE !== "1"`. Keduanya kebetulan sama, tapi keduanya juga sama-sama
// salah terhadap sisi agen, dan tidak ada yang memaksa mereka tetap sama. Dengan satu
// helper, "tombol dirender" dan "proksi menjawab" tidak bisa lagi berbeda pendapat.
//
// KENAPA BUKAN HANYA "1": helper `config_flag` di `agent/agent/vault_client.py` menerima
// `1|true|yes|demo` (TRUE_FLAGS di sana), dan `.env.example` proyek ini menganjurkan
// `DEMO_MODE=true`. Dengan aturan lama, juri yang mengikuti `.env.example` mendapat
// endpoint penghapus memori HIDUP di 8010 tetapi tombolnya TIDAK PERNAH dirender,
// §7 langkah 5 hilang diam-diam dan tampak seperti fitur rusak. Daftar di bawah sengaja
// disalin persis dari sisi agen dan TIDAK boleh diperlebar sendiri.
//
// KENAPA "hadir tapi kosong" = MATI: sama seperti `config_flag`. Operator yang mengetik
// `DEMO_MODE= pnpm start` bermaksud MEMATIKAN gerbangnya; string kosong tidak boleh
// ditafsirkan sebagai "tidak diset" lalu jatuh ke default yang menyala.

/** Nilai yang dihitung "hidup". Cerminan `TRUE_FLAGS` di `agent/agent/vault_client.py`. */
const TRUE_FLAGS = new Set(["1", "true", "yes", "demo"]);

/**
 * Apakah sebuah nilai env dihitung menyala. `undefined`/`null` (tidak diset) = mati,
 * string kosong atau spasi saja = mati.
 *
 * @param {string | undefined | null} raw
 * @returns {boolean}
 */
export function isFlagOn(raw) {
  if (typeof raw !== "string") return false;
  return TRUE_FLAGS.has(raw.trim().toLowerCase());
}

/**
 * Gerbang DEMO_MODE, dibaca dari `process.env` PADA SAAT DIPANGGIL.
 *
 * Harus dipanggil per permintaan, bukan di lingkup modul: kedua pemanggilnya memakai
 * `export const dynamic = "force-dynamic"` supaya nilainya tidak beku pada `next build`.
 *
 * @returns {boolean}
 */
export function demoModeEnabled() {
  return isFlagOn(process.env.DEMO_MODE);
}
