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

      <h2>What this is</h2>
      <p className="lead">
        REFERI is a referee for escrow, not a marketplace and not a wallet. When a client
        creates an ERC-8183 job they name an evaluator; point that at this vault and REFERI
        decides whether the escrowed money is released to the provider or refunded to the
        client — and it remembers that provider on the next job.
      </p>

      <div className="what" data-reveal>
        <div>
          <h3>Who it is for</h3>
          <p>
            Anyone buying work from the same providers more than once. Meet a provider twice
            and a forgetful referee turns into repeated loss.
          </p>
        </div>
        <div>
          <h3>How it is wired in</h3>
          <p>
            Set <code>evaluatorAddress</code> to the vault when the job is created. That is the
            whole integration — no hook to whitelist, no SDK to adopt.
          </p>
        </div>
        <div>
          <h3>What it changes</h3>
          <p>
            A standard ERC-8183 evaluator is stateless, so the same provider can repeat the
            same trick on the next job and leave no trace. This one carries a record, and
            announces its hash on chain with every verdict.
          </p>
        </div>
      </div>

      <h2>How that difference is produced</h2>
      <p className="lead">
        Three steps, in this order. Nothing here is a judgement call by a model — every step is
        a deterministic rule you can read in the repository.
      </p>

      <ol className="steps" data-reveal>
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
          <div data-reveal>
            <ReadWindow text={twinText.text} hash={twinText.sha_keccak} />
          </div>
        </>
      ) : null}

      <h2>Why this could not just be mocked</h2>
      <p className="lead">
        A page can claim anything. These four are checkable without trusting a word of it —
        three of them from a block explorer, one from your own terminal.
      </p>

      <ol className="proofs" data-reveal>
        <li>
          <h3>The reason is bound to the transaction</h3>
          <p>
            Hash the evidence bundle served at <code>/verdicts/422.json</code> and you get the
            <code> reasonHash</code> carried by the <code>VerdictPosted</code> transaction. A
            mock would have to forge a Base Sepolia transaction to match.
          </p>
        </li>
        <li>
          <h3>The pair is readable on chain</h3>
          <p>
            Jobs 421 and 422 hold byte-identical deliverables and ended in opposite states.
            Read both from the explorer instead of from here — this page renders artifacts, it
            does not produce them.
          </p>
        </li>
        <li>
          <h3>Deleting the memory stops it</h3>
          <p>
            Remove <code>memory.db</code> and the agent posts nothing at all: no verdict, no
            finalize, the wallet nonce unmoved. Something with nothing to lose has nothing to
            stop for.
          </p>
        </li>
        <li>
          <h3>There is no model in the decision</h3>
          <p>
            The checks are deterministic code, and the qualitative criteria are recorded as
            unscored rather than quietly passed. A referee that makes judgement calls cannot be
            audited afterwards — that was the trade.
          </p>
        </li>
      </ol>

      <h2>See the whole record</h2>
      <p className="lead">
        Every claim above is backed by an artifact you can open. The timeline lists the five
        jobs that landed on Base Sepolia with the transaction that announced each verdict, and
        the judge panel runs the same checks on any text you paste into it.
      </p>
      <div className="outro" data-reveal>
        <Link className="go" href="/timeline">
          Open the timeline
          <Icon name="arrow-right" size={14} />
        </Link>
        <Link className="go ghost" href="/panel">
          Try the judge panel
          <Icon name="arrow-right" size={14} />
        </Link>
      </div>
    </div>
  );
}
