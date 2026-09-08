/**
 * sim/src/demo.ts — `make demo`: naskah `docs/spec.md` §7 langkah 1-4, DARI NOL, di Anvil lokal.
 *
 * Satu perintah membangun seluruh dunia dan membongkarnya lagi:
 *   1. `anvil --chain-id 84532` baru (rantai kosong, blok 0);
 *   2. deploy MockUSDC + mock AgenticCommerce + EvaluatorVault lewat `forge create`;
 *   3. `mint_min.ts` mendanai wallet client;
 *   4. `scenario.ts --scenario alpha-x3` membuat job A/B/C lewat SDK Virtuals;
 *   5. `agent.vault_client` menilai ketiganya (§7 langkah 1-3);
 *   6. §7 langkah 4 — DUA varian destruktif berurutan, keduanya dicetak:
 *      VARIAN A (di sini, Anvil): vault SEGAR (root on-chain nol lagi) + memori DIHAPUS → cap
 *        hilang, kedalaman turun ke `sampling`, job besar yang tadi ditolak gerbang kini LOLOS
 *        gerbang. Dua job, bukan satu: cacat HALUS (job D) lolos, cacat KASAR (job E) TETAP
 *        ditolak. Varian yang hanya menjalankan job D adalah varian yang dijamin menang.
 *      VARIAN B (vault Base Sepolia yang DIBEKUKAN ADR-022, root non-nol) + memori DIHAPUS →
 *        mode aman: nol postVerdict, nol finalize, dan nonce wallet agen SEBELUM == SESUDAH.
 *
 * Berkas ini tidak berbicara dengan ACP sendiri: seluruh alur job tetap lewat `client_min.ts`
 * → SDK `@virtuals-protocol/acp-node-v2`, dan seluruh verdict tetap lewat `agent/`.
 *
 * ---------------------------------------------------------------------------
 * KENAPA chainId 84532 di rantai lokal
 * ---------------------------------------------------------------------------
 * SDK memetakan chainId → keluarga rantai lewat registri BAWAANNYA dan gagal-tertutup untuk id
 * yang tidak terdaftar (`dist/core/constants.js` `getChainFamily`: `31337` → `UnknownChainIdError`).
 * Alamat KONTRAKNYA memang boleh ditimpa (`CreateAcpClientInput.contractAddresses`), tetapi
 * chainId-nya tidak. Jadi Anvil dijalankan dengan `--chain-id 84532` dan mock ACP dipasang
 * lewat `ACP_ADDRESS`. Ini bukan penyamaran: tidak ada satu pun transaksi yang menyentuh
 * jaringan sungguhan — RPC-nya `127.0.0.1`.
 *
 * ---------------------------------------------------------------------------
 * KENAPA ADA "TIME TICKER"
 * ---------------------------------------------------------------------------
 * `EvaluatorVault.CHALLENGE_WINDOW` = 120 detik dan `finalize` membandingkannya dengan
 * `block.timestamp`. Anvil TIDAK memajukan `block.timestamp` tanpa blok baru, jadi tanpa
 * bantuan apa pun agen menunggu selamanya (terukur: "sisa 121 detik" berulang tanpa henti pada
 * anvil auto-mine). Dua lapis dipakai:
 *   - `--block-time 1` menjamin waktu SELALU maju, bahkan bila ticker mati → demo tetap selesai,
 *     hanya lambat (≈2 menit per job);
 *   - ticker `evm_increaseTime` + `evm_mine` memampatkan jendela itu, dan hanya hidup SELAMA
 *     invokasi agen — tidak pernah saat `client_min.ts` membuat job, supaya `expiredAt` (yang
 *     dihitung dari jam dinding) tidak pernah balapan dengan jam rantai yang dipercepat.
 *
 * ---------------------------------------------------------------------------
 * IDEMPOTEN
 * ---------------------------------------------------------------------------
 * Rantai dibuat dari nol tiap kali, jadi `jobId` (1..4) dan alamat kontrak (turunan nonce
 * deployer) pun deterministik dan ikut masuk blok yang dibandingkan. Yang TIDAK deterministik
 * hanya hash transaksi dan nomor blok — keduanya bergantung pada waktu tanda tangan — dan
 * karena itu dipisah ke baris `[demo] onchain`.
 */

import { spawn, type SpawnOptions } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { mnemonicToAccount } from "viem/accounts";
import { getAddress, toFunctionSelector, toHex, type Address, type Hex } from "viem";

const SIM_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = join(SIM_ROOT, "..");
const AGENT_ROOT = join(REPO_ROOT, "agent");
const CONTRACTS_ROOT = join(REPO_ROOT, "contracts");

/** Semua artefak run ada di bawah `agent/data/` yang sudah di-`.gitignore` (`data/`). */
const WORK_ROOT = join(AGENT_ROOT, "data", "demo");
const DB_PATH = join(WORK_ROOT, "memory.db");
const VERDICT_DIR = join(WORK_ROOT, "verdicts");
const DELIVERABLE_DIR = join(WORK_ROOT, "deliverables");
const LOG_DIR = join(WORK_ROOT, "logs");

/** Ketiga file memori yang dituntut "hapus memori" (`memory.db`, `-wal`, `-shm`). */
const MEMORY_DB_SUFFIXES = ["", "-wal", "-shm"] as const;

const CHAIN_ID = 84532;
const PORT = Number(process.env.DEMO_PORT ?? "8545");
const RPC_URL = `http://127.0.0.1:${PORT}`;

