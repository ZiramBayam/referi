import Link from "next/link";
import { ArrowRight, ExternalLink, FileCheck2, ShieldCheck, TriangleAlert } from "lucide-react";
import { buttonClasses } from "./ui/Button.jsx";
import { Reveal } from "./motion.jsx";
import { GateChain } from "./illustrations/GateChain.jsx";
import { cn, shortenAddress } from "../lib/utils.js";
import { ACTION_CLASS, HYPOTHESIS_ID, INCIDENT_TYPE } from "../lib/passportDemo.js";
import {
  PASSPORT_BLOCK,
  PASSPORT_CONTRACTS,
  PASSPORT_DEPLOY_COST_ETH,
  passportAddressUrl,
} from "../lib/deployment.js";

/**
 * Halaman depan. Tugasnya SATU: membuat mekanismenya bisa dimengerti, lalu
 * mengantar orang ke ruang eksekusi. Gerbang yang sesungguhnya tidak hidup di sini,
 * supaya halaman ini bisa dibaca tanpa harus dioperasikan lebih dulu.
 */
export default function Landing() {
  return (
    <>
      <Hero />
      <MemoryChangesCondition />
      <TwoGates />
      <DeployedOnChain />
      <ReproduceBand />
      <FinalCta />
    </>
  );
}

function Hero() {
  return (
    <section className="relative border-b border-border">
      <div className="mx-auto grid max-w-6xl items-center gap-14 px-5 py-20 lg:grid-cols-[1.05fr_0.95fr] lg:py-28">
        <div>
          <div
            className="reveal inline-flex items-center gap-2.5 rounded-full border border-border bg-surface/60 px-3 py-1.5 text-xs text-muted"
            style={{ animationDelay: "0.02s" }}
          >
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary-ink opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-primary" />
            </span>
            Mock treasury fixture
            <span className="text-border-strong">·</span>
            <span>no real funds move</span>
          </div>

          <h1
            className="reveal mt-6 font-display text-[clamp(2.4rem,6vw,4.25rem)] font-semibold leading-[1.04] tracking-[-0.03em] text-ink"
            style={{ animationDelay: "0.08s" }}
          >
            An agent should not repeat the failure it already survived.
          </h1>

          <p
            className="reveal mt-6 max-w-xl text-lg leading-relaxed text-muted"
            style={{ animationDelay: "0.14s" }}
          >
            Referi turns a past incident into deterministic proof obligations, then issues a
            one-time Execution Passport bound to the exact action. Nothing moves value until every
            obligation holds.
          </p>

          <div
            className="reveal mt-9 flex flex-wrap items-center gap-3"
            style={{ animationDelay: "0.2s" }}
          >
            <Link
              href="/execution"
              className={buttonClasses("primary", "lg", "w-full sm:w-auto")}
            >
              Open the execution room
              <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden />
            </Link>
            <a
              href="#how-it-works"
              className={buttonClasses("secondary", "lg", "w-full sm:w-auto")}
            >
              How it works
            </a>
          </div>

          <dl
            className="reveal mt-12 grid grid-cols-2 gap-x-10 gap-y-5 border-t border-border pt-7 sm:flex sm:flex-wrap"
            style={{ animationDelay: "0.26s" }}
          >
            <Stat value="4" label="Blocking obligations" />
            <Stat value="60 s" label="Passport lifetime" />
            <Stat value="1" label="Execution per passport" />
          </dl>
        </div>

        {/* Kartu ringkasan, bukan gerbang. Ia menyebut apa yang ditegakkan dan di mana,
            lalu menunjuk ke ruang eksekusi tempat semuanya bisa dicoba. */}
        <div
          className="reveal w-full rounded-[20px] border border-border bg-surface p-6 sm:p-8"
          style={{ animationDelay: "0.16s" }}
        >
          <span className="font-mono text-[11px] uppercase tracking-wide text-faint">
            What is enforced
          </span>
          <dl className="mt-5 flex flex-col">
            <SummaryRow label="Action class" value={ACTION_CLASS} />
            <SummaryRow label="Remembered policy" value={HYPOTHESIS_ID} />
            <SummaryRow label="Seeded incident" value={INCIDENT_TYPE} />
            <SummaryRow label="Enforcement" value="block without a valid passport" plain />
          </dl>
          <Link
            href="/execution"
            className={buttonClasses("secondary", "md", "mt-6 w-full")}
          >
            Try it against the fixture
            <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden />
          </Link>
        </div>
      </div>
    </section>
  );
}

