import { txUrl, addressUrl } from "../lib/chain.js";
import Icon from "./Icon.jsx";

/**
 * Tautan transaksi. Bila hash BELUM ADA, yang ditampilkan adalah kata "not available" —
 * bukan hash palsu dan bukan tautan mati.
 * @param {{ hash?: string | null, label?: string }} props
 */
export function TxLink({ hash, label }) {
  if (!hash) return <span className="none">not available</span>;
  return (
    <a
      className="mono"
      href={txUrl(hash)}
      target="_blank"
      rel="noreferrer"
      aria-label={`Transaction ${hash} on the block explorer (opens in a new tab)`}
    >
      {label ?? hash}
      <Icon name="external-link" size={12} />
    </a>
  );
}

/** @param {{ address?: string | null, label?: string }} props */
export function AddressLink({ address, label }) {
  if (!address) return <span className="none">not available</span>;
  return (
    <a
      className="mono"
      href={addressUrl(address)}
      target="_blank"
      rel="noreferrer"
      aria-label={`Address ${address} on the block explorer (opens in a new tab)`}
    >
      {label ?? address}
      <Icon name="external-link" size={12} />
    </a>
  );
}

/** @param {{ value?: string | null }} props */
export function Hash({ value }) {
  if (!value) return <span className="none">not available</span>;
  return <span className="mono">{value}</span>;
}

/** @param {string} hash */
export function shorten(hash) {
  if (typeof hash !== "string" || hash.length < 14) return hash;
  return hash.slice(0, 10) + "…" + hash.slice(-6);
}
