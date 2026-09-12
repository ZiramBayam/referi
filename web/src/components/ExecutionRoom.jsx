"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Clock,
  FileCheck2,
  Loader2,
  Lock,
  RotateCcw,
  Radio,
  ScanLine,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import { buttonClasses } from "./ui/Button.jsx";
import { EASE } from "./motion.jsx";
import { cn, formatAmount, shortenAddress, shortenHash } from "../lib/utils.js";
import {
  ACTION_CLASS,
  CHAIN_ID,
  CHAIN_LABEL,
  DEMO_DEFAULTS,
  FRESHNESS_WINDOW,
  HYPOTHESIS_ID,
  INCIDENT_TYPE,
  INITIAL_RESERVE,
  MINIMUM_RESERVE,
  evaluateDemoAction,
} from "../lib/passportDemo.js";

const WAIT = 420;
const STAGES = ["proposal", "preflight", "passport", "execute"];
const STAGE_LABEL = {
  proposal: "Propose",
  preflight: "Preflight",
  passport: "Passport",
  execute: "Execute",
};

/** @param {number} ms */
function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Status kewajiban bukti selalu dibawa IKON + KATA, tidak pernah warna saja, jadi
 * `satisfied` / `unsatisfied` / `unverifiable` terbaca tanpa melihat warnanya.
 */
const PROOF_TONE = {
  satisfied: {
    Icon: Check,
    word: "PASS",
    text: "text-proof-pass",
    ring: "border-proof-pass/60 text-proof-pass bg-proof-pass/10",
  },
  unsatisfied: {
    Icon: X,
    word: "BLOCK",
    text: "text-proof-block",
    ring: "border-proof-block/60 text-proof-block bg-proof-block/10",
  },
  unverifiable: {
    Icon: TriangleAlert,
    word: "REVIEW",
    text: "text-proof-review",
    ring: "border-proof-review/60 text-proof-review bg-proof-review/10",
  },
};

const DECISION_TONE = {
  "passport-issued": {
    label: "Passport ready",
    Icon: ShieldCheck,
    className: "border-proof-pass/40 bg-proof-pass/12 text-proof-pass",
  },
  block: {
    label: "Blocked",
    Icon: Lock,
    className: "border-proof-block/40 bg-proof-block/12 text-proof-block",
  },
  "human-review-required": {
    label: "Human review",
    Icon: TriangleAlert,
    className: "border-proof-review/40 bg-proof-review/12 text-proof-review",
  },
  checking: {
    label: "Checking",
    Icon: Loader2,
    className: "border-primary/40 bg-primary/12 text-primary-ink",
  },
  awaiting: {
    label: "Awaiting preflight",
    Icon: Clock,
    className: "border-border bg-surface-2 text-muted",
  },
};

/**
 * Ruang eksekusi.
 *
 * Susunannya mengikuti urutan eksekusi yang sesungguhnya, dari atas ke bawah: usulkan
 * aksi, jalankan preflight, terima passport, lalu eksekusi dan uji sekali-pakainya.
 * Setiap langkah adalah satu bagian bernomor yang menyatakan statusnya sendiri, dan
 * langkah yang belum bisa dijangkau tidak dirender sama sekali, karena langkah kosong
 * yang diredupkan tetap terbaca sebagai sesuatu yang bisa ditekan.
 */
