# Limitations & trust assumptions

The complete list of REFERI's limitations. The numbering **does not change** from earlier README
versions — `demo/video-script.md` and `docs/posts/` refer to these items by
the same numbers. A summary of the eight most important ones is in [`README.md`](../README.md).

Items 1-13 were moved here as-is from the ADRs and the deploy artifacts; items 14-25 were added after a
"claims vs reality" audit and their sources are code and chain data you can open yourself. The numbers
are not softened. Items 26-35 come from security reviews of the contract and the agent: each one was
**proven by the reviewer through adversarial tests** — the role that tried it and the error it got — not
inferred by reading code. Item 36 is a review finding on `web/` that was **not fully closed** when this
document was written.

If you only have time for four: **item 14** (the fee incentive is not fixed — the biggest reversal),
**item 16** (the root anchor is circular and carries no consequence), **item 19** (the destructive test
leaves no artifacts), and **item 22** — the vault's `lastMemoryRoot()` is **deliberately not equal** to
`memory_export` over today's DB, because memory is written after `postVerdict`. If you are going to copy
exactly one command block, read item 22 first so you know which values are supposed to match.

And if you read only one item from the 26-36 group: **item 26** — a wrong verdict cannot be undone by
anyone, so `CHALLENGE_WINDOW` today is latency with zero protection. If you intend to **run** `web/`
yourself, read **item 36** first — it holds the full history of the memory-wipe surface: a BLOCK verdict,
what failed, what closed it, and the LOW risk we still accept.

## 1. What the evaluator stakes today = zero

`MIN_BOND` on the deployed contract is **0** (`deployments/84532.json` → `"minBondWei": "0"`). The deploy
note from that same file, verbatim:

> `minBondWei = 0 disengaja: vault belum punya jalur ETH keluar (ADR-013), jadi bond yang disetor akan
> terkunci permanen.`
>
> *(gloss: minBondWei = 0 is deliberate: the vault has no ETH exit path yet (ADR-013), so a deposited
> bond would be locked permanently.)*

Which means: `deposit()` exists and is real, but today the evaluator **stakes nothing on chain**, and
deposited ETH has no way out. Quoting ADR-013: "Bond evaluator lewat `deposit()` tetap nyata dan tetap
dipertaruhkan secara sosial, tetapi hari ini tidak ada jalur on-chain yang menyitanya." *(gloss: the
evaluator bond via `deposit()` is still real and still socially at stake, but today no on-chain path
confiscates it.)*

## 2. `challenge`/`resolve` are stubs — `CHALLENGE_WINDOW` is pure latency

`challenge(uint256,bytes32)` and `resolve(uint256,bool)` are in the ABI as required by `docs/spec.md` §4,
with bodies of `revert NotImplemented()` (ADR-013). The consequence: the **120-second window**
(`deployments/84532.json` → `constants.CHALLENGE_WINDOW: 120`) is a waiting period, **not a protection**.

A wrong verdict cannot be undone by anyone before `finalize`: the agent gets `VerdictAlreadyPosted`, and
challengers and the arbiter get `NotImplemented` (finding by @agent-security-reviewer on
`EvaluatorVault`, task 4.3b). "Bonded disputes" are **v2**, not a live feature — ADR-013 forbids calling
it a feature.

## 3. `arbiter()` == `agent()`, and that is permanent

```
$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "arbiter()(address)" --rpc-url https://sepolia.base.org
0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894

$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "agent()(address)" --rpc-url https://sepolia.base.org
0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894
```

Both addresses are the SAME. The same values are recorded in `deployments/84532.json` (`"agent"`,
`"arbiter"`), and that file's note states the consequence plainly:

> `arbiter == agent pada deploy ini, dan tetap begitu SELAMANYA: ADR-022 membekukan alamat ini sebagai
> kontrak submission, kontraknya immutable, jadi tidak ada redeploy yang memisahkannya.`
>
> *(gloss: arbiter == agent on this deploy, and stays that way FOREVER: ADR-022 freezes this address as
> the submission contract, the contract is immutable, so no redeploy will separate them.)*

What mitigates it, and you can check this yourself: on this contract the **arbiter has no on-chain
powers at all** — `resolve()` is a stub (item 2) and `sweepToken` is absent from the deployed bytecode
(item 4). A decentralised arbiter (`v2: ERC-8004 validation`, `docs/spec.md` §4 line 136) is out of scope
for this build.

What does **not** mitigate it, and must be said: **one key, immutable, with no rotation and no pause.**
`acp`, `agent`, `arbiter`, and `MIN_BOND` are declared `immutable` with no setters at all
(`contracts/src/EvaluatorVault.sol:106-114`; the scope note on line 14 names "pause" as something
deliberately absent), and in `deployments/84532.json` the `agent`, `arbiter`, and `deployer` fields all
hold the same address — one EOA is deployer, agent, arbiter, and the only signer. The consequence runs
both ways and is permanent: **key lost** → this vault can never `postVerdict` / `setProviderCap` /
`finalize` again, and unfinalized verdicts hang forever; **key stolen** → arbitrary verdicts, caps, and
`memoryRoot` values with no path to undo them (`resolve` is a stub, item 2).

## 4. The deployed contract has NO `sweepToken`; 62,500 token units are permanently stranded

```
$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "sweepToken(address,address)" \
    0xECc22a8F6fD62388498fBa19813E214605a2BDb3 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894 \
    --rpc-url https://sepolia.base.org
execution reverted
```

`sweepToken(address,address) onlyArbiter` landed in the **source** (commit `e675234`) as code plus tests
only; ADR-022 froze the address above as the submission contract and cancelled the redeploy, so that
function is not in the deployed bytecode.

The vault holds **62,500 units** of the escrow token, and that is a balance you can still read yourself
right now:

```
$ cast call 0xECc22a8F6fD62388498fBa19813E214605a2BDb3 "balanceOf(address)(uint256)" \
    0x5c6EE4586ACABcb6326069c229E58091B21ef384 --rpc-url https://sepolia.base.org
62500
```

That number = `evaluatorFeeBP()` 500 = 5% of the budgets of the two jobs that reached `Completed`:
**50,000** from job 417 (budget 1,000,000, `deployments/pipeline-84532.md:84`, fund-flow table) +
**12,500** from job 421 (budget 250,000, the depth demo — item 25). Both are jobs the evaluator
**passed**; the four jobs it rejected contributed zero (item 14). The ADR-018 artifact sentence was
written while the balance was still 50,000; we paste it as-is together with its correction:

> `50.000 unit (0,05 USDC testnet) hangus permanen; ini dilepas secara sadar oleh ADR-018 keputusan 2,
> bukan kelalaian.`
>
> *(gloss: 50,000 units (0.05 testnet USDC) are permanently stranded; this was consciously accepted by
> ADR-018 decision 2, not an oversight.)*

What is stranded today is **62,500**, not 50,000 — the artifact's number was correct on its date and has
since been overtaken by job 421. The reasoning is unchanged: there is no way out of this frozen vault.

## 5. Public `claimRefund` + `EVALUATOR_GRACE_PERIOD` of 900 seconds → orphan verdicts are an ACCEPTED risk

`claimRefund` on the ACP contract can legitimately be called by **anyone** from Open/Funded/Submitted; for
Submitted there is an `EVALUATOR_GRACE_PERIOD` of **900 seconds** after `expiredAt`, and after that
refund the evaluator's `complete`/`reject` revert with `WrongStatus()` (`docs/api-facts.md` §A CORRECTION
2026-09-03, from a fork of the original bytecode + Sourcify-verified source; summarised in ADR-014).

Our contract **cannot prevent this**: permission for `claimRefund` lives in ACP, not in the vault
(ADR-014). Mitigation exists only on the agent side (re-reading the status before `postVerdict` and
before `finalize`), and the value 900 is read on chain, never hardcoded in agent code. As a result an
orphan verdict (the job already refunded via `claimRefund`, the vault verdict living on forever with no
on-chain marker) can happen — ADR-015 records it as an accepted consequence, not an undiscovered bug.

## 6. Deliverable text does NOT come from the official ACP API

