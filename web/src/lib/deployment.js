/**
 * Fixture Execution Passport di Base Sepolia.
 *
 * Nilai-nilai ini disalin dari `deployments/passport-84532.json`, yang isinya sendiri
 * dibaca ULANG dari chain sesudah broadcast, bukan dari log `forge script`. Halaman
 * TIDAK memanggil RPC untuk menampilkannya: kalau ia memanggil RPC, halaman ini akan
 * kosong setiap kali jaringan juri bermasalah, padahal alamatnya sudah pasti.
 *
 * Explorer-nya Blockscout, bukan BaseScan, dengan alasan yang sama seperti rute
 * bukti lama: hanya Blockscout yang menarik verifikasi Sourcify, jadi hanya di sana
 * sumbernya terbaca alih-alih tampil sebagai bytecode mentah.
 */

export const PASSPORT_EXPLORER = "https://base-sepolia.blockscout.com";
export const PASSPORT_BLOCK = 46629087;
export const PASSPORT_DEPLOY_COST_ETH = "0.0000088";

export const PASSPORT_CONTRACTS = /** @type {const} */ ([
  {
    name: "PassportVerifier",
    address: "0x43D978e26bEe32A8f2E2DaB1f212F9A36F5937C1",
    role: "Accepts one exact action, once, then burns the nonce",
  },
  {
    name: "MockTreasury",
    address: "0x68Cca28DceFAd1c7a73f97FACC74cD51B145772B",
    role: "The fixture reserve the rebalance moves",
  },
  {
    name: "MockOracle",
    address: "0x8b0e7572eDF67Fded93ff8dBFfD318d2E3D2bDe3",
    role: "The observation the seeded incident is about",
  },
]);

/** @param {string} address */
export function passportAddressUrl(address) {
  return `${PASSPORT_EXPLORER}/address/${address}`;
}
