/**
 * sim/src/scenario.ts — menjalankan RANTAI job yang diminta naskah demo, satu perintah.
 *
 *   pnpm sim:run --scenario alpha-x3
 *
 * Berkas ini TIDAK berbicara dengan rantai sama sekali: ia tidak mengimpor viem, tidak memegang
 * kunci privat, dan tidak meng-encode satu byte calldata pun. Yang dilakukannya hanya memanggil
 * `src/client_min.ts` — satu proses per job — dengan variabel lingkungan yang berbeda, lalu
 * memanen baris `[client_min] summary` dari keluarannya. Seluruh alur ACP (`createJob`,
 * `setBudget`, `fund`, `submit`) tetap terjadi di dalam `client_min.ts` lewat SDK
 * `@virtuals-protocol/acp-node-v2`, jadi rantai ini tidak menambah satu pun jalur transaksi baru
 * yang harus diaudit terpisah.
 *
 * Kenapa proses TERPISAH, bukan pemanggilan fungsi: `client_min.ts` membaca tombol skenarionya
 * dari `process.env` dan menjalankan `main()` saat diimpor. Satu proses per job memberi isolasi
 * yang sama seperti mengetik tiga perintah dengan tangan (persis yang selama ini didokumentasikan
 * di README) — nonce, cache `.env`, dan state modul tidak bisa merembes antar job.
 *
 * ---------------------------------------------------------------------------
 * IDEMPOTEN — apa yang dijanjikan dan apa yang TIDAK
 * ---------------------------------------------------------------------------
 * DIJANJIKAN: satu putaran tidak membaca dan tidak bergantung pada state putaran sebelumnya.
 * Menjalankannya dua kali berturut-turut menghasilkan baris `[scenario] step` yang IDENTIK
 * byte-per-byte (langkah, provider, budget, sampai di mana job dibawa, hash deliverable, dan
 * status akhir job on-chain).
 *
 * TIDAK DIJANJIKAN: `jobId` dan hash transaksi yang sama. `jobCounter` ACP menaik dan tidak
 * bisa diputar balik — itu sifat kontrak, bukan pilihan kita. Karena itu keduanya sengaja
 * DIPISAH ke baris `[scenario] onchain`, supaya baris yang dibandingkan antar-putaran tidak
 * ikut tercemar. Memori agen juga TIDAK direset dari sini (ia milik `agent/`): rantai A/B/C
 * hanya bermakna di atas memori yang bersih untuk provider itu.
 *
 * ---------------------------------------------------------------------------
 * BATAS: skrip ini menyiapkan JOB, bukan VERDICT
 * ---------------------------------------------------------------------------
 * Kolom `expectVerdict` di bawah adalah EKSPEKTASI naskah demo (docs/spec.md §7 langkah 1-3),
 * bukan pengamatan. Yang menghasilkan verdict adalah `agent/`; skrip ini berhenti tepat pada
 * status yang dituntut tiap langkah (`SUBMITTED` untuk A/B, `FUNDED` untuk C) dan mencetak
 * `jobId`-nya supaya agen bisa dijalankan atasnya.
 */

import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SIM_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CLIENT_MIN = join(SIM_ROOT, "src", "client_min.ts");

/**
 * Tombol skenario `client_min.ts`. Semuanya DIHAPUS dari environment anak lebih dulu, lalu
 * hanya yang relevan untuk langkah itu yang diisi ulang.
 *
 * Ini bukan kerapian: `BUDGET_RAW=2000000` yang tertinggal di shell pemanggil akan diam-diam
 * membuat job A dan B melebihi cap, dan `STOP_AFTER=fund` yang tertinggal membuat keduanya tidak
 * pernah `submit`. Rantai tetap "berhasil" dan tetap salah. Dengan dihapus dulu, satu-satunya
 * sumber nilai tombol adalah tabel STEPS di bawah.
 */
const SCENARIO_ENV_KEYS = [
  "BUDGET_RAW",
  "STOP_AFTER",
  "DELIVERABLE_TEXT",
  "DELIVERABLE_FILE",
  "PROVIDER_SLOT",
] as const;

type StepEnv = Partial<Record<(typeof SCENARIO_ENV_KEYS)[number], string>>;

type Step = {
  /** Label langkah di naskah demo. */
  readonly id: string;
  /** Kalimat naskah yang dilayani langkah ini. */
  readonly note: string;
  /** Status job yang WAJIB tercapai; kalau tidak, rantai berhenti. */
  readonly expectStatus: "SUBMITTED" | "FUNDED";
  /** Verdict yang diharapkan dari `agent/` — EKSPEKTASI, bukan pengamatan. */
  readonly expectVerdict: string;
  readonly env: StepEnv;
};

