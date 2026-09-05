/**
 * sim/src/client_min.ts — satu putaran alur ACP minimal di Base Sepolia (task 1.3c).
 *
 * createJob (CLIENT) -> setBudget (PROVIDER) -> fund (CLIENT) -> submit (PROVIDER)
 *
 * SATU putaran = SATU job. Rantai A/B/C spec §7 langkah 1-3 dijalankan dengan MEMANGGIL file ini
 * tiga kali, bukan dengan menambah alur baru di sini; yang berbeda antar panggilan hanya tiga
 * variabel lingkungan (lihat "Tombol skenario" di bawah): `DELIVERABLE_TEXT`, `BUDGET_RAW`,
 * `STOP_AFTER`. Urutan panggilan ACP dan pemegang tanda tangan tiap langkah TIDAK berubah.
 *
 * SEMUA transaksi lewat SDK `@virtuals-protocol/acp-node-v2@0.1.12`. File ini TIDAK
 * meng-encode satu pun calldata ACP sendiri: kalender panggilan, ABI, dan urutan approve+fund
 * datang dari SDK. Yang kita sediakan hanya adapter penanda tangan (viem) yang diminta
 * antarmuka `IEvmProviderAdapter`.
 *
 * TIGA EOA, dipaksa kontrak — bukan gaya (ADR-017 poin 3, docs/api-facts.md §A):
 *   - CLIENT   : pemegang token escrow; menandatangani createJob + fund.
 *   - PROVIDER : ETH saja; menandatangani setBudget + submit (keduanya provider-only).
 *   - EVALUATOR: alamat EvaluatorVault (kontrak, bukan EOA).
 * `createJob` merevert `ClientIsProvider()` 0x332ff0f9 bila msg.sender == provider, dan
 * `EvaluatorIsProvider()` 0xc7b4e9eb bila evaluator == provider.
 *
 * `evaluatorAddress` WAJIB diisi eksplisit. Default SDK = alamat nol = "skip evaluation":
 * `submit` akan LANGSUNG menyelesaikan job dan membayar provider tanpa wasit
 * (docs/api-facts.md §A), yang menghapus seluruh alasan proyek ini ada.
 *
 * Di luar lingkup task ini: watcher/polling event, memori Sibyl, postVerdict/finalize,
 * multi-provider, hook, x402.
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  AcpAgent,
  AssetToken,
  JobSession,
  ViemProviderAdapter,
  type AcpJobApi,
  type AcpAgentDetail,
  type OffChainJob,
} from "@virtuals-protocol/acp-node-v2";
import {
  createPublicClient,
  createWalletClient,
  http,
  keccak256,
  toHex,
  type Address,
  type Call,
  type Hex,
  type Log,
  type TransactionReceipt,
} from "viem";
import { privateKeyToAccount, type PrivateKeyAccount } from "viem/accounts";
import { baseSepolia } from "viem/chains";

// ---------------------------------------------------------------------------
// Konstanta jaringan — docs/versions.md "Jaringan & alamat"
// ---------------------------------------------------------------------------

const CHAIN = baseSepolia;
const CHAIN_ID = baseSepolia.id; // 84532
const DEFAULT_RPC_URL = "https://sepolia.base.org";

/** Proxy AgenticCommerceV3 Base Sepolia. */
const ACP_ADDRESS = "0x0b93793923CD5De81850aF8604a233f3f24d461e" as Address;

/** EvaluatorVault kita — dipakai sebagai `evaluatorAddress`, WAJIB, bukan alamat nol. */
const VAULT_ADDRESS = "0x5c6EE4586ACABcb6326069c229E58091B21ef384" as Address;

/**
 * Token yang benar-benar ditarik escrow ACP = `paymentToken()`.
 * BUKAN USDC Circle (0x036CbD…): kedua token menjawab `symbol()` = "USDC", jadi satu-satunya
 * pembeda yang mengikat adalah ALAMAT. Nilai ini hanya dipakai sebagai ASERSI terhadap alamat
 * yang dipilih `AssetToken.usdc*` untuk chainId 84532 — kalau SDK memilih token lain, `fund`
 * akan menarik token yang salah dan kita berhenti sebelum mengirim transaksi apa pun.
 */
const ESCROW_TOKEN_ADDRESS = "0xECc22a8F6fD62388498fBa19813E214605a2BDb3" as Address;

/** Alamat wallet agen/evaluator. Ia TIDAK boleh muncul sebagai client maupun provider. */
const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000" as Address;