/** @param {{ value: string, label: string }} props */
function Stat({ value, label }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-lg font-semibold tnum text-ink">{value}</dt>
      <dd className="text-xs text-muted">{label}</dd>
    </div>
  );
}

/** @param {{ label: string, value: string, plain?: boolean, key?: any }} props */
function SummaryRow({ label, value, plain }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-border py-3 first:border-t-0 first:pt-0">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className={cn("text-sm text-ink", plain ? "" : "font-mono text-xs")}>{value}</dd>
    </div>
  );
}

function MemoryChangesCondition() {
  const steps = [
    {
      icon: TriangleAlert,
      n: "01",
      title: "Incident to hypothesis",
      body: "A stale oracle is not just a failed run. Sibyl stores it as a structured Control Hypothesis that names the mechanism, not the symptom.",
    },
    {
      icon: FileCheck2,
      n: "02",
      title: "Hypothesis to obligations",
      body: "The recalled hypothesis selects the four facts that must be true before this action class can move value again.",
    },
    {
      icon: ShieldCheck,
      n: "03",
      title: "Obligations to passport",
      body: "The verifier accepts one exact, short-lived, single-use action. Not a score, not a narrative, not a promise.",
    },
  ];

  return (
    <section className="border-b border-border" id="how-it-works">
      <div className="mx-auto max-w-6xl px-5 py-20">
        <Reveal>
          <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
            <h2 className="font-display text-[clamp(1.8rem,3.5vw,2.6rem)] font-semibold leading-tight text-ink">
              Memory has to change the condition, not the commentary.
            </h2>
            <div className="flex flex-col gap-5 text-[15px] leading-relaxed text-muted lg:pt-2">
              <p>
                Most agent memory produces a better explanation after the fact. It does not stand
                between the agent and the transaction, so the same class of failure stays reachable
                on the next run.
              </p>
              <p className="text-ink">
                Referi treats a past incident as a precondition. The lesson is compiled into
                deterministic proof obligations, and permission is issued only when those
                obligations hold for the exact bytes being submitted.
              </p>
            </div>
          </div>
        </Reveal>

        <Reveal delay={0.08}>
          <ol className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-border bg-border md:grid-cols-3">
            {steps.map((s) => (
              <li key={s.n} className="flex flex-col gap-4 bg-bg p-7">
                <div className="flex items-center justify-between">
                  <s.icon className="size-6 text-primary-ink" strokeWidth={1.75} aria-hidden />
                  <span className="font-mono text-sm text-faint">{s.n}</span>
                </div>
                <h3 className="font-display text-xl font-semibold text-ink">{s.title}</h3>
                <p className="text-sm leading-relaxed text-muted">{s.body}</p>
              </li>
            ))}
          </ol>
        </Reveal>

        <Reveal delay={0.14}>
          {/* Bentuk mekanismenya, yaitu empat kewajiban bertemu di satu gerbang dan dari
              passport hanya ada satu jalan keluar yang diterima, tidak bisa disampaikan
              paragraf. Di sinilah ia digambar, dan animasinya menjalankan alur itu. */}
          <figure className="mt-8 overflow-hidden rounded-2xl border border-border bg-surface/30 p-6 sm:p-8">
            <GateChain />
            <figcaption className="mt-6 border-t border-border pt-4 text-xs leading-relaxed text-muted">
              The seeded incident is{" "}
              <span className="font-mono text-ink">{INCIDENT_TYPE}</span>, and the hypothesis it
              compiles to is <span className="font-mono text-ink">{HYPOTHESIS_ID}</span>. All four
              obligations are blocking: one unsatisfied row and the gate stays shut. A passport
              expires in 60 seconds and is consumed by its first accepted call, so the second
              submission of the same passport, or the same passport against changed calldata, is
              refused at the verifier.
            </figcaption>
          </figure>
        </Reveal>
      </div>
    </section>
  );
}

