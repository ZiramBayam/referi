/**
 * sim/src/client_min.ts — satu putaran alur ACP minimal di Base Sepolia (task 1.3c).
 *
 * createJob (CLIENT) -> setBudget (PROVIDER) -> fund (CLIENT) -> submit (PROVIDER)
 *
 * SATU putaran = SATU job. Rantai A/B/C spec §7 langkah 1-3 dan pasangan D/E langkah 4 dijalankan
 * dengan MEMANGGIL file ini berulang kali, bukan dengan menambah alur baru di sini; yang berbeda
 * antar panggilan hanya variabel lingkungan (lihat "Tombol skenario" di bawah): `DELIVERABLE_TEXT`
 * atau `DELIVERABLE_FILE`, `BUDGET_RAW`, `STOP_AFTER`, `PROVIDER_SLOT`. Urutan panggilan ACP dan
 * pemegang tanda tangan tiap langkah TIDAK berubah.
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
import { dirname, isAbsolute, join } from "node:path";
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

/**
 * Alamat DEFAULT = Base Sepolia. TIGA di antaranya bisa ditimpa lewat env dengan nama yang SAMA
 * seperti di `.env.example` (`ACP_ADDRESS`, `VAULT_ADDRESS`, `AGENT_ADDRESS`), supaya rantai yang
 * sama bisa dijalankan di Anvil lokal terhadap mock ACP tanpa menyalin file ini. Yang KEEMPAT —
 * alamat token escrow — sengaja TIDAK punya env: ia dibaca dari `paymentToken()` kontrak ACP. Yang TIDAK ikut berubah: chainId. SDK memetakan chainId → keluarga rantai lewat
 * `ACP_CONTRACT_ADDRESSES` miliknya sendiri dan MELEMPAR `UnknownChainIdError` untuk id yang
 * tidak terdaftar (`dist/core/constants.js` `getChainFamily`, "Fails closed"), jadi node lokal
 * WAJIB dijalankan dengan `--chain-id 84532`. Alamat kontraknya sendiri memang boleh ditimpa:
 * `CreateAcpClientInput.contractAddresses` adalah parameter publik SDK (`dist/clientFactory.d.ts`).
 */

/** Proxy AgenticCommerceV3 Base Sepolia. */
const DEFAULT_ACP_ADDRESS = "0x0b93793923CD5De81850aF8604a233f3f24d461e" as Address;

/** EvaluatorVault kita — dipakai sebagai `evaluatorAddress`, WAJIB, bukan alamat nol. */
const DEFAULT_VAULT_ADDRESS = "0x5c6EE4586ACABcb6326069c229E58091B21ef384" as Address;

/**
 * Token yang benar-benar ditarik escrow ACP = `paymentToken()`.
 * BUKAN USDC Circle (0x036CbD…): kedua token menjawab `symbol()` = "USDC" DAN `decimals()` = 6,
 * jadi satu-satunya pembeda yang mengikat adalah ALAMAT — dan satu-satunya sumber alamat yang sah
 * adalah `paymentToken()` kontrak ACP itu sendiri. Konstanta di bawah TIDAK dipakai untuk memilih
 * token (skrip membacanya dari kontrak); ia dipakai sebagai ASERSI terhadap jawaban kontrak saat
 * kita memang berbicara dengan ACP Base Sepolia. SENGAJA tidak ada env `USDC_ADDRESS` di sini:
 * alamat token yang boleh menimpa jawaban kontrak adalah persis jenis nilai yang tidak boleh ada.
 */
const DEFAULT_ESCROW_TOKEN_ADDRESS = "0xECc22a8F6fD62388498fBa19813E214605a2BDb3" as Address;

/** Alamat wallet agen/evaluator. Ia TIDAK boleh muncul sebagai client maupun provider. */
const DEFAULT_AGENT_ADDRESS = "0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894" as Address;

/** Desimal token escrow ACP. Sama di Base Sepolia (docs/versions.md) dan di MockUSDC lokal. */
const ESCROW_TOKEN_DECIMALS = 6;

/** Satu-satunya view ACP yang dibaca skrip ini sendiri; sisanya lewat SDK. */
const ACP_PAYMENT_TOKEN_ABI = [
  {
    type: "function",
    name: "paymentToken",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "address" }],
  },
] as const;