The SDK's `session.submit()` calls `api.postDeliverable` against the Virtuals off-chain API, and that API
rejects our simulator wallet — `POST https://api.acp.virtuals.io/auth/agent` → **404**
`Agent not found with wallet address 0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2` (verified 4 Sep,
ADR-019). So on chain there is only the deliverable's `keccak256`, not its text.

ADR-019's decision: `sim/` writes the text to `demo/deliverables/<jobId>.json`
(`{"jobId","text","sha_keccak"}`), and the agent reads it **only** from there and must re-verify that
`keccak256(text)` equals the on-chain `deliverable` value before evaluating; mismatch or missing file →
the agent stops with zero `postVerdict` and zero `finalize`. This is a local artifact bound to the chain,
but it is **not** an official ACP source, and that is a real limitation of this submission.

## 7. Three of the eight vault roots are NOT derived from memory — and one more root is permanently lost

The ADR-018 rollback path is active (ADR-022 froze v1), so the vault's root history carries leftovers
from the early pipeline. The following two root **values** are **labelled constants**, not derived from
memory (and together they fill **three** of the eight `MemoryRootUpdated` events — full table below).
**Neither can be reconstructed from any `memory.db`**, and we paste their preimages so you can check for
yourself:

```
$ cast keccak "the-evaluator/live/memory-root/v1"
0x1fa62c3db5c16f4c831ee1d9ee4c083745b8c8bae86bda3587b8b02ba52f7bf0

$ cast keccak "the-evaluator/selftest/memory-root/v1"
0x5ff921fda73362d23f66dcac204d1ace7a287fa0a2cf3bde12e4b37c6812a19e
```

- **Live pipeline 1.3d (job 417):** `0x1fa62c3d…7bf0`. It was briefly the vault's `lastMemoryRoot()`
  (ADR-023 context, demonstrated with `cast call <vault> "lastMemoryRoot()(bytes32)"` at the time).
- **The `--selftest` path (task 1.3b):** `0x5ff921fd…a19e`, recorded in ADR-023 decision 4 as
  `SELFTEST_MEMORY_ROOT`. Its definition is still findable in git history — commit `26f11d6`,
  `SELFTEST_MEMORY_ROOT = bytes.fromhex("5ff921fd…a19e")` with the comment
  `keccak256("the-evaluator/selftest/memory-root/v1")`, revoked by commit `190cb44`.

That selftest root really was **announced on chain, twice**, but over **SYNTHETIC jobIds**, so it never
touched a single real ACP job:

```
$ cast logs --address 0x5c6EE4586ACABcb6326069c229E58091B21ef384 \
    0xc6028d32061c1f0b8f4f1370b6f1ab5105a96bfc6631a3840371ebbcb27c7923 \
    --from-block 46355036 --to-block 46355080 --rpc-url https://sepolia.base.org

block 46355036  jobId 0x895440 = 9000000  root(topic1) 0x5ff921fd…a19e
block 46355080  jobId 0x895441 = 9000001  root(topic1) 0x5ff921fd…a19e
```

(Both `MemoryRootUpdated` arguments are `indexed`, so the root is in **topic1** and `data` is empty — a
script decoding `data` will get nothing.)

Both were **REVOKED from the production path** by task 2.4b (commit `190cb44`): the only source of a
`memory_root` that may be sent to `postVerdict` is `memory_policy.memory_root()`, the same function used
by `agent/memory_export.py`, and `_send()` **refuses to sign** if the root in the calldata does not match
memory at that moment — enforced in `_send()`, not in the caller (`agent/agent/vault_client.py:1339`,
`_require_derived_root`, called from `_send()` :1473).

But `postVerdict` writes every root into `knownRoots` **with no remover** (ADR-011), so both constants
remain valid roots forever in the frozen vault. Framed plainly: **the submission vault carries a
permanent trace of a phase that predates its own rule.** That is a fact we acknowledge, not one we hide.

**The vault's complete root history, all eight, so nothing is left for you to find on your own.**
`MemoryRootUpdated` was emitted **eight times** over the vault's lifetime (`cast logs` on topic0
`0xc6028d32…7923`, blocks 46350667→46455552, split into windows of ≤ 9,999 blocks because of the public
RPC limit — `docs/api-facts.md` §E). The root is in topic1, the jobId in topic2:

| # | root | jobId | what it is | recomputable today? |
|---|---|---|---|---|
| 1 | `0x5ff921fd…a19e` | 9000000 (synthetic) | selftest constant | no — labelled constant, preimage above |
| 2 | `0x5ff921fd…a19e` | 9000001 (synthetic) | selftest constant | no — same |
| 3 | `0x1fa62c3d…7bf0` | **417** | legacy constant from the early pipeline | no — labelled constant, preimage above |
| 4 | `0x4e2a1ca1697b2a287fcfc8158fd5c460298aa69af8d5bec2d35671d71c4dff5a` | **418** | the **empty** memory root | **yes** — anyone can, from a new DB |
| 5 | `0x3f506e52977407d8a4a1eb88179773f66679c992e6c74ac3cf20adcd7b9eecc2` | **419** | intermediate state | **no — PERMANENTLY LOST** |
| 6 | `0xcfdab1b0…5b26` | **420** | the state after 419 (job 420 was a gate rejection: it writes no memory) | **no — PERMANENTLY LOST** |
| 7 | `0xcfdab1b0…5b26` | **421** | the SAME state as #6 — see the explanation below | **no — PERMANENTLY LOST** |
| 8 | `0x999a9570…9b7d` | **422** | the state after job 421 wrote its memory | **no — PERMANENTLY LOST** |

Row 4 needs explaining so it does not read as more impressive than it is: job 418's root is **identical
to the empty-DB root**, and that is a **mechanical coincidence**, not a property we designed. The reason
is in `docs/spec.md` §5 step 5 — memory is written **after** `postVerdict`, so when job A's verdict was
announced its memory really was still empty. Anyone can reproduce it **without any of our memory files
at all**:

```
$ cd agent && uv run python -c "from agent.memory_policy import empty_memory_root; print(empty_memory_root().hex())"
4e2a1ca1697b2a287fcfc8158fd5c460298aa69af8d5bec2d35671d71c4dff5a
```

One correction to how an earlier README version wrote this: the reproduction is **not** via
`memory_export.py` over a "new DB". The export tool **deliberately refuses to create a DB** and stops
with `MemoryExportError: DB memori tidak ditemukan … (alat ini sengaja TIDAK membuat DB baru)`
*(gloss: memory DB not found … this tool deliberately does NOT create a new DB)*, so there is no "new DB"
to point it at. The correct path is the function above — and its value is exactly the same, as ADR-026
decision (e) already measured. Precisely because of that, this root **proves nothing about the contents
of memory** — it only proves the memory was empty.

**Why #6 and #7 have the same value, and why that matters.** Job 420 was a **gate rejection**: it was
rejected while `Funded` because the budget exceeded the cap, so it never produced an `evaluation` and
therefore **wrote nothing to memory**. The root announced by job 421 is therefore still exactly the state
job 420 saw. Only after job 421 finished and wrote its memory did job 422 announce a different value
(`0x999a9570…9b7d`). That "write **after** post" ordering is what keeps every on-chain root **one write
behind** the memory file.

So the correct claim is not "only the last root is auditable", it is: **the only vault root that can be
recomputed today is 418, and that is precisely because the memory was still empty at the time.** Roots
419, 420/421, and 422 are all **intermediate states, permanently lost**. The Sibyl DB stores the
**current** state — no version table, no per-job snapshot — so intermediate states cannot be rebuilt once
memory moves on. The most important conclusion stands: **this anchor expires every time memory changes.**
A per-job root log for backward audits is v2 (ADR-023 decision 5).

What you **can** still verify yourself today, and this is what we ask you to check, is **the binding
between the on-chain root and the evidence bundle** — see item 22.

## 8. The initial cap is a TEAM PARAMETER, not a learned result

`BASELINE_CAP_USDC` = **1,000,000** (1 USDC, 6 decimals) and the floor `MIN_CAP_USDC` = **250,000** are
constants chosen by the team (ADR-020 decisions 3 and 5). ADR-020's consequence, verbatim:

> `Cap awal kini angka pilihan tim, bukan turunan data; WAJIB disebut di README sebagai parameter, bukan
> disamarkan sebagai hasil pembelajaran.`
>
> *(gloss: the initial cap is now a team-chosen number, not derived from data; it MUST be stated in the
> README as a parameter, not disguised as a learned result.)*

ADR-021 decision 1 installs a growth ceiling: each PASSED job's contribution to the median is capped at
`min(budget, BASELINE_CAP_USDC)`, so a **history-derived cap never exceeds 1,000,000**, and for risk ≥ 2
never exceeds 250,000. It is one-directional: **memory can only TIGHTEN the cap, never loosen it.**
"Providers build trust through a good history" is **not** a claim you may read out of this system —
reputation recovery is v2 (ADR-021 consequences).

What holds on the demo chain, as-is: the **250,000** cap that rejected job C **was not learned from
data**. The job 420 evidence bundle records for itself `"cap": {"basis": "baseline-constant",
"sample_size": 0, "usdc": 250000}` — `sample_size: 0` means **zero** passing budgets went into the
calculation, so the number is `ceil(BASELINE_CAP_USDC / 4)` = `ceil(1,000,000 / 4)` from a team constant
(`agent/agent/memory_policy.py:1666`, branch `basis = "baseline-constant"`). What **does** come from
memory is the **risk level** (risk = 2, the result of pattern promotion on jobs A and B) — and the risk
level is what picks the divisor of 4. Read the "What changed in memory" column (`docs/evidence.md`) with
that limit in mind.

And the easiest thing to misread, from ADR-021 decision 4:

> `Cap BUKAN pertahanan tunggal terhadap provider curang; ia hanya membatasi UKURAN kerugian per job.
> Pertahanan terhadap deliverable curang tetap cek deterministik dan mode aman.`
>
> *(gloss: the cap is NOT the only defence against a cheating provider; it only bounds the SIZE of the
> loss per job. The defence against a cheating deliverable remains the deterministic checks and safe
> mode.)*

## 9. The agent is invoked per job — it is not autonomous

The event watcher was dropped from the critical path (ADR-022 decision 3). Today the agent is run once
per job with `--job-id <N> --kind reject|complete`; without `--kind` it exits with code 2 having made no
RPC call at all. The claim "autonomous agent" is forbidden in the README/video/posts by ADR-022 — and it
does not appear.

## 10. The detection that is MISSING, stated plainly

ADR-024's consequence sentence, verbatim:

> `HILANG: deteksi "memory.db diganti DB LAIN", baik kosong maupun terisi.`
>
> *(gloss: MISSING: detection of "memory.db replaced by ANOTHER DB", whether empty or populated.)*

Safe mode v1 is triggered by **local memory being unreadable**, not by a root comparison. There are
exactly three triggers, and the third has an extra condition that is easy to miss
(`agent/agent/memory_policy.py:1461-1500`):

1. the single-instance lock on `memory.db` cannot be acquired;
2. the DB file exists but `load_snapshot`/`memory_root` raises;
3. the DB file is **missing** — **AND** the on-chain `lastMemoryRoot()` is **non-zero**. If the on-chain
   root is zero (fresh vault / day one), a missing DB file gives **NAIVE mode**, not safe mode. That
   second condition is what makes the destructive test possible at all.

**The consequence of that missing detection, stated all the way through:** if `memory.db` is not deleted
but **replaced by another readable DB**, none of the three triggers above fire. The agent enters
**NORMAL MODE**, issues a full verdict, and anchors the root from the swapped DB — forever, because
`knownRoots` has no remover (item 7) and there is no path to undo it (items 2, 16).

Hardening based on a local root log is v2 (ADR-023 decision 5, ADR-024 decision 2). While safe mode is
active the agent stops entirely: zero `postVerdict`, zero `finalize`, zero `setProviderCap` — the job
hangs until `expiredAt`, then anyone may call `claimRefund` and the client gets a full refund. That is
the intended behaviour (ADR-020 decision 8), and recovery means restoring `memory.db` from backup.

## 11. What IS in the specification but is NOT live yet

Do not judge from `docs/spec.md` alone — here is what is not running today:

| Not live | Evidence |
|---|---|
| ~~`make demo`~~ | **NOW LIVE** since commit `a03e294` — it runs §7 steps 1-4 from scratch on local Anvil; the SECOND destructive variant (safe mode) followed in commit `986fad6`. Still missing: the artifacts (logs/fixtures) it should leave behind — item 19 |
| x402 up-front fee (ADR-004) | the 402 gate EXISTS (`agent/agent/payment_402.py`), but is **not consumed by the job path** — item 23 |
| `MemoryGateHook` | not present in `contracts/src/` (only `EvaluatorVault.sol`, `IACP.sol`); hooks need a Virtuals admin whitelist (ADR-001) |
| LLM rubric | cut; only the deterministic checks run (`agent/agent/checks/`: `format`, `links`, `chain`) |
| `checks/sandbox` | not implemented and not claimed as live |
| ~~web UI / judge panel~~ | **NOW LIVE** — `web/` has three routes (`web/src/app/page.jsx`, the timeline of jobs 418-422 with `VerdictPosted` tx links; `web/src/app/verdict/[jobId]/page.jsx`; `web/src/app/panel/page.jsx`), and the judge panel runs **genuine** deterministic checks in the browser through `POST /api/evaluate` over the `format`+`links` port in `web/src/lib/checks.js`. That port's parity is **guarded by tests** (`web/test/checks-parity.test.js`, 5 tests via `pnpm -r test` — item 18). What it does NOT do: the panel does not run the cap gate, does not read memory, and does not send transactions (stated on the page itself), and the `DEMO_MODE` memory-wipe surface failed a security review before it was closed — the full history plus the LOW risk still accepted is in item 36 |
| event watcher | item 9 |

## 12. Artifact limitation: the memory files are not committed

`data/` is in `.gitignore:3`, so the A/B/C chain's `memory.db` and the `reasonHash` evidence bundles are
**not in the public repo**. Third-party root reconstruction requires those files to be handed over first;
the verification command (`agent/memory_export.py --check`) does not touch the DB. The claim "anyone can
reconstruct the root" is therefore mechanically true, but the files have not been published yet.

## 13. The escrow token on Base Sepolia is NOT Circle USDC

The ACP contract's `paymentToken()` = `0xECc22a8F6fD62388498fBa19813E214605a2BDb3`, and that is **not**
Circle's USDC `0x036CbD53842c5426634e7929541eC2318f3dCF7e`. Both carry the symbol `USDC`, so compare
**addresses**, not `symbol()` (`deployments/84532.json` → `notes`). That testnet token also has a
`mint()` with no access control (ADR-017/ADR-021) — a fact that shaped the cap decision in item 8.

## 14. The evaluator incentive is NOT fixed — this referee is still paid only when it passes work

This is the biggest reversal in this repo.

The ACP contract's `evaluatorFeeBP()` = **500** (5%), and that fee is **only paid out when a job is
`Completed`** (`docs/spec.md` §1 line 19; fund-flow table `deployments/pipeline-84532.md:84`). The
arithmetic consequence on the chain today:

- job **417** (`Completed`, and a job the evaluator **PASSED**) → the vault received **50,000** units;
- jobs **418, 419, 420** (demo chain A/B/C, all three **REJECT**) → the vault received **0**;
- job **421** (`Completed`, the depth demo — the evaluator **PASSED** it) → the vault received **12,500**
  units (5% of the 250,000 budget);
- job **422** (**REJECT**, the exact same deliverable as 421 — item 25) → the vault received **0**.

You can read the total yourself, and the number **rises** precisely on the jobs that were passed:

```
$ cast call 0xECc22a8F6fD62388498fBa19813E214605a2BDb3 "balanceOf(address)(uint256)" \
    0x5c6EE4586ACABcb6326069c229E58091B21ef384 --rpc-url https://sepolia.base.org
62500
```

**62,500 = 50,000 (job 417) + 12,500 (job 421), and both come from jobs that were PASSED.** The four
rejected jobs contributed nothing. All 62,500 is **permanently stranded** because `sweepToken` is not in
the deployed bytecode (item 4).