/**
 * `alpha-x3` — docs/spec.md §7 langkah 1-3, SATU provider (slot `alpha`), tiga job.
 *
 * Angka budget bukan selera:
 *  - A (250.000 = 0,25 USDC): provider masih risk 0, belum ada cap sama sekali.
 *  - B (250.000): sesudah insiden pertama risk 1 → cap `BASELINE_CAP_USDC` = 1.000.000
 *    (ADR-020 keputusan 3), jadi job ini LOLOS gerbang cap dan ditolak murni karena isinya.
 *  - C (2.000.000 = 2 USDC): sesudah insiden kedua risk >= 2 → cap 1.000.000 // 4 = 250.000,
 *    jadi 2 USDC MELEBIHI cap. ADR-020 keputusan 3 memilih angka-angka itu justru supaya
 *    langkah 3 muat di 2 USDC yang dimiliki wallet client.
 *
 * Teks deliverable A dan B diberikan lewat BERKAS, bukan `DELIVERABLE_TEXT`, supaya byte-nya
 * tidak bergantung pada pengutipan shell dan bisa dibandingkan langsung dengan deliverable yang
 * sudah pernah diserahkan di Base Sepolia (`demo/deliverables/418.json` dan `419.json`).
 * Keduanya membawa penanda `TODO` — cacat DETERMINISTIK, sehingga penolakan datang dari
 * `checks/format.py`, bukan dari penilaian LLM.
 *
 * Job C sengaja BERHENTI sesudah `fund`: naskah menuntut agen menolaknya saat status `Funded`,
 * yaitu SEBELUM provider menyerahkan apa pun. Kalau `submit` sempat jalan, klaim "gerbang cap
 * menolak lebih awal" hilang.
 */
const STEPS: readonly Step[] = [
  {
    id: "A",
    note: "§7 step 1 — tidy job but a deterministic defect; REJECT, suspicion count=1",
    expectStatus: "SUBMITTED",
    expectVerdict: "REJECT (deterministic check failed)",
    env: {
      PROVIDER_SLOT: "alpha",
      BUDGET_RAW: "250000",
      STOP_AFTER: "submit",
      DELIVERABLE_FILE: "sim/scenarios/alpha-x3-a.md",
    },
  },
  {
    id: "B",
    note: "§7 step 2 — same pattern, different job; second REJECT -> count=2 -> pattern promoted, risk=2",
    expectStatus: "SUBMITTED",
    expectVerdict: "REJECT (deterministic check failed) + setProviderCap",
    env: {
      PROVIDER_SLOT: "alpha",
      BUDGET_RAW: "250000",
      STOP_AFTER: "submit",
      DELIVERABLE_FILE: "sim/scenarios/alpha-x3-b.md",
    },
  },
  {
    id: "C",
    note: "§7 step 3 — budget 2 USDC exceeds the 0.25 USDC cap; the gate rejects while Funded",
    expectStatus: "FUNDED",
    expectVerdict: "REJECT while Funded (over cap; 2 confirmed incidents)",
    env: {
      PROVIDER_SLOT: "alpha",
      BUDGET_RAW: "2000000",
      STOP_AFTER: "fund",
    },
  },
];

const SCENARIOS: Readonly<Record<string, readonly Step[]>> = { "alpha-x3": STEPS };

// ---------------------------------------------------------------------------

class UsageError extends Error {}

/** `--scenario <nama>` atau `--scenario=<nama>`. Tidak ada default: rantai yang salah itu mahal. */
export function parseScenarioName(argv: readonly string[]): string {
  let name: string | undefined;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] as string;
    if (arg === "--scenario") {
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("--")) {
        throw new UsageError("--scenario butuh nilai, mis. --scenario alpha-x3");
      }
      name = next;
      i += 1;
      continue;
    }
    if (arg.startsWith("--scenario=")) {
      name = arg.slice("--scenario=".length);
      continue;
    }
    throw new UsageError(`argumen tidak dikenal: ${arg}`);
  }
  if (name === undefined) throw new UsageError("wajib --scenario <nama>");
  if (!(name in SCENARIOS)) {
    throw new UsageError(`skenario "${name}" tidak dikenal; yang ada: ${Object.keys(SCENARIOS).join(", ")}`);
  }
  return name;
}

/**
 * Environment untuk satu langkah: warisan pemanggil MINUS seluruh tombol skenario, PLUS tombol
 * milik langkah ini. Rahasia (kunci privat) dan alamat jaringan tetap diwariskan apa adanya —
 * skrip ini tidak pernah membacanya.
 */
export function childEnv(base: NodeJS.ProcessEnv, step: StepEnv): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...base };
  for (const key of SCENARIO_ENV_KEYS) delete env[key];
  for (const [key, value] of Object.entries(step)) env[key] = value;
  return env;
}