// ---------------------------------------------------------------------------
// Tombol skenario (spec §7 langkah 1-3)
//
// Ketiganya dibaca dari `process.env` SAJA — sengaja TIDAK lewat configValue()/.env root.
// Nilainya berganti tiap job dalam satu rantai A/B/C, jadi nilai yang mengendap di `.env`
// akan diam-diam ikut ke job berikutnya: `STOP_AFTER=fund` yang tertinggal membuat job A/B
// tidak pernah `submit`, dan `BUDGET_RAW` yang tertinggal membuat job A/B melebihi cap.
// Rahasia tetap dari `.env` (kunci privat, RPC); tombol skenario diberikan per-perintah.
// ---------------------------------------------------------------------------

const BUDGET_RAW_ENV = "BUDGET_RAW";
const STOP_AFTER_ENV = "STOP_AFTER";
const DELIVERABLE_TEXT_ENV = "DELIVERABLE_TEXT";

/**
 * Budget default 1 USDC (6 desimal) — nilai yang dipakai job 1.3c/1.3d, dipertahankan supaya
 * pemanggil lama tidak berubah perilaku. Job C rantai 2.5 melebihi cap dengan `BUDGET_RAW=2000000`.
 */
const DEFAULT_BUDGET_RAW = 1_000_000n;

/** Unit MENTAH token escrow (6 desimal): "2000000" = 2 USDC. Bukan angka desimal berkoma. */
export function parseBudgetRaw(raw: string | undefined): bigint {
  const text = (raw ?? "").trim();
  if (!text) return DEFAULT_BUDGET_RAW;
  if (!/^[0-9][0-9_]*$/.test(text)) {
    throw new Error(
      `${BUDGET_RAW_ENV}="${text}" bukan bilangan bulat unit mentah token (6 desimal, mis. 2000000 = 2 USDC)`,
    );
  }
  const value = BigInt(text.split("_").join(""));
  if (value <= 0n) throw new Error(`${BUDGET_RAW_ENV} harus > 0, dapat "${text}"`);
  return value;
}

/**
 * Sampai langkah mana putaran ini berjalan.
 *
 * `submit` (default) = alur penuh 1.3c, job berakhir `Submitted`.
 * `fund` = BERHENTI sesudah `fund`, job SENGAJA ditinggal berstatus `Funded`. Itu yang dituntut
 * job C spec §7 langkah 3: agen harus menolaknya SAAT Funded, yaitu sebelum provider menyerahkan
 * apa pun (spec §5 langkah 2). Kalau `submit` sempat jalan, klaim intinya hilang.
 */
const STOP_AFTER_VALUES = ["fund", "submit"] as const;
type StopAfter = (typeof STOP_AFTER_VALUES)[number];

export function parseStopAfter(raw: string | undefined): StopAfter {
  const text = (raw ?? "").trim().toLowerCase();
  if (!text) return "submit";
  const match = STOP_AFTER_VALUES.find((value) => value === text);
  if (!match) {
    throw new Error(`${STOP_AFTER_ENV}="${text}" tidak dikenal; pilih ${STOP_AFTER_VALUES.join(" atau ")}`);
  }
  return match;
}

/**
 * `expiredAt` = now + 1 jam.
 *
 * Batas BAWAH: kontrak menolak `expiredAt <= now + 300` dengan `ExpiryTooShort()` 0xf7a0748c.
 * Batas ATAS praktis: sesudah `expiredAt` + `EVALUATOR_GRACE_PERIOD` (900 detik) SIAPA PUN boleh
 * `claimRefund` job berstatus Submitted dan menggugurkan verdict evaluator, sementara vault masih
 * harus menunggu CHALLENGE_WINDOW 120 detik sebelum `finalize`. Satu jam memberi anggaran jauh di
 * atas ~387 detik yang dibutuhkan jalur deteksi→LLM→postVerdict→challenge→finalize, tanpa membuat
 * demo menunggu lama (ADR-014).
 */
const EXPIRY_SECONDS = 3600;

const JOB_DESCRIPTION =
  "the-evaluator smoke job: provider menyerahkan satu deliverable, EvaluatorVault yang menilai.";

