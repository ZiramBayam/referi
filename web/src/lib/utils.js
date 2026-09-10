import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Gabungkan kelas Tailwind dengan logika kondisional. `twMerge` yang membuat
 * override dari pemanggil benar-benar menang atas kelas bawaan komponen.
 *
 * @param {...any} inputs
 * @returns {string}
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * 0x1234…abcd, dipakai untuk alamat kontrak di manifest deployment.
 * @param {string} address
 * @param {number} [chars]
 */
export function shortenAddress(address, chars = 4) {
  if (!address || !address.startsWith("0x") || address.length < 10) return address;
  return `${address.slice(0, 2 + chars)}…${address.slice(-chars)}`;
}

/**
 * Pemendek hash/fingerprint untuk tampilan.
 * @param {string} hash
 * @param {number} [head]
 * @param {number} [tail]
 */
export function shortenHash(hash, head = 10, tail = 6) {
  if (typeof hash !== "string" || hash.length < head + tail + 2) return hash;
  return `${hash.slice(0, head)}…${hash.slice(-tail)}`;
}

/**
 * Angka besar dengan pemisah ribuan, selalu locale en-US supaya nilai yang sama
 * tidak pernah dirender berbeda antara server dan browser (sumber hydration
 * mismatch yang klasik pada nilai fixture).
 *
 * @param {number} value
 */
export function formatAmount(value) {
  return new Intl.NumberFormat("en-US").format(value);
}