/** Memanen `key=value` dari baris `[client_min] <event> k=v k=v`. */
export function parseLogLine(line: string, event: string): Record<string, string> | null {
  const prefix = `[client_min] ${event} `;
  if (!line.startsWith(prefix)) return null;
  const fields: Record<string, string> = {};
  for (const token of line.slice(prefix.length).trim().split(" ")) {
    const eq = token.indexOf("=");
    if (eq > 0) fields[token.slice(0, eq)] = token.slice(eq + 1);
  }
  return fields;
}

function log(event: string, fields: Record<string, unknown>): void {
  const parts = Object.entries(fields).map(([k, v]) => `${k}=${String(v)}`);
  console.log([`[scenario] ${event}`, ...parts].join(" "));
}

type StepResult = {
  readonly summary: Record<string, string>;
  readonly deliverableSha: string;
};

/**
 * Menjalankan satu job. Keluaran anak diteruskan APA ADANYA ke stdout kita (anak sudah menyensor
 * kunci privat lewat `scrub()`), sekaligus dipanen barisnya.
 */
function runStep(step: Step): Promise<StepResult> {
  return new Promise((resolve, reject) => {
    // `node --import tsx <file>` — jalur resmi tsx untuk menjalankan TypeScript di proses baru,
    // dan `process.execPath` memastikan anak memakai runtime Node yang SAMA dengan induk.
    const child = spawn(process.execPath, ["--import", "tsx", CLIENT_MIN], {
      cwd: SIM_ROOT,
      env: childEnv(process.env, step.env),
      stdio: ["ignore", "pipe", "inherit"],
    });

    let summary: Record<string, string> | null = null;
    let deliverableSha = "-";
    let pending = "";

    const consume = (line: string): void => {
      console.log(line);
      const artifact = parseLogLine(line, "deliverable.artifact");
      if (artifact?.sha_keccak) deliverableSha = artifact.sha_keccak;
      const found = parseLogLine(line, "summary");
      if (found) summary = found;
    };

    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      pending += chunk;
      const lines = pending.split("\n");
      pending = lines.pop() ?? "";
      for (const line of lines) consume(line);
    });

    child.on("error", reject);
    child.on("close", (code) => {
      if (pending) consume(pending);
      if (code !== 0) {
        reject(new Error(`langkah ${step.id}: client_min.ts keluar dengan kode ${String(code)}`));
        return;
      }
      if (!summary) {
        reject(new Error(`langkah ${step.id}: baris "[client_min] summary" tidak ditemukan di keluaran`));
        return;
      }
      resolve({ summary, deliverableSha });
    });
  });
}

async function main(): Promise<void> {
  const name = parseScenarioName(process.argv.slice(2));
  const steps = SCENARIOS[name] as readonly Step[];
  log("start", { scenario: name, steps: steps.length });

  const results: { step: Step; result: StepResult }[] = [];
  for (const step of steps) {
    log("step.begin", { scenario: name, step: step.id, note: `"${step.note}"` });
    const result = await runStep(step);
    const status = result.summary.status ?? "?";
    if (status !== step.expectStatus) {
      throw new Error(
        `step ${step.id}: final status ${status}, expected ${step.expectStatus} — chain halted`,
      );
    }
    results.push({ step, result });
  }

  // Blok DETERMINISTIK: tidak memuat jobId maupun hash tx, jadi dua putaran berturut-turut
  // menghasilkan baris yang identik byte-per-byte. Inilah yang dibandingkan untuk membuktikan
  // skenario idempoten.
  for (const { step, result } of results) {
    log("step", {
      scenario: name,
      step: step.id,
      providerSlot: step.env.PROVIDER_SLOT ?? "alpha",
      budgetRaw: result.summary.budgetRaw ?? "?",
      stopAfter: step.env.STOP_AFTER ?? "submit",
      deliverableSha: result.deliverableSha,
      status: result.summary.status ?? "?",
      expectVerdict: `"${step.expectVerdict}"`,
    });
  }

  // Blok yang MEMANG berbeda tiap putaran — dipisah supaya tidak mencemari blok di atas.
  for (const { step, result } of results) {
    log("onchain", {
      scenario: name,
      step: step.id,
      jobId: result.summary.jobId ?? "?",
      providerAddress: result.summary.providerAddress ?? "?",
      evaluatorAddress: result.summary.evaluatorAddress ?? "?",
      escrowToken: result.summary.escrowToken ?? "?",
      deliverablePath: result.summary.deliverablePath ?? "-",
    });
  }

  log("done", {
    scenario: name,
    jobIds: results.map(({ result }) => result.summary.jobId ?? "?").join(","),
    next: '"run agent/ over each jobId for its verdict — this script prepares jobs, not verdicts"',
  });
}

main().catch((err: unknown) => {
  if (err instanceof UsageError) {
    console.error(`[scenario] USAGE ${err.message}`);
    console.error("[scenario] example: pnpm sim:run --scenario alpha-x3");
    process.exitCode = 2;
    return;
  }
  const message = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
  console.error(`[scenario] FAILED ${message}`);
  process.exitCode = 1;
});
