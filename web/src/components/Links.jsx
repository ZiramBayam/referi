import { ExternalLink } from "lucide-react";
import { txUrl, addressUrl } from "../lib/chain.js";
import { NotAvailable } from "./PageShell.jsx";

const linkClass =
  "group inline-flex items-center gap-1.5 font-mono text-xs text-primary-ink transition-colors hover:text-ink";

/**
 * Tautan transaksi. Bila hash BELUM ADA, yang ditampilkan adalah kata "not available",
 * bukan hash palsu dan bukan tautan mati.
 * @param {{ hash?: string | null, label?: string }} props
 */
export function TxLink({ hash, label }) {
  if (!hash) return <NotAvailable />;
  return (
    <a
      className={linkClass}
      href={txUrl(hash)}
      target="_blank"
      rel="noreferrer"
      aria-label={`Transaction ${hash} on the block explorer (opens in a new tab)`}
    >
      {/* Hash penuh boleh patah; label yang SUDAH dipendekkan tidak, patahan di
          tengah "0x20212E4D…66b3" membuatnya terbaca seperti dua nilai. */}
      <span className={label ? "whitespace-nowrap" : "break-all"}>{label ?? hash}</span>
      <ExternalLink
        className="size-3 shrink-0 text-faint transition-colors group-hover:text-primary-ink"
        strokeWidth={2}
        aria-hidden
      />
    </a>
  );
}

/** @param {{ address?: string | null, label?: string }} props */
export function AddressLink({ address, label }) {
  if (!address) return <NotAvailable />;
  return (
    <a
      className={linkClass}
      href={addressUrl(address)}
      target="_blank"
      rel="noreferrer"
      aria-label={`Address ${address} on the block explorer (opens in a new tab)`}
    >
      <span className={label ? "whitespace-nowrap" : "break-all"}>{label ?? address}</span>
      <ExternalLink
        className="size-3 shrink-0 text-faint transition-colors group-hover:text-primary-ink"
        strokeWidth={2}
        aria-hidden
      />
    </a>
  );
}

/** @param {{ value?: string | null }} props */
export function Hash({ value }) {
  if (!value) return <NotAvailable />;
  return <span className="break-all font-mono text-xs text-ink">{value}</span>;
}

/** @param {string} hash */
export function shorten(hash) {
  if (typeof hash !== "string" || hash.length < 14) return hash;
  return hash.slice(0, 10) + "…" + hash.slice(-6);
}