So in this submission the fee flows exactly along the bias ERC-8183 is criticised for: payment arrives
only together with a pass. The fix — the client paying up front via x402 at an identical rate for
`complete` and `reject` — is designed in ADR-004, and its 402 gate **exists** today
(`agent/agent/payment_402.py`) but is **not consumed by the job path** (item 23). What prevents that bias
from biting today is not the incentive structure but something far weaker: the fee is locked in the vault
so nobody can enjoy it.

## 15. The submission contract IS NOW verified on Sourcify (`exact_match`) — from commit `8d3e596`, not HEAD

An earlier README version stated that a Sourcify query returned
`{"match":null,"creationMatch":null,"runtimeMatch":null}`. That has **no longer been true** since 8 Sep
2026:

```
$ curl -s https://sourcify.dev/server/v2/contract/84532/0x5c6EE4586ACABcb6326069c229E58091B21ef384
match: exact_match   creationMatch: exact_match   runtimeMatch: exact_match
```

The values are recorded in `deployments/84532.json:36-44` (`sourcify`), together with the re-check command
and a link to the Sourcify repo. **What makes this claim traceable is where it was verified from**:
source at **commit `8d3e596`**, NOT HEAD — HEAD already contains `sweepToken`, which is absent from the
on-chain bytecode (item 4). Before uploading, the build was compared against `cast code` and the numbers
recorded as-is (`deployments/84532.json:31-32`):

- runtime length **identical, 3518 bytes**;
- **174 bytes differ, ALL of them inside `immutableReferences`** (`acp`, `agent`, `arbiter`, `MIN_BOND`)
  — zero differing bytes outside the immutable spans;
- **the last 32 metadata-hash bytes are IDENTICAL** (a trap we hit: `lib/` as a symlink pushed absolute
  remappings into the solc metadata and inflated the false diff to 206 bytes — so the verification
  worktree copies `lib/` physically).

**A limit that still holds, and please do not generalise it to all explorers.** Blockscout imported that
Sourcify verification and now **decodes vault events by name** — `Finalized`, `MemoryRootUpdated`,
`VerdictPosted`, `ProviderCapSet`, `FinalizeFailed`
(`https://base-sepolia.blockscout.com/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384?tab=logs`).
**BaseScan does not follow**, because Etherscan does not import from Sourcify and verifying there needs an
API key this repo does not have; we therefore **claim nothing in either direction** about its status on
BaseScan. On any explorer, the transactions, events, and `cast call` results used as evidence remain real
with or without source verification.

One old provenance limit that has **not** changed: the artifact
`contracts/broadcast/Deploy.s.sol/84532/run-1788469622537.json` — which records `"commit": "8d3e596"`
itself and whose init code is byte-identical to a build of that revision — is excluded by `.gitignore:6`,
so **it is not in the public repo**. Sourcify now covers the "which source became this bytecode" question;
what still needs that artifact is an independent check of the init code plus constructor arguments.

## 16. The root anchor is circular, and there is no consequence for a fabricated root

Two facts that must be read side by side:

- **Off-chain:** `_require_derived_root` compares the root in the calldata against the root the agent
  **just computed from the file it read itself** (`agent/agent/vault_client.py:1339`,
  `_require_derived_root`).
- **On-chain:** `postVerdict` only rejects a **zero** root (`if (memoryRoot == bytes32(0)) revert
  ZeroMemoryRoot();`, `contracts/src/EvaluatorVault.sol:303`). **Any** non-zero root is accepted.

So the root proves "**the agent hashed a file**", not "**that file is the real memory**". And if the root
is fabricated, no consequence awaits: `MIN_BOND` = 0 (item 1), `challenge`/`resolve` are stubs (item 2),
arbiter == agent (item 3). Combined with item 10, the worst path is complete: swapped DB → NORMAL mode →
full verdict + a fake root anchored forever, with no challenger.

## 17. The cap is PUBLISHED by the contract, but NOT enforced by the contract

What rejected job C is the **off-chain Python agent**, not the contract. In
`contracts/src/EvaluatorVault.sol` the word `providerCap` appears **exactly twice**: line **142** (the
declaration `mapping(address => uint256) public providerCap;`) and line **289** (the write inside
`setProviderCap`). **Zero reads** — there is no branch in `postVerdict` or `finalize` comparing a job's
budget against the cap. The contract works as a **noticeboard anyone can read**, and that is still useful
(the number is public, time-bound, and comparable against the verdict) — but it is not an enforcer.

## 18. `pnpm -r test` now runs ONE project — and `sim/` still has zero tests

An earlier README version stated that `make test`'s third suite was green over **zero** projects. That is
**no longer true**: `web/package.json:11` now has `"test": "node --test test/checks-parity.test.js"`, so
`pnpm -r test` runs **one** project with **five** tests.

Its content closes a gap we used to admit ourselves: the claim "the `web/src/lib/checks.js` port produces
a `checks` array identical to the on-chain evidence bundle" used to be **checked once, by hand**; it is
now **guarded by tests** (`web/test/checks-parity.test.js`). What is compared is not port output against
port output: the text is read from `web/public/deliverables/<jobId>.json` and the expectations from
`web/public/verdicts/<jobId>.json`, with the binding `sha_keccak` of the text == the bundle's
`evaluation.deliverable` checked first (`:65-71`), then the **whole check object** compared field by
field — `check`, `criterion`, `depth`, `detail`, `pattern`, `proof`, `section`, `status` (`:77-93`) —
plus `failed_checks`, `unverified`, `category`, `depth`, `verdict` (`:95-99`) and the deterministic
criteria catalogue (`:103-110`), for jobs **418, 419, 421, 422**. The runner is Node's built-in
`node:test` on the Node 24 major line (`docs/versions.md:9`, actual `v24.15.0`) — **zero new
dependencies**. `web/test/` is deliberately outside `tsconfig.lint.json` because importing
`node:test`/`node:fs` requires `@types/node`, which is not pinned.

**What it does NOT guard**, and must not be misread: it guards parity of the **deterministic check
port**, not that the panel runs the cap gate or reads memory — the panel does neither (item 36) — and the
qualitative criterion (`qualitative.0`) is deliberately not ported because the LLM rubric was cut
(item 33).

**What remains true from the old limitation:** `sim/` **still has no automated tests at all** —
`sim/package.json:6-10` holds `job:min`, `sim:run`, `demo`, `mint:client`, `typecheck`, and no `test`. So
the only code that touches the Virtuals SDK is still guarded solely by hand-run on-chain chains.
`forge test` and `uv run pytest` are real.

## 19. Destructive test: both variants are now automated — what is missing is the ARTIFACTS

Most of this limitation has been lifted, and an earlier README version still said otherwise. The state
today, as-is:

**Variant A — degradation (commit `a03e294`).** `make demo` runs §7 steps 1-4 from scratch on local
Anvil; its step 4 is the first destructive variant — fresh vault + empty memory, so job C, which was
REJECTED while memory existed, **passes** when memory is gone, at an IDENTICAL budget. Two consecutive
runs give an identical summary. The mode label is `normal`, not `naive` — read item 34 before quoting it.

**A "BLATANT" defect in variant A is NOT a scored severity.** Variant A's summary line distinguishes
`subtle defect PASSES` and `coarse defect REJECTED` (`sim/src/demo.ts:929-935`), and that is easy to read
as if the evaluator knew two severity
classes. It does not. The "coarse" defect is **exactly the SAME `TODO` token**, only **moved into the
FIRST section** of the document: `sim/scenarios/coarse-defect.md:3` vs `sim/scenarios/depth-demo.md:11`
(third section) — two files with identical defects at different positions. Because
`SAMPLING_SECTION_LIMIT = 2`, the first sits **inside** the `sampling` window and the second outside it.
So what variant A proves is: **lost memory lowers the DEPTH, it does not switch the evaluator off — a
defect inside the sampling window is still caught** (`sim/src/demo.ts:110-116`, and the properties of
those two files are pinned by `agent/tests/test_criteria.py`). There is no severity scoring, and no
qualitative criterion is scored at all (item 33).

