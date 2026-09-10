// Tabel bukti per-kriteria. SATU komponen dipakai oleh /verdict/[jobId] (bukti yang
// sudah mendarat di chain) dan /panel (evaluasi ulang atas teks yang ditempel juri),
// supaya juri melihat bentuk bukti yang sama persis di kedua tempat.
//
// KEAMANAN: `detail` dan `proof` adalah TEKS PIHAK, dan `proof` adalah kutipan mentah
// dari deliverable pihak lain. Keduanya dirender sebagai CHILDREN React, yang di-escape
// otomatis. Jalur "sisipkan HTML mentah" tidak dipakai di berkas ini maupun di rute
// bukti mana pun; satu-satunya pemakaiannya di repo ini ada di root layout, untuk dua
// string yang ditulis pengembang (kontrak arah dan skrip tema anti-FOUC).

import { KeyValue, KeyValues, NotAvailable, Tag } from "./PageShell.jsx";
import { gloss } from "../lib/gloss.js";

/** @param {{ text: string }} props */
function Gloss({ text }) {
  const en = gloss(text);
  if (!en) return null;
  return (
    <span className="mt-1.5 flex items-start gap-2 text-[13px] leading-relaxed text-muted">
      <span className="mt-px shrink-0 rounded border border-border px-1 font-mono text-[10px] uppercase text-faint">
        en
      </span>
      {en}
    </span>
  );
}

/**
 * @param {{ checks: { check: string, criterion: string, status: string, detail: string,
 *   proof: string, pattern: string, section: number | null, depth: string }[],
 *   criteria?: { id: string, kind: string, text: string, check: string }[] }} props
 */
export default function Checks({ checks, criteria }) {
  if (!checks || checks.length === 0) {
    return (
      <p className="text-sm text-faint">
        not available. This bundle carries no <code className="font-mono">evaluation</code> block,
        so there are no per-criterion check results to show.
      </p>
    );
  }
  /** @type {Record<string, string>} */
  const criterionText = {};
  for (const c of criteria ?? []) criterionText[c.id] = c.text;

  return (
    <div className="flex flex-col gap-4">
      {checks.map((c, i) => (
        <article
          key={c.criterion + ":" + i}
          className="overflow-hidden rounded-2xl border border-border bg-surface"
        >
          <header className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
            <h3 className="min-w-0 truncate font-mono text-sm font-medium text-ink">
              {c.criterion}
            </h3>
            <Tag status={c.status} />
          </header>

          <div className="px-5 py-4">
            {criterionText[c.criterion] && (
              <p className="mb-4 max-w-prose text-sm leading-relaxed text-ink">
                {criterionText[c.criterion]}
                <Gloss text={criterionText[c.criterion]} />
              </p>
            )}

            <KeyValues>
              <KeyValue label="check">
                <span className="font-mono text-xs">{c.check}</span>
              </KeyValue>
              <KeyValue label="depth">
                <span className="font-mono text-xs">{c.depth}</span>
              </KeyValue>
              <KeyValue label="section">
                <span className="font-mono text-xs">
                  {c.section === null || c.section === undefined ? (
                    <NotAvailable />
                  ) : c.section < 0 ? (
                    "-1 (points at no single section)"
                  ) : (
                    String(c.section)
                  )}
                </span>
              </KeyValue>
              <KeyValue label="pattern id">
                <span className="font-mono text-xs">
                  {c.pattern ? c.pattern : <span className="text-faint">none</span>}
                </span>
              </KeyValue>
              <KeyValue label="reason">
                <span className="leading-relaxed">
                  {c.detail}
                  <Gloss text={c.detail} />
                </span>
              </KeyValue>
            </KeyValues>

            <div className="mt-5">
              <h4 className="text-xs font-medium uppercase tracking-wide text-faint">
                Evidence (proof)
              </h4>
              {c.proof ? (
                <pre className="mt-2 overflow-x-auto rounded-xl border border-border bg-bg px-4 py-3.5 font-mono text-xs leading-relaxed text-ink">
                  {c.proof}
                </pre>
              ) : (
                <p className="mt-2 text-sm text-faint">
                  not available. This check passed or was not verified, so the agent stored no
                  excerpt.
                </p>
              )}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