export default function ExecutionRoom() {
  const reduce = useReducedMotion();

  const [amountInput, setAmountInput] = useState(String(DEMO_DEFAULTS.amount));
  const [memoryAvailable, setMemoryAvailable] = useState(DEMO_DEFAULTS.memoryAvailable);
  const [oracleFresh, setOracleFresh] = useState(DEMO_DEFAULTS.oracleFresh);
  const [busy, setBusy] = useState(false);
  const [preflight, setPreflight] = useState(/** @type {any} */ (null));
  const [preflightRun, setPreflightRun] = useState(0);
  const [executed, setExecuted] = useState(false);
  const [replayRejected, setReplayRejected] = useState(false);
  const [tamperRejected, setTamperRejected] = useState(false);
  const [error, setError] = useState("");

  const amount = Number.parseInt(amountInput, 10);
  const amountIsValid = Number.isInteger(amount) && amount >= 0 && amount <= INITIAL_RESERVE;
  const effectiveAmount = amountIsValid ? amount : DEMO_DEFAULTS.amount;

  const preview = useMemo(
    () => evaluateDemoAction({ amount: effectiveAmount, memoryAvailable, oracleFresh }),
    [effectiveAmount, memoryAvailable, oracleFresh]
  );

  const passportIssued = preflight?.decision === "passport-issued";
  const currentStage = executed
    ? "execute"
    : passportIssued
      ? "passport"
      : busy || preflight
        ? "preflight"
        : "proposal";

  /** Setiap perubahan masukan membatalkan verdict lama: verdict basi lebih buruk dari kosong. */
  function invalidate() {
    setPreflight(null);
    setExecuted(false);
    setReplayRejected(false);
    setTamperRejected(false);
  }

  /** @param {any} event */
  function handleAmountChange(event) {
    setAmountInput(event.target.value.replace(/[^0-9]/g, ""));
    invalidate();
  }

  async function runPreflight() {
    if (!amountIsValid || busy) return;
    setBusy(true);
    setError("");
    invalidate();
    await wait(WAIT);
    try {
      const response = await fetch("/api/passport/preflight", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ amount, memoryAvailable, oracleFresh }),
      });
      const data = await response.json();
      setPreflightRun((value) => value + 1);
      if (!response.ok) throw new Error(data.error || "preflight failed");
      setPreflight(data);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "preflight failed");
      setPreflight(null);
    } finally {
      setBusy(false);
    }
  }

  function refreshOracle() {
    setOracleFresh(true);
    invalidate();
  }

  function toggleMemory() {
    setMemoryAvailable((value) => !value);
    invalidate();
  }

  function executeFixture() {
    if (!passportIssued || executed) return;
    setExecuted(true);
  }

  // Kedua uji penolakan berdiri sendiri. Menjalankan yang satu TIDAK mengunci yang lain:
  // keduanya menguji properti verifier yang berbeda atas passport yang sama.
  function tryReplay() {
    if (!executed) return;
    setReplayRejected(true);
  }

  function tryTamper() {
    if (!executed) return;
    setTamperRejected(true);
  }

  const decisionKey = busy ? "checking" : preflight ? preflight.decision : "awaiting";
  const decision = DECISION_TONE[decisionKey] ?? DECISION_TONE.awaiting;
  // Kunci badan konsol: berganti berarti React memasang ulang, jadi kewajiban bukti
  // selalu tiba lagi dengan stagger-nya, termasuk saat preflight yang sama diulang.
  const bodyKey = busy ? "checking" : preflight ? `proofs-${preflightRun}` : "empty";

  return (
    <>
      <header className="border-b border-border">
        <div className="mx-auto max-w-6xl px-5 pb-8 pt-14">
          <Link
            href="/"
            className="inline-flex w-fit items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink"
          >
            <ArrowLeft className="size-3.5" strokeWidth={2} aria-hidden />
            Overview
          </Link>
          <h1 className="mt-5 font-display text-4xl font-semibold tracking-tight text-ink">
            Execution room
          </h1>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted">
            Four steps against a mock treasury. Propose an amount, run the agent preflight, receive
            a passport, then try to spend it twice. The first run starts with the oracle
            deliberately stale, which is the condition that seeded the agent&apos;s incident memory.
          </p>
        </div>
      </header>

      {/* Rel tahap menempel di bawah nav supaya posisi orang di dalam alur tetap terbaca
          sejauh apa pun ia menggulir. */}
      <StageRail current={currentStage} reduce={reduce} />

      <div className="mx-auto max-w-6xl px-5 pb-8">
        <Step
          n="01"
          title="Propose the action"
          state={preflight || busy ? "done" : "current"}
          hint={`${formatAmount(effectiveAmount)} MOCK out of ${formatAmount(INITIAL_RESERVE)}`}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
              <label htmlFor="amount" className="text-sm font-medium text-ink">
                Rebalance amount
              </label>
              <div
                className={cn(
                  "mt-2 flex h-14 items-center rounded-xl border bg-bg transition-colors",
                  amountIsValid ? "border-border focus-within:border-primary" : "border-proof-block"
                )}
              >
                <input
                  id="amount"
                  inputMode="numeric"
                  value={amountInput}
                  onChange={handleAmountChange}
                  aria-describedby="amount-help"
                  aria-invalid={!amountIsValid}
                  className="min-w-0 flex-1 bg-transparent px-4 font-mono text-xl tnum text-ink outline-none"
                />
                <span className="pr-4 font-mono text-xs text-faint">MOCK</span>
              </div>
              <p id="amount-help" className="mt-2 text-xs leading-relaxed text-muted">
                Treasury reserve {formatAmount(INITIAL_RESERVE)} MOCK. The remembered minimum after
                the action is {formatAmount(MINIMUM_RESERVE)} MOCK.
              </p>
              {!amountIsValid && (
                <p className="mt-1.5 text-xs text-proof-block">
                  Enter a whole number from 0 to {formatAmount(INITIAL_RESERVE)}.
                </p>
              )}

              {/* Memori Sibyl: ada atau hilang. Hilangnya memori BUKAN lolos diam-diam. */}
              <div className="mt-5 flex items-center gap-3 border-t border-border pt-5">
                <span
                  className={cn(
                    "grid size-9 shrink-0 place-items-center rounded-lg border transition-colors",
                    memoryAvailable
                      ? "border-proof-pass/50 bg-proof-pass/10 text-proof-pass"
                      : "border-proof-review/50 bg-proof-review/10 text-proof-review"
                  )}
                  aria-hidden
                >
                  {memoryAvailable ? (
                    <FileCheck2 className="size-[18px]" strokeWidth={1.75} />
                  ) : (
                    <TriangleAlert className="size-[18px]" strokeWidth={1.75} />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-ink">
                    {memoryAvailable ? "Control Hypothesis loaded" : "Control Hypothesis missing"}
                  </div>
                  <div className="mt-0.5 truncate font-mono text-xs text-faint">
                    {memoryAvailable ? HYPOTHESIS_ID : "sibyl / unavailable, human review"}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={toggleMemory}
                  className={buttonClasses("secondary", "sm", "shrink-0")}
                >
                  {memoryAvailable ? "Remove" : "Restore"}
                </button>
              </div>
            </div>

            {/* Insiden yang di-seed. Amber adalah konteks insiden, tidak pernah sukses. */}
            <div className="rounded-2xl border border-proof-review/30 bg-proof-review/[0.06] p-5 sm:p-6">
              <div className="flex items-center gap-2">
                <TriangleAlert className="size-4 text-proof-review" strokeWidth={2} aria-hidden />
                <span className="text-sm font-medium text-ink">Seeded incident</span>
                <span className="ml-auto font-mono text-xs text-faint">{INCIDENT_TYPE}</span>
              </div>
              <p className="mt-3 text-[13px] leading-relaxed text-muted">
                An earlier run moved value on an observation that was already stale. The agent
                remembers the mechanism, so this action class now has to prove freshness before it
                can move value again.
              </p>
              <dl className="mt-4 flex flex-col">
                <div className="flex items-baseline justify-between gap-4 border-t border-proof-review/20 py-2.5">
                  <dt className="text-xs text-muted">Oracle observation</dt>
                  <dd className="font-mono text-xs text-ink">
                    {oracleFresh ? "5 seconds old" : "120 seconds old"}
                  </dd>
                </div>
                <div className="flex items-baseline justify-between gap-4 border-t border-proof-review/20 py-2.5">
                  <dt className="text-xs text-muted">Remembered limit</dt>
                  <dd className="font-mono text-xs text-ink">{FRESHNESS_WINDOW} seconds</dd>
                </div>
              </dl>
              <button
                type="button"
                onClick={refreshOracle}
                disabled={oracleFresh}
                className={buttonClasses("secondary", "sm", "mt-4")}
              >
                <RotateCcw className="size-3.5" strokeWidth={2} aria-hidden />
                {oracleFresh ? "Fixture oracle refreshed" : "Refresh oracle fixture"}
              </button>
            </div>
          </div>
        </Step>

        <Step
          n="02"
          title="Run the agent preflight"
          state={preflight ? "done" : "current"}
          hint={preflight ? decision.label : "not run yet"}
        >
          {/* Kiri bukti, kanan keputusan dan aksi. Bukti mendapat lebar lebih besar
              karena di sanalah orang membaca ALASAN, bukan sekadar hasilnya. */}
          <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr] lg:items-start" aria-live="polite">
            <div className="overflow-hidden rounded-2xl border border-border bg-surface">
              <div className="border-b border-border px-5 py-3.5">
                <span className="text-xs font-medium uppercase tracking-wide text-faint">
                  Proof obligations
                </span>
              </div>
              {preflight && (
                <div className="px-5 pt-5">
                  <EngineNote preflight={preflight} />
                </div>
              )}
              <div className="relative px-5">
                <motion.div
                  key={bodyKey}
                  initial={reduce ? false : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.2, ease: EASE }}
                >
                  {busy ? (
                    <div
                      className={cn(
                        "relative my-5 overflow-hidden rounded-xl border border-border bg-bg/40 px-4 py-8",
                        !reduce && "scanline"
                      )}
                      style={{ "--scan-distance": "120px" }}
                    >
                      <div className="flex items-start gap-3">
                        <ScanLine
                          className="mt-0.5 size-4 shrink-0 text-primary-ink"
                          strokeWidth={2}
                          aria-hidden
                        />
                        <div>
                          <div className="text-sm font-medium text-ink">
                            Agent is checking the action
                          </div>
                          <p className="mt-1 font-mono text-xs text-faint">
                            Reading {HYPOTHESIS_ID}, then evaluating five blocking proofs.
                          </p>
                        </div>
                      </div>
                    </div>
                  ) : preflight ? (
                    <div className="my-1">
                      {preflight.proofs.map((/** @type {any} */ proof, /** @type {number} */ i) => (
                        <ProofRow key={proof.id} proof={proof} index={i} reduce={reduce} />
                      ))}
                    </div>
                  ) : (
                    <div className="my-5 rounded-xl border border-dashed border-border px-4 py-8 text-center">
                      <p className="mx-auto max-w-xs text-sm leading-relaxed text-muted">
                        No passport has been issued, so the verifier is not being called yet.
                      </p>
                      <p className="mt-3 font-mono text-xs text-faint">
                        {preview.proofs.length} obligations pending
                      </p>
                    </div>
                  )}
                </motion.div>
              </div>
            </div>

            <div className="overflow-hidden rounded-2xl border border-border bg-surface lg:sticky lg:top-40">
              <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
                <h3 className="font-display text-lg font-semibold text-ink">Execution gate</h3>
                <motion.span
                  key={decisionKey}
                  initial={reduce ? false : { opacity: 0, y: -6, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.24, ease: EASE }}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 font-mono text-[11px] font-medium uppercase tracking-wide",
                    decision.className
                  )}
                >
                  <decision.Icon
                    className={cn("size-3.5", decisionKey === "checking" && "animate-spin")}
                    strokeWidth={2.25}
                    aria-hidden
                  />
                  {decision.label}
                </motion.span>
              </div>

              <div className="px-5 pt-5">
                <div className="rounded-xl border border-border bg-bg/60 p-4">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-xs text-muted">Proposed action</span>
                    <span className="font-mono text-xs text-faint">
                      {CHAIN_LABEL} · {CHAIN_ID}
                    </span>
                  </div>
                  <div className="mt-1.5 break-all font-mono text-sm text-ink">
                    MockTreasury.rebalance({formatAmount(effectiveAmount)})
                  </div>
                  <div className="mt-2.5 flex items-baseline justify-between gap-3 border-t border-border pt-2.5">
                    <span className="text-xs text-muted">Action class</span>
                    <span className="font-mono text-xs text-primary-ink">{ACTION_CLASS}</span>
                  </div>
                </div>
              </div>

              <div className="px-5 py-5">
                {error && (
                  <p className="mb-3 font-mono text-xs text-proof-block" role="alert">
                    {error}
                  </p>
                )}
                <p className="mb-4 min-h-10 text-[13px] leading-relaxed text-muted">
                  {preflight ? preflight.reason : "No decision yet. Nothing is authorised to move."}
                </p>
                <button
                  type="button"
                  onClick={runPreflight}
                  disabled={!amountIsValid || busy}
                  className={buttonClasses("primary", "lg", "w-full")}
                >
                  {busy ? (
                    <>
                      <Loader2 className="size-4 animate-spin" strokeWidth={2.25} aria-hidden />
                      Running preflight
                    </>
                  ) : (
                    <>
                      {preflight ? "Run preflight again" : "Run agent preflight"}
                      <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden />
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </Step>

        {/* Langkah 03 adalah passport ATAU penolakan, tidak pernah keduanya. */}
        {preflight && !passportIssued && (
          <RefusalStep key={`refusal-${preflight.decision}`} preflight={preflight} reduce={reduce} />
        )}

        {passportIssued && (
          <PassportStep
            key="passport"
            preflight={preflight}
            reduce={reduce}
            executed={executed}
            onExecute={executeFixture}
          />
        )}

        {executed && (
          <OutcomeStep
            key="outcome"
            preflight={preflight}
            reduce={reduce}
            replayRejected={replayRejected}
            tamperRejected={tamperRejected}
            onReplay={tryReplay}
            onTamper={tryTamper}
          />
        )}
      </div>
    </>
  );
}

