# REFERI

An ERC-8183 escrow referee whose memory of each provider can be **recomputed from files**. A standard
ERC-8183 evaluator is stateless and "fully trusted": the same provider can repeat the same trick on the
next job, leaving no trace. Here every `postVerdict` announces a `memoryRoot` on chain, and that memory is
what sets the check depth and the per-provider budget cap.

- Status: **hackathon project on Base Sepolia (testnet); never run on mainnet.**
- Submission contract (FROZEN, ADR-022): [`0x5c6EE4586ACABcb6326069c229E58091B21ef384`](https://sepolia.basescan.org/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384)
- **The incentive is NOT fixed yet**: `evaluatorFeeBP` = 500 (5%) is only paid out when a job is
  `Completed`, so this referee is still paid only when it passes work. An up-front fee via x402 is a
  design (ADR-004), not a feature. Details: [`docs/limitations.md`](docs/limitations.md) item 14.
- Prose, identifiers, and commands are in English. Licence: MIT.

## If you only have 3 minutes

These are the three things we most want you to check. All three open without running anything:

1. **A verdict shaped by history, on chain.** Jobs 421 and 422 use byte-for-byte identical deliverables;
   421 passed, 422 was rejected. `postVerdict` for job 422:
   [`0xe95910d2…295830`](https://base-sepolia.blockscout.com/tx/0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830)
   (Blockscout decodes the event name — item 15). The full story: **item 25**.
2. **The evidence bundle for job 422**, whose hash was announced on chain before execution:
   [`web/public/verdicts/422.json`](web/public/verdicts/422.json) — it carries `memory_root`, `checks`,
   `incident_jobs`, and the criteria that were **not** scored. How to match it against the chain:
   **item 22**.
3. **The `claim step=C-vs-D` line** printed by `make demo` (`sim/src/demo.ts:902-908`): the same cap gate,
   with memory and without, at an identical budget. Context and limits: **item 19**.

If you only want to know what does NOT work: [`docs/limitations.md`](docs/limitations.md).

## Flow

```
CLIENT ──createJob(evaluator = VAULT)──► ACP (Base Sepolia) ◄──setBudget / submit── PROVIDER
                                              │
                                              │ getJob + log JobFunded / JobSubmitted
                                              ▼
                                 Evaluator Agent (Python, invoked per job)
                                   • deterministic checks: format, links, chain
                                   • Sibyl memory: provider / pattern / suspicion (quarantine)
                                   • derive_cap(memory) — can only tighten
                                              │
                                              │ setProviderCap(provider, cap)
                                              │ postVerdict(jobId, kind, reasonHash, memoryRoot)
                                              ▼
                                 EvaluatorVault 0x5c6EE45…f384
                                   • emit MemoryRootUpdated(memoryRoot)
                                   • wait CHALLENGE_WINDOW = 120 seconds
                                   • finalize() → acp.complete / acp.reject
                                              ▼
                                    JobCompleted / JobRejected
```

Why those three pieces sit outside the ERC-8183 spec, and which ADR decided each:
[`docs/design.md`](docs/design.md).

## Escrow Firewall: terms before funding

Escrow Firewall adds a second, cross-provider memory loop. When deterministic evidence shows
*how* a delivery failed, Sibyl stores a structured failure pattern. For a later, similar job,
the agent recalls that pattern and creates stricter acceptance criteria before the client funds
escrow — for example a commit hash, test command, test output, and environment version after a
previous claim could not be reproduced. The pattern is not a provider score: a different provider
receives the same safeguard when the task has the same failure mechanism.

Create the immutable terms artifact first, then pass its printed commitment to the ACP simulator:

```sh
cd agent
TERMS_COMMITMENT="$(uv run python -m agent.escrow_firewall \
  --memory-db ./data/memory.db \
  --task-category general \
  --output ./data/terms/job-next.json)"
cd ../sim
TERMS_COMMITMENT="$TERMS_COMMITMENT" bun run job:min
```

The simulator appends the hash to ACP's immutable `description` at `createJob`; it is therefore
committed before `fund`, without changing the deployed ACP ABI. The evaluator includes the exact
terms policy, applied patterns, and commitment in its verdict evidence bundle. A fresh process
with the same Sibyl database recalls the safeguard; deleting the database produces explicit
generic terms instead. The terms CLI refuses to overwrite a different artifact at the same path.

## How to run

```
make doctor    # print toolchain versions, exit 1 if they do not match docs/versions.md
make test      # forge test + uv run pytest + pnpm -r test
make demo      # §7 steps 1-4 from SCRATCH on local Anvil + TWO destructive variants
               # NEEDS INTERNET (variant B reads the frozen Sepolia vault: no funds, no transactions)
               # measured runtime: 3m23s and 3m56s across two runs
```

UI (optional, outside `make demo`):

```
DEMO_MODE=1 pnpm --filter web start          # http://127.0.0.1:3000/panel
cd agent && DEMO_MODE=1 uv run python -m agent.demo_reset --host 127.0.0.1 --port 8010
```

Per-job commands, reproducing the A/B/C chain, reproducing the depth demo, and troubleshooting exit
code 4: [`docs/reproduce.md`](docs/reproduce.md).

## Destructive test

`make demo` runs both variants. Both delete `memory.db`; what differs is the environment:

| Variant | Condition | What changes |
|---|---|---|
| **A — degradation** (local Anvil) | fresh vault, `lastMemoryRoot()` = 0, `SIBYL_DB_PATH` pointed at a path that never existed | job C, REJECTED while memory existed, now **passes** at an IDENTICAL budget: `depth=sampling`, `cap=NO CAP`. The mode label is `normal`, not `naive` (item 34) |
| **B — safe mode** (reads the frozen Sepolia vault) | non-zero on-chain root + `memory.db` deleted | **safe mode**: zero `postVerdict`, zero `finalize`, zero `setProviderCap`; the job hangs until `expiredAt`. The run is aborted if the evidence does not appear (`sim/src/demo.ts:672-687`) |

```
# variant A, run by hand (make demo uses the same form)
cd agent && uv run python -m agent.vault_client --job-id <job C> --kind reject
```

On a fresh vault that command needs **two** invocations: the first creates `memory.db` and is then
refused by the `MODE_DRIFT` guard with **exit code 4 and zero transactions** (ADR-026). Full result table
and troubleshooting: [`docs/reproduce.md`](docs/reproduce.md). What is missing is the **artifacts** — the
command leaves no log or fixture in the repo (item 19).

> **Delete our memory, and you get an ordinary stateless evaluator — exactly our competitors.**

What does **not** change when memory is gone: the deterministic checks still run, so coarse defects are
still rejected. What is lost is calibration — check depth, learned patterns, and cap gating. Important
note: the `coarse defect` the demo prints is the **position** of a `TODO` token inside the sampling
window, not a scored severity (item 19).

## On-chain evidence (the strongest part)

| Fact | Value / evidence |
|---|---|
| EvaluatorVault (submission, frozen) | `0x5c6EE4586ACABcb6326069c229E58091B21ef384` |
| ACP (Virtuals ERC-8183, Base Sepolia) | `0x0b93793923CD5De81850aF8604a233f3f24d461e` |
| Source verification | Sourcify `exact_match` (creation + runtime), from commit `8d3e596` — `deployments/84532.json:36-44`; Blockscout decodes vault events by name; BaseScan does not import it (item 15) |
| `postVerdict` job 422 (`VerdictPosted`, kind=2) | [`0xe95910d2…295830`](https://base-sepolia.blockscout.com/tx/0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830) — block 46455552 |
| SDK used | `@virtuals-protocol/acp-node-v2@0.1.12` (`sim/package.json:12`); `evaluatorAddress` is set to the vault address (SDK default = 0x0 = skip evaluation) |

**Identical text, opposite verdicts.** Two jobs, byte-for-byte identical deliverables
(`keccak256(text)` = `0x246071b3…0a51` in `demo/deliverables/421.json` and `422.json`), same budget
(250,000), same evaluator — the only difference is the provider's history in memory:

| job | provider | history | depth | on-chain verdict |
|---|---|---|---|---|
| 421 | `0xc3c6Bf20…aeff` | zero incidents | `sampling` (first 2 sections) | `kind=1` → status 3 (Completed) |
| 422 | `0x20212E4D…b321` | 2 incidents (418, 419) | `full` | `kind=2` → status 4 (Rejected) — `TODO` in the third section |

`SAMPLING_SECTION_LIMIT = 2` (`agent/agent/checks/base.py:78`); the placeholder regex is in
`agent/agent/checks/format.py:47-50`. What this pair does **not** prove: item 25.

Full address list, the A/B/C chain with `cast logs` for `JobRejected`, the history of eight
`MemoryRootUpdated` events, four depth-demo tx hashes, and a number → source map:
[`docs/evidence.md`](docs/evidence.md).

## Limitations & trust assumptions

The full list of 36 items is in [`docs/limitations.md`](docs/limitations.md) — the numbering does not
change, and the video script refers to the same numbers. The eight that matter most:

1. **A wrong verdict cannot be undone by anyone.** `challenge`/`resolve` are stubs
   (`revert NotImplemented()`), so `CHALLENGE_WINDOW` = 120 seconds is **pure latency, zero protection**;
   after the window `finalize` is permissionless and the money moves
   (`EvaluatorVault.sol:327-331`, `:363`; items 2 and 26).
2. **The evaluator's bond is zero.** `MIN_BOND` on the deployed contract is 0 (`deployments/84532.json` →
   `minBondWei`), so the `BondTooLow` branch is unreachable (items 1 and 28).
3. **`arbiter()` == `agent()`, permanently.** One EOA is deployer, agent, arbiter, and the only signer;
   the contract is immutable, with no rotation and no pause (items 3 and 27).
4. **Funds that enter the vault are stuck.** `sweepToken` exists in the source but is **not in the
   deployed bytecode**, and there is no ETH exit path — 62,500 units of fees are permanently stranded
   (items 4 and 28).
5. **Qualitative criteria are NOT scored.** The LLM rubric was cut; there is no LLM call anywhere in the
   evaluation path. Those criteria are recorded as `unscored` in every bundle and are never treated as
   passed (`agent/agent/criteria.py:121-124`; item 33).
6. **The initial cap is a team parameter, not a learned result.** `BASELINE_CAP_USDC` = 1,000,000 was
   picked by the team; the job 420 bundle itself records `sample_size: 0`. Memory can only **tighten** the
   cap (item 8).
7. **The cap is published by the contract but enforced by the off-chain agent.** `providerCap` is written
   (`EvaluatorVault.sol:289`) and **never read** by the contract (item 17).
8. **The root anchor is circular, and the agent is not autonomous.** On chain, only a zero root is
   rejected (`EvaluatorVault.sol:303`); a `memory.db` **swapped** for another DB is not detected
   (items 16, 29, 30). The agent is invoked per job with `--job-id` — it is not a watcher (item 9).

Also on that list, among others: the deliverable text does not come from the official ACP API (item 6),
three of the eight vault roots are not derived from memory (item 7), `sim/` has no automated tests
(item 18), the destructive test leaves no artifacts (item 19), the 402 gate is not consumed by the job
path (item 23), the simulator wallet is not registered in the Virtuals Service Registry (item 24), and
the security-review history of the memory-wipe surface (item 36).

## Repo structure

```
contracts/   EvaluatorVault.sol, IACP.sol, script/Deploy.s.sol, test/ (Foundry)
agent/       Python: memory_policy.py (memory schema, derive_cap, promotion), vault_client.py,
             memory_export.py (audit root), checks/{format,links,chain}.py, tools/memory_root_check.mjs
sim/         TypeScript client simulator on @virtuals-protocol/acp-node-v2 (no tests — item 18)
web/         Next.js: job timeline, verdict+evidence page, judge panel (deterministic-check port in
             src/lib/checks.js, parity guarded by test/checks-parity.test.js); data from static JSON
             in web/public/, zero RPC from the browser (items 18 and 36)
demo/        deliverables/<jobId>.json (deliverable text from the simulator, ADR-019 — item 21)
deployments/ 84532.json (addresses + constants), pipeline-84532.md (live pipeline, job 417)
docs/        spec.md, decisions.md (ADRs), api-facts.md, versions.md,
             limitations.md, evidence.md, reproduce.md, design.md
```

## Documents

| File | Contents |
|---|---|
| [`docs/limitations.md`](docs/limitations.md) | all 36 limitations & trust assumptions |
| [`docs/evidence.md`](docs/evidence.md) | full on-chain evidence, tx tables, number → source map |
| [`docs/reproduce.md`](docs/reproduce.md) | reproduction commands, destructive variants, troubleshooting |
| [`docs/design.md`](docs/design.md) | problem → solution, day-one consumer, what sits outside ERC-8183 |
| [`docs/decisions.md`](docs/decisions.md) | ADRs — where the spec and an ADR disagree, the ADR wins (ADR-025) |
| [`demo/video-script.md`](demo/video-script.md) | the demo video script — one canonical script, in English |

## Licence

MIT — see [LICENSE](LICENSE).