/**
 * Mnemonic pengembangan Anvil — PUBLIK, tercetak di banner Anvil sendiri, dan hanya berlaku di
 * rantai `127.0.0.1` yang lahir dan mati bersama perintah ini. Kunci privatnya DITURUNKAN saat
 * jalan, tidak pernah ditulis sebagai literal di repo.
 */
const ANVIL_MNEMONIC = "test test test test test test test test test test test junk";

/** Peran → indeks akun Anvil. Empat alamat BERBEDA; kontrak ACP dan ADR-017 poin 3 memaksanya. */
const ROLE_INDEX = { deployer: 0, client: 1, provider: 2, agent: 3, arbiter: 4 } as const;
type Role = keyof typeof ROLE_INDEX;

/** Penerima fee platform mock. Alamat pembuangan; tidak pernah menandatangani apa pun. */
const TREASURY = "0x000000000000000000000000000000000000dEaD" as Address;

/** 10 USDC — cukup untuk A (0,25) + B (0,25) + C (2) + D (2) + E (2) dengan sisa. */
const MINT_RAW = "10000000";

/** §7 langkah 4: job besar yang DITOLAK gerbang di langkah 3, diulang tanpa memori. */
const STEP4_BUDGET_RAW = "2000000";

/**
 * Deliverable §7 langkah 4 — TIGA bagian, dengan cacat (`TODO`) HANYA di bagian ketiga.
 *
 * Itu yang membuat langkah ini membuktikan sesuatu: pada memori kosong provider berisiko-nol
 * dinilai `sampling` (bagian ketiga tidak dibaca) sehingga deliverable LOLOS, sedangkan provider
 * yang memorinya memuat dua insiden dinilai `full` dan cacat itu tertangkap. Berkas yang sama
 * dipakai `agent/tests/test_criteria.py`, jadi propertinya terikat tes, bukan klaim naskah.
 */
const STEP4_DELIVERABLE_FILE = "sim/scenarios/depth-demo.md";

/**
 * Deliverable VARIAN A job E — `depth-demo.md` dengan cacat yang SAMA dipindah ke bagian
 * PERTAMA. Ia yang membuat varian A jujur: memori yang dihapus menurunkan KEDALAMAN, bukan
 * mematikan evaluator, jadi cacat yang duduk di dalam jendela `sampling` tetap tertangkap.
 * `agent/tests/test_criteria.py` mengikat kedua properti itu ke berkas ini.
 */
const VARIANT_A_COARSE_FILE = "sim/scenarios/coarse-defect.md";

/**
 * VARIAN B — vault SUBMISSION yang dibekukan ADR-022 di Base Sepolia, `lastMemoryRoot()`
 * NON-NOL. Alamatnya dipin: varian ini tidak boleh ikut berpindah bila `.env` berubah.
 * Nol transaksi dikirim, jadi varian ini tidak butuh dana sama sekali; yang dibaca hanya
 * dua `eth_call` view + `eth_getTransactionCount`.
 */
const FROZEN_VAULT = "0x5c6EE4586ACABcb6326069c229E58091B21ef384" as Address;
const SEPOLIA_RPC = "https://sepolia.base.org";
const SEPOLIA_ACP = "0x0b93793923CD5De81850aF8604a233f3f24d461e" as Address;

/**
 * Job Sepolia yang SUDAH TERMINAL (422, Rejected). Lapis kedua yang disengaja: gerbang mode
 * aman keluar jauh sebelum job dibaca, tetapi seandainya ia gagal menahan, job terminal tetap
 * tidak bisa menerima verdict — jadi tidak ada jalur di mana varian B menghasilkan transaksi.
 */
const FROZEN_JOB_ID = 422;

/** Ruang kerja varian B — TERPISAH, supaya memori varian A tidak pernah menghidupkannya. */
const VARIANT_B_ROOT = join(WORK_ROOT, "varian-b");
const VARIANT_B_DB = join(VARIANT_B_ROOT, "memory.db");

const ZERO_ROOT = `0x${"0".repeat(64)}`;

/** Selector view vault. Diturunkan dari signature, tidak diketik sebagai literal. */
const SELECTOR_AGENT = toFunctionSelector("function agent() view returns (address)");
const SELECTOR_LAST_MEMORY_ROOT = toFunctionSelector(
  "function lastMemoryRoot() view returns (bytes32)",
);

/** ADR-026: pada memori yang belum lahir, invokasi PERTAMA berakhir `EXIT_REFUSED` (4), nol tx. */
const EXIT_REFUSED = 4;

// ---------------------------------------------------------------------------
// Akun
// ---------------------------------------------------------------------------

type Wallet = { readonly address: Address; readonly privateKey: Hex };

function wallet(role: Role): Wallet {
  const account = mnemonicToAccount(ANVIL_MNEMONIC, { addressIndex: ROLE_INDEX[role] });
  const key = account.getHdKey().privateKey;
  if (!key) throw new Error(`kunci untuk peran ${role} tidak bisa diturunkan dari mnemonic Anvil`);
  return { address: account.address, privateKey: toHex(key) };
}

// ---------------------------------------------------------------------------
// Log
// ---------------------------------------------------------------------------

function log(event: string, fields: Record<string, unknown> = {}): void {
  const parts = Object.entries(fields).map(([k, v]) => `${k}=${String(v)}`);
  console.log([`[demo] ${event}`, ...parts].join(" "));
}

// ---------------------------------------------------------------------------
// Proses anak
// ---------------------------------------------------------------------------

type RunResult = { readonly code: number; readonly stdout: string };

