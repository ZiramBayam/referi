/**
 * sim/src/mint_min.ts — mendanai wallet CLIENT dengan token escrow ACP (langkah 0 rantai 2.5).
 *
 * Kenapa ada: `fund()` hanya menarik `paymentToken()` milik kontrak ACP, dan wallet client
 * simulator memegang 0 unit token itu. Token escrow Base Sepolia
 * (`0xECc22a8F6fD62388498fBa19813E214605a2BDb3`) punya `mint(address,uint256)` TANPA kontrol
 * akses — selector `0x40c10f19`, dibuktikan di fork Base Sepolia (docs/api-facts.md §A) —
 * jadi tidak ada faucet yang perlu diminta. Skrip ini TIDAK menyentuh satu pun fungsi ACP.
 *
 * IDENTITAS TOKEN — satu-satunya cek yang sah (docs/api-facts.md §A): alamat hasil
 * `paymentToken()` pada kontrak ACP. `symbol()` DILARANG dipakai: USDC Circle
 * `0x036CbD53…dCF7e` dan token escrow sama-sama menjawab `"USDC"` dengan 6 desimal, jadi
 * simbol tidak bisa membedakan keduanya dan "membuktikan token dengan symbol()" adalah cacat
 * yang lolos untuk token yang salah.
 *
 * PENERIMA diturunkan dari `CLIENT_PRIVATE_KEY`, bukan dari sebuah alamat yang diketik: yang
 * harus punya saldo adalah wallet yang nanti MENANDATANGANI `fund`. Menyalin alamat dengan
 * tangan adalah satu-satunya cara token bisa mendarat di wallet yang salah.
 *
 * SUMBER KEBENARAN hasil tx = event `Transfer` di RECEIPT, bukan `balanceOf` sesudahnya:
 * RPC publik Base Sepolia melayani `eth_call` dari node yang bisa TERTINGGAL di belakang
 * receipt yang baru saja ia kembalikan (docs/api-facts.md §E.1 kasus 2 — `balanceOf` = 0
 * sesudah `mint` yang sukses). Receipt bersifat self-contained dan tidak bisa "tertinggal".
 *
 * Kunci privat TIDAK PERNAH dicetak: lihat `scrub()`, pola yang sama dengan client_min.ts.
 *
 * Pakai:
 *   MINT_RAW=10000000 pnpm --filter sim run mint:client
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  createPublicClient,
  createWalletClient,
  decodeEventLog,
  http,
  parseAbi,
  type Address,
  type Hex,
} from "viem";
import { privateKeyToAccount, type PrivateKeyAccount } from "viem/accounts";
import { baseSepolia } from "viem/chains";

const CHAIN = baseSepolia;
const CHAIN_ID = baseSepolia.id; // 84532
const DEFAULT_RPC_URL = "https://sepolia.base.org";

/**
 * ACP default = Base Sepolia, bisa ditimpa lewat `ACP_ADDRESS` (nama yang sama seperti
 * `.env.example` dan `client_min.ts`) supaya alur yang sama bisa dijalankan di Anvil lokal
 * terhadap mock. chainId TIDAK ikut berubah: node lokal WAJIB `--chain-id 84532`.
 */
const DEFAULT_ACP_ADDRESS = "0x0b93793923CD5De81850aF8604a233f3f24d461e" as Address;

/**
 * Nilai `paymentToken()` yang diharapkan SAAT kita memang berbicara dengan ACP Base Sepolia.
 * Token yang benar-benar di-mint SELALU jawaban `paymentToken()` kontrak ACP — konstanta ini
 * hanya asersi, tidak pernah menjadi sumber alamat.
 */
const DEFAULT_ESCROW_TOKEN_ADDRESS = "0xECc22a8F6fD62388498fBa19813E214605a2BDb3" as Address;

/** 10 USDC (6 desimal) — cukup untuk job A (1) + job B (1) + job C (2) dengan sisa. */
const DEFAULT_MINT_RAW = 10_000_000n;

const ACP_ABI = parseAbi(["function paymentToken() view returns (address)"]);
const TOKEN_ABI = parseAbi([
  "function mint(address to, uint256 amount)",
  "function balanceOf(address account) view returns (uint256)",
  "event Transfer(address indexed from, address indexed to, uint256 value)",
]);

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

function parseEnvFile(text: string): Record<string, string> {
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

/** Alamat dari env/.env, bentuknya divalidasi sebelum satu panggilan RPC pun dikirim. */
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
  if (!key) throw new Error(`${name} kosong (environment maupun .env root)`);
  if (!key.startsWith("0x")) key = `0x${key}`;
  secrets.push(key, key.slice(2));
  return key as Hex;
}

function scrub(text: string): string {
  let out = text;
  for (const secret of secrets) {
    if (secret.length >= 16) out = out.split(secret).join("<REDACTED>");
  }
  return out;
}

function log(event: string, fields: Record<string, unknown> = {}): void {
  const parts = Object.entries(fields).map(([k, v]) => `${k}=${String(v)}`);
  console.log(scrub([`[mint_min] ${event}`, ...parts].join(" ")));
}