/**
 * Mesin apa yang menghasilkan keputusan di layar.
 *
 * Ini bukan hiasan dan bukan debug output. Ruang ini memanggil agen Python yang
 * sesungguhnya bila ia bisa dijalankan, dan jatuh ke simulasi aturan dalam JavaScript
 * bila tidak. Kedua keadaan itu terlihat identik tanpa penanda ini, dan halaman yang
 * tidak bisa dibedakan dari mesinnya adalah halaman yang membuat pembacanya salah
 * menyimpulkan. Jadi ia dinyatakan, bukan disiratkan.
 *
 * @param {{ preflight: any }} props
 */
function EngineNote({ preflight }) {
  const live = preflight.engine === "agent";
  return (
    <div
      className={cn(
        "mb-4 flex flex-wrap items-start gap-x-3 gap-y-1.5 rounded-xl border px-4 py-3 text-xs leading-relaxed",
        live
          ? "border-proof-pass/30 bg-proof-pass/[0.06]"
          : "border-proof-review/30 bg-proof-review/[0.06]"
      )}
    >
      <span
        className={cn(
          "inline-flex shrink-0 items-center gap-1.5 font-mono font-medium uppercase tracking-wide",
          live ? "text-proof-pass" : "text-proof-review"
        )}
      >
        <Radio className="size-3.5" strokeWidth={2.25} aria-hidden />
        {live ? "Live agent" : "Rule simulation"}
      </span>
      {live ? (
        <span className="text-muted">
          Decided by the same Python path{" "}
          <span className="font-mono text-ink">make demo-passport</span> runs, reading real Sibyl
          memory.
          {preflight.memoryRoot && (
            <>
              {" "}
              Memory root{" "}
              <span className="font-mono text-ink">{shortenHash(preflight.memoryRoot)}</span>.
            </>
          )}
          {preflight.deployment?.verifier && (
            <>
              {" "}
              Bound to the verifier deployed at{" "}
              <span className="font-mono text-ink">
                {shortenAddress(preflight.deployment.verifier)}
              </span>
              .
            </>
          )}
        </span>
      ) : (
        <span className="text-muted">
          The Python agent is not reachable, so this decision came from a JavaScript
          re-implementation of the rules. Sibyl was not read and nothing was hashed. Run{" "}
          <span className="font-mono text-ink">make demo-passport</span> to see the real mechanism.
          {preflight.engineReason && (
            <>
              {" "}
              <span className="text-faint">({preflight.engineReason})</span>
            </>
          )}
        </span>
      )}
    </div>
  );
}

