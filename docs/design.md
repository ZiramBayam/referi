# Problem, solution, and what sits outside the ERC-8183 spec

Item numbers refer to [`docs/limitations.md`](limitations.md). The flow diagram is in
[`README.md`](../README.md).

## Problem → solution

ERC-8183 puts all trust in the evaluator and gives it no reason to be honest: the evaluator is "fully
trusted", `evaluatorFeeBP` is only paid out when a job is **Completed** so the referee gets paid when it
passes work, there is no partial payment (Completed = 100% to the provider, Rejected/Expired = 100%
refund), and a standard evaluator is stateless — the same provider can repeat the same trick on the next
job without leaving a trace (`docs/spec.md` §1). The Evaluator adds three things on top of the spec:
**provider memory anchored on chain** (every `postVerdict` announces a `memoryRoot`; the **current**
state's root can be recomputed from the memory files, intermediate states cannot — items 7 and 16),
**budget gating through the `reject()` right during `Funded`**, which already exists in the spec and so
needs no whitelisted hook (ADR-001), and **an evaluator that is a contract** (`EvaluatorVault`) holding
the verdict, the time window, and the memory anchor (ADR-003).

Of those three spec defects, this submission attacks **one**: forgetfulness (statelessness). The fee
incentive defect still applies to this referee itself (item 14), and we did not touch "no partial
payment" at all — Rejected still means a 100% refund to the client, not a partial payment to the
provider.

One sentence that is often misquoted: "paid the same whether it passes or rejects". The up-front fee via
x402 that would make that sentence true is a **design (ADR-004), not a feature** (item 11). The sentence
comes from `docs/spec.md` §0, and §0 is titled "Pitch satu kalimat" (*one-sentence pitch*) — aspiration, not a factual record;
the README no longer quotes it as fact.

## Who uses this on day one, and why they would pay

A fair question: if I can already put my own address in `evaluatorAddress`, why do I need this? Our
answer names one concrete consumer, not "agents in general":

**The consumer: an operator running many ACP jobs against the same providers repeatedly** — in this repo
played by `sim/` as the client, and outside this repo it looks like a team buying repeated work
(research, summaries, data collection) from the same small set of providers. The trait that makes them a
day-one consumer: **they meet the same provider more than once**, so an evaluator's forgetfulness turns
directly into repeated loss.

**Why `evaluatorAddress` = your own EOA is NOT enough for that person:**

1. **An EOA has no memory it can show.** It can reject a job, but it cannot prove to the provider (or to
   anyone) **on what history** it rejected. Here the rejection reason is hash-bound to an evidence bundle
   containing `incident_jobs` and the cap, and that hash is announced on chain before execution
   (item 22).
2. **An EOA is a judge ruling on its own case.** A client acting as evaluator for its own jobs has an
   incentive to reject and collect a 100% refund. Moving that role to a third-party evaluator with
   auditable memory separates the two — and when that memory is **lost**, the agent stops transacting
   instead of guessing (item 22, and the destructive test in `docs/reproduce.md`).
3. **Calibration cannot be carried into the next job.** What got job 422 rejected was not a new rule but
   a check depth **derived from two earlier jobs** — on text identical to a job that passed (item 25). An
   EOA without memory would pass both.

**What they pay, and what they save.** The numbers we can show today come from the demo, not from market
research, so we state them as a **labelled illustration**, not a validated price. The contract rate
`evaluatorFeeBP` is **500** (5% of budget). On job 422 (budget 250,000 testnet units) that is **12,500
units** — and what it avoids is paying the **full 250,000 units** for a deliverable containing an
unfinished `TODO`, because Rejected means a 100% refund to the client (there is no partial payment in
ERC-8183). **That ratio is 1:20**: pay 5% to avoid losing 100% on a job that should not have passed. The
break-even is therefore low — this evaluator "pays for itself" if it catches more than one bad job in
every twenty.

Two things keep those numbers from being read as evidence of demand: (1) 5% is a rate that already exists
in the ACP contract, **not** a price we set or tested; (2) today that fee is only paid out on
`Completed`, so on the rejected job 422 the evaluator received **0** (item 14) — a structure that turns
the 1:20 ratio above into an argument for an up-front fee (ADR-004), not a picture of today's cash flow.

**The honesty that goes with it:** today that consumer is our own simulator (item 21), there are no
third-party users, the 402 payment gate that would bill them is not wired into the job path (item 23),
and the simulator wallet is not registered in the Virtuals Service Registry (item 24). What is real is
the mechanism on chain; what is not yet real is the demand.

## Outside the ERC-8183 spec — and why

| Addition | Reason | ADR |
|---|---|---|
| **EvaluatorVault** as the evaluator address (not an EOA) | the spec has no evaluator bond/challenge/timeout; the spec does allow the evaluator to be a contract | ADR-003 |
| **On-chain memory anchor** (`MemoryRootUpdated`, `knownRoots`) | every execution against ACP is bound to a root announced BEFORE execution; the limit: of the **eight** vault roots only **418** can be recomputed today, the rest are intermediate states lost permanently (item 7), and the anchor is circular (item 16) | ADR-011 |
| **Cap gating via `reject()` during `Funded`** | a custom hook needs a Virtuals admin whitelist we do not have; the reject right during Funded is already in the spec. Enforcement is off-chain; the contract only publishes the cap (item 17) | ADR-001 |
| **Quarantine as a `suspicion` entity** | Sibyl only has HOT/WARM/COLD/REFERENCE/ARCHIVE — there is no FLAGGED tier, so quarantine is built as a convention, and the decision path is forbidden to read it | ADR-002 |
| **Bond + dispute window** | designed, but today `MIN_BOND` = 0 and `challenge`/`resolve` are stubs — see items 1-2 | ADR-013 |
| **Up-front fee via x402** | the contract fee is only paid out on Completed → an incentive to pass, **including for this referee itself**. **Not implemented** (items 11 and 14) | ADR-004 |
