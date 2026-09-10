import { Fragment } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { loadIndex } from "../../lib/data.js";
import { formatUsdc6 } from "../../lib/canonical.js";
import { acpStatusLabel, verdictKindLabel, EXPLORER_NAME } from "../../lib/chain.js";
import { TxLink, AddressLink, shorten } from "../../components/Links.jsx";
import { Page, PageHeader, Notice, NotAvailable, Tag, KeyValues, KeyValue } from "../../components/PageShell.jsx";
import { Reveal } from "../../components/motion.jsx";
import { cn } from "../../lib/utils.js";

export const metadata = {
  title: "On-chain record · Referi",
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
    <span className="inline-flex items-center gap-[3px]" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <i
          key={i}
          className={cn(
            "block h-3 w-[3px] rounded-full",
            i < on ? "bg-primary-ink" : "bg-border-strong"
          )}
        />
      ))}
    </span>
  );
}

const COLUMNS = [
  "Job",
  "Provider",
  "Budget",
  "Depth",
  "ACP status",
  "Verdict",
  "VerdictPosted tx",
  "Evidence",
];

export default async function TimelinePage() {
  const index = await loadIndex();
  const jobs = index.jobs;

  return (
    <Page>
      <PageHeader
        title="Five jobs that really landed on chain"
        lede={
          <>
            <p>
              Five evaluation jobs that ran for real on Base Sepolia. Every verdict below links to
              the transaction that announced it, so you can check any row yourself.
            </p>
            <p className="mt-3">
              This is the record of Referi&apos;s earlier evaluator direction. The current product
              is the{" "}
              <Link href="/execution" className="text-primary-ink underline-offset-4 hover:underline">
                execution room
              </Link>
              .
            </p>
          </>
        }
      />

      <Notice className="mt-8">
        Links go to Blockscout rather than BaseScan. It is the only explorer that picks up the
        vault&apos;s Sourcify verification, so event names show up decoded instead of as raw topics.
      </Notice>

      <Reveal>
        <div className="mt-10 overflow-x-auto rounded-2xl border border-border bg-surface">
          <table className="w-full min-w-[62rem] border-collapse text-left">
            <caption className="border-b border-border px-5 py-3.5 text-left text-xs text-muted">
              Jobs 418 to 422, ordered by job id.
            </caption>
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <th
                    key={c}
                    scope="col"
                    className="border-b border-border px-5 py-3 text-xs font-medium uppercase tracking-wide text-faint"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {jobs.map((/** @type {any} */ job) => (
                <Fragment key={job.jobId}>
                  <tr className="align-top transition-colors hover:bg-surface-2/40">
                    <td className="px-5 pb-2 pt-4 font-mono text-sm font-semibold tnum text-ink">
                      {job.jobId}
                    </td>
                    <td className="px-5 pb-2 pt-4">
                      <AddressLink address={job.provider} label={shorten(job.provider)} />
                      <div className="mt-1 text-xs text-muted">{job.providerLabel}</div>
                    </td>
                    <td className="px-5 pb-2 pt-4 font-mono text-xs tnum text-ink">
                      {formatUsdc6(job.budgetUsdc6) ?? <NotAvailable />}
                    </td>
                    <td className="px-5 pb-2 pt-4">
                      <span className="inline-flex items-center gap-2 font-mono text-xs text-ink">
                        <DepthBar depth={job.depth} />
                        {job.depth || <NotAvailable />}
                      </span>
                    </td>
                    <td className="px-5 pb-2 pt-4 text-sm text-muted">
                      {acpStatusLabel(job.acpStatus)}
                    </td>
                    <td className="px-5 pb-2 pt-4">
                      <Tag status={job.verdictKind === 1 ? "pass" : "fail"}>
                        {verdictKindLabel(job.verdictKind)}
                      </Tag>
                      <div className="mt-1 font-mono text-xs text-faint">{job.bundleKind}</div>
                    </td>
                    <td className="px-5 pb-2 pt-4">
                      <TxLink hash={job.verdictTxHash} label={shorten(job.verdictTxHash)} />
                    </td>
                    <td className="px-5 pb-2 pt-4">
                      <Link
                        href={"/verdict/" + job.jobId}
                        className="group inline-flex items-center gap-1.5 whitespace-nowrap text-sm text-primary-ink transition-colors hover:text-ink"
                      >
                        open evidence
                        <ArrowRight
                          className="size-3.5 transition-transform group-hover:translate-x-0.5"
                          strokeWidth={2}
                          aria-hidden
                        />
                      </Link>
                    </td>
                  </tr>
                  {/* Catatan per job dulu hidup sebagai daftar terpisah di bawah tabel,
                      mengulang kelima job yang sama. Ia milik barisnya. */}
                  <tr className="border-b border-border">
                    <td />
                    <td
                      colSpan={7}
                      className="px-5 pb-4 pt-1 text-[13px] leading-relaxed text-muted"
                    >
                      {job.note}
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </Reveal>

      <Reveal delay={0.06}>
        <section className="mt-14">
          <h2 className="font-display text-2xl font-semibold text-ink">
            Where each column comes from
          </h2>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted">
            Nothing here is fetched live. Each value is read from a file already in the repository,
            listed below.
          </p>
          <div className="mt-5 rounded-2xl border border-border bg-surface px-5 py-1">
            <KeyValues>
              {Object.entries(index.source).map(([key, value]) => (
                <KeyValue key={key} label={key}>
                  <span className="break-all font-mono text-xs">{String(value)}</span>
                </KeyValue>
              ))}
            </KeyValues>
          </div>
          <Notice className="mt-4">
            No RPC calls, no wallet, no hashing. This page only renders files that already exist.
          </Notice>
        </section>
      </Reveal>
    </Page>
  );
}