/**
 * Teks deliverable yang benar-benar diserahkan.
 *
 * ADR-019 keputusan 1: yang dikirim on-chain adalah `keccak256` dari byte UTF-8 teks INI
 * (SDK: `keccak256(toHex(deliverable))`), dan teks yang sama ditulis apa adanya ke
 * `demo/deliverables/<jobId>.json` supaya `agent/` punya preimage untuk diverifikasi ulang.
 * Salinan off-chain resmi Virtuals TIDAK tersedia bagi wallet simulator kita
 * (`postDeliverable` → 404 "Agent not found"), jadi file itulah satu-satunya sumber teks.
 *
 * Isinya bisa diganti lewat env `DELIVERABLE_TEXT` (skenario provider jujur / angka salah /
 * setengah jadi pada spec §7) tanpa mengubah kode.
 */
const DEFAULT_DELIVERABLE_TEXT = [
  "# Summary",
  "Laporan token escrow ACP di Base Sepolia untuk satu putaran alur minimal.",
  "",
  "## Supply",
  "- Decimals: 6",
  "",
  "## Sources",
  "- https://sepolia.basescan.org/address/0xECc22a8F6fD62388498fBa19813E214605a2BDb3",
  "",
].join("\n");

/**
 * Teks deliverable. `DELIVERABLE_TEXT` yang DISETEL tapi kosong ditolak: `DELIVERABLE_TEXT=$VAR`
 * dengan `VAR` yang salah ketik akan menyerahkan string kosong dan meng-hash keccak256("") ke
 * on-chain — job "berhasil" dengan deliverable yang tidak pernah ada. Hapus variabelnya bila
 * memang menginginkan teks default.
 */
export function parseDeliverableText(raw: string | undefined): { text: string; source: "env" | "default" } {
  if (raw === undefined) return { text: DEFAULT_DELIVERABLE_TEXT, source: "default" };
  if (!raw.trim()) throw new Error(`${DELIVERABLE_TEXT_ENV} disetel tapi kosong/spasi saja`);
  return { text: raw, source: "env" };
}

/** Nama direktori artefak deliverable (ADR-019 keputusan 2: `DELIVERABLE_DIR`). */
const DELIVERABLE_DIR_PARTS = ["demo", "deliverables"] as const;

/** Batas percobaan baca ulang state setelah sebuah transaksi ter-mining. */
const READ_RETRIES = 12;
const READ_DELAY_MS = 2_000;
/** Batas percobaan simulasi (`eth_call`) sebelum sebuah revert dianggap nyata, bukan lag node. */
const SIMULATE_RETRIES = 8;

// ---------------------------------------------------------------------------
// Rahasia: environment dulu, lalu parser .env kecil buatan sendiri
// (pola yang sama dengan agent/vault_client.py — tanpa dependensi dotenv).
// Nilainya TIDAK PERNAH dicetak, di-log, atau masuk pesan error: lihat scrub().
// ---------------------------------------------------------------------------

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

export function parseEnvFile(text: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const rawLine of text.split("\n")) {
    let line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("export ")) line = line.slice("export ".length).trim();
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    if (!key) continue;
    let value = line.slice(eq + 1).trim();
    // Komentar sebaris: `#` di awal nilai, atau `#` yang didahului spasi/tab.
    if (value.startsWith("#")) {
      value = "";
    } else {
      for (const marker of [" #", "\t#"]) {
        const idx = value.indexOf(marker);
        if (idx !== -1) value = value.slice(0, idx);
      }
    }
    value = value.trim();
    if (value.length >= 2 && value[0] === value[value.length - 1] && (value[0] === '"' || value[0] === "'")) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

let envFileCache: Record<string, string> | null = null;

function envFileValues(): Record<string, string> {
  if (envFileCache === null) {
    try {
      envFileCache = parseEnvFile(readFileSync(join(REPO_ROOT, ".env"), "utf8"));
    } catch {
      envFileCache = {};
    }
  }
  return envFileCache;
}

function configValue(name: string, fallback: string): string {
  const fromEnv = process.env[name];
  if (fromEnv && fromEnv.trim()) return fromEnv.trim();
  const fromFile = envFileValues()[name];
  return fromFile && fromFile.trim() ? fromFile.trim() : fallback;
}

const secrets: string[] = [];

function loadPrivateKey(name: string): Hex {
  let key = (process.env[name] ?? "").trim();
  if (!key) key = (envFileValues()[name] ?? "").trim();
  if (!key) throw new Error(`${name} kosong (environment maupun .env root) — tidak bisa menandatangani tx`);
  if (!key.startsWith("0x")) key = `0x${key}`;
  secrets.push(key, key.slice(2));
  return key as Hex;
}

/** Menyensor kunci privat bila entah bagaimana muncul di teks (pesan error, log). */
function scrub(text: string): string {
  let out = text;
  for (const secret of secrets) {
    if (secret.length >= 16) out = out.split(secret).join("<REDACTED>");
  }
  return out;
}

