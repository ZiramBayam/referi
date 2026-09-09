import { Fragment } from "react";
import Link from "next/link";
import { loadIndex, loadDeliverable } from "../lib/data.js";
import { formatUsdc6 } from "../lib/canonical.js";
import { acpStatusLabel, verdictKindLabel, EXPLORER_NAME } from "../lib/chain.js";
import { TxLink, AddressLink, shorten } from "../components/Links.jsx";
import Icon from "../components/Icon.jsx";
import ReadWindow from "../components/ReadWindow.jsx";

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

  // Teks deliverable yang dipakai peraga interaktif diambil dari artefak yang
  // SAMA yang di-hash ke chain, bukan disalin ke dalam komponen.
  const twinText = await loadDeliverable("422").catch(() => null);

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
          <h1>
            Identical text. <em>Opposite verdicts.</em>
          </h1>
          <p className="sub">
            Two jobs, the same bytes, the same budget — one passed, one rejected. The only
            difference was what this referee remembered about the provider.
          </p>
          <div className="actions">
            <Link className="go" href={"/verdict/" + rejected.jobId}>
              Open the evidence for job {rejected.jobId}
              <Icon name="arrow-right" size={14} />
            </Link>
            <a className="quiet" href="#record">
              or read the record
            </a>
          </div>

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

          <p className="more">how that difference is produced</p>
        </section>
      ) : null}

      <h2>How that difference is produced</h2>
      <p className="lead">
        Three steps, in this order. Nothing here is a judgement call by a model — every step is
        a deterministic rule you can read in the repository.
      </p>

      <ol className="steps">
        <li>
          <span className="n">1</span>
          <h3>Memory accrues</h3>
          <p>
            Every deterministic check failure is quarantined against the provider that caused
            it. A pattern that fails on <strong>two different jobs</strong> is promoted to a
            confirmed pattern on that provider&apos;s record.
          </p>
          <span className="src">agent/agent/memory_policy.py</span>
        </li>
        <li>
          <span className="n">2</span>
          <h3>Memory sets the reading depth</h3>
          <p>
            A provider with a clean record is <strong>sampled</strong> — only the first two
            sections are read. A provider carrying confirmed incidents is read in{" "}
            <strong>full</strong>. Same checks either way; different amount of the work seen.
          </p>
          <span className="src">SAMPLING_SECTION_LIMIT = 2</span>
        </li>
        <li>
          <span className="n">3</span>
          <h3>The verdict carries its own root</h3>
          <p>
            <code>postVerdict</code> announces the reason hash together with the{" "}
            <code>memoryRoot</code> the decision was made against, so the verdict can be checked
            later against the memory that produced it.
          </p>
          <span className="src">contracts/src/EvaluatorVault.sol</span>
        </li>
      </ol>

      {twinText?.text ? (
        <>
          <h2>Read it the way the referee did</h2>
          <p className="lead">
            This is the deliverable from job 422, read by the same check code that produced
            the on-chain bundles. Move the depth and watch the third section — and the verdict
            — change.
          </p>
          <ReadWindow text={twinText.text} hash={twinText.sha_keccak} />
        </>
      ) : null}

      <h2 id="record">Five jobs that really landed on chain</h2>
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
