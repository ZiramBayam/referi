import Link from "next/link";
import Icon from "../../../components/Icon.jsx";
import { notFound } from "next/navigation";
import { loadJobs, loadJob, loadBundle, loadDeliverable } from "../../../lib/data.js";
import { readSmallInt, readUint, readSectionIndex, formatUsdc6 } from "../../../lib/canonical.js";
import { acpStatusLabel, verdictKindLabel } from "../../../lib/chain.js";
import { TxLink, AddressLink, Hash, shorten } from "../../../components/Links.jsx";
import Checks from "../../../components/Checks.jsx";

export async function generateStaticParams() {
  const jobs = await loadJobs();
  return jobs.map((/** @type {{ jobId: string }} */ j) => ({ jobId: j.jobId }));
}

/** @param {{ params: Promise<{ jobId: string }> }} props */
export default async function VerdictPage({ params }) {
  const { jobId } = await params;
  const job = await loadJob(jobId);
  const bundle = await loadBundle(jobId);
  if (!job || !bundle) notFound();

  const deliverable = await loadDeliverable(jobId);
  const evaluation = bundle.evaluation ?? null;
  const gate = bundle.gate ?? null;

  const checks = (evaluation?.checks ?? []).map((/** @type {any} */ c) => ({
    check: c.check,
    criterion: c.criterion,
    status: c.status,
    detail: c.detail,
    proof: c.proof,
    pattern: c.pattern,
    section: readSectionIndex(c.section),
    depth: c.depth,
  }));

  return (
    <div>
      <p className="lead">
        <Link href="/" className="backlink">
          <Icon name="arrow-left" size={14} />
          job timeline
        </Link>
      </p>
      <h2>
        Verdict for job <span className="mono">{jobId}</span> —{" "}
        {verdictKindLabel(readSmallInt(bundle.verdict))}
      </h2>
      <p className="lead">
        Why it was decided this way, and what the evidence is. Everything on this page is the
        evidence bundle that is keccak-hashed into the <code>reasonHash</code> of the{" "}
        <code>VerdictPosted</code> transaction — not a rewritten summary.
      </p>
      <p className="lead">
        <strong>Bundle strings are quoted, not translated.</strong> The gate <code>reason</code>,
        each criterion&apos;s text, and every <code>reason</code>/<code>proof</code> line below are
        the agent&apos;s own output, copied out of the bundle byte for byte. They are written in
        Indonesian and stay that way on purpose: the bundle is what gets hashed into{" "}
        <code>reasonHash</code>, so rewording it here would stop matching the chain.
      </p>

      <div className="card">
        <dl className="kv">
          <dt>bundle version</dt>
          <dd className="mono">{bundle.version}</dd>
          <dt>bundle shape</dt>
          <dd className="mono">{bundle.kind}</dd>
          <dt>memory mode</dt>
          <dd className="mono">{bundle.mode}</dd>
          <dt>memory_root (from the agent)</dt>
          <dd>
            <Hash value={bundle.memory_root} />
          </dd>
          <dt>check depth</dt>
          <dd className="mono">{evaluation?.depth ?? gate?.depth ?? "—"}</dd>
          <dt>provider</dt>
          <dd>
            <AddressLink address={job.provider} /> ({job.providerLabel})
          </dd>
          <dt>budget</dt>
          <dd className="mono">
            {formatUsdc6(job.budgetUsdc6) ?? <span className="none">not available</span>} units of
            the escrow token (6 decimals)
          </dd>
          <dt>last ACP status</dt>
          <dd>{acpStatusLabel(job.acpStatus)}</dd>
          <dt>deliverable hash</dt>
          <dd>
            <Hash value={evaluation?.deliverable} />
          </dd>
          <dt>VerdictPosted tx</dt>
          <dd>
            <TxLink hash={job.verdictTxHash} />
          </dd>
          <dt>finalize tx</dt>
          <dd>
            <TxLink hash={job.finalizeTxHash} />
          </dd>
          <dt>bundle file</dt>
          <dd className="mono">
            agent/data/chain-abc/verdicts/{job.bundleFile}
            <div style={{ color: "var(--muted)" }}>
              file name = keccak256 of the file contents; a verbatim copy is served at{" "}
              <a href={"/verdicts/" + jobId + ".json"}>/verdicts/{jobId}.json</a>
            </div>
          </dd>
        </dl>
      </div>

      <p className="lead">
        <strong>memory_root is shown as-is.</strong> This page does not compute the root: the
        value above is read straight from the bundle the agent wrote, and the root that BINDS is
        the one recorded in the <code>VerdictPosted</code> transaction above.
      </p>

      {gate ? (
        <div>
          <h2>Gate decision (no deliverable evaluated)</h2>
          <p className="lead">
            This job was rejected <em>before</em> any deliverable was scored, so its bundle has
            the shape <code>gate-rejection</code> and carries no per-criterion check results.
          </p>
          <div className="card">
            <dl className="kv">
              <dt>accepted?</dt>
              <dd>
                <span className={"tag " + (gate.accept ? "pass" : "fail")}>
                  {gate.accept ? "accept" : "reject"}
                </span>
              </dd>
              <dt>reason</dt>
              <dd>{gate.reason}</dd>
              <dt>budget</dt>
              <dd className="mono">{readUint(gate.budget) ?? "not available"}</dd>
              <dt>provider cap</dt>
              <dd className="mono">
                {readUint(gate.cap?.usdc) ?? <span className="none">not available</span>} (basis{" "}
                {gate.cap?.basis ?? "—"}, sample_size {readUint(gate.cap?.sample_size) ?? "—"})
              </dd>
              <dt>risk level</dt>
              <dd className="mono">{readUint(gate.risk_level) ?? "not available"}</dd>
              <dt>incident jobs behind it</dt>
              <dd>
                {(gate.incident_jobs ?? []).length === 0 ? (
                  <span className="none">not available</span>
                ) : (
                  gate.incident_jobs.map((/** @type {any} */ j, i) => {
                    const id = readUint(j);
                    return (
                      <span key={i} className="mono">
                        {i > 0 ? ", " : ""}
                        {id ? <Link href={"/verdict/" + id}>{id}</Link> : "not available"}
                      </span>
                    );
                  })
                )}
              </dd>
              <dt>provider</dt>
              <dd>
                <AddressLink address={gate.provider} label={shorten(gate.provider)} />
              </dd>
            </dl>
          </div>
        </div>
      ) : null}

      {evaluation ? (
        <div>
          <h2>Per-criterion evidence</h2>
          <p className="lead">
            Rubric category <code>{evaluation.category}</code>, depth{" "}
            <code>{evaluation.depth}</code>. <code>failed_checks</code>:{" "}
            <span className="mono">
              {evaluation.failed_checks.length ? evaluation.failed_checks.join(", ") : "[] (empty)"}
            </span>
          </p>
          <Checks checks={checks} criteria={evaluation.criteria} />

          {evaluation.unscored?.length ? (
            <div className="card warn">
              <h3 style={{ marginTop: 0 }}>Criteria that were NOT scored</h3>
              <p className="mono">{evaluation.unscored.join(", ")}</p>
              <p style={{ marginBottom: 0 }}>{evaluation.unscored_reason}</p>
            </div>
          ) : null}
        </div>
      ) : null}

      <h2>The deliverable that was scored</h2>
      {deliverable ? (
        <div className="card">
          <dl className="kv">
            <dt>keccak256(text)</dt>
            <dd>
              <Hash value={deliverable.sha_keccak} />
            </dd>
          </dl>
          <pre className="doc">{deliverable.text}</pre>
        </div>
      ) : (
        <p className="none">
          not available — this job was rejected before the provider ever submitted, so no
          deliverable text was stored.
        </p>
      )}
    </div>
  );
}
