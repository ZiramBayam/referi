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
  cwd(): string;
};

// Rute preflight menjalankan agen Python sungguhan lewat subprocess, jadi `web/` kini
// memakai dua modul bawaan Node. Yang dideklarasikan HANYA permukaan yang benar-benar
// dipanggil `src/lib/agentPreflight.js`, dengan alasan yang sama seperti di atas:
// memasang `@types/node` di `web/` butuh ADR, dan permukaan yang dipakai sangat kecil.
declare module "node:child_process" {
  export function execFile(
    file: string,
    args: readonly string[],
    options: { cwd?: string; timeout?: number; maxBuffer?: number },
    callback: (
      error: (Error & { killed?: boolean }) | null,
      stdout: string,
      stderr: string
    ) => void
  ): { stdin?: { end(chunk: string): void } };
}

declare module "node:path" {
  export function resolve(...paths: string[]): string;
  export function join(...paths: string[]): string;
  const path: { resolve: typeof resolve; join: typeof join };
  export default path;
}

// `import "./globals.css"` adalah efek samping yang ditangani bundler Next, bukan modul
// TypeScript. Tanpa deklarasi ini tsc menolaknya (TS2882).
declare module "*.css";
