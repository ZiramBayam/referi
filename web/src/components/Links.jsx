import { txUrl, addressUrl } from "../lib/chain.js";

/**
 * Tautan transaksi. Bila hash BELUM ADA, yang ditampilkan adalah kata "belum ada" —
 * bukan hash palsu dan bukan tautan mati.
 * @param {{ hash?: string | null, label?: string }} props
 */
export function TxLink({ hash, label }) {
  if (!hash) return <span className="none">belum ada</span>;
  return (
    <a className="mono" href={txUrl(hash)} target="_blank" rel="noreferrer">
      {label ?? hash}
    </a>
  );
}

/** @param {{ address?: string | null, label?: string }} props */
export function AddressLink({ address, label }) {
  if (!address) return <span className="none">belum ada</span>;
  return (
    <a className="mono" href={addressUrl(address)} target="_blank" rel="noreferrer">
      {label ?? address}
    </a>
  );
}

/** @param {{ value?: string | null }} props */
export function Hash({ value }) {
  if (!value) return <span className="none">belum ada</span>;
  return <span className="mono">{value}</span>;
}

/** @param {string} hash */
export function shorten(hash) {
  if (typeof hash !== "string" || hash.length < 14) return hash;
  return hash.slice(0, 10) + "…" + hash.slice(-6);
}
