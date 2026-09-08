// Deklarasi ambient MINIMAL untuk `pnpm lint` (`tsc --noEmit -p tsconfig.lint.json`).
//
// Kenapa ditulis tangan dan bukan memasang `@types/node`: paket itu di luar
// `docs/versions.md` untuk `web/` (di sana ia devDependency `sim/` SAJA), jadi
// memasangnya butuh ADR. Yang dibutuhkan `web/` hanya SATU global — `process.env` untuk
// membaca DEMO_MODE di server — jadi itu saja yang dideklarasikan.
//
// Berkas ini TIDAK ikut runtime: `noEmit` dan hanya dibaca tsconfig.lint.json.

declare const process: {
  env: Record<string, string | undefined>;
};

// `import "./globals.css"` adalah efek samping yang ditangani bundler Next, bukan modul
// TypeScript. Tanpa deklarasi ini tsc menolaknya (TS2882).
declare module "*.css";
