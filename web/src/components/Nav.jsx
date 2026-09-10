"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { Logo } from "./Logo.jsx";
import { ThemeToggle } from "./theme/ThemeToggle.jsx";
import { cn } from "../lib/utils.js";
import { CHAIN_NAME } from "../lib/chain.js";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/execution", label: "Execution room" },
  { href: "/timeline", label: "On-chain record" },
  { href: "/panel", label: "Judge panel" },
];

export function Nav() {
  const pathname = usePathname();
  const reduce = useReducedMotion();

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-bg/75 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5">
        <Link href="/" className="rounded-md" aria-label="Referi home">
          <Logo />
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {LINKS.map((link) => {
            // "/" harus cocok PERSIS: sebagai prefix ia akan menyalakan setiap rute.
            const active =
              link.href === "/"
                ? pathname === "/"
                : pathname === link.href || pathname.startsWith(link.href + "/");
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative rounded-lg px-3 py-1.5 text-sm font-medium transition-colors duration-200",
                  active ? "bg-primary/20 text-primary-ink" : "text-muted hover:bg-surface hover:text-ink"
                )}
              >
                {link.label}
                {active &&
                  (reduce ? (
                    <span className="absolute inset-x-2 bottom-0 h-[2px] rounded-full bg-primary-ink opacity-80" />
                  ) : (
                    // Satu penanda yang BERGESER antar tautan, bukan empat penanda yang
                    // muncul-hilang: perpindahan halaman jadi punya kontinuitas ruang.
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-x-2 bottom-0 h-[2px] rounded-full bg-primary-ink opacity-80"
                      transition={{ type: "spring", stiffness: 480, damping: 40 }}
                    />
                  ))}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3">
          <span className="hidden items-center gap-2 rounded-lg border border-border bg-surface/60 px-2.5 py-1.5 font-mono text-[11px] text-muted sm:inline-flex">
            <span className="relative flex size-1.5" aria-hidden>
              <span className="absolute inline-flex size-full rounded-full bg-proof-review opacity-60 stage-glow" />
              <span className="relative inline-flex size-1.5 rounded-full bg-proof-review" />
            </span>
            {CHAIN_NAME}
            <span className="text-faint">fixture</span>
          </span>
          <ThemeToggle />
        </div>
      </div>

      {/* Di bawah md tautan utama tidak boleh ikut hilang: tanpa baris ini rute bukti
          hanya bisa dicapai lewat footer, dan di ponsel itu berarti tidak bisa dicapai. */}
      <nav
        aria-label="Sections"
        className="flex items-center gap-1 overflow-x-auto border-t border-border px-4 py-2 md:hidden"
      >
        {LINKS.map((link) => {
          const active =
            link.href === "/"
              ? pathname === "/"
              : pathname === link.href || pathname.startsWith(link.href + "/");
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors",
                active ? "bg-primary/20 text-primary-ink" : "text-muted"
              )}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