// ---------------------------------------------------------------------------
// Logging terstruktur sederhana (tanpa dependensi)
// ---------------------------------------------------------------------------

function log(event: string, fields: Record<string, unknown> = {}): void {
  const parts = Object.entries(fields).map(([k, v]) => `${k}=${String(v)}`);
  console.log(scrub([`[client_min] ${event}`, ...parts].join(" ")));
}

/**
 * Menulis `demo/deliverables/<jobId>.json` = `{jobId, text, sha_keccak}` (ADR-019 kep. 1).
 *
 * `sha_keccak` dihitung dengan fungsi yang SAMA yang dipakai SDK saat submit
 * (`keccak256(toHex(text))`, docs/api-facts.md §B.1), sehingga nilai on-chain dan nilai di
 * file dijamin berasal dari satu string. `agent/` tetap menghitungnya ULANG dan tetap
 * membandingkannya dengan slot on-chain — file ini tidak dipercaya, ia hanya mengusulkan
 * preimage.
 *
 * Mengembalikan path yang BENAR-BENAR ditulis, supaya ringkasan akhir tidak menyusun ulang path
 * yang sama di tempat kedua (dua sumber = dua kesempatan untuk berbeda).
 */
function writeDeliverableArtifact(jobId: bigint, text: string): { path: string; shaKeccak: Hex } {
  const id = jobId.toString();
  const dir = join(REPO_ROOT, ...DELIVERABLE_DIR_PARTS);
  mkdirSync(dir, { recursive: true });
  const shaKeccak = keccak256(toHex(text));
  const path = join(dir, `${id}.json`);
  // `jobId` ditulis sebagai STRING: JSON.stringify melempar untuk bigint, dan id job bisa
  // melewati 2^53 sehingga number bukan pilihan yang jujur.
  writeFileSync(path, JSON.stringify({ jobId: id, text, sha_keccak: shaKeccak }), "utf8");
  log("deliverable.artifact", {
    jobId: id,
    path,
    sha_keccak: shaKeccak,
    bytes: new TextEncoder().encode(text).length,
  });
  return { path, shaKeccak };
}

// ---------------------------------------------------------------------------
// Adapter penanda tangan untuk SDK: satu EOA lokal, satu RPC.
// SDK memanggil sendCalls(); kita mensimulasikan tiap panggilan lebih dulu supaya revert
// muncul sebagai selector mentah, bukan sebagai transaksi gagal yang membakar gas.
// ---------------------------------------------------------------------------

function makePublicClient(rpcUrl: string) {
  return createPublicClient({ chain: CHAIN, transport: http(rpcUrl) });
}

function makeWalletClient(account: PrivateKeyAccount, rpcUrl: string) {
  return createWalletClient({ account, chain: CHAIN, transport: http(rpcUrl) });
}

class LocalKeyEvmProvider extends ViemProviderAdapter {
  readonly account: PrivateKeyAccount;
  readonly sentTxHashes: Hex[] = [];
  // Tipe klien viem sengaja diturunkan dari factory di bawah: tipe generik
  // `PublicClient`/`WalletClient` tidak cocok dengan formatter khusus rantai Base.
  private readonly publicClient: ReturnType<typeof makePublicClient>;
  private readonly walletClient: ReturnType<typeof makeWalletClient>;

  constructor(providerName: string, privateKey: Hex, rpcUrl: string) {
    super(providerName);
    this.account = privateKeyToAccount(privateKey);
    this.publicClient = makePublicClient(rpcUrl);
    this.walletClient = makeWalletClient(this.account, rpcUrl);
  }

  private assertChain(chainId: number): void {
    if (chainId !== CHAIN_ID) throw new Error(`Adapter hanya melayani chainId ${CHAIN_ID}, diminta ${chainId}`);
  }

  override async getAddress(): Promise<Address> {
    return this.account.address;
  }

  override async getSupportedChainIds(): Promise<number[]> {
    return [CHAIN_ID];
  }

  override async sendTransaction(chainId: number, call: Call | Call[]): Promise<Address> {
    const hashes = await this.sendCalls(chainId, Array.isArray(call) ? call : [call]);
    const list = Array.isArray(hashes) ? hashes : [hashes];
    return list[list.length - 1] as Address;
  }