/**
 * Satu langkah alur. Nomornya bukan hiasan: urutan inilah yang dijalankan agen.
 *
 * @param {{ n: string, title: string, state: "current" | "done", hint?: string,
 *   children: any, tone?: "default" | "pass" | "block" | "review" }} props
 */
function Step({ n, title, state, hint, children, tone = "default" }) {
  const ring =
    tone === "pass"
      ? "border-proof-pass/60 bg-proof-pass/10 text-proof-pass"
      : tone === "block"
        ? "border-proof-block/60 bg-proof-block/10 text-proof-block"
        : tone === "review"
          ? "border-proof-review/60 bg-proof-review/10 text-proof-review"
          : state === "done"
            ? "border-proof-pass/60 bg-proof-pass/10 text-proof-pass"
            : "border-primary bg-primary/15 text-primary-ink";

  return (
    <section className="border-b border-border py-10 last:border-b-0">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <span
          className={cn(
            "grid size-7 shrink-0 place-items-center rounded-full border font-mono text-[11px]",
            ring
          )}
        >
          {state === "done" ? <Check className="size-3.5" strokeWidth={2.5} aria-hidden /> : n}
        </span>
        <h2 className="font-display text-xl font-semibold text-ink">{title}</h2>
        {hint && <span className="ml-auto font-mono text-xs text-faint">{hint}</span>}
      </div>
      {children}
    </section>
  );
}

