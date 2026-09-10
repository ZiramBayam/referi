import Link from "next/link";
import { ArrowLeft, Check, Info, TriangleAlert, X } from "lucide-react";
import { cn } from "../lib/utils.js";

/**
 * Kerangka halaman dalam. Satu tempat yang memegang lebar kontainer, gutter, dan
 * irama judul, supaya rute bukti tidak pelan-pelan menyimpang dari ruang eksekusi.
 *
 * @param {{ children: any, className?: string }} props
 */
export function Page({ children, className }) {
  return <div className={cn("mx-auto max-w-6xl px-5 py-14", className)}>{children}</div>;
}

/**
 * @param {{ title: any, lede?: any, back?: { href: string, label: string },
 *   actions?: any }} props
 */
export function PageHeader({ title, lede, back, actions }) {
  return (
    <div className="flex flex-col gap-5">
      {back && (
        <Link
          href={back.href}
          className="inline-flex w-fit items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink"
        >
          <ArrowLeft className="size-3.5" strokeWidth={2} aria-hidden />
          {back.label}
        </Link>
      )}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-4xl font-semibold tracking-tight text-ink">{title}</h1>
          {lede && (
            <div className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted">{lede}</div>
        )}
        </div>
        {actions}
      </div>
    </div>
  );
}

/**
 * Pita konteks. `tone` menentukan warnanya, tapi kata di dalamnya yang menanggung
 * artinya, status di sini tidak pernah disampaikan warna saja.
 *
 * @param {{ children: any, tone?: "info" | "warn", title?: string, className?: string }} props
 */
export function Notice({ children, tone = "info", title, className }) {
  const warn = tone === "warn";
  const Icon = warn ? TriangleAlert : Info;
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-xl border px-5 py-4",
        warn
          ? "border-proof-review/35 bg-proof-review/[0.06]"
          : "border-border bg-surface",
        className
      )}
    >
      <Icon
        className={cn("mt-0.5 size-4 shrink-0", warn ? "text-proof-review" : "text-primary-ink")}
        strokeWidth={2}
        aria-hidden
      />
      <div className="text-sm leading-relaxed text-muted">
        {title && <span className="mr-1.5 font-medium text-ink">{title}</span>}
        {children}
      </div>
    </div>
  );
}

/** Label kelompok di dalam kartu bukti. */
/** @param {{ children: any, className?: string }} props */
export function GroupLabel({ children, className }) {
  return (
    <h2
      className={cn(
        "text-xs font-medium uppercase tracking-wide text-faint",
        className
      )}
    >
      {children}
    </h2>
  );
}

/**
 * Daftar kunci-nilai. Grid dua kolom di layar lebar, menumpuk di sempit, dan
 * setiap barisnya dipisah garis rambut supaya bisa dipindai baris demi baris.
 *
 * @param {{ children: any, className?: string }} props
 */
export function KeyValues({ children, className }) {
  return (
    <dl className={cn("grid gap-x-8 gap-y-0 sm:grid-cols-[minmax(0,14rem)_1fr]", className)}>
      {children}
    </dl>
  );
}

/** @param {{ label: any, children: any, key?: any }} props */
export function KeyValue({ label, children }) {
  return (
    <>
      <dt className="border-t border-border py-3 font-mono text-xs text-faint sm:pt-3.5">
        {label}
      </dt>
      <dd className="-mt-3 break-words pb-3 text-sm text-ink sm:mt-0 sm:border-t sm:border-border sm:py-3.5">
        {children}
      </dd>
    </>
  );
}

/** Nilai yang tidak tersedia, kata, bukan tanda hubung yang ambigu. */
export function NotAvailable() {
  return <span className="text-faint">not available</span>;
}

/**
 * Penanda status. Ikon + kata selalu ikut, jadi statusnya terbaca tanpa warna:
 * `pass` hijau, `fail` merah, apa pun selain itu amber (belum terverifikasi).
 *
 * @param {{ status: string, children?: any, className?: string }} props
 */
export function Tag({ status, children, className }) {
  const pass = status === "pass";
  const fail = status === "fail";
  const Icon = pass ? Check : fail ? X : TriangleAlert;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 font-mono text-[11px] font-medium uppercase tracking-wide",
        pass
          ? "border-proof-pass/40 bg-proof-pass/10 text-proof-pass"
          : fail
            ? "border-proof-block/40 bg-proof-block/10 text-proof-block"
            : "border-proof-review/40 bg-proof-review/10 text-proof-review",
        className
      )}
    >
      <Icon className="size-3" strokeWidth={2.5} aria-hidden />
      {children ?? status}
    </span>
  );
}
