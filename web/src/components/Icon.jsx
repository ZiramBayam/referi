/**
 * Ikon Lucide, di-inline sebagai path (bukan paket npm) — nol dependency runtime,
 * nol permintaan jaringan, dan bobot garis yang sama untuk semuanya.
 *
 * Sumber: https://github.com/lucide-icons/lucide — ISC License,
 * Copyright (c) 2026 Lucide Icons and Contributors. Lisensi ISC mengizinkan
 * redistribusi di dalam repo MIT ini selama pemberitahuan hak ciptanya ikut,
 * dan itulah gunanya blok komentar ini.
 *
 * Setiap ikon di sini MENGERJAKAN sesuatu: menggantikan glyph Unicode yang dipakai
 * sebagai ikon, atau menyampaikan status tanpa mengandalkan warna saja. Tidak ada
 * yang dipasang sebagai hiasan.
 */

/** @type {Record<string, string[]>} */
const PATHS = {
  "arrow-left": ["m12 19-7-7 7-7", "M19 12H5"],
  "arrow-right": ["M5 12h14", "m12 5 7 7-7 7"],
  check: ["M20 6 9 17l-5-5"],
  x: ["M18 6 6 18", "m6 6 12 12"],
  "external-link": [
    "M15 3h6v6",
    "M10 14 21 3",
    "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
  ],
  "triangle-alert": [
    "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",
    "M12 9v4",
    "M12 17h.01",
  ],
  trash: [
    "M10 11v6",
    "M14 11v6",
    "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6",
    "M3 6h18",
    "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2",
  ],
};

/**
 * Selalu `aria-hidden`: setiap pemakaian di repo ini menemani teks yang sudah
 * mengatakan hal yang sama, jadi mengumumkannya lagi hanya menggandakan bunyi
 * di pembaca layar.
 *
 * @param {{ name: keyof typeof PATHS | string, size?: number, className?: string }} props
 */
export default function Icon({ name, size = 16, className }) {
  const paths = PATHS[name];
  if (!paths) return null;
  return (
    <svg
      className={className ? "icon " + className : "icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