/** @param {{ proof: any, index: number, reduce: boolean | null, key?: any }} props */
function ProofRow({ proof, index, reduce }) {
  const tone = PROOF_TONE[proof.result] ?? PROOF_TONE.unverifiable;
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.42, ease: EASE, delay: reduce ? 0 : index * 0.075 }}
      className="border-t border-border first:border-t-0"
    >
      {/* Baris yang GAGAL terbuka sendiri: alasan penolakan tidak boleh disembunyikan. */}
      <details open={proof.result !== "satisfied"} className="group">
        <summary className="flex cursor-pointer list-none items-center gap-3 py-4 [&::-webkit-details-marker]:hidden">
          <span
            className={cn("grid size-6 shrink-0 place-items-center rounded-full border", tone.ring)}
            aria-hidden
          >
            <tone.Icon className="size-3.5" strokeWidth={2.5} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium text-ink">{proof.label}</span>
            <span className="mt-0.5 block truncate font-mono text-xs text-faint">{proof.id}</span>
          </span>
          <span
            className={cn("shrink-0 font-mono text-[11px] font-semibold tracking-wide", tone.text)}
          >
            {tone.word}
          </span>
        </summary>
        <div className="pb-4 pl-9">
          <p className="max-w-prose text-[13px] leading-relaxed text-muted">{proof.explanation}</p>
          <dl className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="border-t border-border pt-2">
              <dt className="text-[11px] uppercase tracking-wide text-faint">Observed</dt>
              <dd className="mt-1 font-mono text-xs text-ink">{proof.observed}</dd>
            </div>
            <div className="border-t border-border pt-2">
              <dt className="text-[11px] uppercase tracking-wide text-faint">Required</dt>
              <dd className="mt-1 font-mono text-xs text-ink">{proof.threshold}</dd>
            </div>
          </dl>
        </div>
      </details>
    </motion.div>
  );
}

