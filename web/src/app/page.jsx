import Link from "next/link";
import { loadIndex } from "../lib/data.js";
import { formatUsdc6 } from "../lib/canonical.js";
import { acpStatusLabel, verdictKindLabel, EXPLORER_NAME } from "../lib/chain.js";
import { TxLink, AddressLink, shorten } from "../components/Links.jsx";

/**
 * Batang kedalaman. `sampling` membaca 2 bagian pertama (SAMPLING_SECTION_LIMIT
 * di `agent/agent/checks/base.py`), `full` membaca semuanya — jadi kedalaman
 * punya bentuk, bukan cuma kata.
 *
 * @param {{ depth?: string }} props
 */
function DepthBar({ depth }) {
  const total = 6;
  const on = depth === "full" ? total : depth === "sampling" ? 2 : 0;
  return (
    <span className="depthbar" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <i key={i} className={i < on ? "on" : ""} />
      ))}
    </span>
  );
}

export default async function TimelinePage() {
  const index = await loadIndex();
  const jobs = index.jobs;

  // Pasangan tesis: dua job dengan deliverable byte-identik dan anggaran sama.
  // Dicari DARI data, bukan ditulis tangan — kalau artefaknya berubah, hero ikut
  // berubah atau hilang, dan tidak pernah mengklaim sesuatu yang tidak ada.
  const twins = jobs.filter(
    (/** @type {any} */ j) =>
      j.deliverableHash &&
      jobs.some(
        (/** @type {any} */ k) =>
          k !== j && k.deliverableHash === j.deliverableHash && k.budgetUsdc6 === j.budgetUsdc6
      )
  );
  const passed = twins.find((/** @type {any} */ j) => j.verdictKind === 1);
  const rejected = twins.find((/** @type {any} */ j) => j.verdictKind === 2);
  return (
    <div>
      {passed && rejected ? (
        <section className="hero">
          <p className="eyebrow">Evidence anchored on chain</p>
          <h1>
            Identical text. <em>Opposite verdicts.</em>
          </h1>
          <p className="sub">
            Jobs {passed.jobId} and {rejected.jobId} carry byte-for-byte identical deliverables
            at the same budget. One passed, one was rejected. The only thing that differed was
            what this referee remembered about the provider — and that memory set how deeply
            the work was read.
          </p>

          <div className="plates">
            <div className="plate is-pass">
              <span className="id">job {passed.jobId} · {passed.providerLabel}</span>
              <p className="verdict">{verdictKindLabel(passed.verdictKind)}</p>
              <dl>
                <dt>check depth</dt>
                <dd>{passed.depth || "—"}</dd>
                <dt>budget</dt>
                <dd>{formatUsdc6(passed.budgetUsdc6) ?? "—"}</dd>
                <dt>on chain</dt>
                <dd>{acpStatusLabel(passed.acpStatus)}</dd>
              </dl>
            </div>

            <div className="plate-split">
              <span>same bytes</span>
            </div>

            <div className="plate is-fail">
              <span className="id">job {rejected.jobId} · {rejected.providerLabel}</span>
              <p className="verdict">{verdictKindLabel(rejected.verdictKind)}</p>
              <dl>
                <dt>check depth</dt>
                <dd>{rejected.depth || "—"}</dd>
                <dt>budget</dt>
                <dd>{formatUsdc6(rejected.budgetUsdc6) ?? "—"}</dd>
                <dt>on chain</dt>
                <dd>{acpStatusLabel(rejected.acpStatus)}</dd>
              </dl>
            </div>
          </div>

          <p className="shared">
            keccak256 of both deliverables <b>{shorten(passed.deliverableHash)}</b>
          </p>
        </section>
      ) : null}

      <h2>Five jobs that really landed on chain</h2>
      <p className="lead">
        Ordered by jobId. The &quot;verdict&quot; column is the <code>kind</code> announced by{" "}
        <code>EvaluatorVault.postVerdict</code>; the &quot;ACP status&quot; column is the
        ERC-8183 job status enum. Every verdict links to its own <code>VerdictPosted</code>{" "}
        transaction on {EXPLORER_NAME} — that explorer is used because it is the only one that
        picks up the vault contract&apos;s Sourcify verification, so event names show up decoded
        instead of as raw topics.
      </p>

      <div className="table-wrap">
        <table>
          <caption>
            Jobs 418–422: provider, budget, on-chain status, and the verdict announced for each.
          </caption>
          <thead>
            <tr>
              <th scope="col">Job</th>
              <th scope="col">Provider</th>
              <th scope="col">Budget</th>
              <th scope="col">Depth</th>
              <th scope="col">ACP status</th>
              <th scope="col">Verdict</th>
              <th scope="col">VerdictPosted tx</th>
              <th scope="col">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((/** @type {any} */ job) => (
              <tr key={job.jobId}>
                <td className="mono">
                  <strong>{job.jobId}</strong>
                </td>
                <td>
                  <AddressLink address={job.provider} label={shorten(job.provider)} />
                  <div style={{ color: "var(--dim)", fontSize: 12 }}>{job.providerLabel}</div>
                </td>
                <td className="mono">
                  {formatUsdc6(job.budgetUsdc6) ?? <span className="none">not available</span>}
                </td>
                <td className="mono">
                  <DepthBar depth={job.depth} />
                  {job.depth || "—"}
                </td>
                <td>{acpStatusLabel(job.acpStatus)}</td>
                <td>
                  <span className={"tag " + (job.verdictKind === 1 ? "pass" : "fail")}>
                    {verdictKindLabel(job.verdictKind)}
                  </span>
                  <div style={{ color: "var(--dim)", fontSize: 12 }}>{job.bundleKind}</div>
                </td>
                <td>
                  <TxLink hash={job.verdictTxHash} label={shorten(job.verdictTxHash)} />
                </td>
                <td>
                  <Link href={"/verdict/" + job.jobId}>open evidence</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>What happened, in order</h2>
      <ul className="lead">
        {jobs.map((/** @type {any} */ job) => (
          <li key={job.jobId}>
            <strong className="mono">job {job.jobId}</strong> — {job.note}
          </li>
        ))}
      </ul>

      <h2>Where these numbers come from</h2>
      <div className="card note">
        <dl className="kv">
          {Object.entries(index.source).map(([key, value]) => (
            <div key={key} style={{ display: "contents" }}>
              <dt className="mono">{key}</dt>
              <dd>{String(value)}</dd>
            </div>
          ))}
        </dl>
        <p className="lead" style={{ marginBottom: 0 }}>
          This page makes no RPC calls, connects no wallet, and computes no hashes. It only
          renders artifacts that already exist in the repository.
        </p>
      </div>
    </div>
  );
}
