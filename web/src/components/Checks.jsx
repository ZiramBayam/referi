// Tabel bukti per-kriteria. SATU komponen dipakai oleh /verdict/[jobId] (bukti yang
// sudah mendarat di chain) dan /panel (evaluasi ulang atas teks yang ditempel juri),
// supaya juri melihat bentuk bukti yang sama persis di kedua tempat.
//
// KEAMANAN: `detail` dan `proof` adalah TEKS PIHAK, dan `proof` adalah kutipan mentah
// dari deliverable pihak lain. Keduanya dirender sebagai CHILDREN React, yang di-escape
// otomatis. Jalur "sisipkan HTML mentah" tidak dipakai di berkas ini maupun di mana pun
// di `web/src`; AC task ini menuntut grep atas nama prop itu mengembalikan hasil KOSONG,
// jadi namanya sengaja tidak ditulis di sini juga.

import Icon from "./Icon.jsx";
import { gloss } from "../lib/gloss.js";

/**
 * @param {{ checks: { check: string, criterion: string, status: string, detail: string,
 *   proof: string, pattern: string, section: number | null, depth: string }[],
 *   criteria?: { id: string, kind: string, text: string, check: string }[] }} props
 */
export default function Checks({ checks, criteria }) {
  if (!checks || checks.length === 0) {
    return (
      <p className="none">
        not available — this bundle carries no `evaluation` block, so there are no
        per-criterion check results to show.
      </p>
    );
  }
  /** @type {Record<string, string>} */
  const criterionText = {};
  for (const c of criteria ?? []) criterionText[c.id] = c.text;

  return (
    <div>
      {checks.map((c, i) => (
        <div className="card" key={c.criterion + ":" + i}>
          <div className="row" style={{ margin: 0, justifyContent: "space-between" }}>
            <strong className="mono">{c.criterion}</strong>
            <span className={"tag " + c.status}>
              <Icon name={c.status === "pass" ? "check" : c.status === "fail" ? "x" : "triangle-alert"} size={11} />
              {c.status}
            </span>
          </div>
          {criterionText[c.criterion] ? (
            <p className="lead" style={{ margin: "6px 0" }}>
              {criterionText[c.criterion]}
              {gloss(criterionText[c.criterion]) ? (
                <span className="gloss">
                  <span>EN</span>
                  {gloss(criterionText[c.criterion])}
                </span>
              ) : null}
            </p>
          ) : null}
          <dl className="kv" style={{ marginTop: 6 }}>
            <dt>check</dt>
            <dd className="mono">{c.check}</dd>
            <dt>depth</dt>
            <dd className="mono">{c.depth}</dd>
            <dt>section</dt>
            <dd className="mono">
              {c.section === null || c.section === undefined ? (
                <span className="none">not available</span>
              ) : c.section < 0 ? (
                "-1 (points at no single section)"
              ) : (
                String(c.section)
              )}
            </dd>
            <dt>pattern id</dt>
            <dd className="mono">{c.pattern ? c.pattern : <span className="none">none</span>}</dd>
            <dt>reason</dt>
            <dd>
              {c.detail}
              {gloss(c.detail) ? (
                <span className="gloss">
                  <span>EN</span>
                  {gloss(c.detail)}
                </span>
              ) : null}
            </dd>
          </dl>
          <h3 style={{ marginBottom: 0 }}>evidence (proof)</h3>
          {c.proof ? (
            <pre className="proof">{c.proof}</pre>
          ) : (
            <p className="none" style={{ marginTop: 4 }}>
              not available — this check passed or was not verified, so the agent stored no
              excerpt.
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
