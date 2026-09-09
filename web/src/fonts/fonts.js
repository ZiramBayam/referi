import localFont from "next/font/local";

/**
 * Tiga huruf, di-vendor ke repo (bukan CDN) supaya halaman ini utuh saat juri
 * menjalankannya tanpa internet. Ketiganya SIL Open Font License 1.1 — lihat
 * `src/fonts/NOTICE.md`. Subset yang diunduh hanya latin dasar (U+0000-00FF):
 * ~100 KB untuk ketiganya.
 *
 *   display : Instrument Serif — suara judul. Besar, tracking rapat.
 *   sans    : Inter            — prosa dan antarmuka.
 *   mono    : JetBrains Mono   — angka, hash, alamat, apa pun yang dibandingkan
 *                                antar baris.
 */

export const display = localFont({
  src: "./InstrumentSerif-Regular.woff2",
  weight: "400",
  style: "normal",
  display: "swap",
  variable: "--font-display",
  fallback: ["Georgia", "Times New Roman", "serif"],
});

export const sans = localFont({
  src: "./Inter-Variable.woff2",
  weight: "100 900",
  style: "normal",
  display: "swap",
  variable: "--font-sans",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
});

export const mono = localFont({
  src: "./JetBrainsMono-Variable.woff2",
  weight: "100 800",
  style: "normal",
  display: "swap",
  variable: "--font-mono",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
});
