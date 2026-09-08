---
title: "What broke while building it (and what is still broken)"
date: 2026-09-08
project: The Evaluator (Sibyl hackathon, Base Sepolia)
repo: EvaluatorVault 0x5c6EE4586ACABcb6326069c229E58091B21ef384
---

# What broke while building it (and what is still broken)

Two days before submission, the honest version of the last ten days. Not the smooth version — the one
that names four things that broke, who found them, and what we did afterwards.

## 1. Our destructive test used to run only the variant guaranteed to win

This hackathon's gate is blunt: strip out the memory layer, and if the project still does what it claims,
it is a wrapper. We built the destructive test ourselves — and the first version ran only **one** variant:
a fresh vault on local Anvil, memory empty, so a job that was REJECTED with memory present now passes at
an identical budget. Degradation visible, crowd pleased.

The problem: that is not the only thing that happens when memory is deleted. On a vault that is already
live — on-chain root non-zero — deleting `memory.db` triggers **safe mode** instead: the agent stops
entirely, zero `postVerdict`, the job hangs until `expiredAt`, the client gets a full refund. Showing only
one variant means picking the most flattering scene.

Now `make demo` runs **both**, and the second variant is not a stage we built ourselves: it runs against
the **frozen Base Sepolia vault**, so the non-zero `lastMemoryRoot()` is a real state. More importantly,
it **aborts the whole run** if the evidence does not appear — agent exit ≠ 0, the `MODE AMAN:` line not
printed, the gate not reporting `mode=safe`, the trigger not being the "file missing" rule, any
transaction sent, or the agent wallet's nonce moving. All of them come out as `VARIAN B GUGUR: …` in
`sim/src/demo.ts:672-685`. Its network touch is read-only, and that is **measured** through the nonce
before vs after, not asserted.

One label correction we ask judges to note: in the first variant, the mode the agent reports is `normal`,
**not** "naive mode". What shows the degradation is two other columns in the summary line — `depth=sampling`
and `cap=TANPA CAP` (ADR-026).

## 2. Our root guard was blind to `importlib`, `sys.modules`, and re-binding

We have a hard rule: only one function may produce the `memory_root` sent to `postVerdict`. Part of the
enforcement is a static scanner over the production path's source.

An adversarial security review broke through it. The first version of the scanner populated its module
list **only** from `import`/`from … import` nodes, so a module obtained via
`importlib.import_module(...)`, `__import__(...)`, or `sys.modules["…"]` was never recognised at all — and
a re-binding as simple as `alt = mp` cut the trail. Six forms were demonstrated to pass **without a single
red test**.

The fix was not patching one form but teaching the scanner to recognise modules obtained without an import
statement, plus tracking aliases. Those six forms are now tests that must go red:
`test_root_gate_scanner_catches_the_six_bypasses_from_the_4_1_review`
(`agent/tests/test_memory_policy.py:2175`). The lesson we wrote into the code: a scanner that never goes
red guards nothing, so every guard in this repo must carry its own proof that it can go red — plus a
negative control, so that "always red" does not pass as a working guard.

## 3. Our vault was frozen before it was finished, and 62,500 units froze with it

ADR-022 froze `0x5c6EE45…f384` as the submission contract. That decision was taken when a fix already
written in source — `sweepToken(address,address)` for withdrawing ERC-20 fees — had not yet landed in the
bytecode. We accept the consequence openly: that function is **absent** from the deployed contract, and
the 62,500 units of escrow token the vault holds (5% of two passed jobs) are **permanently stranded**.

Why we froze it anyway: all the on-chain evidence we offer — jobs 417 through 422, eight
`MemoryRootUpdated` events, job 420's `JobRejected` — is attached to that address. A redeploy would mean a
tidier but younger evidence chain, and a story restarted two days before the deadline. We chose evidence
that is flawed but whole over evidence that is clean but new. This decision can reasonably be judged
wrong, and we do not use the words "audited" or "production-ready" to cover it.

An equally bitter side effect, already written in the README: `arbiter()` == `agent()` on this instance,
and that is permanent because the contract is immutable.

## 4. `make demo` now needs internet — and we chose to fail loudly

A consequence of point 1: our demo command is no longer fully offline, because the second variant reads
the frozen Sepolia vault. There was a more comfortable option: silently skip when there is no network,
print "skipped", keep the run green.

We refused. The second variant is the climax of our destructive test; a green run that never executed it
is a run that lies about what was checked. So without internet, `make demo` does not finish — and that is
deliberate behaviour, recorded as a limitation, not as a feature.

One small surprise that we print as-is rather than hide: on a fresh vault, the agent's first invocation
**creates** `memory.db` midway, so the mode it planned no longer matches the mode read just before
signing, and the `MODE_DRIFT` guard refuses to transact — exit code 4, zero transactions, fail-closed. The
second invocation runs to completion. `make demo` prints `agent.retry … firstExit=4` as-is (ADR-026).

## 5. Judge panel: real checks in the browser — and a surface that just failed a security review