function parseAmountRaw(raw: string | undefined): bigint {
  const text = (raw ?? "").trim();
  if (!text) return DEFAULT_MINT_RAW;
  if (!/^[0-9][0-9_]*$/.test(text)) {
    throw new Error(`MINT_RAW="${text}" bukan bilangan bulat unit mentah token (6 desimal)`);
  }
  const value = BigInt(text.split("_").join(""));
  if (value <= 0n) throw new Error(`MINT_RAW harus > 0, dapat "${text}"`);
  return value;
}

async function main(): Promise<void> {
  const amountRaw = parseAmountRaw(process.env.MINT_RAW);
  const rpcUrl = configValue("RPC_URL", DEFAULT_RPC_URL);
  const acpAddress = addressConfig("ACP_ADDRESS", DEFAULT_ACP_ADDRESS);

  const publicClient = createPublicClient({ chain: CHAIN, transport: http(rpcUrl) });

  // RPC yang menunjuk rantai lain = mint ke tempat yang salah. Dicek sebelum kunci dimuat.
  const nodeChainId = await publicClient.getChainId();
  if (nodeChainId !== CHAIN_ID) {
    throw new Error(
      `RPC ${rpcUrl} melayani chainId ${nodeChainId}, sedangkan skrip ini terikat ${CHAIN_ID}. ` +
        `Anvil lokal WAJIB dijalankan dengan --chain-id ${CHAIN_ID}.`,
    );
  }

  // PENANDA TANGAN: wallet agen (satu-satunya yang punya ETH untuk gas dan tidak berperan
  // sebagai client/provider di alur job). `mint` tanpa kontrol akses → siapa pun boleh.
  const minter: PrivateKeyAccount = privateKeyToAccount(loadPrivateKey("AGENT_PRIVATE_KEY"));
  // PENERIMA: wallet yang nanti menandatangani `fund`, diturunkan dari kuncinya sendiri.
  const recipient: Address = privateKeyToAccount(loadPrivateKey("CLIENT_PRIVATE_KEY")).address;

  // Token yang di-mint = jawaban kontrak, selalu. Asersi terhadap konstanta hanya berlaku bila
  // ACP-nya memang ACP Base Sepolia; pada ACP yang DITIMPA (mock di Anvil) tidak ada konstanta
  // yang bisa dibandingkan, dan mengarang salah satu justru yang berbahaya.
  const paymentToken = (await publicClient.readContract({
    address: acpAddress,
    abi: ACP_ABI,
    functionName: "paymentToken",
  })) as Address;
  const onDefaultAcp = acpAddress.toLowerCase() === DEFAULT_ACP_ADDRESS.toLowerCase();
  if (onDefaultAcp && paymentToken.toLowerCase() !== DEFAULT_ESCROW_TOKEN_ADDRESS.toLowerCase()) {
    throw new Error(
      `paymentToken() ACP = ${paymentToken}, bukan ${DEFAULT_ESCROW_TOKEN_ADDRESS} — token escrow berubah; ` +
        "dihentikan sebelum mint apa pun",
    );
  }

  log("config", {
    chainId: CHAIN_ID,
    rpc: rpcUrl,
    acp: acpAddress,
    token: paymentToken,
    minter: minter.address,
    recipient,
    amountRaw,
  });

  const before = (await publicClient.readContract({
    address: paymentToken,
    abi: TOKEN_ABI,
    functionName: "balanceOf",
    args: [recipient],
  })) as bigint;
  log("balance.before", { recipient, balanceRaw: before });

  // Simulasi dulu: revert keluar sebagai error tanpa membakar gas.
  const { request } = await publicClient.simulateContract({
    account: minter,
    address: paymentToken,
    abi: TOKEN_ABI,
    functionName: "mint",
    args: [recipient, amountRaw],
  });

  const walletClient = createWalletClient({ account: minter, chain: CHAIN, transport: http(rpcUrl) });
  const hash = await walletClient.writeContract(request);
  const receipt = await publicClient.waitForTransactionReceipt({ hash });
  if (receipt.status !== "success") {
    throw new Error(`mint ${hash} ter-mining dengan status ${receipt.status}`);
  }

  // Bukti yang mengikat: event Transfer DI RECEIPT (bukan balanceOf sesudahnya).
  let minted = 0n;
  for (const entry of receipt.logs) {
    if (entry.address.toLowerCase() !== paymentToken.toLowerCase()) continue;
    try {
      const decoded = decodeEventLog({ abi: TOKEN_ABI, data: entry.data, topics: entry.topics });
      if (decoded.eventName !== "Transfer") continue;
      const args = decoded.args as { from: Address; to: Address; value: bigint };
      if (args.to.toLowerCase() !== recipient.toLowerCase()) continue;
      minted += args.value;
      log("transfer", { from: args.from, to: args.to, value: args.value });
    } catch {
      // log lain di receipt yang sama bukan urusan skrip ini
    }
  }
  if (minted !== amountRaw) {
    throw new Error(
      `receipt ${hash} tidak memuat Transfer sebesar ${amountRaw} ke ${recipient} (terbaca ${minted})`,
    );
  }

  log("summary", {
    tx: hash,
    block: receipt.blockNumber,
    status: receipt.status,
    token: paymentToken,
    recipient,
    mintedRaw: minted,
  });
}

main().catch((err: unknown) => {
  const message = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
  console.error(scrub(`[mint_min] FAILED ${message}`));
  process.exitCode = 1;
});