/**
 * Menjalankan satu perintah sampai selesai dan mengembalikan stdout-nya.
 *
 * `echo: true` meneruskan stdout anak ke stdout kita saat itu juga (dipakai untuk sim/agen,
 * yang barisnya memang bagian dari naskah demo). stderr SELALU diwariskan.
 */
function run(
  command: string,
  args: readonly string[],
  options: { cwd: string; env?: NodeJS.ProcessEnv; echo?: boolean },
): Promise<RunResult> {
  return new Promise((resolve, reject) => {
    const spawnOptions: SpawnOptions = {
      cwd: options.cwd,
      env: options.env ?? process.env,
      stdio: ["ignore", "pipe", "inherit"],
    };
    const child = spawn(command, args, spawnOptions);
    let stdout = "";
    let pending = "";
    child.stdout?.setEncoding("utf8");
    child.stdout?.on("data", (chunk: string) => {
      stdout += chunk;
      if (!options.echo) return;
      pending += chunk;
      const lines = pending.split("\n");
      pending = lines.pop() ?? "";
      for (const line of lines) console.log(line);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (options.echo && pending) console.log(pending);
      resolve({ code: code ?? -1, stdout });
    });
  });
}

/** Sama seperti `run`, tetapi kode keluar bukan-nol adalah kegagalan demo. */
async function mustRun(
  command: string,
  args: readonly string[],
  options: { cwd: string; env?: NodeJS.ProcessEnv; echo?: boolean },
): Promise<RunResult> {
  const result = await run(command, args, options);
  if (result.code !== 0) {
    throw new Error(`perintah gagal (exit ${result.code}): ${command} ${args.join(" ")}`);
  }
  return result;
}