/** @param {{ current: string, reduce: boolean | null }} props */
function StageRail({ current, reduce }) {
  const activeIndex = STAGES.indexOf(current);
  return (
    <div className="sticky top-16 z-10 border-b border-border bg-bg/85 backdrop-blur-xl">
      <div className="mx-auto max-w-6xl px-5 py-3">
        <ol className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-4">
          {STAGES.map((stage, i) => {
            const done = i < activeIndex;
            const active = i === activeIndex;
            return (
              <li
                key={stage}
                aria-current={active ? "step" : undefined}
                className="relative flex items-center gap-3 bg-bg px-4 py-3"
              >
                <span
                  className={cn(
                    "grid size-6 shrink-0 place-items-center rounded-full border font-mono text-[11px] transition-colors",
                    done
                      ? "border-proof-pass/60 bg-proof-pass/10 text-proof-pass"
                      : active
                        ? "border-primary bg-primary/15 text-primary-ink"
                        : "border-border text-faint"
                  )}
                >
                  {done ? <Check className="size-3.5" strokeWidth={2.5} aria-hidden /> : i + 1}
                </span>
                <span
                  className={cn(
                    "text-sm transition-colors",
                    active ? "font-medium text-ink" : done ? "text-muted" : "text-faint"
                  )}
                >
                  {STAGE_LABEL[stage]}
                </span>
                {active &&
                  (reduce ? (
                    <span className="absolute inset-x-0 bottom-0 h-[2px] bg-primary" />
                  ) : (
                    <motion.span
                      layoutId="stage-active"
                      className="absolute inset-x-0 bottom-0 h-[2px] bg-primary"
                      transition={{ type: "spring", stiffness: 420, damping: 38 }}
                    />
                  ))}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

/**
 * @param {{ preflight: any, reduce: boolean | null, executed: boolean,
 *   onExecute: () => void, key?: any }} props
 */
function PassportStep({ preflight, reduce, executed, onExecute }) {
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE }}
    >
      <Step n="03" title="Receive the passport" state="done" tone="pass" hint="single use">
        <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr] lg:items-start">
          <div>
            <p className="max-w-lg text-[15px] leading-relaxed text-muted">
              The agent does not return a trust score. It signs structured evidence for this target,
              this calldata, this state anchor, and this nonce, so the verifier can enforce exactly
              what was proven and nothing adjacent to it.
            </p>
            <div className="mt-6 flex flex-col items-start gap-3">
              <button
                type="button"
                onClick={onExecute}
                disabled={executed}
                className={buttonClasses(
                  executed ? "secondary" : "primary",
                  "lg",
                  "w-full sm:w-auto"
                )}
              >
                {executed ? (
                  <>
                    <Check className="size-4 text-proof-pass" strokeWidth={2.5} aria-hidden />
                    Fixture action executed
                  </>
                ) : (
                  <>
                    Execute exact fixture action
                    <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden />
                  </>
                )}
              </button>
              <span className="text-xs text-faint">
                local proof · wallet integration follows public deployment
              </span>
            </div>
          </div>

          {/* Passport terbuka lewat clip-path, seperti segel yang dipecah. */}
          <motion.div
            initial={reduce ? false : { clipPath: "inset(0 0 100% 0)", opacity: 0 }}
            animate={{ clipPath: "inset(0 0 0% 0)", opacity: 1 }}
            transition={{ duration: 0.75, ease: EASE, delay: 0.1 }}
            className="overflow-hidden rounded-2xl border border-proof-pass/35 bg-proof-pass/[0.06]"
          >
            <div className="flex items-center justify-between gap-4 border-b border-proof-pass/25 px-5 py-3">
              <span className="font-mono text-xs text-muted">ExecutionPassport</span>
              <span className="inline-flex items-center gap-1.5 font-mono text-xs text-proof-pass">
                <ShieldCheck className="size-3.5" strokeWidth={2.25} aria-hidden />
                EIP-712 shape · fixture preview
              </span>
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap px-5 pt-5 font-mono text-xs leading-relaxed text-ink [overflow-wrap:anywhere] sm:whitespace-pre sm:[overflow-wrap:normal]">
              {JSON.stringify(preflight.passport, null, 2)}
            </pre>
            {/* Penyangkalannya mengikuti mesin. Saat agen jalan, nilai-nilai itu BENAR-BENAR
                dihitung, dan menyebutnya placeholder akan salah. Saat fixture yang jalan,
                menyebutnya terhitung akan lebih salah lagi. */}
            <p className="border-t border-proof-pass/20 px-5 py-3.5 text-xs leading-relaxed text-muted">
              {preflight.engine === "agent" ? (
                <>
                  <span className="font-mono text-ink">calldataHash</span>,{" "}
                  <span className="font-mono text-ink">memoryRoot</span>, and{" "}
                  <span className="font-mono text-ink">obligationResultsHash</span> are computed by
                  the agent from the exact calldata and the Sibyl root it loaded. The passport is
                  unsigned: signing needs a private key, and no key runs inside a process that
                  serves web requests.
                </>
              ) : (
                <>
                  <span className="font-mono text-ink">calldataHash</span> and{" "}
                  <span className="font-mono text-ink">memoryRoot</span> are described here, not
                  computed, because the rule simulation produced this. Nothing on this page is
                  signed.
                </>
              )}
            </p>
          </motion.div>
        </div>
      </Step>
    </motion.div>
  );
}

/** @param {{ preflight: any, reduce: boolean | null, key?: any }} props */
function RefusalStep({ preflight, reduce }) {
  const review = preflight.decision === "human-review-required";
  const tone = review ? PROOF_TONE.unverifiable : PROOF_TONE.unsatisfied;
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE }}
    >
      <Step
        n="03"
        title={review ? "The agent stops for a human" : "The agent blocks the action"}
        state="current"
        tone={review ? "review" : "block"}
        hint="no passport issued"
      >
        <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-start">
          <div className="flex gap-4">
            <span
              className={cn(
                "grid size-11 shrink-0 place-items-center rounded-full border",
                tone.ring
              )}
              aria-hidden
            >
              <tone.Icon className="size-5" strokeWidth={2.25} />
            </span>
            <p className="max-w-xl text-[15px] leading-relaxed text-muted">{preflight.reason}</p>
          </div>
          <div className="border-t border-border pt-4 lg:min-w-56 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
            <span className="text-xs uppercase tracking-wide text-faint">Next move</span>
            <p className="mt-2 text-sm font-medium text-ink">
              {review
                ? "Restore the memory policy in step 01"
                : "Satisfy the failed obligation in step 01"}
            </p>
          </div>
        </div>
      </Step>
    </motion.div>
  );
}

