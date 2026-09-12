import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { Logo } from "./Logo.jsx";
import { ACTION_CLASS } from "../lib/passportDemo.js";

const REPO_URL = "https://github.com/ZiramBayam/referi";
const REPRODUCTION_URL = `${REPO_URL}#reproduction`;

export function Footer() {
  return (
    <footer className="mt-28 border-t border-border">
      <div className="mx-auto grid max-w-6xl gap-10 px-5 py-12 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr]">
        <div className="flex flex-col gap-2">
          <Logo />
          <p className="max-w-xs text-sm text-muted">
            An incident-conditioned control plane for agent execution. Memory becomes proof
            obligations; proof becomes one short-lived permission.
          </p>
        </div>

        <nav className="flex flex-col gap-2.5 text-sm text-muted" aria-label="Product">
          <span className="text-xs font-medium uppercase tracking-wide text-faint">Product</span>
          <Link href="/" className="transition-colors hover:text-ink">
            Overview
          </Link>
          <Link href="/execution" className="transition-colors hover:text-ink">
            Execution room
          </Link>
          <Link href="/timeline" className="transition-colors hover:text-ink">
            On-chain record
          </Link>
          <Link href="/panel" className="transition-colors hover:text-ink">
            Judge panel
          </Link>
          <Link href="/firewall" className="transition-colors hover:text-ink">
            Escrow Firewall
            <span className="ml-1.5 text-xs text-faint">earlier direction</span>
          </Link>
        </nav>

        <nav className="flex flex-col gap-2.5 text-sm text-muted" aria-label="Evidence">
          <span className="text-xs font-medium uppercase tracking-wide text-faint">
            Evidence · reproducible locally
          </span>
          <a
            href={REPRODUCTION_URL}
            target="_blank"
            rel="noreferrer"
            className="group inline-flex items-center gap-1.5 transition-colors hover:text-ink"
          >
            Reproduction guide
            <ExternalLink
              className="size-3 text-faint transition-colors group-hover:text-primary-ink"
              strokeWidth={2}
              aria-hidden
            />
          </a>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="group inline-flex items-center gap-1.5 transition-colors hover:text-ink"
          >
            Source on GitHub
            <ExternalLink
              className="size-3 text-faint transition-colors group-hover:text-primary-ink"
              strokeWidth={2}
              aria-hidden
            />
          </a>
        </nav>
      </div>

      <div className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-5 py-5 text-xs text-faint sm:flex-row sm:items-center sm:justify-between">
          <span>
            Safe integration, production oracles, and other DeFi actions are roadmap items, not
            claims.
          </span>
          <span className="font-mono">
            {ACTION_CLASS} · Base Sepolia fixture · no real funds
          </span>
        </div>
      </div>
    </footer>
  );
}
