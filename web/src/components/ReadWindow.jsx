"use client";

import { useMemo, useState } from "react";
import {
  parseDocument,
  sectionsInScope,
  sectionText,
  evaluateText,
  DEPTH_SAMPLING,
  DEPTH_FULL,
} from "../lib/checks.js";
import Icon from "./Icon.jsx";
import { DELIVERABLE_EN } from "../lib/gloss.js";

/**
 * "Baca seperti wasitnya membaca."
 *
 * Ini BUKAN peragaan. Tombolnya memanggil `evaluateText` — fungsi yang sama yang
 * menghasilkan bundel bukti on-chain, dan yang paritasnya dijaga
 * `test/checks-parity.test.js` terhadap bundel job 421/422. Jadi verdict yang
 * berkedip saat kamu menggeser kedalaman adalah verdict yang sesungguhnya, bukan
 * angka yang ditulis tangan ke dalam komponen.
 *
 * Yang membuatnya bisa dimainkan: pada `sampling` seksi ketiga TIDAK dibaca, dan
 * `TODO` yang ada di sana lolos. Pada `full` seksi itu menyala dan verdictnya
 * berbalik. Itulah seluruh tesis produk ini, dalam satu klik.
 *
 * @param {{ text: string, hash?: string }} props — `text` adalah byte ASLI yang
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
      inScope: new Set(scope.map((s) => s.index)),
      result: evaluateText(DELIVERABLE_EN, depth),
    };
  }, [depth]);

  const rejected = result.verdict === 2;

  return (
    <div className="readwin">
      <div className="readwin-controls" role="group" aria-label="Check depth">
        <button
          type="button"
          className={depth === DEPTH_SAMPLING ? "on" : ""}
          aria-pressed={depth === DEPTH_SAMPLING}
          onClick={() => setDepth(DEPTH_SAMPLING)}
        >
          sampling
          <em>provider with a clean record</em>
        </button>
        <button
          type="button"
          className={depth === DEPTH_FULL ? "on" : ""}
          aria-pressed={depth === DEPTH_FULL}
          onClick={() => setDepth(DEPTH_FULL)}
        >
          full
          <em>provider carrying incidents</em>
        </button>
      </div>

      <div className="readwin-body">
        <div className="doc">
          {sections.map((s) => {
            const read = inScope.has(s.index);
            return (
              <div key={s.index} className={read ? "sec read" : "sec"}>
                <span className="marker">
                  {read ? (
                    <>
                      <Icon name="check" size={11} /> read
                    </>
                  ) : (
                    "not read at this depth"
                  )}
                </span>
                <pre>{highlight(sectionText(s), read)}</pre>
              </div>
            );
          })}
        </div>

        <aside className={rejected ? "out is-fail" : "out is-pass"} aria-live="polite">
          <span className="k">Verdict</span>
          <p className="v">{rejected ? "REJECT" : "COMPLETE"}</p>
          <dl>
            <dt>sections read</dt>
            <dd>
              {result.sections_read} of {result.sections}
            </dd>
            <dt>failed checks</dt>
            <dd>
              {result.failed_checks.length ? result.failed_checks.join(", ") : "none"}
            </dd>
          </dl>
          <p className="why">
            {rejected
              ? "The placeholder in the third section is inside the read window, so it is caught."
              : "The third section is never opened at this depth, so the placeholder it contains is never seen."}
          </p>
        </aside>
      </div>

      <details className="source">
        <summary>
          Shown in English. The bytes that were hashed are the Indonesian original —
          open to read them.
        </summary>
        <p className="note-line">
          The translation above is structurally faithful: run through the same check
          code it yields the same three sections and the same two verdicts. Only the
          original below was hashed
          {hash ? (
            <>
              {" "}
              — <span className="mono">{hash}</span>
            </>
          ) : null}
          .
        </p>
        <pre>{text}</pre>
      </details>
    </div>
  );
}

/**
 * Tandai token placeholder HANYA di seksi yang benar-benar dibaca — menyorotnya di
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
      <mark key={i}>{part}</mark>
    ) : (
      part
    )
  );
}