/** Menjalankan berkas TypeScript `sim/` di proses baru, dengan runtime Node yang sama. */
function runTs(
  file: string,
  args: readonly string[],
  env: NodeJS.ProcessEnv,
): Promise<RunResult> {
  return mustRun(process.execPath, ["--import", "tsx", join(SIM_ROOT, "src", file), ...args], {
    cwd: SIM_ROOT,
    env,
    echo: true,
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Anvil
// ---------------------------------------------------------------------------

async function rpcTo(url: string, method: string, params: unknown[] = []): Promise<unknown> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const body = (await res.json()) as { result?: unknown; error?: { message?: string } };
  if (body.error) throw new Error(`${method}: ${body.error.message ?? "galat RPC"}`);
  return body.result;
}

/** RPC ke rantai lokal demo. */
function rpc(method: string, params: unknown[] = []): Promise<unknown> {
  return rpcTo(RPC_URL, method, params);
}

/** Jumlah transaksi yang PERNAH dikirim sebuah alamat — satuan bukti varian A dan B. */
async function nonceOf(url: string, address: Address): Promise<number> {
  return Number(await rpcTo(url, "eth_getTransactionCount", [address, "latest"]));
}

/** `eth_call` tanpa argumen (view nol-parameter). */
async function callView(url: string, to: Address, selector: Hex): Promise<string> {
  return String(await rpcTo(url, "eth_call", [{ to, data: selector }, "latest"]));
}

let anvil: ReturnType<typeof spawn> | null = null;

async function startAnvil(): Promise<void> {
  // Port yang sudah dihuni adalah jebakan diam: kita akan men-deploy dan menilai di atas rantai
  // ORANG LAIN yang punya riwayat sendiri, dan "dari nol" langsung jadi bohong tanpa satu pun
  // pesan galat. Jadi diperiksa dulu — dan yang menghentikan demo adalah keberadaan siapa pun
  // di sana, bukan hanya chainId yang salah.
  let occupied = false;
  try {
    await rpc("eth_chainId");
    occupied = true;
  } catch {
    // Tidak ada yang menjawab — persis yang kita mau.
  }
  if (occupied) {
    throw new Error(
      `${RPC_URL} sudah dihuni proses lain. Demo menuntut rantai yang lahir dari NOL; ` +
        "matikan node itu, atau jalankan dengan DEMO_PORT=<port lain>.",
    );
  }

  // `--block-time 1` BUKAN kosmetik: lihat catatan "TIME TICKER" di kepala berkas.
  anvil = spawn(
    "anvil",
    ["--chain-id", String(CHAIN_ID), "--block-time", "1", "--port", String(PORT), "--silent"],
    { cwd: REPO_ROOT, stdio: ["ignore", "ignore", "inherit"] },
  );
  anvil.on("error", (err) => {
    throw new Error(`anvil tidak bisa dijalankan: ${err.message} (foundryup terpasang?)`);
  });
  for (let attempt = 1; attempt <= 40; attempt += 1) {
    try {
      const chainId = Number(await rpc("eth_chainId"));
      if (chainId !== CHAIN_ID) {
        throw new Error(`anvil di ${RPC_URL} melayani chainId ${chainId}, bukan ${CHAIN_ID}`);
      }
      return;
    } catch (err) {
      if (attempt === 40) throw err;
      await sleep(250);
    }
  }
}

function stopAnvil(): void {
  if (!anvil) return;
  anvil.kill("SIGTERM");
  anvil = null;
}

/**
 * Memajukan jam rantai selama sebuah invokasi agen.
 *
 * Tanpa ini `finalize` menunggu 120 detik jam dinding per job. `evm_increaseTime` menggeser
 * offset waktu Anvil secara permanen, jadi ia hanya dijalankan saat agen menunggu — tidak
 * pernah saat job dibuat.
 */
async function withTimeTicker<T>(work: () => Promise<T>): Promise<T> {
  let running = true;
  const ticker = (async () => {
    while (running) {
      try {
        await rpc("evm_increaseTime", [5]);
        await rpc("evm_mine");
      } catch {
        // Node sedang sibuk/mati; putaran berikutnya mencoba lagi. `--block-time 1` tetap
        // menjamin waktu maju, jadi kegagalan di sini memperlambat, bukan menggantung.
      }
      await sleep(200);
    }
  })();
  try {
    return await work();
  } finally {
    running = false;
    await ticker;
  }
}

// ---------------------------------------------------------------------------
// Deploy
// ---------------------------------------------------------------------------

/**
 * `forge create` satu kontrak dan mengembalikan alamatnya.
 *
 * Kontraknya sendiri TIDAK disentuh demo ini: yang dipakai adalah mock yang sudah ada di
 * `contracts/test/mocks/` dan `contracts/src/EvaluatorVault.sol` apa adanya.
 */
async function forgeCreate(
  target: string,
  constructorArgs: readonly string[],
  deployer: Wallet,
): Promise<Address> {
  const args = [
    "create",
    target,
    "--rpc-url",
    RPC_URL,
    "--private-key",
    deployer.privateKey,
    "--broadcast",
  ];
  if (constructorArgs.length > 0) args.push("--constructor-args", ...constructorArgs);
  const { stdout } = await mustRun("forge", args, { cwd: CONTRACTS_ROOT });
  const match = stdout.match(/Deployed to:\s*(0x[0-9a-fA-F]{40})/);
  if (!match) throw new Error(`forge create ${target}: alamat tidak terbaca dari keluarannya`);
  return match[1] as Address;
}

// ---------------------------------------------------------------------------
// Pemanen baris
// ---------------------------------------------------------------------------

/** `key=value` dari baris `[<prog>] <event> k=v k=v`. */
export function parseLogLine(line: string, prog: string, event: string): Record<string, string> | null {
  const prefix = `[${prog}] ${event} `;
  if (!line.startsWith(prefix)) return null;
  const fields: Record<string, string> = {};
  for (const token of line.slice(prefix.length).trim().split(" ")) {
    const eq = token.indexOf("=");
    if (eq > 0) fields[token.slice(0, eq)] = token.slice(eq + 1);
  }
  return fields;
}

/** Baris `RENCANA jobId=… mode=… depth=… cap=… gate=… evaluasi=…` milik `vault_client`. */
export function parsePlanLine(text: string): Record<string, string> {
  const line = text.split("\n").find((l) => l.startsWith("RENCANA "));
  if (!line) return {};
  const grab = (key: string, stop: string): string => {
    const re = new RegExp(`${key}=(.*?)(?= ${stop}=)`);
    return line.match(re)?.[1] ?? "?";
  };
  return {
    mode: grab("mode", "depth"),
    depth: grab("depth", "cap"),
    cap: grab("cap", "gate"),
    gate: grab("gate", "evaluasi"),
    evaluasi: line.match(/ evaluasi=(.*)$/)?.[1] ?? "?",
  };
}

function firstMatch(text: string, re: RegExp): string {
  return text.match(re)?.[1] ?? "-";
}

// ---------------------------------------------------------------------------
// Fase
// ---------------------------------------------------------------------------

type Deployment = { readonly usdc: Address; readonly acp: Address; readonly vault: Address };

type AgentOutcome = {
  readonly exit: number;
  readonly retried: boolean;
  readonly plan: Record<string, string>;
  readonly memoryRoot: string;
  readonly reasonHash: string;
  readonly cap: string;
  readonly postVerdict: string;
  readonly finalize: string;
};

/** Env dasar untuk SETIAP anak: alamat rantai lokal + lokasi memori, eksplisit. */
function baseEnv(deployment: Deployment, vaultAddress: Address): NodeJS.ProcessEnv {
  const agent = wallet("agent");
  return {
    ...process.env,
    RPC_URL,
    CHAIN_ID: String(CHAIN_ID),
    ACP_ADDRESS: deployment.acp,
    VAULT_ADDRESS: vaultAddress,
    AGENT_ADDRESS: agent.address,
    AGENT_PRIVATE_KEY: agent.privateKey,
    CLIENT_PRIVATE_KEY: wallet("client").privateKey,
    PROVIDER_PRIVATE_KEY: wallet("provider").privateKey,
    // Ketiganya DITERUSKAN EKSPLISIT, tidak pernah diwarisi `.env`: `.env` repo ini menunjuk
    // memori operasional yang terikat pada vault Base Sepolia, dan memakainya di sini berarti
    // demo menilai dengan memori yang tidak ada hubungannya dengan rantai yang baru lahir.
    SIBYL_DB_PATH: DB_PATH,
    VERDICT_BUNDLE_DIR: VERDICT_DIR,
    DELIVERABLE_DIR,
  };
}

/**
 * Satu invokasi agen atas satu job, dengan SATU kali coba ulang bila `EXIT_REFUSED`.
 *
 * Coba-ulang itu ADR-026: pada memori yang belum lahir, invokasi pertama menyusun rencananya
 * dalam mode `naive`, melahirkan `memory.db` di tengah jalan, lalu gerbang yang dibaca ulang
 * sesaat sebelum menandatangani melihat `normal` — beda keadaan, jadi ia menolak dengan NOL
 * transaksi. Invokasi kedua atas job yang sama berjalan sampai selesai. Ini dicetak apa adanya,
 * bukan disembunyikan: kode keluar 4 pada invokasi pertama adalah perilaku yang benar.
 */
async function runAgent(
  jobId: number,
  kind: "complete" | "reject",
  env: NodeJS.ProcessEnv,
): Promise<AgentOutcome> {
  const invoke = async (): Promise<RunResult> =>
    run("uv", ["run", "python", "-m", "agent.vault_client", "--job-id", String(jobId), "--kind", kind], {
      cwd: AGENT_ROOT,
      env,
      echo: true,
    });

  return withTimeTicker(async () => {
    let result = await invoke();
    let retried = false;
    if (result.code === EXIT_REFUSED) {
      log("agent.retry", { jobId, reason: "MODE_DRIFT-memori-baru-lahir-ADR-026", firstExit: EXIT_REFUSED });
      retried = true;
      result = await invoke();
    }
    if (result.code !== 0) {
      throw new Error(`agen keluar dengan kode ${result.code} untuk jobId=${jobId}`);
    }
    return {
      exit: result.code,
      retried,
      plan: parsePlanLine(result.stdout),
      memoryRoot: firstMatch(result.stdout, /memory_root TURUNAN[^=]*= (0x[0-9a-f]{64})/),
      reasonHash: firstMatch(result.stdout, /reason_hash \([^)]*\)=(0x[0-9a-f]{64})/),
      cap: firstMatch(result.stdout, /^cap provider=0x[0-9a-f]{40}: (\d+ → \d+)/m),
      postVerdict: firstMatch(result.stdout, /postVerdict terkirim: (0x[0-9a-f]{64})/),
      finalize: firstMatch(result.stdout, /finalize terkirim: (0x[0-9a-f]{64})/),
    };
  });
}

/**
 * VARIAN B — vault Sepolia BEKU (root non-nol) + `memory.db` DIHAPUS → mode aman.
 *
 * URUTAN WAJIB (AC 3.3b, review 2.4a-fix): gerbang dibaca SEBELUM alat apa pun menyentuh
 * path DB. `MemoryClient.local(path)` MEMBUAT filenya, jadi menjalankan alat ekspor lebih
 * dulu mengubah keadaan `HILANG` menjadi `ada (kosong)` dan varian ini gugur DIAM-DIAM:
 * gerbang pertama mencetak `safe`, satu pembacaan melahirkan file, gerbang berikutnya
 * `normal`, dan transaksi ikut terbangun. Karena itu yang menyentuh path ini di sini hanya
 * `rmSync` + `existsSync` (keduanya tidak membuat apa pun), dan proses pertama yang
 * membukanya adalah agen — yang membaca gerbangnya sebelum memuat kunci privat.
 *
 * PEMICUNYA aturan (a) ADR-024 keputusan 2 (file HILANG), bukan aturan (b) yang sudah
 * DICABUT: itu diverifikasi dari alasan yang dicetak agen, bukan diasumsikan.
 *
 * NOL transaksi, jadi NOL dana: yang dikirim ke Base Sepolia hanya dua `eth_call` view dan
 * dua `eth_getTransactionCount`. Kalau varian ini pernah menuntut dana, ia salah dibangun.
 */
type VariantBResult = {
  readonly nonceBefore: number;
  readonly nonceAfter: number;
  readonly onchainRoot: string;
  readonly agentAddress: Address;
  readonly exit: number;
};

export async function runVariantB(): Promise<VariantBResult> {
  mkdirSync(VARIANT_B_ROOT, { recursive: true });
  for (const suffix of MEMORY_DB_SUFFIXES) rmSync(`${VARIANT_B_DB}${suffix}`, { force: true });
  const sisa = MEMORY_DB_SUFFIXES.map((suffix) => `${VARIANT_B_DB}${suffix}`).filter(existsSync);
  if (sisa.length > 0) {
    // Nama BERKASNYA, bukan sufiksnya: sufiks `""` mencetak string kosong dan pesan
    // "masih ada " yang tidak menyebut apa pun adalah pesan yang tidak bisa dipakai.
    throw new Error(`memori varian B tidak benar-benar terhapus: masih ada ${sisa.join(", ")}`);
  }
  log("varianB.memory.wiped", { db: VARIANT_B_DB, files: MEMORY_DB_SUFFIXES.length });

  const onchainRoot = await callView(SEPOLIA_RPC, FROZEN_VAULT, SELECTOR_LAST_MEMORY_ROOT as Hex);
  if (onchainRoot === ZERO_ROOT) {
    throw new Error(
      `lastMemoryRoot() vault ${FROZEN_VAULT} NOL — varian B menuntut vault yang sudah ` +
        "mengumumkan root; pada root nol yang benar adalah mode NAIF (varian A), bukan mode aman",
    );
  }
  const agentAddress = getAddress(
    `0x${(await callView(SEPOLIA_RPC, FROZEN_VAULT, SELECTOR_AGENT as Hex)).slice(-40)}`,
  );
  const nonceBefore = await nonceOf(SEPOLIA_RPC, agentAddress);
  log("varianB.begin", {
    rpc: SEPOLIA_RPC,
    vault: FROZEN_VAULT,
    jobId: FROZEN_JOB_ID,
    onchainRoot,
    agent: agentAddress,
    nonce: nonceBefore,
  });

  // Konfigurasi DITERUSKAN EKSPLISIT, sama seperti varian A: `.env` repo ini menunjuk
  // memori operasional yang MASIH ADA, dan mewarisinya berarti gerbang membaca DB yang
  // salah lalu melaporkan `normal` — kebalikan dari yang sedang dibuktikan.
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    RPC_URL: SEPOLIA_RPC,
    CHAIN_ID: String(CHAIN_ID),
    ACP_ADDRESS: SEPOLIA_ACP,
    VAULT_ADDRESS: FROZEN_VAULT,
    SIBYL_DB_PATH: VARIANT_B_DB,
    VERDICT_BUNDLE_DIR: join(VARIANT_B_ROOT, "verdicts"),
    DELIVERABLE_DIR: join(VARIANT_B_ROOT, "deliverables"),
  };
  const result = await run(
    "uv",
    ["run", "python", "-m", "agent.vault_client", "--job-id", String(FROZEN_JOB_ID), "--kind", "reject"],
    { cwd: AGENT_ROOT, env, echo: true },
  );
  const nonceAfter = await nonceOf(SEPOLIA_RPC, agentAddress);

  const gugur = (pesan: string): never => {
    throw new Error(`VARIAN B GUGUR: ${pesan}`);
  };
  // Mode aman adalah perilaku yang DIINGINKAN, jadi kode keluarnya 0 — bukan kegagalan.
  if (result.code !== 0) gugur(`agen keluar dengan kode ${result.code}, seharusnya 0`);
  if (!/MODE AMAN:/.test(result.stdout)) gugur("agen tidak mencetak baris MODE AMAN");
  if (!/gerbang memori: mode=safe\b/.test(result.stdout)) gugur("gerbang tidak melaporkan mode=safe");
  if (!/memori lokal hilang .* → memori dihapus/.test(result.stdout)) {
    gugur("mode aman tidak dipicu aturan (a) 'file hilang' — ADR-024 keputusan 2 cabang 2");
  }
  if (/(postVerdict|finalize|setProviderCap) terkirim/.test(result.stdout)) {
    gugur("ada transaksi yang terkirim");
  }
  if (nonceAfter !== nonceBefore) gugur(`nonce agen berubah ${nonceBefore} -> ${nonceAfter}`);

  return { nonceBefore, nonceAfter, onchainRoot, agentAddress, exit: result.code };
}