const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000" as Address;

// ---------------------------------------------------------------------------
// Tombol skenario (spec §7 langkah 1-3)
//
// Semuanya dibaca dari `process.env` SAJA — sengaja TIDAK lewat configValue()/.env root.
// Nilainya berganti tiap job dalam satu rantai A/B/C, jadi nilai yang mengendap di `.env`
// akan diam-diam ikut ke job berikutnya: `STOP_AFTER=fund` yang tertinggal membuat job A/B
// tidak pernah `submit`, dan `BUDGET_RAW` yang tertinggal membuat job A/B melebihi cap.
// Rahasia tetap dari `.env` (kunci privat, RPC); tombol skenario diberikan per-perintah.
// ---------------------------------------------------------------------------

const BUDGET_RAW_ENV = "BUDGET_RAW";
const STOP_AFTER_ENV = "STOP_AFTER";
const DELIVERABLE_TEXT_ENV = "DELIVERABLE_TEXT";
const DELIVERABLE_FILE_ENV = "DELIVERABLE_FILE";
const PROVIDER_SLOT_ENV = "PROVIDER_SLOT";

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
 * PROVIDER mana yang menandatangani `setBudget` + `submit`.
 *
 * Dua slot, dua wallet TERPISAH, dan pemisahan itu bukan gaya: pasangan job D/E spec §7
 * langkah 4 menyerahkan teks deliverable yang SAMA PERSIS dari dua provider yang riwayat
 * memorinya berbeda, supaya satu-satunya variabel yang tersisa adalah KEDALAMAN cek yang
 * diturunkan agen dari memorinya sendiri. Kalau keduanya memakai satu wallet, riwayatnya
 * ikut sama dan klaim itu mustahil dibuktikan.
 *
 *   alpha = `PROVIDER_PRIVATE_KEY`  — provider ber-riwayat (2 insiden, risk 2 → `full`);
 *   beta  = `PROVIDER2_PRIVATE_KEY` — provider BERSIH tanpa riwayat (risk 0 → `sampling`).
 *
 * Nama VARIABEL yang dipilih, bukan nilainya: kunci tetap hanya hidup di `.env`.
 */
const PROVIDER_KEY_BY_SLOT = {
  alpha: "PROVIDER_PRIVATE_KEY",
  beta: "PROVIDER2_PRIVATE_KEY",
} as const;
type ProviderSlot = keyof typeof PROVIDER_KEY_BY_SLOT;