**Variant B — safe mode (commit `986fad6`).** It is **also automated now**, in the same command: non-zero
on-chain root + `memory.db` deleted → **safe mode**, zero `postVerdict`, the job hangs until `expiredAt`.
It is not staged on a chain of our own making but run against the **frozen Sepolia vault**, and it
**aborts the whole run** if any of its evidence fails to appear — agent exit ≠ 0, the `SAFE MODE:` line
not printed, `memory gate: mode=safe` not printed, the trigger not being rule (a) "file missing", any
`postVerdict`/`finalize`/`setProviderCap` sent, or the agent wallet's nonce changing
(`sim/src/demo.ts:672-687`, with messages of the form `VARIANT B FAILED: …`). That is also why `make demo`
needs internet (item 34).

**What is STILL missing is the artifacts, not the automation.** `make demo` creates the directory
`agent/data/demo/logs/` (`sim/src/demo.ts:71` and `:618`) but **never writes a single file into it** —
there is no file write anywhere in that script. All of the demo's evidence is therefore **stdout that
scrolls past**, and `data/` is gitignored (item 12). There is no fixture, and no companion file for the
"md5 identical before/after" claim in the destructive-test table (`docs/reproduce.md`). So that table
remains a **report** you cannot match against any file in the repo; what you can do is run `make demo`
yourself and compare by eye.

## 20. A third party cannot repeat the A/B/C chain on this vault

The vault is frozen (ADR-022) and its `agent` is immutable and ours (item 3), so **no one else will ever
make THIS vault announce a verdict or a cap**. What a third party can do: (a) **re-read** all the
on-chain evidence (`docs/evidence.md`) with `cast`/BaseScan, and (b) deploy their own vault from HEAD —
whose bytecode already differs from what is deployed (item 15). Independent reproduction "from scratch to
the same tx" is not something we can offer.

## 21. The "cheating provider" on the demo chain is our own simulator, and the pattern is one word

Jobs A and B do not come from a real provider: `demo/deliverables/418.json` and `419.json` are
three-line stubs written by `sim/`, and **both contain the word "TODO"**. The detector is one regex,
`agent/agent/checks/format.py:47-50`:

```python
_PLACEHOLDER_RE: Final = re.compile(
    r"(?i)(?:\b(?:todo|tbd|fixme|wip|lorem ipsum|coming soon|placeholder|to be filled)\b"
    r"|<[a-z][a-z0-9 _-]{2,30}>)"
)
```

So the sentence "the SAME pattern from a DIFFERENT job", which triggers memory promotion, literally
means: **the word "TODO" was typed twice by our own script, under two different jobIds**. The promotion
mechanism (≥ 2 distinct jobs, evidence required from a deterministic check) is what is being tested, and
it works — but a provider that deletes that one word **passes** the `format` check. The `links` and
`chain` checks also run (item 11), while the sandbox and the LLM rubric do not. The strength of the
detector is not part of this project's claim; what is claimed is what memory does **after** a
deterministic check fails.

## 22. The vault's `lastMemoryRoot()` is DELIBERATELY not equal to `memory_export` over today's DB

This reverses how an earlier README version sold this project, and we write it out explicitly so you do
not discover it yourself at the judging table. The two commands below do **not** return the same value,
and they should not:

```
$ cd agent && uv run python -m agent.memory_export --db ./data/chain-abc/memory.db --out /tmp/mem.json
memory_root: 0x50750074c376526f2d86d7bc85234c10cabda21bcc31c9cabe69e50aeac90c3c

$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "lastMemoryRoot()(bytes32)" \
    --rpc-url https://sepolia.base.org
0x999a957070e0740b81f1142cd6a5173ff53f446ad1ea3e6e240a20abd2789b7d
```

The reason is **structural, not stale data**: `docs/spec.md` §5 step 5 writes memory **after**
`postVerdict`. The root `0x999a9570…9b7d` is the memory state **before** job 422 wrote its result;
today's DB already contains that write, so it is **one write ahead** of the chain. The value
`0x50750074…0c3c` has never been announced on chain — it would become the root announced by the **next**
`postVerdict`. The vault is frozen (ADR-022), so there will never be a next `postVerdict` on this vault,
and that one-step gap is **permanent**.

**The pair that really does match today** is an on-chain root with the **evidence bundle** of the job
that announced it — and that binding is by hash, not by trust:

```
# the root announced by job 422 (MemoryRootUpdated topic1, and the memoryRoot argument of VerdictPosted)
0x999a957070e0740b81f1142cd6a5173ff53f446ad1ea3e6e240a20abd2789b7d

# the memory_root field inside the job 422 evidence bundle
$ cd agent && uv run python -c "import json;print(json.load(open('data/chain-abc/verdicts/422-0x2b0ca5747abea9c81c5f85741e8cdc92dab3b44f92bbbcbc03aec59ddcbc0704.json'))['memory_root'])"
0x999a957070e0740b81f1142cd6a5173ff53f446ad1ea3e6e240a20abd2789b7d

# and the bundle itself is bound to the on-chain reasonHash: keccak256(file bytes) == filename == reasonHash
0x2b0ca5747abea9c81c5f85741e8cdc92dab3b44f92bbbcbc03aec59ddcbc0704
```

All five bundles (418, 419, 420, 421, 422) satisfy that `keccak256(file contents) == filename` match.
What this pair proves: **the root, the verdict, and the reason are bound in one hash that was announced
on chain before execution.** What it does **not** prove: that the memory contents at that moment were
legitimate — for that you would need the DB file in that state, and that state is gone (items 7 and 16).
The limit on publishing memory files: item 12.

## 23. The 402 gate EXISTS, but its registration is NOT consumed by the job path

An earlier README version wrote that this payment gate "is not in the repo". That was **wrong, and wrong
in the direction that understates**: the file is at `agent/agent/payment_402.py` (with its tests in
`agent/tests/test_payment_402.py`). The accurate limitation is narrower:

- **What works:** `POST /jobs/register` answers **402** with its payment scheme when no payment header is
  present, and answers **200** only after the server has **read the receipt itself** on chain — the
  transfer must come from the escrow token, land at the correct recipient, cover the amount, and carry a
  transaction hash that has never been used. In `DEMO_MODE` a dummy header is accepted, but the response
  **says so**, so a 200 can never be misread as a verified payment.
- **What does NOT:** the registration it produces **is not consumed by any job path.** Not one evaluation
  decision today changes because a job is "registered". So this is a **payment-mechanism demo**, not a
  production feature feeding a job queue.
- **The payment is a bearer credential, and that is not a figure of speech.** What is checked is only the
  **content** of the transfer, not who claims it: the `nonce` in the challenge is never stored and never
  compared at claim time (a plain ERC-20 transfer carries no memo), and the sender is never read. So
  anyone who sees that transaction in the mempool or an explorer can **front-run** the client who
  actually paid by quoting the same hash first. This is written in the module itself; an auditor did not
  find it.
- **It does NOT fix the fee incentive.** The ADR-004 up-front fee that would make the referee paid the
  same whether it passes or rejects (item 14) is **not in force**: `evaluatorFeeBP` is still only paid
  out on `Completed`.
- **This is NOT the x402 protocol, and calling it that is forbidden** by **ADR-010 decision 4**. The
  official x402 package does exist (PyPI `x402` 2.22.0) and is **deliberately unused**: its EVM `exact`
  scheme rides on EIP-3009 `transferWithAuthorization`, and the ACP escrow token has no such function —
  in the deployed bytecode the selector `0xe3ee160e` appears **zero** times, with a positive control of
  `transfer` (`0xa9059cbb`) = 1. The `402` here is the HTTP status actually returned (RFC 9110 §15.5.3),
  not a protocol brand; the scheme name in `WWW-Authenticate` is `OnchainPayment`, and the ban on using
  the name `x402` there is guarded by tests.

## 24. The simulator wallet is NOT registered in the Virtuals Service Registry — and that decides a multiplier

This fact previously lived only in a code comment, even though it decides one of the hackathon's judging
criteria. We are surfacing it:

```
POST https://api.acp.virtuals.io/auth/agent
→ 404  Agent not found with wallet address 0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2
```

Source: `sim/src/client_min.ts:510-512` (comment recording a 2026-09-04 verification). That code line
itself writes the placeholder `<client>`, not the address; the literal address is credited to ADR-019
(`docs/decisions.md:385`), and it is indeed `jobs(417..422).client` on chain. So our client simulator
wallet **has never been registered** as an agent in the Virtuals Service Registry. There are three honest
consequences:

1. **The SDK's `session.submit()` cannot post the deliverable text** to the Virtuals off-chain API —
   which is why the text is read from the local artifact `demo/deliverables/<jobId>.json` (item 6),
   not from the official API.
2. **We may not claim the "agent registered with Virtuals" multiplier.** What we can claim is that every
   ACP transaction runs through the genuine Virtuals SDK
   (`@virtuals-protocol/acp-node-v2@0.1.12`) and that `evaluatorAddress` is set to our vault address —
   that is visible in the transaction trace. Registry registration is a **different** thing, and we do
   not have it.
3. That registration requires human action on the Virtuals side; it is **not** blocked by our code, and
   we do not present it as done.

## 25. The depth demo (jobs 421 vs 422): IDENTICAL text, DIFFERENT verdicts — and what it does NOT prove

This is the strongest evidence we have for the claim "memory changes the decision", so its limits must be
written down with it. Two jobs were run with **byte-for-byte identical deliverable text**
(`keccak256(text)` = `0x246071b30c435f192b9ffcb064a11178bc2bd25a02819a1ad7c3b8ee24bf0a51` in
`demo/deliverables/421.json` and `422.json`), the same budget (250,000), the same evaluator (the vault),
but from **different providers**:

| job | provider | history in memory | depth | check result | on-chain verdict |
|---|---|---|---|---|---|
| **421** | `0xc3c6Bf20…aeff` (clean) | zero incidents | `sampling` — only the **first 2 sections** are read | `format.no-placeholder` **pass** ("tanpa penanda pekerjaan pada 2 bagian yang dibaca" — *gloss: no placeholder marker in the 2 sections read*) | `VerdictPosted(kind=1)` → `Finalized` → **status 3 (Completed)** |
| **422** | `0x20212E4D…b321` (2 incidents: jobs 418, 419) | risk 2 | `full` | `format.no-placeholder` **fail** — `TODO` in the **THIRD section** (the bundle writes `section: 2`, 0-based) | `VerdictPosted(kind=2)` → `Finalized` → **status 4 (Rejected)** |

Four transactions you can open yourself:

```
job 421  postVerdict  0x02356b079fa3bfcd32e62d7e2bb61d3f4eb8b66d29fac578cd6318b2028a1467  (block 46455461)
job 421  finalize     0x371a4db2ed4c7975f3806f64392f92ecba2132feb9a1df78889c31af9bcaf020  (block 46455526)
job 422  postVerdict  0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830  (block 46455552)
job 422  finalize     0x502c8d944106914b15d95a38b2815187fa7b3d63965d95414ccd7f15835b5f08  (block 46455616)
```

What it proves: **the check depth is derived from memory, and that depth genuinely changes the verdict** —
the defect is real (`TODO` in the third section) and only visible at `depth=full`. The A/B/C chain proves
the cap gate; the 421/422 pair proves the depth gate, and they are different code paths.

What it does **not** prove, and this must be read with it:

- **Both providers are our own simulators** (item 21). The only difference between them is the history we
  planted through jobs 418/419, not independent third-party behaviour.
- **The defect is one word.** `TODO` is matched by the placeholder regex
  (`agent/agent/checks/format.py:47-50`); this is not sophisticated cheat detection (item 10). The same
  applies to `coarse defect` vs `subtle defect` in the `make demo` summary: that is the **position** of the same token
  inside or outside the sampling window, **not** two scored severity levels — full explanation in
  item 19.