const GATES = [
  {
    name: "Gate 1 · Virtuals ACP",
    what: "Memory sets how deeply a deliverable is checked and what budget cap a provider gets.",
    proof: "Five jobs on the real ACP contract. Jobs 421 and 422 have identical text and opposite verdicts.",
    check: "make virtuals-evidence",
  },
  {
    name: "Gate 2 · Base",
    what: "Memory turns a past incident into four proof obligations a treasury action must satisfy.",
    proof: "PassportVerifier, MockTreasury, and MockOracle deployed and verified on Base Sepolia.",
    check: "make demo-passport",
  },
];

function TwoGates() {
  return (
    <section className="border-b border-border">
      <div className="mx-auto max-w-6xl px-5 py-20">
        <Reveal>
          <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
            <h2 className="font-display text-[clamp(1.8rem,3.5vw,2.6rem)] font-semibold leading-tight text-ink">
              One memory, two gates.
            </h2>
            <div className="flex flex-col gap-5 text-[15px] leading-relaxed text-muted lg:pt-2">
              <p>
                Referi enforces in two places, on two protocols, against two different failure
                modes. Both gates read the same Sibyl store through the same code.
              </p>
              <p className="text-ink">
                They are anchored together, not merely adjacent. The passport gate&apos;s Control
                Hypothesis lives in the same reference namespace the on-chain memory root commits
                to, so the root the ACP evaluator announces also commits to the Base gate&apos;s
                policy. Change one and the other&apos;s root changes.
              </p>
            </div>
          </div>
        </Reveal>

        <Reveal delay={0.08}>
          <ol className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-border bg-border md:grid-cols-2">
            {GATES.map((g) => (
              <li key={g.name} className="flex flex-col gap-4 bg-bg p-7">
                <h3 className="font-display text-xl font-semibold text-ink">{g.name}</h3>
                <p className="text-sm leading-relaxed text-muted">{g.what}</p>
                <p className="text-sm leading-relaxed text-ink">{g.proof}</p>
                <p className="mt-auto pt-2 font-mono text-xs text-primary-ink">{g.check}</p>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </section>
  );
}

function DeployedOnChain() {
  return (
    <section className="border-b border-border bg-surface/30">
      <div className="mx-auto max-w-6xl px-5 py-20">
        <div className="grid gap-12 lg:grid-cols-[0.95fr_1.05fr] lg:gap-16">
          <Reveal>
            <h2 className="font-display text-[clamp(1.8rem,3.5vw,2.6rem)] font-semibold leading-tight text-ink">
              The gate is on chain, and its source is readable.
            </h2>
            <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-muted">
              The verifier that refuses a replayed passport is deployed on Base Sepolia, not described
              in a diagram. All three contracts are verified on Sourcify, so the explorer shows source
              rather than bytecode.
            </p>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink">
              Two of the bindings that matter are immutable and you can read them back yourself: the
              verifier points at that treasury, and it accepts exactly one signer. Neither can be
              changed after deployment, which is what makes the refusal meaningful.
            </p>
            <p className="mt-4 max-w-xl text-[13px] leading-relaxed text-faint">
              Fixture boundary: the treasury holds no real funds and the oracle observation is set by
              its own owner. This demonstrates the enforcement mechanism, it does not move money.
            </p>
          </Reveal>

          <Reveal delay={0.1}>
            <div className="rounded-2xl border border-border bg-surface/40 p-2">
              <div className="flex items-center justify-between px-3 py-3">
                <span className="text-xs font-medium text-muted">Deployment manifest</span>
                <span className="font-mono text-xs text-faint">
                  chain 84532 · block {PASSPORT_BLOCK.toLocaleString("en-US")}
                </span>
              </div>
              <ul className="overflow-hidden rounded-xl border border-border bg-bg">
                {PASSPORT_CONTRACTS.map((c, i) => (
                  <li key={c.name} className={cn(i > 0 && "border-t border-border")}>
                    <a
                      href={passportAddressUrl(c.address)}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`View ${c.name} on Blockscout, opens in a new tab`}
                      className="group flex items-center justify-between gap-4 px-4 py-4 transition-colors hover:bg-surface"
                    >
                      <div className="min-w-0">
                        <div className="truncate font-mono text-sm text-ink">{c.name}</div>
                        <div className="mt-0.5 text-xs text-muted">{c.role}</div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2 font-mono text-xs text-primary-ink">
                        {shortenAddress(c.address)}
                        <ExternalLink
                          className="size-3.5 text-faint transition-colors group-hover:text-primary-ink"
                          strokeWidth={2}
                          aria-hidden
                        />
                      </div>
                    </a>
                  </li>
                ))}
              </ul>
              <p className="px-3 py-3 text-xs leading-relaxed text-faint">
                Verified on Sourcify, exact match, all three. Deployed for{" "}
                {PASSPORT_DEPLOY_COST_ETH} ETH. Addresses, transaction hashes, and the post-deploy
                state read back from chain are in{" "}
                <span className="font-mono text-muted">deployments/passport-84532.json</span>.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

const ARTIFACTS = [
  {
    name: "make demo-passport",
    role: "End-to-end run, block then allow",
    path: "Makefile",
  },
  {
    name: "execution_passport.py",
    role: "Obligation evaluation and passport issuance",
    path: "agent/agent/",
  },
  {
    name: "PassportVerifier.sol",
    role: "Action-bound, single-use enforcement",
    path: "contracts/src/",
  },
  {
    name: "canonical-formats.md",
    role: "Passport and hypothesis schemas",
    path: "docs/execution-passport/",
  },
];

function ReproduceBand() {
  return (
    <section className="border-b border-border">
      <div className="mx-auto max-w-6xl px-5 py-20">
        <div className="grid gap-12 lg:grid-cols-[0.95fr_1.05fr] lg:gap-16">
          <Reveal>
            <h2 className="font-display text-[clamp(1.8rem,3.5vw,2.6rem)] font-semibold leading-tight text-ink">
              Not a mockup. Run the refusal yourself.
            </h2>
            <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-muted">
              Everything on this page resolves to code you can execute locally. The scenario is a
              mock treasury and a mock oracle on a testnet fixture, deliberately bounded, and
              labelled as such wherever a number appears.
            </p>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink">
              Today Referi enforces one action class. Migration, risk-parameter changes, upgrades,
              and Safe or AccessManager integration each need their own obligations and recovery
              analysis, so they are roadmap, not claims.
            </p>
          </Reveal>

          <Reveal delay={0.1}>
            <div className="rounded-2xl border border-border bg-surface/40 p-2">
              <div className="flex items-center justify-between px-3 py-3">
                <span className="text-xs font-medium text-muted">Reproduction manifest</span>
                <span className="font-mono text-xs text-faint">local · deterministic</span>
              </div>
              <ul className="overflow-hidden rounded-xl border border-border bg-bg">
                {ARTIFACTS.map((a, i) => (
                  <li
                    key={a.name}
                    className={cn(
                      "flex items-center justify-between gap-4 px-4 py-4",
                      i > 0 && "border-t border-border"
                    )}
                  >
                    <div className="min-w-0">
                      <div className="truncate font-mono text-sm text-ink">{a.name}</div>
                      <div className="mt-0.5 text-xs text-muted">{a.role}</div>
                    </div>
                    <span className="shrink-0 font-mono text-xs text-faint">{a.path}</span>
                  </li>
                ))}
              </ul>
              <p className="px-3 py-3 text-xs leading-relaxed text-faint">
                The execution room calls the same evaluation the CLI does. No wallet, no RPC, and
                no signed transaction is involved until public testnet deployment lands.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-24 text-center">
      <Reveal>
        <h2 className="mx-auto max-w-2xl font-display text-[clamp(2rem,4vw,3rem)] font-semibold leading-tight text-ink">
          Watch the same rebalance get refused, then allowed.
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-muted">
          Four steps against a mock treasury: propose an amount, run the agent preflight, receive a
          passport, then try to spend it twice.
        </p>
        <div className="mt-9 flex justify-center">
          <Link href="/execution" className={buttonClasses("primary", "lg")}>
            Open the execution room
            <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden />
          </Link>
        </div>
      </Reveal>
    </section>
  );
}