  private async simulateWithRetry(to: Address, data: Hex, value: bigint): Promise<void> {
    for (let attempt = 1; ; attempt += 1) {
      try {
        await this.publicClient.call({ account: this.account, to, data, value });
        return;
      } catch (err) {
        if (attempt >= SIMULATE_RETRIES) throw err;
        const message = err instanceof Error ? err.message.split("\n")[0] : String(err);
        log("simulate.retry", { to, attempt, reason: message });
        await sleep(READ_DELAY_MS);
      }
    }
  }

  override async sendCalls(chainId: number, calls: Call[]): Promise<Address[]> {
    this.assertChain(chainId);
    const hashes: Hex[] = [];
    // Berurutan, satu per satu, menunggu receipt: nonce EOA tidak boleh balapan dan
    // `fund` baru sah setelah `approve` benar-benar ter-mining.
    for (const call of calls) {
      const to = call.to as Address;
      const data = (call.data ?? "0x") as Hex;
      const value = (call.value ?? 0n) as bigint;
      // Simulasi dulu: revert kontrak keluar sebagai error dengan returndata mentah, tanpa
      // membakar gas. RPC publik melayani eth_call dari node yang bisa TERTINGGAL di belakang
      // receipt yang baru saja ia kembalikan (mis. allowance masih 0 sesaat setelah `approve`
      // ter-mining), jadi simulasi yang gagal diulang beberapa kali sebelum dianggap revert nyata.
      await this.simulateWithRetry(to, data, value);
      const hash = await this.walletClient.sendTransaction({
        account: this.account,
        chain: CHAIN,
        to,
        data,
        value,
      });
      const receipt = await this.publicClient.waitForTransactionReceipt({ hash });
      if (receipt.status !== "success") {
        throw new Error(`transaksi ${hash} ter-mining dengan status ${receipt.status}`);
      }
      this.sentTxHashes.push(hash);
      hashes.push(hash);
    }
    return hashes as Address[];
  }

  override async getTransactionReceipt(chainId: number, hash: Address): Promise<TransactionReceipt> {
    this.assertChain(chainId);
    return this.publicClient.getTransactionReceipt({ hash: hash as Hex });
  }

  override async readContract(chainId: number, params: { address: Address; abi: readonly unknown[]; functionName: string; args?: readonly unknown[] }): Promise<unknown> {
    this.assertChain(chainId);
    return this.publicClient.readContract({
      address: params.address,
      abi: params.abi as never,
      functionName: params.functionName,
      args: params.args as never,
    });
  }

  override async getLogs(chainId: number, params: { address: Address; events: readonly unknown[]; fromBlock: bigint; toBlock?: bigint | "latest" }): Promise<Log[]> {
    this.assertChain(chainId);
    return this.publicClient.getLogs({
      address: params.address,
      events: params.events as never,
      fromBlock: params.fromBlock,
      toBlock: params.toBlock ?? "latest",
    }) as Promise<Log[]>;
  }

  override async getBlockNumber(chainId: number): Promise<bigint> {
    this.assertChain(chainId);
    return this.publicClient.getBlockNumber();
  }

  override async signMessage(chainId: number, message: string): Promise<string> {
    this.assertChain(chainId);
    return this.account.signMessage({ message });
  }

  override async signTypedData(_chainId: number, _typedData: unknown): Promise<string> {
    throw new Error("signTypedData tidak dipakai alur 1.3c");
  }
}

// ---------------------------------------------------------------------------
// `AcpJobApi` yang membaca job dari CHAIN, bukan dari API off-chain Virtuals.
//
// Alasan (diverifikasi 2026-09-04): `AcpApiClient` mengautentikasi lewat POST /auth/agent, dan
// server menjawab 404 `Agent not found with wallet address <client>` untuk wallet yang belum
// terdaftar di Service Registry Virtuals — baik di api.acp.virtuals.io maupun api-dev. Karena
// `JobSession.setBudget/fund/submit` semuanya menuntut `_job` sudah terisi lewat `fetchJob()`,
// tanpa pengganti ini permukaan `session.*` di docs/api-facts.md §B TIDAK bisa dipakai sama
// sekali oleh wallet simulator. Yang dibaca tetap `getJob` milik SDK (EvmAcpClient), jadi
// alur tetap 100% lewat SDK.
// ---------------------------------------------------------------------------

const STATUS_NAMES = ["OPEN", "FUNDED", "SUBMITTED", "COMPLETED", "REJECTED", "EXPIRED"] as const;

class OnChainJobApi implements AcpJobApi {
  private agent: AcpAgent | null = null;

  attach(agent: AcpAgent): void {
    this.agent = agent;
  }

  async getActiveJobs(): Promise<{ chainId: number; onChainJobId: string }[]> {
    return [];
  }

