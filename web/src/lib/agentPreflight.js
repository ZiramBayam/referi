import { execFile } from "node:child_process";
import path from "node:path";

/**
 * Jembatan ke agen Python yang SEBENARNYA.
 *
 * Rute preflight dulu memanggil `passportDemo.js`, sebuah implementasi ulang aturan
 * dalam JavaScript. Modul ini menggantinya dengan pemanggilan ke `agent.passport_preflight`,
 * yang menjalankan `evaluate_rebalance_for_passport` yang sama dengan `make demo-passport`
 * di atas memori Sibyl yang sama.
 *
 * Kenapa subprocess dan bukan HTTP: tidak ada layanan tambahan yang perlu dinyalakan
 * juri, tidak ada port baru, dan tidak ada proses yang menganggur. Biayanya satu proses
 * per permintaan, dan itu murah karena evaluasinya murni deterministik (nol RPC).
 *
 * Kegagalan TIDAK PERNAH menjatuhkan halaman: bila `uv` tidak ada, venv belum dibuat,
 * atau prosesnya melewati batas waktu, pemanggil jatuh ke fixture dan halaman
 * MENGATAKAN yang mana yang berjalan. Diam-diam jatuh ke fixture adalah bentuk
 * ketidakjujuran yang persis ingin dihapus modul ini.
 */

const TIMEOUT_MS = 20_000;
const MAX_OUTPUT = 4 * 1024 * 1024;

/** Label yang terbaca manusia untuk tiap id kewajiban milik agen. */
const LABELS = {
  "state-anchor-fresh": "State anchor freshness",
  "oracle-freshness": "Oracle freshness",
  "simulation-match": "Exact simulation match",
  "post-state-invariant": "Post-state invariant",
  "actor-standing": "Executor standing on ACP",
};

/** @param {Record<string, any>} value */
function readable(value) {
  if (!value || typeof value !== "object") return String(value ?? "");
  const entries = Object.entries(value);
  if (entries.length === 0) return "";
  // Angka detik dan cadangan adalah yang dicari mata lebih dulu, jadi ia didahulukan
  // dan sisanya dibiarkan mengikuti urutan aslinya dari agen.
  const priority = ["age_seconds", "max_age_seconds", "simulated_post_reserve", "minimum_reserve"];
  entries.sort((a, b) => priority.indexOf(b[0]) - priority.indexOf(a[0]));
  const [key, first] = entries[0];
  const shown = typeof first === "string" && first.startsWith("0x") ? shortHex(first) : String(first);
  const suffix = key.endsWith("_seconds") ? " seconds" : "";
  return `${key.replace(/_/g, " ")}: ${shown}${suffix}`;
}

/** @param {string} hex */
function shortHex(hex) {
  return hex.length > 18 ? `${hex.slice(0, 10)}…${hex.slice(-6)}` : hex;
}

/**
 * Terjemahkan bentuk agen ke bentuk yang dipakai komponen. Kosakata hasilnya
 * (`satisfied` / `unsatisfied` / `unverifiable`) sudah sama, jadi ia tidak dipetakan
 * ulang: memetakannya berarti menciptakan tempat kedua yang bisa menyimpang.
 *
 * @param {any} agent
 */
export function toRoomShape(agent) {
  const proofs = (agent.obligations ?? []).map((/** @type {any} */ o) => ({
    id: o.id,
    label: LABELS[o.id] ?? o.id,
    result: o.result,
    observed: readable(o.observed),
    threshold: readable(o.threshold),
    explanation: o.explanation,
  }));

  return {
    engine: "agent",
    decision: agent.decision,
    reason: agent.reason,
    proofs,
    passport: agent.passport,
    postReserve: agent.postReserve,
    memoryRoot: agent.memoryRoot,
    hypothesisId: agent.hypothesisId,
    signed: false,
    deployment: agent.deployment,
    action: {
      amount: undefined,
      asset: "MOCK",
      target: agent.action?.target,
      calldata: agent.action?.calldata,
      chain: `chain ${agent.action?.chain_id}`,
    },
    memoryAvailable: Boolean(agent.memoryRoot),
    oracleFresh: agent.oracleAgeSeconds !== undefined ? agent.oracleAgeSeconds <= 60 : undefined,
  };
}

/**
 * Jalankan agen. Mengembalikan bentuk ruang eksekusi, atau melempar dengan alasan
 * yang bisa ditampilkan.
 *
 * @param {{ amount: number, memoryAvailable: boolean, oracleFresh: boolean }} input
 */
export function runAgentPreflight(input) {
  const repoRoot = path.resolve(process.cwd(), "..");
  const agentDir = path.join(repoRoot, "agent");

  return new Promise((resolve, reject) => {
    // `execFile`, BUKAN `exec`: tidak ada shell, jadi tidak ada tempat bagi metakarakter
    // untuk berarti apa pun. Masukannya lewat stdin, bukan argv, dengan alasan yang sama.
    const child = execFile(
      "uv",
      ["run", "python", "-m", "agent.passport_preflight"],
      { cwd: agentDir, timeout: TIMEOUT_MS, maxBuffer: MAX_OUTPUT },
      (error, stdout, stderr) => {
        if (error && !stdout) {
          reject(new Error(error.killed ? "agent timed out" : `agent unavailable: ${error.message}`));
          return;
        }
        let parsed;
        try {
          parsed = JSON.parse(stdout);
        } catch {
          reject(new Error(`agent returned non-JSON: ${String(stderr).slice(0, 200)}`));
          return;
        }
        if (parsed.error) {
          reject(new Error(parsed.error));
          return;
        }
        resolve(toRoomShape(parsed));
      },
    );
    child.stdin?.end(JSON.stringify(input));
  });
}
