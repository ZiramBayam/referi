"use client";

import { useMemo, useState } from "react";
import { Check } from "lucide-react";
import {
  parseDocument,
  sectionsInScope,
  sectionText,
  evaluateText,
  DEPTH_SAMPLING,
  DEPTH_FULL,
} from "../lib/checks.js";
import { DELIVERABLE_EN } from "../lib/gloss.js";
import { KeyValue, KeyValues } from "./PageShell.jsx";
import { cn } from "../lib/utils.js";

/**
 * "Baca seperti wasitnya membaca."
 *
 * Ini BUKAN peragaan. Tombolnya memanggil `evaluateText`, fungsi yang sama yang
 * menghasilkan bundel bukti on-chain, dan yang paritasnya dijaga
 * `test/checks-parity.test.js` terhadap bundel job 421/422. Jadi verdict yang
 * berkedip saat kamu menggeser kedalaman adalah verdict yang sesungguhnya, bukan
 * angka yang ditulis tangan ke dalam komponen.
 *
 * Yang membuatnya bisa dimainkan: pada `sampling` seksi ketiga TIDAK dibaca, dan
 * `TODO` yang ada di sana lolos. Pada `full` seksi itu menyala dan verdictnya
 * berbalik. Itulah seluruh tesis produk ini, dalam satu klik.
 *
 * @param {{ text: string, hash?: string }} props, `text` adalah byte ASLI yang
 *   di-hash (ditampilkan di kaki), `hash` keccak-nya.
 */
export default function ReadWindow({ text, hash }) {
  const [depth, setDepth] = useState(DEPTH_SAMPLING);

  // Dibaca dari TERJEMAHAN, bukan dari byte asli: strukturnya identik, jadi
  // `evaluateText` mengembalikan hasil yang sama persis (diuji: 3 seksi,
  // sampling -> COMPLETE 2/3, full -> REJECT 3/3 gagal `format`). Aslinya tetap
  // ditampilkan di bawah sebagai byte yang di-hash.
  const { sections, inScope, result } = useMemo(() => {
    const doc = parseDocument(DELIVERABLE_EN);
    const scope = sectionsInScope(doc, depth);
    return {
      sections: doc.sections,
      inScope: new Set(scope.map((/** @type {any} */ s) => s.index)),
      result: evaluateText(DELIVERABLE_EN, depth),
    };
  }, [depth]);

  const rejected = result.verdict === 2;

  const options = [
    { value: DEPTH_SAMPLING, label: "sampling", caption: "provider with a clean record" },
    { value: DEPTH_FULL, label: "full", caption: "provider carrying incidents" },
  ];

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-surface">
      <div
        role="group"
        aria-label="Check depth"
        className="grid gap-1 border-b border-border p-3 sm:grid-cols-2"
      >
        {options.map((o) => {
          const active = depth === o.value;
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={active}
              onClick={() => setDepth(o.value)}
              className={cn(
                "flex flex-col items-start gap-0.5 rounded-xl border px-4 py-3 text-left transition-colors",
                active
                  ? "border-primary/45 bg-primary/[0.09]"
                  : "border-transparent hover:bg-surface-2"
              )}
            >
              <span
                className={cn("font-mono text-sm", active ? "text-primary-ink" : "text-muted")}
              >
                {o.label}
              </span>
              <span className="text-xs text-faint">{o.caption}</span>
            </button>
          );
        })}
      </div>

      <div className="grid gap-px bg-border lg:grid-cols-[1.35fr_0.65fr]">
        <div className="flex flex-col gap-3 bg-bg p-5">
          {sections.map((/** @type {any} */ s) => {
            const read = inScope.has(s.index);
            return (
              <div
                key={s.index}
                className={cn(
                  "rounded-xl border px-4 py-3.5 transition-colors",
                  read ? "border-border bg-surface" : "border-dashed border-border bg-transparent"
                )}
              >
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wide",
                    read ? "text-primary-ink" : "text-faint"
                  )}
                >
                  {read ? (
                    <>
                      <Check className="size-3" strokeWidth={2.5} aria-hidden /> read
                    </>
                  ) : (
                    "not read at this depth"
                  )}
                </span>
                <pre
                  className={cn(
                    "mt-2 overflow-x-auto whitespace-pre-wrap font-mono text-xs leading-relaxed",
                    read ? "text-ink" : "text-faint"
                  )}
                >
                  {highlight(sectionText(s), read)}
                </pre>
              </div>
            );
          })}
        </div>

        <aside className="flex flex-col bg-bg p-5" aria-live="polite">
          <span className="text-xs font-medium uppercase tracking-wide text-faint">Verdict</span>
          <p
            className={cn(
              "mt-1 font-display text-3xl font-semibold",
              rejected ? "text-proof-block" : "text-proof-pass"
            )}
          >
            {rejected ? "REJECT" : "COMPLETE"}
          </p>
          <div className="mt-4">
            <KeyValues className="sm:grid-cols-[minmax(0,8rem)_1fr]">
              <KeyValue label="sections read">
                <span className="font-mono text-xs tnum">
                  {result.sections_read} of {result.sections}
                </span>
              </KeyValue>
              <KeyValue label="failed checks">
                <span className="font-mono text-xs">
                  {result.failed_checks.length ? result.failed_checks.join(", ") : "none"}
                </span>
              </KeyValue>
            </KeyValues>
          </div>
          <p className="mt-4 text-[13px] leading-relaxed text-muted">
            {rejected
              ? "The placeholder in the third section is inside the read window, so it is caught."
              : "The third section is never opened at this depth, so the placeholder it contains is never seen."}
          </p>
        </aside>
      </div>

      <details className="group border-t border-border">
        <summary className="cursor-pointer list-none px-5 py-4 text-sm text-muted transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
          Shown in English. The bytes that were hashed are the Indonesian original, open to read
          them.
        </summary>
        <div className="px-5 pb-5">
          <p className="max-w-3xl text-[13px] leading-relaxed text-muted">
            The translation above is structurally faithful: run through the same check code it
            yields the same three sections and the same two verdicts. Only the original below was
            hashed
            {hash ? (
              <>
                {", "}
                <span className="break-all font-mono text-xs text-ink">{hash}</span>
              </>
            ) : null}
            .
          </p>
          <pre className="mt-3 overflow-x-auto rounded-xl border border-border bg-bg px-4 py-3.5 font-mono text-xs leading-relaxed text-ink">
            {text}
          </pre>
        </div>
      </details>
    </div>
  );
}

/**
 * Tandai token placeholder HANYA di seksi yang benar-benar dibaca, menyorotnya di
 * seksi yang tidak dibaca akan berbohong tentang apa yang dilihat wasitnya.
 *
 * @param {string} body
 * @param {boolean} read
 */
function highlight(body, read) {
  if (!read) return body;
  const parts = body.split(/(TODO)/g);
  return parts.map((part, i) =>
    part === "TODO" ? (
      <mark
        key={i}
        className="rounded bg-proof-review/25 px-1 text-ink [box-decoration-break:clone]"
      >
        {part}
      </mark>
    ) : (
      part
    )
  );
}
