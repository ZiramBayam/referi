import Link from "next/link";
import { loadIndex } from "../lib/data.js";
import { formatUsdc6 } from "../lib/canonical.js";
import { acpStatusLabel, verdictKindLabel, EXPLORER_NAME } from "../lib/chain.js";
import { TxLink, AddressLink, shorten } from "../components/Links.jsx";

export default async function TimelinePage() {
  const index = await loadIndex();
  const jobs = index.jobs;

  return (
    <div>
      <h2>Job timeline 418–422 (Base Sepolia)</h2>
      <p className="lead">
        Five jobs that really landed on chain, ordered by jobId. The &quot;verdict&quot; column
        is the <code>kind</code> announced by <code>EvaluatorVault.postVerdict</code>; the
        &quot;ACP status&quot; column is the ERC-8183 job status enum. Every verdict links to its
        own <code>VerdictPosted</code> transaction on {EXPLORER_NAME} — that explorer is used
        because it is the only one that picks up the vault contract&apos;s Sourcify
        verification, so event names show up decoded instead of as raw topics.
      </p>

      <table>
        <thead>
          <tr>
            <th>Job</th>
            <th>Provider</th>
            <th>Budget</th>
            <th>ACP status</th>
            <th>Verdict</th>
            <th>Bundle shape</th>
            <th>VerdictPosted tx</th>
            <th>Evidence</th>
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
                <div style={{ color: "var(--muted)", fontSize: 12 }}>{job.providerLabel}</div>
              </td>
              <td className="mono">
                {formatUsdc6(job.budgetUsdc6) ?? <span className="none">not available</span>}
              </td>
              <td>{acpStatusLabel(job.acpStatus)}</td>
              <td>
                <span className={"tag " + (job.verdictKind === 1 ? "pass" : "fail")}>
                  {verdictKindLabel(job.verdictKind)}
                </span>
              </td>
              <td className="mono">
                {job.bundleKind}
                <div style={{ color: "var(--muted)" }}>depth {job.depth || "—"}</div>
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

      <h2>What happened, in order</h2>
      <ul className="lead">
        {jobs.map((/** @type {any} */ job) => (
          <li key={job.jobId}>
            <strong className="mono">job {job.jobId}</strong> — {job.note}
          </li>
        ))}
      </ul>

      <div className="card note">
        <h3 style={{ marginTop: 0 }}>Where the numbers on this page come from</h3>
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