type StepRow = {
  readonly id: string;
  readonly note: string;
  readonly jobId: string;
  readonly budgetRaw: string;
  readonly deliverableSha: string;
  readonly jobStatus: string;
  readonly outcome: AgentOutcome;
};

async function main(): Promise<void> {
  const deployer = wallet("deployer");

  log("start", { rpc: RPC_URL, chainId: CHAIN_ID, workdir: WORK_ROOT });

  // Ruang kerja BERSIH tiap kali — kalau tidak, "dari nol" jadi bohong dan dua eksekusi
  // berturut-turut tidak mungkin identik.
  rmSync(WORK_ROOT, { recursive: true, force: true });
  for (const dir of [WORK_ROOT, VERDICT_DIR, DELIVERABLE_DIR, LOG_DIR]) mkdirSync(dir, { recursive: true });

  await startAnvil();
  log("anvil.up", { rpc: RPC_URL, blockTime: 1 });

  const usdc = await forgeCreate("test/mocks/MockUSDC.sol:MockUSDC", [], deployer);
  const acp = await forgeCreate(
    "test/mocks/AgenticCommerce.sol:AgenticCommerce",
    [usdc, TREASURY],
    deployer,
  );
  const vault = await forgeCreate(
    "src/EvaluatorVault.sol:EvaluatorVault",
    [acp, wallet("agent").address, wallet("arbiter").address, "0"],
    deployer,
  );
  const deployment: Deployment = { usdc, acp, vault };
  const env = baseEnv(deployment, vault);

  // --- §7 langkah 1-3: tiga job dari satu provider ------------------------------------
  await runTs("mint_min.ts", [], { ...env, MINT_RAW });
  const scenario = await runTs("scenario.ts", ["--scenario", "alpha-x3"], env);

  const steps = ["A", "B", "C"].map((id) => {
    const stepLine = scenario.stdout
      .split("\n")
      .find((l) => parseLogLine(l, "scenario", "step")?.step === id);
    const onchainLine = scenario.stdout
      .split("\n")
      .find((l) => parseLogLine(l, "scenario", "onchain")?.step === id);
    const step = stepLine ? parseLogLine(stepLine, "scenario", "step") : null;
    const onchain = onchainLine ? parseLogLine(onchainLine, "scenario", "onchain") : null;
    if (!step || !onchain) throw new Error(`baris skenario untuk langkah ${id} tidak ditemukan`);
    return { id, step, onchain };
  });

  const rows: StepRow[] = [];
  const notes: Record<string, string> = {
    A: "§7 langkah 1 — cek deterministik gagal → REJECT, insiden 1",
    B: "§7 langkah 2 — insiden 2 → cap turun",
    C: "§7 langkah 3 — budget melebihi cap → gerbang menolak saat Funded",
  };
  for (const { id, step, onchain } of steps) {
    const jobId = Number(onchain.jobId);
    log("agent.begin", { step: id, jobId, kind: "reject", note: `"${notes[id]}"` });
    const outcome = await runAgent(jobId, "reject", env);
    rows.push({
      id,
      note: notes[id] as string,
      jobId: String(jobId),
      budgetRaw: step.budgetRaw as string,
      deliverableSha: step.deliverableSha as string,
      jobStatus: step.status as string,
      outcome,
    });
  }

  // --- §7 langkah 4 / VARIAN A: root on-chain DI-RESET + memori dihapus ---------------
  // Vault BARU, bukan reset in-place: `lastMemoryRoot` sebuah kontrak tidak bisa diputar
  // balik, dan memalsukannya justru merusak klaimnya. Vault segar = root nol = keadaan hari
  // pertama, yaitu satu-satunya keadaan di mana ADR-024 keputusan 2 cabang (2) mengizinkan
  // agen tetap bekerja tanpa memori.
  //
  // DUA job, dan itu inti amandemen 3.3b: job D membawa cacat HALUS (bagian ke-3, di luar
  // jendela `sampling`) dan LOLOS; job E membawa cacat KASAR (bagian pertama) dan TETAP
  // DITOLAK. Menjalankan D saja berarti mementaskan varian yang dijamin menang.
  const agentAddress = wallet("agent").address;
  const nonceLocalBefore = await nonceOf(RPC_URL, agentAddress);
  log("varianA.begin", {
    agent: agentAddress,
    nonce: nonceLocalBefore,
    note: '"VARIAN A — vault segar (root nol) + memori dihapus"',
  });
  const vault2 = await forgeCreate(
    "src/EvaluatorVault.sol:EvaluatorVault",
    [acp, wallet("agent").address, wallet("arbiter").address, "0"],
    deployer,
  );
  for (const suffix of MEMORY_DB_SUFFIXES) rmSync(`${DB_PATH}${suffix}`, { force: true });
  log("varianA.memory.wiped", { db: DB_PATH, files: MEMORY_DB_SUFFIXES.length, vault: vault2 });

  const env4 = baseEnv(deployment, vault2);
  // Job D BERJALAN SAMPAI `submit`, tidak berhenti di `fund` seperti job C. Sebabnya bukan
  // gaya: pada memori kosong gerbang MELOLOSKAN budget 2 USDC, dan agen yang gerbangnya lolos
  // tetapi providernya belum submit apa pun memang menolak mengumumkan apa pun (nol tx, exit 4)
  // — tidak ada hasil cek maupun penolakan cap yang bisa di-hash jadi `reasonHash`. Supaya
  // langkah 4 punya verdict, job ini harus benar-benar menyerahkan deliverable.
  const job4 = await runTs("client_min.ts", [], {
    ...env4,
    PROVIDER_SLOT: "alpha",
    BUDGET_RAW: STEP4_BUDGET_RAW,
    STOP_AFTER: "submit",
    DELIVERABLE_FILE: STEP4_DELIVERABLE_FILE,
  });
  const summary4 = job4.stdout
    .split("\n")
    .map((l) => parseLogLine(l, "client_min", "summary"))
    .find((f) => f !== null);
  if (!summary4) throw new Error("baris summary client_min untuk langkah 4 tidak ditemukan");
  const jobId4 = Number(summary4.jobId);
  // `--kind complete` di sini adalah PERMINTAAN, bukan jaminan: `required_verdict_kind` tetap
  // memaksa REJECT bila cek deterministik gagal atau gerbang cap menolak. Kalau langkah 4
  // berakhir `complete`, itu karena bukti agen sendiri mengizinkannya.
  const outcome4 = await runAgent(jobId4, "complete", env4);
  const deliverableSha4 =
    job4.stdout.match(/sha_keccak=(0x[0-9a-f]{64})/)?.[1] ?? "-";
  rows.push({
    id: "D",
    note: "VARIAN A — memori dihapus, root nol: budget yang sama LOLOS gerbang, cacat HALUS lolos",
    jobId: String(jobId4),
    budgetRaw: STEP4_BUDGET_RAW,
    deliverableSha: deliverableSha4,
    jobStatus: summary4.status as string,
    outcome: outcome4,
  });

  // --- VARIAN A, job E: cacat KASAR pada keadaan yang SAMA -----------------------------
  // Vault KETIGA + memori dihapus lagi, supaya job E dinilai pada keadaan yang identik
  // dengan job D. Tanpa vault ketiga, `postVerdict` job D sudah membuat `lastMemoryRoot`
  // vault kedua NON-NOL, dan menghapus memori di atasnya justru memicu MODE AMAN — yaitu
  // varian B, bukan varian A.
  const vault3 = await forgeCreate(
    "src/EvaluatorVault.sol:EvaluatorVault",
    [acp, wallet("agent").address, wallet("arbiter").address, "0"],
    deployer,
  );
  for (const suffix of MEMORY_DB_SUFFIXES) rmSync(`${DB_PATH}${suffix}`, { force: true });
  log("varianA.memory.wiped", { db: DB_PATH, files: MEMORY_DB_SUFFIXES.length, vault: vault3 });

  const env5 = baseEnv(deployment, vault3);
  const job5 = await runTs("client_min.ts", [], {
    ...env5,
    PROVIDER_SLOT: "alpha",
    BUDGET_RAW: STEP4_BUDGET_RAW,
    STOP_AFTER: "submit",
    DELIVERABLE_FILE: VARIANT_A_COARSE_FILE,
  });
  const summary5 = job5.stdout
    .split("\n")
    .map((l) => parseLogLine(l, "client_min", "summary"))
    .find((f) => f !== null);
  if (!summary5) throw new Error("baris summary client_min untuk job E tidak ditemukan");
  const jobId5 = Number(summary5.jobId);
  // `--kind complete` DIMINTA di sini juga — persis seperti job D. Kalau job E berakhir
  // REJECT, yang menolaknya adalah cek deterministik agen sendiri, bukan baris perintah.
  const outcome5 = await runAgent(jobId5, "complete", env5);
  rows.push({
    id: "E",
    note: "VARIAN A — keadaan SAMA dengan D, cacat KASAR di bagian pertama: TETAP DITOLAK",
    jobId: String(jobId5),
    budgetRaw: STEP4_BUDGET_RAW,
    deliverableSha: job5.stdout.match(/sha_keccak=(0x[0-9a-f]{64})/)?.[1] ?? "-",
    jobStatus: summary5.status as string,
    outcome: outcome5,
  });
  const nonceLocalAfter = await nonceOf(RPC_URL, agentAddress);

  // --- VARIAN B ------------------------------------------------------------------------
  const varianB = await runVariantB();

  // --- Ringkasan ----------------------------------------------------------------------
  // BLOK DETERMINISTIK. Rantai lahir dari nol tiap kali, jadi alamat kontrak dan jobId ikut
  // di sini; hanya hash tx dan nomor blok yang tidak bisa diulang.
  log("addr", { usdc, acp, vault, vaultD: vault2, vaultE: vault3, treasury: TREASURY });
  log("wallet", {
    client: wallet("client").address,
    provider: wallet("provider").address,
    agent: wallet("agent").address,
    arbiter: wallet("arbiter").address,
  });
  for (const row of rows) {
    log("step", {
      step: row.id,
      jobId: row.jobId,
      budgetRaw: row.budgetRaw,
      jobStatus: row.jobStatus,
      deliverableSha: row.deliverableSha,
      mode: row.outcome.plan.mode ?? "?",
      depth: row.outcome.plan.depth ?? "?",
      cap: row.outcome.plan.cap ?? "?",
      gate: `"${row.outcome.plan.gate ?? "?"}"`,
      evaluasi: `"${row.outcome.plan.evaluasi ?? "?"}"`,
      capSet: `"${row.outcome.cap}"`,
      memoryRoot: row.outcome.memoryRoot,
      reasonHash: row.outcome.reasonHash,
      agentExit: row.outcome.exit,
      agentRetried: row.outcome.retried,
      note: `"${row.note}"`,
    });
  }
  log("claim", {
    step: "C-vs-D",
    budgetRaw: STEP4_BUDGET_RAW,
    gateWithMemory: `"${rows[2]?.outcome.plan.gate ?? "?"}"`,
    gateWithoutMemory: `"${rows[3]?.outcome.plan.gate ?? "?"}"`,
    note: '"budget IDENTIK, yang berbeda hanya memori — itulah capnya"',
  });
  log("claim", {
    step: "D-vs-E",
    depth: `"${rows[3]?.outcome.plan.depth ?? "?"}"`,
    halus: `"${rows[3]?.outcome.plan.evaluasi ?? "?"}"`,
    kasar: `"${rows[4]?.outcome.plan.evaluasi ?? "?"}"`,
    note: '"memori dihapus menurunkan KEDALAMAN, tidak mematikan evaluator"',
  });

  // --- DUA VARIAN DESTRUKTIF -----------------------------------------------------------
  // Kedua baris di bawah adalah klimaks naskah dan dicetak APA ADANYA. Jumlah transaksinya
  // BERBEDA, dan keduanya diukur dari nonce wallet agen — bukan dari kalimat.
  log("varianA", {
    vaultD: vault2,
    vaultE: vault3,
    onchainRoot: "0x0 (vault segar)",
    depth: rows[3]?.outcome.plan.depth ?? "?",
    cap: `"${rows[3]?.outcome.plan.cap ?? "?"}"`,
    txBaru: nonceLocalAfter - nonceLocalBefore,
    nonce: `${nonceLocalBefore} -> ${nonceLocalAfter}`,
  });
  console.log(
    `VARIAN A: ROOT ONCHAIN DIRESET, cap hilang (${rows[3]?.outcome.plan.cap ?? "?"}), ` +
      `mode ${rows[3]?.outcome.plan.depth ?? "?"}, ` +
      `cacat halus LOLOS (job ${rows[3]?.jobId ?? "?"}: ${rows[3]?.outcome.plan.evaluasi ?? "?"}), ` +
      `cacat kasar DITOLAK (job ${rows[4]?.jobId ?? "?"}: ${rows[4]?.outcome.plan.evaluasi ?? "?"}), ` +
      `${nonceLocalAfter - nonceLocalBefore} tx baru, nonce ${nonceLocalBefore} -> ${nonceLocalAfter}`,
  );
  log("varianB", {
    vault: FROZEN_VAULT,
    rpc: SEPOLIA_RPC,
    jobId: FROZEN_JOB_ID,
    onchainRoot: varianB.onchainRoot,
    agent: varianB.agentAddress,
    agentExit: varianB.exit,
    txBaru: varianB.nonceAfter - varianB.nonceBefore,
    aturan: '"(a) memori lokal HILANG (ADR-024 kep. 2 cabang 2), bukan (b)"',
  });
  console.log(
    `VARIAN B: MODE AMAN, 0 tx baru, nonce ${varianB.nonceBefore} -> ${varianB.nonceAfter}, ` +
      "job menggantung sampai expiredAt, pulih dengan memory.db dari backup",
  );

  // Baris yang MEMANG berbeda tiap eksekusi.
  for (const row of rows) {
    log("onchain", {
      step: row.id,
      jobId: row.jobId,
      postVerdict: row.outcome.postVerdict,
      finalize: row.outcome.finalize,
    });
  }
  log("done", { steps: rows.length, workdir: WORK_ROOT });
}

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    stopAnvil();
    process.exit(130);
  });
}

/**
 * Dijalankan HANYA saat berkas ini adalah entrypoint.
 *
 * Tanpa penjaga ini, `import` apa pun atas modul ini — termasuk oleh tes yang hanya ingin
 * memakai `parseLogLine`/`runVariantB` — menyalakan Anvil dan menjalankan seluruh naskah
 * sebagai efek samping.
 */
const isEntrypoint =
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(process.argv[1]).href;

if (isEntrypoint) {
  main()
    .then(() => stopAnvil())
    .catch((err: unknown) => {
      stopAnvil();
      const message = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
      console.error(`[demo] GAGAL ${message}`);
      process.exitCode = 1;
    });
}
