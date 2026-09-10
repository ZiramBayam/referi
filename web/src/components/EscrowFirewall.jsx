import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { firewallDemo } from "../lib/escrowFirewall.js";
import { KeyValue, KeyValues, Notice, Page, PageHeader } from "./PageShell.jsx";
import { Reveal } from "./motion.jsx";
import { cn } from "../lib/utils.js";

/**
 * @param {{ title: string, terms: any, emphasized?: boolean }} props
 */
function TermsColumn({ title, terms, emphasized = false }) {
  return (
    <section
      className={cn(
        "flex flex-col overflow-hidden rounded-2xl border bg-surface",
        emphasized ? "border-primary/40" : "border-border"
      )}
    >
      <header
        className={cn(
          "border-b px-5 py-4",
          emphasized ? "border-primary/25 bg-primary/[0.07]" : "border-border"
        )}
      >
        <p className="text-xs font-medium uppercase tracking-wide text-faint">{title}</p>
        <h3 className="mt-1.5 font-display text-lg font-semibold text-ink">
          {emphasized ? "Memory-informed terms" : "Generic terms"}
        </h3>
      </header>

      <div className="px-5 py-1">
        <KeyValues className="sm:grid-cols-[minmax(0,10rem)_1fr]">
          <KeyValue label="acceptance criteria">
            <ul className="flex flex-col gap-1.5">
              {terms.acceptance.map((/** @type {string} */ item) => (
                <li key={item} className="flex items-start gap-2 leading-relaxed">
                  <Check
                    className={cn(
                      "mt-1 size-3 shrink-0",
                      emphasized ? "text-primary-ink" : "text-faint"
                    )}
                    strokeWidth={2.5}
                    aria-hidden
                  />
                  {item}
                </li>
              ))}
            </ul>
          </KeyValue>
          <KeyValue label="required evidence">
            <ul className="flex flex-col gap-1.5">
              {terms.evidence.map((/** @type {string} */ item) => (
                <li key={item} className="flex items-start gap-2 leading-relaxed">
                  <Check
                    className={cn(
                      "mt-1 size-3 shrink-0",
                      emphasized ? "text-primary-ink" : "text-faint"
                    )}
                    strokeWidth={2.5}
                    aria-hidden
                  />
                  {item}
                </li>
              ))}
            </ul>
          </KeyValue>
          <KeyValue label="milestone gate">
            <span className="leading-relaxed">{terms.milestone}</span>
          </KeyValue>
          <KeyValue label="review">
            <span className="leading-relaxed">{terms.review}</span>
          </KeyValue>
        </KeyValues>
      </div>
    </section>
  );
}

export default function EscrowFirewall() {
  const { taskCategory, generic, recalled } = firewallDemo;
  return (
    <Page>
      <PageHeader
        title="Escrow Firewall: before funding"
        lede={
          <>
            <p>
              Same task category: <span className="font-medium text-ink">{taskCategory}</span>. The
              difference is not a provider score. A stored failure mechanism changes what the next
              provider must prove before escrow is funded.
            </p>
            <p className="mt-3">
              This documents an <span className="font-medium text-ink">earlier direction</span> of
              the project, kept because the mechanism is real. The current product direction is the{" "}
              <Link
                href="/"
                className="inline-flex items-center gap-1 text-primary-ink underline-offset-4 hover:underline"
              >
                Execution Passport
                <ArrowRight className="size-3.5" strokeWidth={2} aria-hidden />
              </Link>
            </p>
          </>
        }
      />

      <Notice className="mt-8" title="Recalled Sibyl memory · demo fixture.">
        <span className="font-mono text-xs text-ink">pattern:{recalled.pattern}</span> · confidence{" "}
        <span className="font-mono text-xs text-ink">{recalled.confidence}</span>
        <span className="mt-2 block">
          Countermeasure: require reproducible evidence before the milestone. This is a
          recommendation until the client approves it.
        </span>
      </Notice>

      <Reveal>
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          <TermsColumn title="No recalled pattern" terms={generic} />
          <TermsColumn title="Relevant failure pattern recalled" terms={recalled} emphasized />
        </div>
      </Reveal>

      <Reveal delay={0.08}>
        <section className="mt-8 overflow-hidden rounded-2xl border border-border bg-surface">
          <header className="border-b border-border px-5 py-4">
            <h2 className="text-xs font-medium uppercase tracking-wide text-faint">
              Pre-funding commitment
            </h2>
          </header>
          <div className="px-5 py-4">
            <p className="max-w-3xl text-sm leading-relaxed text-muted">
              The approved canonical terms are hashed before{" "}
              <span className="font-mono text-xs text-ink">fund</span> and appended to ACP&apos;s
              immutable job description.
            </p>
            <p className="mt-3 break-all font-mono text-xs text-ink">
              Terms hash: {recalled.commitment}
            </p>
            <p className="mt-4 max-w-3xl text-sm leading-relaxed text-muted">
              In a real run this value is generated by the agent CLI and included in the verdict
              evidence bundle. The value above is illustrative, so the page cannot be mistaken for
              a live transaction viewer.
            </p>
          </div>
        </section>
      </Reveal>
    </Page>
  );
}