- **`sampling` vs `full` only differ if the document is longer than the sampling limit.** Deliverable
  421/422 was deliberately built with **THREE** sections (`# Summary`, `## Cara kerja`,
  `## Catatan lanjutan`) with the `TODO` placed in the **third**, while `SAMPLING_SECTION_LIMIT = 2`
  (`agent/agent/checks/base.py:78`) — so `sampling` reads the first two sections and **never reaches** the
  defect, while `full` reads all three and finds it. On the older demo artifacts (418/419), which have
  only one section, `sampling` and `full` read **exactly** the same number of sections, so depth could not
  change anything. Note the two different index conventions in the table above: the evidence bundle uses a
  **0-based** index (`section: 2` = third section), while the check prose uses a section **count** ("2
  sections read").
- **`kind:"evaluation"` bundles do NOT contain a `gate` block.** Only the `gate-rejection` shape (job 420)
  has one. As a result the 421/422 bundles — precisely the two artifacts we offer as our strongest
  evidence — **cannot prove on their own** to an auditor that what rejected job 422 was the depth gate and
  not the cap gate. What closes that gap today is only reading the code (`criteria.py` only accepts
  `depth`, never `risk`), not the artifact. This is known debt, not a fresh discovery.
- **The job 421 that passed is what paid the evaluator** 12,500 units (item 14) — the incentive bias we
  criticise still applies to this very demo.

## 26. A wrong verdict cannot be undone by anyone — `CHALLENGE_WINDOW` is latency, not protection

Item 2 already names `challenge`/`resolve` as stubs. What is added here is **the consequence, all the way
through**, because the security reviewer ran the whole matrix as adversarial tests instead of reading it:

| Who tried to undo a wrong verdict | What they got | Evidence |
|---|---|---|
| the agent itself (`postVerdict` again on the same job) | `VerdictAlreadyPosted()` | `contracts/src/EvaluatorVault.sol:307`; `contracts/test/EvaluatorVault.t.sol:446` |
| a challenger, carrying an ETH bond | `NotImplemented()` — and the ETH returns intact because the tx is reverted | `EvaluatorVault.sol:327-331`; `test_challenge_reverts` (`EvaluatorVault.t.sol:865-885`, all four roles, with and without `msg.value`) |
| the arbiter | `NotImplemented()` | `EvaluatorVault.sol:341-345`; `test_resolve_arbiter_reverts_notImplemented` (`:887`) |
| a stranger who wants to execute the verdict | **succeeds** — `finalize` is permissionless, and the job really does move to status 3 (`Completed`), i.e. **a real payment to the provider** | `EvaluatorVault.sol:363` (`finalize` with no role modifier); `test_authMatrix_finalize_openToAllRoles` (`:987-997`, all four roles, `assertEq(_status(jobId), 3)`) |

So the sentence to take away from this section, unsoftened:

> **`CHALLENGE_WINDOW` = 120 seconds on the submission contract is PURE LATENCY. It provides ZERO
> protection.** During those two minutes no call can stop the verdict; after those two minutes anyone may
> execute it, and the money moves.

The only thing standing between a wrong verdict and a payment today is **the agent holding back before it
signs**, not the contract. That is why items 16, 29, 30, and 31 below matter: every real defence lives
off-chain.

## 27. The `ArbiterEqualsAgent` guard is in the DEPLOY SCRIPT, not in the contract

Item 3 pastes `cast` output showing `arbiter() == agent()`. What is not yet written: the contract itself
**never** forbids that state. Only the deploy script does —
`contracts/script/Deploy.s.sol:64` (`error ArbiterEqualsAgent();`) and `:112`
(`if (arbiter == agent && !allowArbiterEqAgent) revert ArbiterEqualsAgent();`) — so that guard can be
switched off via `ALLOW_ARBITER_EQ_AGENT`, and on the submission deploy it was.

`EvaluatorVault.sol` itself has no such branch in any constructor. The `sweepToken` NatSpec even rests its
`onlyArbiter` justification on that guard:

> `` `onlyArbiter`, bukan `onlyAgent`: agen adalah pihak yang mengumumkan verdict, jadi memberinya kunci ke
> hasil finansial dari verdictnya sendiri meniadakan pemisahan peran yang justru dijaga guard
> `ArbiterEqualsAgent` di skrip deploy. `` (`contracts/src/EvaluatorVault.sol:255-257`)
>
> *(gloss: `onlyArbiter`, not `onlyAgent`: the agent is the party that announces the verdict, so giving it
> the key to the financial outcome of its own verdict would destroy the role separation that the
> `ArbiterEqualsAgent` guard in the deploy script exists to protect.)*

The role separation that sentence promises **does not exist on the deployed instance**, and never will:
the contract is immutable and ADR-022 decision 1 freezes it as the submission contract. Read that NatSpec
as design intent, not as a description of vault `0x5c6EE45…f384`.

## 28. `BondTooLow` never fires — the evaluator stakes nothing, and ETH is trapped too

`postVerdict` does check the bond (`if (bond < MIN_BOND) revert BondTooLow();`,
`contracts/src/EvaluatorVault.sol:304`), but `MIN_BOND` on the deployed contract is **0**
(`deployments/84532.json` → `"minBondWei": "0"`, item 1). `bond` is a `uint256`, so `bond < 0` is
impossible: **on the submission vault the `BondTooLow` branch is completely unreachable.** Do not read the
presence of that error in the ABI as a live protection.

Do not read the number as "a small bond" either: what the evaluator stakes today is **zero**. And even if
it did deposit, that ETH could not get out — there is no ETH exit path from the vault at all
(deliberate, ADR-013; the `sweepToken` NatSpec stresses that the function is "tidak `payable`, tidak
pernah menyentuh `bond`" *(gloss: not `payable`, never touches `bond`)*,
`EvaluatorVault.sol:243-247`). For ERC-20 the situation is just as bad by another road: `sweepToken`
EXISTS in the source but is **not in the deployed bytecode**, so 62,500 units of evaluator fees are
permanently stranded (item 4). **Both, ETH and ERC-20, are permanently trapped in the vault.**

## 29. Whoever can write `memory.db` can LOOSEN the cap without limit

Item 10 explains what happens when memory is **lost**. This is the opposite: what happens when memory is
**written to**. The memory module states it itself, verbatim
(`agent/agent/memory_policy.py:45-51`):

> `CAP BISA DILONGGARKAN SAMPAI TANPA BATAS. … penulis memory.db tidak hanya bisa mematikan agen, ia bisa
> MENIMPA body provider menjadi risk_level: 0 tanpa cap_usdc, sehingga derive_cap mengembalikan NO_CAP →
> cap_to_onchain = 0 → di kontrak berarti TANPA BATAS (ADR-001). Monoton tidak-naik tidak menolong:
> jangkarnya adalah cap_usdc yang tersimpan di body yang sama, dan penyerang menghapusnya bersamaan.`
>
> *(gloss: THE CAP CAN BE LOOSENED WITHOUT LIMIT. … whoever writes memory.db can not only kill the agent,
> they can OVERWRITE the provider body to risk_level: 0 with no cap_usdc, so derive_cap returns NO_CAP →
> cap_to_onchain = 0 → which in the contract means NO LIMIT (ADR-001). Monotonic non-increase does not
> help: its anchor is the cap_usdc stored in that same body, and the attacker deletes it at the same
> time.)*

They can also delete `incident_jobs`, `confirmed_patterns`, and the entire provider entity at once.

**The mitigation is real but has a hole, and the hole must be named.** `gate_job` uses the on-chain
`providerCap()` as a **floor** — a cap from memory looser than the one the vault is currently enforcing is
not used (`agent/agent/memory_policy.py:1752-1758`), and a `setProviderCap` that raises the cap is refused
by `_require_onchain_cap_floor` (`agent/agent/vault_client.py:1440`, called from `_send()` :1484). The
hole is on the next line of that same code: **`providerCap == 0` is NOT a floor** — it means NO LIMIT
(ADR-001, `agent/agent/vault_client.py:1547`). So for a provider that has never been given a cap, that
floor does not exist, and the memory writer is entirely free.

## 30. A `memory.db` SWAPPED for another DB is not detected

This sharpens item 10, and we repeat it here because it is easy to miss in the middle of a trigger list:
safe mode inspects the **FILE state** of memory — missing, unreadable, or locked by another instance —
and **never inspects its contents** (`agent/agent/memory_policy.py:59-63`; ADR-024's consequences write
`HILANG: deteksi "memory.db diganti DB LAIN", baik kosong maupun terisi` *(gloss: MISSING: detection of
"memory.db replaced by ANOTHER DB", whether empty or populated)*). A readable swapped DB puts the agent
into **normal mode**, not safe mode.

## 31. `postVerdict` accepts a zero `reasonHash` and any jobId; `UnknownMemoryRoot` cannot be triggered

Two things that make "root-based protection in the contract" a misreading:

- **`postVerdict` validates almost nothing.** It rejects a `kind` outside {1,2}, rejects a zero
  `memoryRoot`, and rejects a duplicate verdict — that is all
  (`contracts/src/EvaluatorVault.sol:301-320`). A **zero `reasonHash` is accepted**, and the `jobId` is
  **never checked for existence in ACP**. Which means the `lastMemoryRoot` anchor can be moved over a job
  that never existed. The honest mitigation: through our code that does not bite, because
  `_require_derived_root` refuses to sign if the `memory_root` in the calldata is not derived from the
  memory the agent just read (`agent/agent/vault_client.py:1339`, called from `_send()` :1473) — zero
  transactions sent. What is not covered is a **direct** call to the contract with the agent key, which
  never passes through our code at all.
- **`UnknownMemoryRoot` in `finalize` is vestigial.** `finalize` requires `knownRoots[v.memoryRoot]`
  (`EvaluatorVault.sol:369`), but `postVerdict` writes `verdicts[jobId].memoryRoot` **and**
  `knownRoots[memoryRoot] = true` in the **same transaction** (`:312` and `:315`). There is no
  `knownRoots` remover (item 7), so that condition is always satisfied once the verdict exists. **That
  guard cannot be triggered on this contract.**

The conclusion, and this must not be misread from any flow diagram:
**root-based fail-closed behaviour lives entirely on the agent side, not in the contract.** The contract
only rejects a zero root (item 16).

## 32. The agent has no timeout while waiting for the challenge window

After `postVerdict` lands, the agent waits for `readyAt` in a loop with no upper bound:

```python
log.info("menunggu jendela challenge sampai readyAt=%d", ready_at)
while True:
    now = client.w3.eth.get_block("latest")["timestamp"]
    if now > ready_at:
        break
    ...
    time.sleep(min(20, max(2, ready_at - now + 1)))
```

(`agent/agent/vault_client.py:2586-2592`.) There is no `deadline` and no maximum retry count. If the RPC
stalls or `block.timestamp` stops advancing, **the process hangs with no exit code and no log line saying
it gave up** — the operator only sees a "seconds remaining" line, or nothing. The verdict itself is
already safe on chain and `finalize` is permissionless (item 26), so recovery means calling `finalize`
from outside; but the automation does not provide that itself.

## 33. Qualitative criteria are NOT SCORED — there is no LLM anywhere in the path

Item 11 calls the LLM rubric "cut". What needs stressing: that cut does **not** make qualitative criteria
count as passed, and it is not silent either. It is recorded as its own category in every evidence bundle
— `unscored` together with `unscored_reason` (`agent/agent/criteria.py:390-392` and `:423-424`) with
constant text:

> `kriteria kualitatif TIDAK DINILAI di 2.3-min: rubric LLM dipotong (PM 5 Sep). Ia dicatat apa adanya,
> tidak pernah dianggap lolos.` (`agent/agent/criteria.py:121-124`, locked by
> `agent/tests/test_criteria.py:336-337`)
>
> *(gloss: qualitative criteria are NOT SCORED in 2.3-min: the LLM rubric was cut (PM, 5 Sep). It is
> recorded as-is and never treated as passed.)*

So **there is not a single LLM call in today's evaluation path.** What runs is the deterministic `format`,
`links`, and `chain` checks (item 11). If the README, the video, or any post reads as if there were
qualitative scoring, that is a misreading — the wording deliberately does not promise it.

## 34. `make demo` NEEDS internet, and variant A's mode label is `normal`

Two corrections to how the demo is easy to misunderstand.

**Internet.** Variant A runs entirely on local Anvil, but destructive variant B deliberately reads the
**frozen Sepolia vault** so that the non-zero `lastMemoryRoot()` triggering safe mode is a real state, not
a staged one (`sim/src/demo.ts:125` `SEPOLIA_RPC = "https://sepolia.base.org"`; the variant B block at
`:655-687`). The nature of that touch: **read only — no funds, no transactions**, and that is measured
rather than asserted, via the agent wallet's nonce before vs after (`newTx`, `demo.ts:943`; the
`VARIANT B:` line at `:947`). The practical consequence: **without internet, `make demo` does not
finish** — and it stops in **PREFLIGHT within the first second, before Anvil starts**, with exit 1
(`demo.ts:362` `preflight.ok`).

