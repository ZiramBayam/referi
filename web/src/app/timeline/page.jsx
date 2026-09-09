import { Fragment } from "react";
import Link from "next/link";
import { loadIndex } from "../../lib/data.js";
import { formatUsdc6 } from "../../lib/canonical.js";
import { acpStatusLabel, verdictKindLabel, EXPLORER_NAME } from "../../lib/chain.js";
import { TxLink, AddressLink, shorten } from "../../components/Links.jsx";
import Icon from "../../components/Icon.jsx";

export const metadata = {
  title: "Timeline — REFERI",
  description:
    "The five jobs that landed on Base Sepolia, each verdict linked to the transaction that announced it.",
};

/**
 * Batang kedalaman. `sampling` membaca 2 bagian pertama (SAMPLING_SECTION_LIMIT
 * di `agent/agent/checks/base.py`), `full` membaca semuanya.
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

  return (
    <div>
      <p className="lead">
        <Link href="/" className="backlink">
          <Icon name="arrow-left" size={14} />
          REFERI
        </Link>
      </p>

      <h1 id="record">Five jobs that really landed on chain</h1>
      <p className="lead">
        Ordered by jobId. The &quot;verdict&quot; column is the <code>kind</code> announced by{" "}
        <code>EvaluatorVault.postVerdict</code>; the &quot;ACP status&quot; column is the
        ERC-8183 job status enum. Every verdict links to its own <code>VerdictPosted</code>{" "}
        transaction on {EXPLORER_NAME} — that explorer is used because it is the only one that
        picks up the vault contract&apos;s Sourcify verification, so event names show up decoded
        instead of as raw topics.
      </p>

      <div className="table-wrap" data-reveal>
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
              <Fragment key={job.jobId}>
              <tr>
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
                    <Icon name={job.verdictKind === 1 ? "check" : "x"} size={11} />
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
              {/* Catatan per job dulu hidup sebagai daftar terpisah di bawah tabel,
                  mengulang kelima job yang sama. Ia milik barisnya. */}
              <tr className="note-row">
                <td />
                <td colSpan={7}>{job.note}</td>
              </tr>
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

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