Evidence that can only be read as a table in a README is easy to suspect of being pre-cooked. So `web/`
has three routes: a timeline of jobs 418-422 with `VerdictPosted` tx links to BaseScan, a verdict +
per-criterion evidence page, and a **judge panel** where anyone can paste their own text, pick a depth, and
run the checks. What runs there is not a replay: the deterministic `format` and `links` checks are
**ported** from `agent/agent/checks/` to `web/src/lib/checks.js` and executed through `POST /api/evaluate`,
and that port produces a `checks` array identical to the 418/419/421/422 evidence bundles — down to the
`detail` and `proof` strings.

Until yesterday, that sentence had only ever been **checked once, by hand** — and a claim checked only by
hand breaks silently on the next change. Now it is **guarded by a test**:
`web/test/checks-parity.test.js` reads the text from `web/public/deliverables/<jobId>.json` and the
expectations from `web/public/verdicts/<jobId>.json` (bundles whose hashes are already announced on chain),
first verifies that the text's `sha_keccak` matches the `deliverable` the bundle records, then compares
**the whole check object** field by field — `check`, `criterion`, `depth`, `detail`, `pattern`, `proof`,
`section`, `status` — plus `failed_checks`, `unverified`, `category`, `verdict`, and the deterministic
criteria catalogue. Not a single expected string is retyped inside the test. The runner is Node 24's
built-in `node:test`, **zero new dependencies**, and `pnpm -r test` — once green over zero projects — now
runs 5 tests.

And like every other guard in this repo, it had to be proven capable of going red: changing one word in a
`detail` string turns all four jobs red, and raising `SAMPLING_SECTION_LIMIT` from 2 to 3 flips job 421
from pass to fail; restored, 5/5 green again.

Its limits are stated on the page itself: the panel does not run the cap gate, does not read memory, does
not call the 402 gate, and does not send transactions. There is no RPC from the browser; the data is
static JSON in `web/public/`. It has three dependencies, all pinned in `docs/versions.md` (next 16.3.2,
react 19.2.8, typescript 7.0.2).

There is also a memory-wipe button in the panel, for demonstrating the destructive test to an audience —
and this is where we lost. **That button's surface received a BLOCK verdict from the security review, with
two HIGH findings:** CSRF on its wipe endpoint, and a Next proxy exposing the loopback wiper to the LAN
because Next binds `0.0.0.0` by default.

The first deserves quoting because its lesson is bigger than this repo: **"loopback only" is not a defence
against a browser, because the judge's browser is also on loopback.** One malicious tab only needs to send
`<form method=POST action="http://127.0.0.1:8010/demo/memory/reset">`; that form sends `text/plain`, which
is CORS-safelisted, so no preflight holds it back — and the attacker does not need to read the response,
because wiping is a **side effect**, not a read. CORS was never a defence here.

**The block has since been lifted**, and the way it was proven is the way we think is correct: the
reviewer **re-ran exactly the attack that used to work**. The cross-origin form that once answered
`200 {"deleted": [3 files]}` now answers **403 `cross_origin_request`** with all three files intact;
`curl` from a LAN IP is stopped by two layers — the agent side refuses non-loopback peers, and Next is now
bound with `-H 127.0.0.1`. One MEDIUM finding (TOCTOU on ancestor path components) was closed via the
`dir_fd` route: deletion no longer uses a string path but the root directory's fd. Re-review: zero
CRITICAL, zero HIGH.

What we **still** name as risk, because "passed review" is not "nothing left": the Next proxy restricts
the target **host** to loopback but **not the port**, and the wiper's docstring admits a residual race
between `open` and `unlink` — its impact is limited to the honesty of the report, because the name cannot
escape the directory held by the fd. The full history is in item 36 of `docs/limitations.md`, written as
"failed → what failed → what closed it → what is still accepted", not as a feature that was always safe.

One boundary we set from the start and did not move under pressure: that button has power only over
**demo** memory (`agent/data/demo/`). It can never touch `agent/data/chain-abc/memory.db` — the only file
that can reconstruct the on-chain root.

## What is STILL not fixed

This is the part we would most like to write shorter, which is exactly why it is written out in full in
`docs/limitations.md` and summarised in the README's "Limitations & trust assumptions" section:

- **The incentive is not fixed.** The fee is only paid out on `Completed`; this referee is still paid only
  when it passes work. The up-front fee (ADR-004) is a design, and the 402 gate that exists is not
  consumed by any job path.
- **The stake is zero.** `MIN_BOND` = 0. `challenge`/`resolve` are stubs, so the 120-second window is
  latency with zero protection: a wrong verdict cannot be undone by anyone.
- **The root anchor is circular**, and of the eight vault roots only job 418's can be recomputed today.
- **A `memory.db` swapped for another DB is not detected** — safe mode checks the file's state, not its
  contents.
- **The destructive test leaves no artifacts**: `make demo` runs both variants but leaves no log or
  fixture in the repo, so what you can match against today is your own run.
- **`sim/` has no automated tests at all** — the only code touching the Virtuals SDK is guarded solely by
  hand-run on-chain chains (`web/` now has tests, point 5).
- **Residual risk on the memory-wipe surface**, accepted as-is: the target host is restricted, the port is
  not; and the `open`/`unlink` race the docstring admits itself (point 5 above).

The demo video is recorded tomorrow. What you will see there is exactly the same commands as in the
README — including that exit code 4.