One correction to an earlier README version, which criticised a defect that **no longer exists**: the
`Makefile` comment **no longer** says "Tidak menyentuh jaringan apa pun" (`grep -rn "Tidak menyentuh
jaringan" Makefile` → empty). What it says now is already correct and sharper: "BUTUH INTERNET: varian B
membaca vault BEKU di Base Sepolia … NOL dana, NOL transaksi, NOL kunci privat, hanya dua pembacaan view"
*(gloss: NEEDS INTERNET: variant B reads the FROZEN vault on Base Sepolia … ZERO funds, ZERO transactions,
ZERO private keys, only two view reads)*, together with why its failure is hard (`Makefile:50-54`).

**The mode label.** In variant A, the `plan.mode` the agent reports is **`normal`, not `naive`** — because
the first invocation creates `memory.db` and is then refused by `MODE_DRIFT`, and the invocation that
produces the verdict is the second one, which already has a DB (ADR-026; `sim/src/demo.ts:461-489`). What
shows the degradation is therefore **not** the mode label but two other columns in the summary line:
**`depth=sampling`** and **`cap=NO CAP`** (`demo.ts:826-841`). Do not call variant A "naive mode": that
word appears only in the first invocation's log line, which ends in zero transactions, and it is not a
mode that has ever produced a verdict via the CLI.

## 35. The division of labour between `sim/` and `agent/` — `sim:run` really does not produce a verdict

This is not a limitation but an easy misreading, and this is the most useful place for it.

`sim/` is the **ACP client**: it creates, funds, and submits jobs (`createJob → setBudget → fund →
submit`) through the `@virtuals-protocol/acp-node-v2` SDK, and stops exactly at the status the demo script
requires — `SUBMITTED` for jobs A/B, `FUNDED` for job C — then prints the `jobId`.
`sim/src/scenario.ts:34-39` states that boundary itself:

> `BATAS: skrip ini menyiapkan JOB, bukan VERDICT. … Yang menghasilkan verdict adalah agent/; skrip ini
> berhenti tepat pada status yang dituntut tiap langkah … dan mencetak jobId-nya supaya agen bisa
> dijalankan atasnya.`
>
> *(gloss: BOUNDARY: this script prepares JOBS, not VERDICTS. … What produces a verdict is agent/; this
> script stops exactly at the status each step requires … and prints the jobId so the agent can be run
> against it.)*

`agent/` is the **evaluator**, and it is invoked **per jobId** with
`uv run python -m agent.vault_client --job-id <N> --kind reject|complete` (item 9) — it is **not** invoked
by `sim/`. The event watcher was dropped from the critical path by ADR-022 decision 3, so no process
bridges the two automatically outside `make demo`, which runs both sides in sequence as a demo
orchestrator (`sim/src/demo.ts`). That is why a `pnpm sim:run` that finishes **without** a verdict is
correct behaviour, not a failure; the `expectVerdict` column in the scenarios is a script expectation, not
an observation. The limitation that comes with it: `sim/` still has no automated tests (item 18).

## 36. The memory-wipe surface in the judge panel: FAILED a security review, then closed — the full history

The judge panel (`/panel`) has a memory-wipe button for demonstrating the destructive test to an
audience. That surface **once received a BLOCK verdict from a security review**, with **two HIGH
findings**, and we write it out here as-is instead of deleting the history — this section tells what
failed, what was fixed, and what we **still** accept as risk.

**What failed.** (a) **CSRF** on the wipe endpoint: wiping is a **side effect**, not a read, so CORS was
never a defence — one malicious tab only needs to send
`<form method=POST action="http://127.0.0.1:8010/demo/memory/reset">`, which sends `text/plain` (a
CORS-safelisted type) so no preflight holds it back, and the attacker does not need to read the response.
(b) The Next proxy **exposed the loopback wiper to the LAN**, because Next binds `0.0.0.0` by default.

The lesson is written into the code itself and is worth taking outside this repo:
**"loopback only" is NOT a defence against a browser, because the judge's browser is also on loopback**
(`agent/agent/demo_reset.py:32-41`, limits 4 and 5).

**What was fixed, and how it was proven closed.** The reviewer **re-ran exactly the attack that used to
work**: the cross-origin `text/plain` form POST that once answered `200 {"deleted": [3 files]}` is now
answered with **403 `cross_origin_request`** and all three files intact (`agent/agent/demo_reset.py:126`,
`check_same_origin` :394-417), and `curl` from a LAN IP is stopped by **two layers** — `serve()` refuses
non-loopback peers (`LOOPBACK_HOSTS`, :82) **and** Next is now bound with `-H 127.0.0.1`
(`web/package.json:7,9`). A POST now also requires `Content-Type: application/json` **exactly** (forcing a
preflight) plus a `Host` naming loopback and this server's port, which closes DNS rebinding too
(`_check_host` :420-438). One **MEDIUM** finding — TOCTOU on ancestor path components — was closed via the
**`dir_fd`** route: deletion no longer uses a string path but the root directory's fd, so ancestors are
never re-resolved (`_open_root_fd`, `_remove` :301-336). **Re-review: zero CRITICAL, zero HIGH, verdict
PROCEED.**

**What is STILL accepted as risk, named so you do not have to find it yourself:**

- **LOW — `resetUrl()` restricts the HOST, not the PORT.** The Next proxy rejects a
  `NEXT_PUBLIC_AGENT_RESET_API` whose hostname is outside loopback (`LOOPBACK_HOSTS`,
  `web/src/app/api/demo/memory/reset/route.js:47,59`) but does **not** restrict its port, so a typo'd env
  var could still point this POST at another loopback port. Accepted as-is.
- **A residual race its own docstring admits:** an entry with the same name can still be swapped between
  `open` and `unlink`. The impact is limited to **the honesty of the report** — `unlink(dir_fd=…)` does
  not follow symlinks on the final component and the name **cannot escape** the directory held by the fd,
  so a file lost this way is always an entry inside the demo root itself
  (`agent/agent/demo_reset.py:314-318`).

**The blast radius, and this matters most**: the button is only rendered when `DEMO_MODE=1` — read **on
the server** per request (`web/src/app/panel/page.jsx:8,19`), so there is no HTML flag a client could
flip, and without that env var the agent endpoint is **not registered at all** → 404, not 403
(`agent/agent/demo_reset.py:15-20`). Its target is **only demo memory** (`agent/data/demo/`, derived from
`agent_root()` and **never** from the request): it is **never** given power over
`agent/data/chain-abc/memory.db`, the only file that can reconstruct the on-chain root (items 7 and 12).
All three SQLite files (`memory.db`, `-wal`, `-shm`) are swept, because a leftover WAL could restore the
contents and a "memory wiped" that leaves a WAL behind is a false green.

Still good practice: run `web/` through the script that already pins `-H 127.0.0.1`, and turn on
`DEMO_MODE=1` only when you are actually demonstrating the destructive test.


## 37. `actor-standing` binds a key, not a party, a refusal leaves no on-chain trace, and it landed after the deadline

The fifth obligation reads the executor's provider profile from the same Sibyl store the ACP gate
writes, and `PassportVerifier` v2 refuses anyone but that executor. Three things this does NOT prove:

- That the executor on Base is the same legal party as the provider on ACP. It is the same **key**
  (`0xA2beb04BE7F3d0948828Cf1893876513f4Fa2cde` in the recorded proof). Without ERC-8004 identity that is the strongest link
  available, and it is stated as such.
- That a refusal happened. `decision=block` is an off-chain decision; the chain shows only that no
  second `PassportConsumed` for that executor exists. The command output is the record.
- That this was built inside the hackathon window. It was not: every commit after the tag
  `submission-2026-09-10` is dated 11 Sep, and the v2 fixture was deployed at block 46658144 that
  day. See the README note.

An unknown address (no provider entity) is `satisfied` with `acp_history=none`. That is deliberate:
ACP itself cannot tell a clean provider from a new one, and a gate that punished newcomers would be
lying about what memory knows.