  async getJob(chainId: number, jobId: string): Promise<OffChainJob | null> {
    if (!this.agent) throw new Error("OnChainJobApi belum di-attach ke AcpAgent");
    const job = await this.agent.getClient(chainId).getJob(chainId, BigInt(jobId));
    // `getJob` ACP TIDAK revert untuk id tak dikenal: ia mengembalikan struct nol. RPC publik
    // juga bisa melayani eth_call dari node yang tertinggal di belakang receipt yang baru saja
    // ia kembalikan, sehingga job yang BARU dibuat sesaat terlihat nol → perlakukan sebagai
    // "belum ada" dan biarkan pemanggil mencoba lagi.
    if (!job || job.client === ZERO_ADDRESS) return null;
    const statusName = STATUS_NAMES[Number(job.status)];
    if (!statusName) throw new Error(`status job tidak dikenal: ${String(job.status)}`);
    return {
      chainId,
      onChainJobId: jobId,
      jobStatus: statusName as OffChainJob["jobStatus"],
      clientAddress: job.client,
      providerAddress: job.provider,
      evaluatorAddress: job.evaluator,
      description: job.description,
      budget: job.budget.toString(),
      expiredAt: new Date(Number(job.expiredAt) * 1000).toISOString(),
      hookAddress: job.hook,
      deliverable: null,
      hookConfigs: null,
      clientSubscription: null,
    };
  }

  async postDeliverable(chainId: number, jobId: string, _deliverable: string): Promise<void> {
    // Salinan off-chain deliverable butuh wallet terdaftar di registry Virtuals (lihat catatan
    // di atas). Yang di-hash ke on-chain oleh SDK adalah string LOKAL, jadi `submit` tetap benar;
    // hanya salinan teks penuh di API Virtuals yang tidak ada.
    log("deliverable.offchain.skipped", { chainId, jobId, reason: "wallet-belum-terdaftar-di-registry" });
  }

  async browseAgents(): Promise<AcpAgentDetail[]> {
    throw new Error("browseAgents tidak dipakai alur 1.3c");
  }