export function parseProviderSlot(raw: string | undefined): ProviderSlot {
  const text = (raw ?? "").trim().toLowerCase();
  if (!text) return "alpha";
  const match = (Object.keys(PROVIDER_KEY_BY_SLOT) as ProviderSlot[]).find((slot) => slot === text);
  if (!match) {
    throw new Error(
      `${PROVIDER_SLOT_ENV}="${text}" tidak dikenal; pilih ${Object.keys(PROVIDER_KEY_BY_SLOT).join(" atau ")}`,
    );
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
 * Keccak JSON terms kanonik dari `agent.escrow_firewall`. ACP tidak punya field termsHash,
 * tetapi `description` bersifat immutable sesudah `createJob`, sehingga suffix ini adalah
 * komitmen pre-funding yang kompatibel dengan ACP yang sudah deployed.
 */
const TERMS_COMMITMENT_ENV = "TERMS_COMMITMENT";
const TERMS_COMMITMENT_PREFIX = "\n\n[escrow-firewall-terms:";
const TERMS_COMMITMENT_SUFFIX = "]";

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
 * setengah jadi pada spec §7) tanpa mengubah kode, atau lewat `DELIVERABLE_FILE` yang membaca
 * teksnya dari satu BERKAS. Berkas dipakai untuk pasangan job D/E: dua putaran yang WAJIB
 * menyerahkan byte yang identik tidak boleh bergantung pada pengutipan shell yang diketik dua kali.
 * Berkas skenario kedalaman ada di `sim/scenarios/depth-demo.md`; `agent/tests/test_criteria.py`
 * membaca berkas YANG SAMA, jadi properti "lolos saat sampling, ditolak saat full" terikat tes.
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
export function parseDeliverableText(
  raw: string | undefined,
  file: string | undefined = undefined,
  readText: (path: string) => string = (path) => readFileSync(path, "utf8"),
): { text: string; source: "env" | "file" | "default" } {
  const path = (file ?? "").trim();
  if (path) {
    // DUA sumber teks = dua kesempatan untuk berbeda. Job D dan job E hanya bisa membuktikan
    // "teks SAMA, verdict BERLAWANAN" bila keduanya membaca berkas yang sama, jadi kombinasi
    // yang ambigu ditolak alih-alih dimenangkan salah satu diam-diam.
    if (raw !== undefined) {
      throw new Error(
        `${DELIVERABLE_TEXT_ENV} dan ${DELIVERABLE_FILE_ENV} disetel bersamaan — pilih satu sumber teks`,
      );
    }
    const text = readText(isAbsolute(path) ? path : join(REPO_ROOT, path));
    if (!text.trim()) throw new Error(`${DELIVERABLE_FILE_ENV}="${path}" kosong/spasi saja`);
    return { text, source: "file" };
  }
  if (raw === undefined) return { text: DEFAULT_DELIVERABLE_TEXT, source: "default" };
  if (!raw.trim()) throw new Error(`${DELIVERABLE_TEXT_ENV} disetel tapi kosong/spasi saja`);
  return { text: raw, source: "env" };
}

/**
 * Direktori artefak deliverable, default `demo/deliverables` relatif AKAR REPO.
 *
 * Ditimpa lewat `DELIVERABLE_DIR` — nama, default, dan penjangkaran-ke-akar-repo yang SAMA
 * dengan yang dibaca `agent/` (ADR-019 keputusan 2, `vault_client.configured_deliverable_dir`).
 * Penulis dan pembaca artefak yang sama WAJIB memakai satu variabel: kalau hanya pembacanya
 * yang bisa dipindah, `make demo` yang menulis ke direktori kerja sendiri akan membuat agen
 * menolak menilai job (REFUSE) karena teksnya "tidak ada".
 */
const DELIVERABLE_DIR_ENV = "DELIVERABLE_DIR";
const DEFAULT_DELIVERABLE_DIR = "demo/deliverables";

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

function termsCommitmentConfig(): Hex | null {
  const value = configValue(TERMS_COMMITMENT_ENV, "");
  if (!value) return null;
  if (!/^0x[0-9a-fA-F]{64}$/.test(value)) {
    throw new Error(`${TERMS_COMMITMENT_ENV} harus keccak256 32-byte (0x + 64 hex)`);
  }
  return value as Hex;
}

function committedDescription(description: string, commitment: Hex | null): string {
  return commitment === null
    ? description
    : `${description}${TERMS_COMMITMENT_PREFIX}${commitment}${TERMS_COMMITMENT_SUFFIX}`;
}

/**
 * Alamat dari env/.env dengan default Base Sepolia.
 *
 * Divalidasi bentuknya di sini, bukan nanti: alamat salah ketik yang lolos sampai `createJob`
 * akan muncul sebagai revert tanpa nama atau — lebih buruk — sebagai job yang dibuat terhadap
 * kontrak yang salah. Tidak ada checksum EIP-55 yang dituntut (mock lokal sering ditulis huruf
 * kecil apa adanya oleh `forge create`), hanya `0x` + 40 digit hex.
 */
function addressConfig(name: string, fallback: Address): Address {
  const raw = configValue(name, fallback);
  if (!/^0x[0-9a-fA-F]{40}$/.test(raw)) {
    throw new Error(`${name}="${raw}" bukan alamat EVM (0x + 40 digit hex)`);
  }
  return raw as Address;
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
  const configured = configValue(DELIVERABLE_DIR_ENV, DEFAULT_DELIVERABLE_DIR);
  const dir = isAbsolute(configured) ? configured : join(REPO_ROOT, configured);
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

  /** chainId yang BENAR-BENAR dilayani node — bukan yang kita klaim di konstruktor. */
  async chainIdOfNode(): Promise<number> {
    return this.publicClient.getChainId();
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
    log("deliverable.offchain.skipped", { chainId, jobId, reason: "wallet-not-registered-in-registry" });
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

async function makeAgent(name: string, privateKey: Hex, rpcUrl: string, acpAddress: Address) {
  const provider = new LocalKeyEvmProvider(name, privateKey, rpcUrl);
  const api = new OnChainJobApi();
  const agent = await AcpAgent.create({
    contractAddresses: { [CHAIN_ID]: acpAddress },
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
  const deliverable = parseDeliverableText(
    process.env[DELIVERABLE_TEXT_ENV],
    process.env[DELIVERABLE_FILE_ENV],
  );
  const providerSlot = parseProviderSlot(process.env[PROVIDER_SLOT_ENV]);
  const termsCommitment = termsCommitmentConfig();
  const jobDescription = committedDescription(JOB_DESCRIPTION, termsCommitment);

  const rpcUrl = configValue("RPC_URL", DEFAULT_RPC_URL);
  const acpAddress = addressConfig("ACP_ADDRESS", DEFAULT_ACP_ADDRESS);
  const vaultAddress = addressConfig("VAULT_ADDRESS", DEFAULT_VAULT_ADDRESS);
  const agentAddress = addressConfig("AGENT_ADDRESS", DEFAULT_AGENT_ADDRESS);

  const client = await makeAgent("client-sim", loadPrivateKey("CLIENT_PRIVATE_KEY"), rpcUrl, acpAddress);
  const provider = await makeAgent(
    `provider-sim-${providerSlot}`,
    loadPrivateKey(PROVIDER_KEY_BY_SLOT[providerSlot]),
    rpcUrl,
    acpAddress,
  );

  // RPC yang menunjuk rantai lain adalah salah-ketik yang paling mahal di sini: adapter
  // menolaknya nanti dengan pesan viem tentang "chain mismatch", sesudah kunci dimuat.
  const nodeChainId = await client.provider.chainIdOfNode();
  if (nodeChainId !== CHAIN_ID) {
    throw new Error(
      `RPC ${rpcUrl} melayani chainId ${nodeChainId}, sedangkan skrip ini terikat ${CHAIN_ID}. ` +
        `Anvil lokal WAJIB dijalankan dengan --chain-id ${CHAIN_ID}: SDK memetakan chainId ke ` +
        `keluarga rantai lewat registrinya sendiri dan melempar UnknownChainIdError untuk id lain.`,
    );
  }

  // Tiga alamat berbeda. Kontrak yang memaksanya; cek ini hanya supaya kita gagal SEBELUM
  // membayar gas untuk revert yang sudah bisa diramalkan.
  if (client.address.toLowerCase() === provider.address.toLowerCase()) {
    throw new Error("CLIENT dan PROVIDER memakai alamat yang sama → createJob revert ClientIsProvider() 0x332ff0f9");
  }
  if (provider.address.toLowerCase() === vaultAddress.toLowerCase()) {
    throw new Error("PROVIDER == evaluator → createJob revert EvaluatorIsProvider() 0xc7b4e9eb");
  }
  // ADR-017 poin 3 sampai hari ini hanya hidup sebagai KOMENTAR di kepala berkas. Sejak ada
  // slot provider kedua, salah ketik nama variabel kunci bisa membuat wallet AGEN menjadi
  // provider yang ia nilai sendiri — kontrak TIDAK merevert itu, jadi penjaganya harus di sini.
  if (provider.address.toLowerCase() === agentAddress.toLowerCase()) {
    throw new Error(
      `PROVIDER == wallet agen ${agentAddress} → evaluator menilai pekerjaannya sendiri (ADR-017 poin 3)`,
    );
  }

  // Token escrow — SATU-SATUNYA cek yang mengikat (docs/api-facts.md §A): tanyakan ke kontrak ACP
  // yang benar-benar akan kita panggil. `symbol()`/`decimals()` TIDAK bisa membedakan dua "USDC"
  // di Base Sepolia, jadi yang dibandingkan adalah ALAMAT.
  const paymentToken = ((await client.provider.readContract(CHAIN_ID, {
    address: acpAddress,
    abi: ACP_PAYMENT_TOKEN_ABI,
    functionName: "paymentToken",
  })) as Address).toLowerCase();

  // `AssetToken.usdcFromRaw` mengambil alamat dari registri BAWAAN SDK, dan untuk chainId 84532
  // registri itu SELALU menunjuk token Base Sepolia — benar di testnet, salah di Anvil lokal.
  const sdkToken = AssetToken.usdcFromRaw(budgetRaw, CHAIN_ID);
  let budget: AssetToken;
  if (sdkToken.address.toLowerCase() === paymentToken) {
    // Jalur Base Sepolia, tidak berubah: token pilihan SDK = token yang ditarik escrow.
    if (paymentToken !== DEFAULT_ESCROW_TOKEN_ADDRESS.toLowerCase()) {
      throw new Error(`paymentToken() ${paymentToken} tidak dikenal untuk ACP ${acpAddress} — dihentikan.`);
    }
    budget = sdkToken;
  } else if (acpAddress.toLowerCase() === DEFAULT_ACP_ADDRESS.toLowerCase()) {
    // ACP NYATA menjawab token yang berbeda dari yang dipilih SDK → jangan pernah dilanjutkan.
    throw new Error(
      `SDK memilih token ${sdkToken.address} untuk chainId ${CHAIN_ID}, sedangkan ACP ${acpAddress} ` +
        `menarik ${paymentToken}. fund() akan menarik token yang salah — dihentikan.`,
    );
  } else {
    // ACP yang DITIMPA (mock di Anvil): ikuti jawaban kontraknya. `AssetToken.create` adalah static
    // PUBLIK SDK yang menerima alamat eksplisit (`dist/core/assetToken.d.ts`), jadi jalur lokal tetap
    // memakai tipe AssetToken milik SDK, bukan objek buatan sendiri.
    budget = AssetToken.create(
      paymentToken as Address,
      "USDC",
      ESCROW_TOKEN_DECIMALS,
      Number(budgetRaw) / 10 ** ESCROW_TOKEN_DECIMALS,
    );
  }
  // AssetToken menghitung ulang rawAmount dari `amount` bertipe number: pembulatan float di sana
  // akan mendanai jumlah yang BERBEDA dari yang diminta, diam-diam.
  if (budget.rawAmount !== budgetRaw) {
    throw new Error(`AssetToken menghasilkan ${budget.rawAmount} unit, diminta ${budgetRaw} — dihentikan.`);
  }

  const expiredAt = Math.floor(Date.now() / 1000) + EXPIRY_SECONDS;

  log("config", {
    chainId: CHAIN_ID,
    rpc: rpcUrl,
    acp: acpAddress,
    clientAddress: client.address,
    providerSlot,
    providerAddress: provider.address,
    evaluatorAddress: vaultAddress,
    escrowToken: budget.address,
    budgetRaw: budget.rawAmount,
    stopAfter,
    deliverableTextFrom: deliverable.source,
    deliverableTextBytes: new TextEncoder().encode(deliverable.text).length,
    expiredAt,
    termsCommitment: termsCommitment ?? "generic-terms-no-commitment",
  });

  // 0) preflight saldo — sebelum satu wei gas pun terbakar.
  const clientBalance = await assertClientCanFund(client.provider, budget.address, client.address, budgetRaw);
  log("balance.ok", { token: budget.address, owner: client.address, balanceRaw: clientBalance, neededRaw: budgetRaw });

  // 1) createJob — ditandatangani CLIENT.
  const markCreate = client.provider.sentTxHashes.length;
  const jobId = await client.agent.createJob(CHAIN_ID, {
    providerAddress: provider.address,
    evaluatorAddress: vaultAddress, // eksplisit: alamat nol = evaluasi DILEWATI
    expiredAt,
    description: jobDescription,
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
    // `finalJob.budget.address` BUKAN fakta rantai: SDK membangunnya dengan
    // `AssetToken.usdcFromRaw(raw, chainId)` (`dist/acpJob.js:42`), yang selalu mengambil alamat
    // dari registri BAWAANNYA — untuk chainId 84532 selalu token Base Sepolia, bahkan saat kita
    // berjalan di Anvil terhadap mock. Yang dilaporkan di sini adalah jawaban `paymentToken()`
    // kontrak ACP yang sudah diverifikasi di preflight.
    escrowToken: paymentToken,
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
  console.error(scrub(`[client_min] FAILED ${message}`));
  process.exitCode = 1;
});
