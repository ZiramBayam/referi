import Link from "next/link";
import { notFound } from "next/navigation";
import { gloss, glossSection } from "../../../lib/gloss.js";
import { parseDocument } from "../../../lib/checks.js";
import { loadJobs, loadJob, loadBundle, loadDeliverable } from "../../../lib/data.js";
import { readSmallInt, readUint, readSectionIndex, formatUsdc6 } from "../../../lib/canonical.js";
import { acpStatusLabel, verdictKindLabel } from "../../../lib/chain.js";
import { TxLink, AddressLink, Hash, shorten } from "../../../components/Links.jsx";
import Checks from "../../../components/Checks.jsx";
import {
  GroupLabel,
  KeyValue,
  KeyValues,
  Notice,
  NotAvailable,
  Page,
  PageHeader,
  Tag,
} from "../../../components/PageShell.jsx";

export async function generateStaticParams() {
  const jobs = await loadJobs();
  return jobs.map((/** @type {{ jobId: string }} */ j) => ({ jobId: j.jobId }));
}

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

/** @param {{ title: string, children: any, className?: string }} props */
function EvidenceCard({ title, children }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface">
      <header className="border-b border-border px-5 py-3.5">
        <GroupLabel>{title}</GroupLabel>
      </header>
      <div className="px-5 py-1">{children}</div>
    </section>
  );
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
  const verdictKind = readSmallInt(bundle.verdict);

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
    <Page>
      <PageHeader
        back={{ href: "/timeline", label: "On-chain record" }}
        title={
          <>
            Verdict for job <span className="font-mono tnum">{jobId}</span>
          </>
        }
        actions={<Tag status={verdictKind === 1 ? "pass" : "fail"}>{verdictKindLabel(verdictKind)}</Tag>}
        lede={
          <>
            <p>
              Why it was decided this way, and what the evidence is. Everything on this page is the
              evidence bundle that is keccak-hashed into the{" "}
              <span className="font-mono text-xs">reasonHash</span> of the{" "}
              <span className="font-mono text-xs">VerdictPosted</span> transaction, not a
              rewritten summary.
            </p>
          </>
        }
      />

      <Notice className="mt-8" title="Bundle strings are quoted, never rewritten.">
        The gate <span className="font-mono text-xs">reason</span>, each criterion&apos;s text, and
        every <span className="font-mono text-xs">reason</span>/
        <span className="font-mono text-xs">proof</span> line below are the agent&apos;s own output,
        copied out of the bundle byte for byte. They are written in Indonesian and stay that way on
        purpose: the bundle is what gets hashed into{" "}
        <span className="font-mono text-xs">reasonHash</span>, so rewording it here would stop
        matching the chain. Where a line carries an{" "}
        <span className="rounded border border-border px-1 font-mono text-[10px] uppercase text-faint">
          en
        </span>{" "}
        marker, that is an English translation shown beside the original for reading, it is never
        what was hashed.
      </Notice>

      <div className="mt-8 grid gap-4 lg:grid-cols-2">
        <EvidenceCard title="The job">
          <KeyValues>
            <KeyValue label="provider">
              <AddressLink address={job.provider} />
              <div className="mt-1 text-xs text-muted">{job.providerLabel}</div>
            </KeyValue>
            <KeyValue label="budget">
              <span className="font-mono text-xs tnum">
                {formatUsdc6(job.budgetUsdc6) ?? <NotAvailable />}
              </span>
              <div className="mt-1 text-xs text-muted">
                units of the escrow token (6 decimals)
              </div>
            </KeyValue>
            <KeyValue label="deliverable hash">
              <Hash value={evaluation?.deliverable} />
            </KeyValue>
          </KeyValues>
        </EvidenceCard>

        <EvidenceCard title="Announced on chain">
          <KeyValues>
            <KeyValue label="last ACP status">{acpStatusLabel(job.acpStatus)}</KeyValue>
            <KeyValue label="VerdictPosted tx">
              <TxLink hash={job.verdictTxHash} />
            </KeyValue>
            <KeyValue label="finalize tx">
              <TxLink hash={job.finalizeTxHash} />
            </KeyValue>
          </KeyValues>
        </EvidenceCard>

        <EvidenceCard title="The memory behind the decision">
          <KeyValues>
            <KeyValue label="memory_root">
              <Hash value={bundle.memory_root} />
              <div className="mt-1 text-xs text-muted">read from the agent&apos;s bundle</div>
            </KeyValue>
            <KeyValue label="memory mode">
              <span className="font-mono text-xs">{bundle.mode}</span>
            </KeyValue>
            <KeyValue label="check depth">
              <span className="font-mono text-xs">
                {evaluation?.depth ?? gate?.depth ?? <NotAvailable />}
              </span>
            </KeyValue>
          </KeyValues>
        </EvidenceCard>

        <EvidenceCard title="This bundle">
          <KeyValues>
            <KeyValue label="bundle version">
              <span className="font-mono text-xs">{bundle.version}</span>
            </KeyValue>
            <KeyValue label="bundle shape">
              <span className="font-mono text-xs">{bundle.kind}</span>
            </KeyValue>
            <KeyValue label="bundle file">
              <span className="break-all font-mono text-xs">
                agent/data/chain-abc/verdicts/{job.bundleFile}
              </span>
              <div className="mt-1 text-xs text-muted">
                file name = keccak256 of the file contents; a verbatim copy is served at{" "}
                <a
                  href={"/verdicts/" + jobId + ".json"}
                  className="font-mono text-primary-ink underline-offset-4 hover:underline"
                >
                  /verdicts/{jobId}.json
                </a>
              </div>
            </KeyValue>
          </KeyValues>
        </EvidenceCard>
      </div>

      <Notice className="mt-4" title="memory_root is shown as-is.">
        This page does not compute the root: the value above is read straight from the bundle the
        agent wrote, and the root that BINDS is the one recorded in the{" "}
        <span className="font-mono text-xs">VerdictPosted</span> transaction above.
      </Notice>

      {gate && (
        <section className="mt-14">
          <h2 className="font-display text-2xl font-semibold text-ink">
            Gate decision (no deliverable evaluated)
          </h2>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted">
            This job was rejected <em>before</em> any deliverable was scored, so its bundle has the
            shape <span className="font-mono text-xs">gate-rejection</span> and carries no
            per-criterion check results.
          </p>
          <div className="mt-5 rounded-2xl border border-border bg-surface px-5 py-1">
            <KeyValues>
              <KeyValue label="accepted?">
                <Tag status={gate.accept ? "pass" : "fail"}>
                  {gate.accept ? "accept" : "reject"}
                </Tag>
              </KeyValue>
              <KeyValue label="reason">
                <span className="leading-relaxed">
                  {gate.reason}
                  <Gloss text={gate.reason} />
                </span>
              </KeyValue>
              <KeyValue label="budget">
                <span className="font-mono text-xs tnum">
                  {readUint(gate.budget) ?? <NotAvailable />}
                </span>
              </KeyValue>
              <KeyValue label="provider cap">
                <span className="font-mono text-xs tnum">
                  {readUint(gate.cap?.usdc) ?? <NotAvailable />}
                </span>
                <div className="mt-1 text-xs text-muted">
                  basis {gate.cap?.basis ?? "not available"}, sample_size {readUint(gate.cap?.sample_size) ?? "not available"}
                </div>
              </KeyValue>
              <KeyValue label="risk level">
                <span className="font-mono text-xs tnum">
                  {readUint(gate.risk_level) ?? <NotAvailable />}
                </span>
              </KeyValue>
              <KeyValue label="incident jobs behind it">
                {(gate.incident_jobs ?? []).length === 0 ? (
                  <NotAvailable />
                ) : (
                  <span className="font-mono text-xs">
                    {gate.incident_jobs.map((/** @type {any} */ j, /** @type {number} */ i) => {
                      const id = readUint(j);
                      return (
                        <span key={i}>
                          {i > 0 ? ", " : ""}
                          {id ? (
                            <Link
                              href={"/verdict/" + id}
                              className="text-primary-ink underline-offset-4 hover:underline"
                            >
                              {id}
                            </Link>
                          ) : (
                            <NotAvailable />
                          )}
                        </span>
                      );
                    })}
                  </span>
                )}
              </KeyValue>
              <KeyValue label="provider">
                <AddressLink address={gate.provider} label={shorten(gate.provider)} />
              </KeyValue>
            </KeyValues>
          </div>
        </section>
      )}

      {evaluation && (
        <section className="mt-14">
          <h2 className="font-display text-2xl font-semibold text-ink">Per-criterion evidence</h2>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted">
            Rubric category <span className="font-mono text-xs">{evaluation.category}</span>, depth{" "}
            <span className="font-mono text-xs">{evaluation.depth}</span>.{" "}
            <span className="font-mono text-xs">failed_checks</span>:{" "}
            <span className="font-mono text-xs text-ink">
              {evaluation.failed_checks.length
                ? evaluation.failed_checks.join(", ")
                : "[] (empty)"}
            </span>
          </p>
          <div className="mt-6">
            <Checks checks={checks} criteria={evaluation.criteria} />
          </div>

          {evaluation.unscored?.length ? (
            <Notice className="mt-4" tone="warn" title="Criteria that were NOT scored.">
              <span className="font-mono text-xs text-ink">{evaluation.unscored.join(", ")}</span>
              <span className="mt-2 block">
                {evaluation.unscored_reason}
                <Gloss text={evaluation.unscored_reason} />
              </span>
            </Notice>
          ) : null}
        </section>
      )}

      <section className="mt-14">
        <h2 className="font-display text-2xl font-semibold text-ink">
          The deliverable that was scored
        </h2>
        {deliverable ? (
          <div className="mt-5 overflow-hidden rounded-2xl border border-border bg-surface">
            <div className="px-5 py-1">
              <KeyValues>
                <KeyValue label="keccak256(text)">
                  <Hash value={deliverable.sha_keccak} />
                </KeyValue>
              </KeyValues>
            </div>
            <pre className="overflow-x-auto border-t border-border bg-bg px-5 py-5 font-mono text-xs leading-relaxed text-ink">
              {deliverable.text}
            </pre>
            <div className="flex flex-col gap-2 border-t border-border px-5 py-4">
              {parseDocument(deliverable.text).sections.map((/** @type {any} */ s) =>
                glossSection(s.heading) ? (
                  <p
                    key={s.index}
                    className="flex items-start gap-2 text-[13px] leading-relaxed text-muted"
                  >
                    <span className="mt-px shrink-0 rounded border border-border px-1 font-mono text-[10px] uppercase text-faint">
                      en
                    </span>
                    {glossSection(s.heading)}
                  </p>
                ) : null
              )}
            </div>
          </div>
        ) : (
          <p className="mt-4 text-sm text-faint">
            not available. This job was rejected before the provider ever submitted, so no
            deliverable text was stored.
          </p>
        )}
      </section>
    </Page>
  );
}