/**
 * @param {{ preflight: any, reduce: boolean | null, replayRejected: boolean,
 *   tamperRejected: boolean, onReplay: () => void, onTamper: () => void, key?: any }} props
 */
function OutcomeStep({ preflight, reduce, replayRejected, tamperRejected, onReplay, onTamper }) {
  const tests = [
    {
      key: "consumed",
      state: "PASS",
      tone: "text-proof-pass",
      title: "Passport consumed",
      detail: `nonce ${preflight?.passport?.nonce}`,
      action: null,
    },
    {
      key: "tamper",
      state: tamperRejected ? "REJECT" : "READY",
      tone: tamperRejected ? "text-proof-block" : "text-muted",
      title: "Mutated calldata",
      detail: tamperRejected ? "calldata-mismatch" : null,
      action: tamperRejected ? null : { label: "Try amount + 1", onClick: onTamper },
    },
    {
      key: "replay",
      state: replayRejected ? "REJECT" : "READY",
      tone: replayRejected ? "text-proof-block" : "text-muted",
      title: "Passport replay",
      detail: replayRejected ? "nonce-already-used" : null,
      action: replayRejected ? null : { label: "Try replay", onClick: onReplay },
    },
  ];

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE }}
    >
      <Step
        n="04"
        title="Execute, then try to spend it twice"
        state="done"
        hint="verifier accepted once"
      >
        <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr] lg:items-start">
          <p className="max-w-md text-[15px] leading-relaxed text-muted">
            The fixture reserve moved from {formatAmount(INITIAL_RESERVE)} to{" "}
            {/* Angka ini KLAIM tentang state, bukan hiasan. Ia dirender apa adanya:
                angka yang sedang beranimasi adalah angka yang bisa tertinggal salah. */}
            <span className="font-mono tnum text-ink">{formatAmount(preflight.postReserve)}</span>{" "}
            MOCK, and the passport nonce is spent. Everything on the right is what the verifier now
            refuses.
          </p>

          <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
            {tests.map((test) => (
              <li key={test.key} className="flex items-center gap-4 px-5 py-4">
                <span
                  className={cn(
                    "w-16 shrink-0 font-mono text-[11px] font-semibold tracking-wide",
                    test.tone
                  )}
                >
                  {test.state}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm text-ink">{test.title}</span>
                  {test.detail && (
                    <span className="mt-0.5 block font-mono text-xs text-faint">{test.detail}</span>
                  )}
                </span>
                {test.action && (
                  <button
                    type="button"
                    onClick={test.action.onClick}
                    className={buttonClasses("secondary", "sm", "shrink-0")}
                  >
                    {test.action.label}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </Step>
    </motion.div>
  );
}
