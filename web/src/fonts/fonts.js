import localFont from "next/font/local";

/**
 * Tiga huruf, di-vendor ke repo (bukan CDN) supaya halaman ini utuh saat juri
 * menjalankannya tanpa internet. Ketiganya SIL Open Font License 1.1 — lihat
 * `src/fonts/NOTICE.md`. Subset yang diunduh hanya latin dasar (U+0000-00FF).
 *
 *   display : Fraunces      — serif variabel dengan sumbu WONK dan SOFT: huruf
 *                             yang sengaja miring-lucu dan sudut yang dilunakkan.
 *                             Ia PUNYA watak; Instrument Serif elegan tapi datar.
 *   sans    : Space Grotesk — prosa dan antarmuka. Inter adalah huruf UI paling
 *                             netral yang ada, dan netral itulah yang membuat
 *                             halaman ini terbaca seperti dokumen kantor.
 *   mono    : JetBrains Mono — angka, hash, alamat, apa pun yang dibandingkan
 *                             antar baris.
 */

export const display = localFont({
  src: "./Fraunces-Variable.woff2",
  weight: "400 700",
  style: "normal",
  display: "swap",
  variable: "--font-display",
  fallback: ["Georgia", "Times New Roman", "serif"],
});

export const sans = localFont({
  src: "./SpaceGrotesk-Variable.woff2",
  weight: "300 700",
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
