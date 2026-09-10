// Pembaca encoding kanonik bundel bukti (`evaluator-verdict-evidence/v3` & `/v4`).
//
// Agen menulis setiap uint sebagai objek `{"$u":"418"}`, BUKAN sebagai angka JSON, itu
// yang membuat `keccak256(isi berkas)` bisa dicocokkan ulang tanpa bergantung pada cara
// tiap bahasa mencetak angka. Halaman ini karena itu TIDAK BOLEH menganggap angka biasa.
//
// Catatan penting: `web/` TIDAK PERNAH menghitung ulang hash apa pun. Modul ini hanya
// MEMBACA nilai supaya bisa ditampilkan.

/**
 * Nilai uint kanonik sebagai string desimal, atau `null` bila field tidak ada.
 * Dikembalikan sebagai STRING supaya nilai di luar Number.MAX_SAFE_INTEGER tidak dibulatkan.
 * @param {unknown} value
 * @returns {string | null}
 */
export function readUint(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "object" && value !== null && "$u" in value) {
    const raw = /** @type {{ $u: unknown }} */ (value).$u;
    if (typeof raw === "string" && /^[0-9]+$/.test(raw)) return raw;
    return null;
  }
  // Bundel yang sudah ada SELALU memakai bentuk {"$u": "..."}. Bentuk lain tidak
  // ditebak-tebak: ia dilaporkan sebagai tidak terbaca, bukan dipaksa jadi angka.
  return null;
}

/**
 * Sama dengan `readUint`, tetapi mengembalikan Number untuk nilai kecil yang memang
 * dipakai sebagai enum/indeks (verdict kind, indeks bagian). `null` bila tidak terbaca.
 * @param {unknown} value
 * @returns {number | null}
 */
export function readSmallInt(value) {
  const text = readUint(value);
  if (text === null) return null;
  const n = Number(text);
  return Number.isSafeInteger(n) ? n : null;
}

/**
 * Indeks bagian pada hasil cek. Bundel memakai `-1` untuk "tidak menunjuk satu bagian pun",
 * tetapi menuliskannya sebagai uint kanonik bertanda minus di dalam string.
 * @param {unknown} value
 * @returns {number | null}
 */
export function readSectionIndex(value) {
  if (typeof value === "object" && value !== null && "$u" in value) {
    const raw = /** @type {{ $u: unknown }} */ (value).$u;
    if (typeof raw === "string" && /^-?[0-9]+$/.test(raw)) {
      const n = Number(raw);
      return Number.isSafeInteger(n) ? n : null;
    }
  }
  return null;
}

/**
 * Format unit token 6 desimal (token escrow ACP `0xECc2…BDb3`) sebagai teks, dengan
 * pemisah gaya Inggris (ribuan `,`, desimal `.`) supaya cocok dengan sisa halaman.
 * Dihitung dari STRING supaya tidak lewat floating point.
 * @param {string | null | undefined} units
 * @returns {string | null}
 */
export function formatUsdc6(units) {
  if (typeof units !== "string" || !/^[0-9]+$/.test(units)) return null;
  const padded = units.padStart(7, "0");
  const whole = padded.slice(0, -6).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const frac = padded.slice(-6).replace(/0+$/, "");
  return frac ? `${whole}.${frac}` : whole;
}
