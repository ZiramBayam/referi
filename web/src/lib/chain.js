// Konstanta jaringan & tautan explorer. Diturunkan dari `deployments/84532.json`, yang
// disalin apa adanya ke `public/deployment.json`.
//
// Halaman ini TIDAK memanggil RPC dan TIDAK menyambung wallet: seluruh angka datang dari
// JSON statis yang sudah diverifikasi di luar browser.

export const CHAIN_ID = 84532;
export const CHAIN_NAME = "Base Sepolia";

// SENGAJA BERBEDA dari field `explorer` di `deployments/84532.json` (yang menunjuk
// BaseScan). Alasannya bukan selera: `EvaluatorVault` terverifikasi lewat Sourcify
// (`exact_match`), dan dari kedua explorer HANYA Blockscout yang menarik verifikasi itu.
// Etherscan/BaseScan tidak mengimpor dari Sourcify dan verifikasinya butuh API key yang
// tidak ada di repo, jadi tautan ke sana mendaratkan juri di topic log MENTAH. Di
// Blockscout log yang sama tampil dengan nama event terdekode (`VerdictPosted`,
// `MemoryRootUpdated`) — itulah yang dirujuk README dan naskah video.
//
// Berkas deployment TIDAK diubah untuk mengikuti ini: ia artefak deploy apa adanya, dan
// field `explorer`-nya memang tidak dibaca halaman mana pun.
export const EXPLORER = "https://base-sepolia.blockscout.com";
export const EXPLORER_NAME = "Blockscout";

/** @param {string} hash */
export function txUrl(hash) {
  return `${EXPLORER}/tx/${hash}`;
}

/** @param {string} address */
export function addressUrl(address) {
  return `${EXPLORER}/address/${address}`;
}

/**
 * Nama status job ACP (ERC-8183) — enum apa adanya, bukan istilah karangan.
 * Sumber: `docs/api-facts.md` §A / kontrak ACP Base Sepolia.
 */
export const ACP_STATUS = /** @type {const} */ ({
  0: "Open",
  1: "Funded",
  2: "Submitted",
  3: "Completed",
  4: "Rejected",
  5: "Expired",
});

/**
 * `EvaluatorVault.postVerdict(kind)`: 1 = complete, 2 = reject (deployments/84532.json
 * `constants.KIND_COMPLETE` / `KIND_REJECT`).
 * @param {number | null} kind
 */
export function verdictKindLabel(kind) {
  if (kind === 1) return "COMPLETE (kind=1)";
  if (kind === 2) return "REJECT (kind=2)";
  return "belum ada";
}

/** @param {number | null | undefined} status */
export function acpStatusLabel(status) {
  if (status === null || status === undefined) return "belum ada";
  const name = /** @type {Record<number, string>} */ (ACP_STATUS)[status];
  return name ? `${status} — ${name}` : `${status} — belum ada nama enum`;
}
