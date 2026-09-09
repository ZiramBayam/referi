# Full on-chain evidence

Everything here can be opened without running this repo. Network: **Base Sepolia (chainId 84532)**.
The limitation attached to each claim is in [`docs/limitations.md`](limitations.md) — item numbers on
this page refer to that file.

## Addresses & integration

| Component | Address / package |
|---|---|
| EvaluatorVault (submission contract) | `0x5c6EE4586ACABcb6326069c229E58091B21ef384` |
| ACP (Virtuals' ERC-8183 implementation, Base Sepolia) | `0x0b93793923CD5De81850aF8604a233f3f24d461e` |
| ACP implementation behind the proxy | `0xc4E95dBc7E8C99c114FF9C8299A3E4851e1530fF` |
| Escrow token (`paymentToken()`) | `0xECc22a8F6fD62388498fBa19813E214605a2BDb3` |
| Agent wallet (drives the vault) | `0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894` |
| Client simulator | `0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2` |
| Provider simulator | `0x20212E4D95A75E6716575ED26e884cdeFf66b321` |

Sources: `deployments/84532.json` (network `base-sepolia`, chainId 84532) and
`deployments/pipeline-84532.md`. The vault was deployed in block 46350667 with solc 0.8.36 (evm `osaka`,
optimizer runs 200), using 816,969 gas — all of those numbers are in `deployments/84532.json`. The
contract is **verified on Sourcify with `exact_match`** (creation and runtime), from source at commit
`8d3e596`, so **Blockscout** decodes vault events by name; BaseScan does not import it (item 15):
`https://base-sepolia.blockscout.com/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384?tab=logs`

**The Virtuals SDK is genuinely used, not decoration.** Every ACP transaction in the simulator goes
through `@virtuals-protocol/acp-node-v2@0.1.12` (`sim/package.json:12`); `sim/src/client_min.ts:11-14`
states and keeps the rule that the file encodes no ACP calldata of its own — the call sequence, the ABI,
and the approve+fund ordering all come from the SDK, and all we supply is a viem signer adapter
(`IEvmProviderAdapter`). `evaluatorAddress` is set explicitly to the vault address: the SDK default is
the zero address = "skip evaluation", which would pay the provider immediately with no referee. The
limit, and this is the weakest part of the whole repo: **`sim/` has no automated tests at all** (item 18)
— the only thing proving this SDK path works is the Base Sepolia transactions linked on this page.

The first live pipeline (job 417: `createJob → setBudget → fund → submit → postVerdict → finalize →
JobCompleted`) and its six transaction hashes are documented in `deployments/pipeline-84532.md`.

## Chain A → B → C (6 Sep 2026): the cap gate

Three jobs from **one** provider, `0x20212E4D95A75E6716575ED26e884cdeFf66b321`:

| Job | Budget | Result | What changed in memory |
|---|---|---|---|
| **A = 418** | 1,000,000 | REJECT | the `format` check failed (the word "TODO", item 21) → pattern `format.placeholder-text`, quarantine count = 1, cap 0 → 1,000,000 |
| **B = 419** | 1,000,000 | REJECT | the SAME pattern from a DIFFERENT job → count = 2 → promotion to `reference:pattern` + `provider.confirmed_patterns`, **risk = 2** → cap 1,000,000 → 250,000 |
| **C = 420** | 2,000,000 | **REJECT while `Funded`** | budget > cap → rejected before the provider could submit; final job status = 4 |

Read that last column with two limits: what memory learns is the **risk level and the pattern**, while
the **number** 250,000 is a team constant divided by 4 (`sample_size: 0`, item 8); and the "cheating
pattern" here is the word "TODO" from our own simulator (item 21). Quarantine (`suspicion`) is never read
by the decision path; promotion requires ≥ 2 distinct jobs with evidence from deterministic checks
(ADR-002, `docs/spec.md` §3 rules 1-2).

**`JobRejected` for job C** — the matched log fields (not a full raw dump):

```
$ cast logs --address 0x0b93793923CD5De81850aF8604a233f3f24d461e \
    0xae7362b1af91f4492868987b9c73990d780060811551b58728fbe96fd1bab275 \
    0x00000000000000000000000000000000000000000000000000000000000001a4 \
    --from-block 46426499 --to-block 46436498 --rpc-url https://sepolia.base.org

blockNumber:     46436498
transactionHash: 0x78a3a65db3160f199bddf8eb6e703c000ab322e7fa49dea2058fd93ea794989e
topics[0]:       0xae7362b1af91f4492868987b9c73990d780060811551b58728fbe96fd1bab275   JobRejected(uint256,address,bytes32)
topics[1]:       0x00000000000000000000000000000000000000000000000000000000000001a4   jobId = 0x1a4 = 420
topics[2]:       0x0000000000000000000000005c6ee4586acabcb6326069c229e58091b21ef384   rejector = VAULT
data:            0x1618e7653959fcdbd11565a41e7688ce12e1a6abca3a12f1746ed5348262b5ed   reason
```

[See the transaction on
Blockscout](https://base-sepolia.blockscout.com/tx/0x78a3a65db3160f199bddf8eb6e703c000ab322e7fa49dea2058fd93ea794989e)
— the same explorer used everywhere else here, because it is the one that decodes the vault's event
names (see above).
Two traps we already hit, so you do not have to: `rejector` is the **vault** address, not the agent EOA —
evidence hunting for the agent address will fail spuriously; and `cast logs "<signature>" <jobId>` does
**not** filter (cast 1.7.1 silently ignores arguments after the signature). The fix is **not** merely
padding the topic: as long as the signature is still sent, the topic stays ignored. What works is
dropping the signature and sending topic0 + topic1 together with `--address`, exactly the form in the
block above. A negative control with jobId `999999` over the same range returns EMPTY, so the filter does
bite.

**The cap is PUBLISHED by the contract and readable by anyone — what REJECTED job C is the off-chain
agent:**

```
$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 \
    "providerCap(address)(uint256)" 0x20212E4D95A75E6716575ED26e884cdeFf66b321 \
    --rpc-url https://sepolia.base.org
250000
```

250,000 < job C's budget of 2,000,000 → REJECT. That comparison happens in the **Python process**, not in
Solidity: `EvaluatorVault.sol` writes `providerCap` (line 289) and **never reads it** (item 17). The
value above is the number the agent announced before rejecting, not the thing that enforced the
rejection.

**The announced memory root can be recomputed from the memory files — but only on the state that
produced it.** The root announced by job 420 is `0xcfdab1b0…5b26`:

```
$ cast logs --address 0x5c6EE4586ACABcb6326069c229E58091B21ef384 \
    0xc6028d32061c1f0b8f4f1370b6f1ab5105a96bfc6631a3840371ebbcb27c7923 \
    --from-block 46436434 --to-block 46436434 --rpc-url https://sepolia.base.org
block 46436434  jobId 420  root(topic1) 0xcfdab1b0…5b26
```

**A warning you must read alongside it, so you do not copy this block and get a MISMATCH:**
`memory_export.py` over today's DB does **not** print that value, and neither does the vault's
`lastMemoryRoot()` — both have moved past job 420 (jobs 421 and 422 landed afterwards). Memory is written
**after** `postVerdict` (`docs/spec.md` §5 step 5), so every on-chain root is the state **before** that
job wrote its result, and the DB is always **one write ahead** of the chain. Today's values for both
commands, plus the pair that really does match, are in **item 22**.

The same value also appears as `memory_root` in the job 420 evidence bundle — and **that bundle↔chain
binding is what you can verify today** (item 22). The export and `postVerdict` use the **same single
implementation**, not a copy (`agent/agent/memory_policy.py` → `memory_root_for_onchain`), and its
encoding is locked by a frozen vector in `agent/tests/fixtures/memory_root_vector.json`. A cross-language
recomputation lives in `agent/tools/memory_root_check.mjs`.

What this match does **not** prove, so nobody misreads it: it proves the agent hashed the file it read,
not that the file is legitimate memory — the comparison is circular, and on chain only a zero root is
rejected (item 16). The limit on publishing the file: item 12; the limit on auditing backwards: item 7.

**The on-chain `reason` is the hash of the evidence bundle, not a random number.** The job 420 bundle
contains `"cap": {"usdc": 250000}` and `"incident_jobs": [418, 419]`; keccak256 over the bundle file's
bytes is identical to the `data` in the log above (`0x1618e765…b5ed`) — the bundle's filename is that
hash. The bundle also stores `mode: normal` and `memory_root`, so verdict, memory, and reason are bound
in one hash.

## Job 421 vs 422: the depth gate

The deliverable text is **byte-for-byte identical** (`keccak256(text)` = `0x246071b3…0a51` in
`demo/deliverables/421.json` and `422.json`), same budget (250,000), same evaluator — different provider,
opposite verdicts. The full table, what it proves, and **what it does NOT prove**: item 25.

```
job 421  postVerdict  0x02356b079fa3bfcd32e62d7e2bb61d3f4eb8b66d29fac578cd6318b2028a1467  (block 46455461)
job 421  finalize     0x371a4db2ed4c7975f3806f64392f92ecba2132feb9a1df78889c31af9bcaf020  (block 46455526)
job 422  postVerdict  0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830  (block 46455552)
job 422  finalize     0x502c8d944106914b15d95a38b2815187fa7b3d63965d95414ccd7f15835b5f08  (block 46455616)
```

## `MemoryRootUpdated` history (eight events)

The table of all eight roots with their jobIds, what each one means, and which can still be recomputed
today: **item 7**. The root ↔ evidence-bundle binding (the only pair that matches today): **item 22**.

## Number → source map

| Number | Source |
|---|---|
| `MIN_BOND` = 0 | `deployments/84532.json` → `minBondWei` |
| `CHALLENGE_WINDOW` = 120 seconds | `deployments/84532.json` → `constants.CHALLENGE_WINDOW` |
| `MIN_ACP_GAS` = 300,000 | `deployments/84532.json` → `constants.MIN_ACP_GAS`; derived from the measurements in ADR-015 decision 3 |
| `EVALUATOR_GRACE_PERIOD` = 900 seconds | `docs/api-facts.md` §A CORRECTION 2026-09-03; ADR-014 |
| vault balance = 62,500 units (0.0625 testnet USDC) = 50,000 (job 417) + 12,500 (job 421); `evaluatorFeeBP` 500 = 5% | `cast call paymentToken "balanceOf(address)" <vault>` → `62500` (item 4); `deployments/pipeline-84532.md:84` (fund-flow table); ADR-018 decision 2 |
| the fee is only paid out on `Completed` → evaluator fee for 418/419/420 = 0 | `docs/spec.md` §1 line 19 (ERC-8183 fact) + final status 4 on all three jobs, chain A/B/C above |
| `BASELINE_CAP_USDC` 1,000,000; `MIN_CAP_USDC` 250,000 | ADR-020 decisions 3 and 5; ADR-021 decision 1 |
| job 420's cap: `basis` "baseline-constant", `sample_size` 0, `usdc` 250,000 = ceil(1,000,000 / 4) | job 420 evidence bundle; `agent/agent/memory_policy.py:1666` |
| `providerCap` written at line 289, declared at line 142, zero reads | `contracts/src/EvaluatorVault.sol` (item 17) |
| `postVerdict` only rejects a zero root | `contracts/src/EvaluatorVault.sol:303` (`ZeroMemoryRoot`) |
| the off-chain root guard compares calldata against the file the agent itself read | `agent/agent/vault_client.py:1339` (`_require_derived_root`, called at :1473) (item 16) |
| `agent`/`arbiter`/`MIN_BOND` immutable, no setters, no pause | `contracts/src/EvaluatorVault.sol:14,106-114` |
| three safe-mode triggers; a missing file requires a non-zero on-chain root | `agent/agent/memory_policy.py:1461-1500` |
| `MemoryRootUpdated` history = **eight** events; all eight roots + their jobIds | `cast logs` topic0 `0xc6028d32…7923`, blocks 46350667→46455552 in windows ≤ 9,999 blocks (public RPC limit, `docs/api-facts.md` §E); full table in item 7 |
| job 418's root `0x4e2a1ca1…ff5a` = the empty-DB root (reproducible via `empty_memory_root()`, NOT via `memory_export.py` — that tool refuses to create a DB); roots 419/420/421/422 permanently lost | `empty_memory_root()` in item 7 vs `cast logs` in item 7; `docs/spec.md` §5 step 5 (memory is written AFTER `postVerdict`) |
| Sourcify 84532/`0x5c6EE45…` → `exact_match` (creation + runtime), verified from commit `8d3e596`; runtime 3518 bytes, 174 differing bytes entirely inside `immutableReferences`, identical metadata hash; broadcast still gitignored | `deployments/84532.json:31-32` and `:36-44` (`sourcify.check` holds the `curl` command); `.gitignore:6` (item 15) |
| `sim` has no `test` script; workspace = `sim`, `web` | `sim/package.json:5-8`; `pnpm-workspace.yaml` |
| the placeholder regex (one word triggers `format.placeholder-text`) | `agent/agent/checks/format.py:47-50`; `demo/deliverables/418.json`, `419.json` |
| jobs 418 / 419 / 420, budgets 1,000,000 and 2,000,000, final status 4 | `cast` output in chain A/B/C above |
| job 421 status 3 (Completed) / job 422 status 4 (Rejected), budget 250,000 for both | `cast call <ACP> "jobs(uint256)"` — ABI verified in `docs/api-facts.md` §A, used at `agent/agent/vault_client.py:389-405` (item 25) |
| `keccak256(text)` of deliverable 421 == 422 == `0x246071b3…0a51` | `demo/deliverables/421.json`, `422.json` field `sha_keccak` (item 25) |
| clean provider job 421 = `0xc3c6Bf20…aeff`; risky provider job 422 = `0x20212E4D…b321` | `cast call <ACP> "jobs(uint256)"` (item 25) |
| four depth-demo txs (2× `postVerdict`, 2× `finalize`), blocks 46455461-46455616 | the hash list above and in item 25 |
| the 402 gate lives in `agent/agent/payment_402.py` (NOT `agent/x402_server.py`) | commits `a213cdd`, `3c5cafa`; tests `agent/tests/test_payment_402.py`; ADR-010 (item 23) |
| client simulator wallet `0xbe2c447e…02C2` → 404 `/auth/agent` | `sim/src/client_min.ts:510-512` (the comment uses the placeholder `<client>`); literal address in ADR-019 `docs/decisions.md:385` + `jobs(417..422).client` on chain (item 24) |
| `providerCap` = 250,000 | `cast call providerCap(address)` above |
| block 46436498, tx `0x78a3a65d…989e`, `reason` `0x1618e765…b5ed` | `cast logs JobRejected` above |
| `lastMemoryRoot()` = `0x999a9570…9b7d` (job 422's root), while `memory_export` over today's DB = `0x50750074…0c3c` — **deliberately one write apart** | `cast call lastMemoryRoot()` and `memory_export.py` in item 22; the reason is `docs/spec.md` §5 step 5 |
| legacy root `0x1fa62c3d…7bf0` = `keccak("the-evaluator/live/memory-root/v1")` | `cast keccak` in item 7; ADR-023 context |
| selftest root `0x5ff921fd…a19e` = `keccak("the-evaluator/selftest/memory-root/v1")` | `cast keccak` in item 7; commit `26f11d6` (revoked by `190cb44`) |
| blocks 46355036 / 46355080, synthetic jobIds 9000000 / 9000001 (`0x895440` / `0x895441`) | `cast logs MemoryRootUpdated` in item 7 |
| deploy block 46350667, gas 816,969, solc 0.8.36, optimizer 200 | `deployments/84532.json` |
| chainId 84532 | `deployments/84532.json` |