  async getAgentByWalletAddress(): Promise<AcpAgentDetail | null> {
    throw new Error("getAgentByWalletAddress tidak dipakai alur 1.3c");
  }
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Satu-satunya fungsi ERC-20 yang dibaca skrip ini. Read-only; tidak ada `approve` buatan sendiri. */
const ERC20_BALANCE_OF_ABI = [
  {
    type: "function",
    name: "balanceOf",
    stateMutability: "view",
    inputs: [{ name: "account", type: "address" }],
    outputs: [{ name: "", type: "uint256" }],
  },
] as const;

/**
 * Memastikan CLIENT punya cukup token escrow untuk `BUDGET_RAW` SEBELUM `createJob`.
 *
 * Tanpa ini, kekurangan saldo baru muncul sebagai revert simulasi `approve`/`fund` — sesudah
 * `createJob` + `setBudget` membakar gas dan meninggalkan job yatim berstatus Open.
 *
 * Pembacaan DIULANG: `balanceOf` = 0 tepat sesudah `mint` yang sukses adalah kejadian TERUKUR di
 * RPC publik Base Sepolia (docs/api-facts.md §E.1 kasus 2), jadi nol sekali baca berarti "belum
 * terlihat", BUKAN "tidak ada". Skrip ini tidak mengasumsikan angka saldo tertentu — hanya
 * menuntut >= budget yang diminta, dan bila kurang ia berhenti tanpa mengirim transaksi apa pun.
 */
async function assertClientCanFund(
  reader: LocalKeyEvmProvider,
  token: Address,
  owner: Address,
  neededRaw: bigint,
): Promise<bigint> {
  let balance = 0n;
  for (let attempt = 1; attempt <= READ_RETRIES; attempt += 1) {
    balance = (await reader.readContract(CHAIN_ID, {
      address: token,
      abi: ERC20_BALANCE_OF_ABI,
      functionName: "balanceOf",
      args: [owner],
    })) as bigint;
    if (balance >= neededRaw) return balance;
    log("balance.retry", { attempt, token, owner, balanceRaw: balance, neededRaw });
    await sleep(READ_DELAY_MS);
  }
  throw new Error(
    `saldo token escrow CLIENT tidak cukup: ${owner} memegang ${balance} unit token ${token}, ` +
      `butuh ${neededRaw} (${BUDGET_RAW_ENV}). Top-up dulu lalu jalankan ulang — nol transaksi terkirim.`,
  );
}

/**
 * Baca ulang job sampai `predicate` terpenuhi.
 * RPC publik bisa menjawab dari node yang tertinggal di belakang receipt yang baru saja ia
 * kembalikan, jadi satu pembacaan sesudah transaksi tidak cukup.
 */
async function fetchJobUntil(
  session: JobSession,
  label: string,
  predicate: (job: NonNullable<JobSession["job"]>) => boolean,
): Promise<NonNullable<JobSession["job"]>> {
  let lastError = "";
  for (let attempt = 1; attempt <= READ_RETRIES; attempt += 1) {
    try {
      const job = await session.fetchJob();
      if (predicate(job)) return job;
      lastError = `state belum sesuai (status=${job.status} budget=${job.budget.rawAmount})`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    log("job.read.retry", { label, attempt, reason: lastError });
    await sleep(READ_DELAY_MS);
  }
  throw new Error(`gagal membaca job untuk ${label} setelah ${READ_RETRIES} percobaan: ${lastError}`);
}

async function makeAgent(name: string, privateKey: Hex, rpcUrl: string) {
  const provider = new LocalKeyEvmProvider(name, privateKey, rpcUrl);
  const api = new OnChainJobApi();
  const agent = await AcpAgent.create({
    contractAddresses: { [CHAIN_ID]: ACP_ADDRESS },
    evmProvider: provider,
    api,
  });
  api.attach(agent);
  return { agent, provider, address: provider.account.address };
}

/** Hash yang baru dikirim adapter sejak penanda `from`. */
function newHashes(provider: LocalKeyEvmProvider, from: number): Hex[] {
  return provider.sentTxHashes.slice(from);
}

// ---------------------------------------------------------------------------
// Alur utama
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  // Tombol skenario divalidasi PALING AWAL: salah ketik `STOP_AFTER`/`BUDGET_RAW` harus gagal
  // sebelum kunci dimuat, sebelum RPC disentuh, dan jauh sebelum transaksi pertama.
  const budgetRaw = parseBudgetRaw(process.env[BUDGET_RAW_ENV]);
  const stopAfter = parseStopAfter(process.env[STOP_AFTER_ENV]);
  const deliverable = parseDeliverableText(process.env[DELIVERABLE_TEXT_ENV]);

  const rpcUrl = configValue("RPC_URL", DEFAULT_RPC_URL);

  const client = await makeAgent("client-sim", loadPrivateKey("CLIENT_PRIVATE_KEY"), rpcUrl);
  const provider = await makeAgent("provider-sim", loadPrivateKey("PROVIDER_PRIVATE_KEY"), rpcUrl);

  // Tiga alamat berbeda. Kontrak yang memaksanya; cek ini hanya supaya kita gagal SEBELUM
  // membayar gas untuk revert yang sudah bisa diramalkan.
  if (client.address.toLowerCase() === provider.address.toLowerCase()) {
    throw new Error("CLIENT dan PROVIDER memakai alamat yang sama → createJob revert ClientIsProvider() 0x332ff0f9");
  }
  if (provider.address.toLowerCase() === VAULT_ADDRESS.toLowerCase()) {
    throw new Error("PROVIDER == evaluator → createJob revert EvaluatorIsProvider() 0xc7b4e9eb");
  }

  const budget = AssetToken.usdcFromRaw(budgetRaw, CHAIN_ID);
  if (budget.address.toLowerCase() !== ESCROW_TOKEN_ADDRESS.toLowerCase()) {
    throw new Error(
      `SDK memilih token ${budget.address} untuk chainId ${CHAIN_ID}, sedangkan escrow ACP menarik ` +
        `${ESCROW_TOKEN_ADDRESS}. fund() akan menarik token yang salah — dihentikan.`,
    );
  }

  const expiredAt = Math.floor(Date.now() / 1000) + EXPIRY_SECONDS;

  log("config", {
    chainId: CHAIN_ID,
    rpc: rpcUrl,
    acp: ACP_ADDRESS,
    clientAddress: client.address,
    providerAddress: provider.address,
    evaluatorAddress: VAULT_ADDRESS,
    escrowToken: budget.address,
    budgetRaw: budget.rawAmount,
    stopAfter,
    deliverableTextFrom: deliverable.source,
    deliverableTextBytes: new TextEncoder().encode(deliverable.text).length,
    expiredAt,
  });

  // 0) preflight saldo — sebelum satu wei gas pun terbakar.
  const clientBalance = await assertClientCanFund(client.provider, budget.address, client.address, budgetRaw);
  log("balance.ok", { token: budget.address, owner: client.address, balanceRaw: clientBalance, neededRaw: budgetRaw });

  // 1) createJob — ditandatangani CLIENT.
  const markCreate = client.provider.sentTxHashes.length;
  const jobId = await client.agent.createJob(CHAIN_ID, {
    providerAddress: provider.address,
    evaluatorAddress: VAULT_ADDRESS, // eksplisit: alamat nol = evaluasi DILEWATI
    expiredAt,
    description: JOB_DESCRIPTION,
  });
  const createHash = newHashes(client.provider, markCreate)[0];
  log("createJob.ok", { jobId, tx: createHash });

  const clientSession = new JobSession(client.agent, [client.address], jobId.toString(), CHAIN_ID, ["client"]);
  const providerSession = new JobSession(provider.agent, [provider.address], jobId.toString(), CHAIN_ID, ["provider"]);

  // 2) setBudget — provider-only.
  await fetchJobUntil(providerSession, "setBudget", (job) => job.providerAddress.toLowerCase() === provider.address.toLowerCase());
  const markBudget = provider.provider.sentTxHashes.length;
  await providerSession.setBudget(budget);
  const budgetHash = newHashes(provider.provider, markBudget)[0];
  log("setBudget.ok", { jobId, budgetRaw: budget.rawAmount, tx: budgetHash });

  // 3) fund — client-only; SDK mengirim approve ERC-20 lalu fund dalam satu urutan.
  await fetchJobUntil(clientSession, "fund", (job) => job.budget.rawAmount === budgetRaw);
  const markFund = client.provider.sentTxHashes.length;
  await clientSession.fund(budget);
  const fundHashes = newHashes(client.provider, markFund);
  const fundHash = fundHashes[fundHashes.length - 1];
  log("fund.ok", { jobId, approveTx: fundHashes.length > 1 ? fundHashes[0] : "-", tx: fundHash });

  // 4) submit — provider-only. Tanpa langkah ini job tidak pernah berstatus Submitted dan
  // `complete()` dari vault pasti revert `WrongStatus()`.
  //
  // `STOP_AFTER=fund` MELEWATI langkah ini dengan sengaja: job C harus ditemukan agen dalam
  // status `Funded`. Artefak deliverable juga tidak ditulis — belum ada deliverable on-chain
  // untuk dibandingkan, jadi file preimage untuk job ini akan jadi klaim tanpa lawan.
  const fundedJob = await fetchJobUntil(providerSession, "funded", (job) => job.status === "FUNDED");
  let submitHash: Hex | "-" = "-";
  let deliverablePath = "-";
  if (stopAfter === "submit") {
    const markSubmit = provider.provider.sentTxHashes.length;
    // Artefak DITULIS SEBELUM submit: `agent/` menolak menilai job yang teksnya tidak ada
    // (REFUSE, ADR-019 keputusan 2), jadi urutan ini yang membuat job bisa dievaluasi.
    deliverablePath = writeDeliverableArtifact(jobId, deliverable.text).path;
    await providerSession.submit(deliverable.text);
    submitHash = newHashes(provider.provider, markSubmit)[0] as Hex;
    log("submit.ok", { jobId, tx: submitHash });
  } else {
    log("submit.skipped", { jobId, reason: `${STOP_AFTER_ENV}=fund`, keepsStatus: "FUNDED" });
  }

  const finalJob =
    stopAfter === "submit"
      ? await fetchJobUntil(providerSession, "verifikasi", (job) => job.status === "SUBMITTED")
      : fundedJob;
  log("job.final", {
    jobId,
    status: finalJob.status,
    client: finalJob.clientAddress,
    provider: finalJob.providerAddress,
    evaluator: finalJob.evaluatorAddress,
  });

  // Baris yang dipanen runbook 2.5: satu baris, kunci=nilai, tanpa perhitungan lanjutan.
  log("summary", {
    jobId,
    status: finalJob.status,
    budgetRaw: finalJob.budget.rawAmount,
    escrowToken: finalJob.budget.address,
    providerAddress: finalJob.providerAddress,
    evaluatorAddress: finalJob.evaluatorAddress,
    deliverablePath,
    txCreateJob: createHash,
    txSetBudget: budgetHash,
    txFund: fundHash,
    txSubmit: submitHash,
  });
}

main().catch((err: unknown) => {
  const message = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
  console.error(scrub(`[client_min] GAGAL ${message}`));
  process.exitCode = 1;
});
