# Execution Passport — Independent Hackathon Assessment

Reviewed HEAD: `f46e0ccea8a8311c0ad666a5280f22f795ee3fc9` (`docs: add execution passport review brief`).
Review date: 2026-09-09. Rules source: <https://hack.sibyllabs.org/rules> (fetched during review).
Brief followed: `docs/agent-evaluations/execution-passport-hackathon-review.md`.

## Verdict
- Gate: **FAIL** (nothing to gate: no Execution Passport code exists at HEAD)
- Current implementation maturity: **idea** (two design documents, zero source files)
- One-sentence reason: The product under review exists only as `docs/superpowers/specs/2026-09-09-execution-passport-design.md` and `docs/research/2026-09-09-execution-passport-control-plane.md`; a search for `passport` across `agent/agent`, `contracts/src`, `contracts/test`, `sim/src`, and `web/src` returns zero hits, so there is no memory write, memory read, verifier, or demo to evaluate.

## Evidence inspected
| Claim | Evidence location / command | Result | Confidence |
|---|---|---|---|
| Execution Passport code exists | `grep -ril passport agent/agent contracts/src contracts/test sim/src web/src` | 0 files. Only 3 markdown files match repo-wide. | High |
| `PassportVerifier`, `MockTreasury`, `MockOracle` contracts | `ls contracts/src` → `EvaluatorVault.sol`, `IACP.sol` only | Absent | High |
| Control Hypothesis Sibyl model | `agent/agent/memory_policy.py`, `agent/agent/escrow_firewall.py` | Absent. Sibyl entities present are provider / pattern / suspicion / `FailurePattern` (Escrow Firewall), not Control Hypothesis. | High |
| Proof-obligation evaluator (`state-anchor-fresh`, `oracle-freshness`, `simulation-match`, `post-state-invariant`) | `agent/agent/checks/` → `format.py`, `links.py`, `chain.py`, `source.py` | Absent. Existing checks score deliverable text, not DeFi state. | High |
| EIP-712 passport signing / nonce consumption | `grep -rn "712\|nonce" contracts/src agent/agent` | No passport-related hits. | High |
| Contract tests pass | `cd contracts && forge test` | 159 passed, 0 failed (5 suites). All tests are for `EvaluatorVault`/ACP mocks, none for a passport. | High |
| Agent tests pass on this checkout | `cd agent && uv run pytest -q` | 738 passed, **7 failed**, 2 skipped. All 7 failures are in `tests/test_memory_export.py`; cause: `agent/tools/memory_root_check.mjs:49` throws `keccak256 tidak ditemukan. Jalankan pnpm install di root repo dulu`. Environment/setup failure, not logic. | High |
| Web tests pass | `pnpm -r test` | web: 13 passed, 0 failed. | High |
| Demo video exists | `grep -rn "youtu\|loom\|vimeo" *.md` (repo-wide, excluding OZ lib) | No link. Only `demo/video-script.md` (a script, no recording). | High |
| Spec documents are committed | `git ls-files docs/superpowers docs/research` | Both passport docs tracked; last two commits are docs-only. | High |
| Base deployment for **this** product | `deployments/84532.json`, README | Deployment is `EvaluatorVault` `0x5c6EE45…f384` (Escrow product). No passport contract deployed. | High |
| Virtuals integration for **this** product | `sim/src/*.ts`, `sim/package.json` (`@virtuals-protocol/acp-node-v2`) | ACP used by the escrow-referee flow only. | High |

## Gate analysis: Sibyl Memory load-bearing
- Memory write: **None for Execution Passport.** No code writes a Control Hypothesis. (The repo does write Escrow Firewall `FailurePattern` records via `agent/agent/memory_policy.py`, but that is a different product path and is excluded per brief §"Known current-state warning".)
- Memory read in fresh process: **None for Execution Passport.** `propose_policy_from_memory` (`agent/agent/escrow_firewall.py:168`) is a fresh-session Sibyl read, but it selects escrow acceptance terms for an ACP job, not proof obligations for a treasury rebalance.
- Deletion result: **Not testable.** There is no passport issuance path to delete memory from. (`escrow_firewall.py:94` `generic_policy` is the escrow fallback; not credited.)
- Risk of hardcoded/reconstructible fallback: **Unknown / not assessable.** The spec (`…execution-passport-design.md:159-163`) states the intended behavior, but no code exists to check whether strict obligations would be hardcoded.
- Gate decision and reason: **FAIL.** The rules require a fresh-session recall shown continuously with a timestamp/commit hash, README pointers to critical-path reads/writes, and a deletion test. None of the three can be satisfied for Execution Passport because no implementation, README section, or video exists.

## Rubric score (only if Gate = PASS)
| Criterion | Maximum | Score | Evidence | Why points were withheld |
|---|---:|---:|---|---|
| Memory is load-bearing | 40 | Not scoreable | — | Gate failed |
| Innovation & originality | 25 | Not scoreable | — | Gate failed |
| Technical execution | 20 | Not scoreable | — | Gate failed |
| Pitch & presentation | 15 | Not scoreable | — | Gate failed |
| Rubric subtotal | 100 | Not scoreable | — | — |

## PMF bonus
- Score: **0**
- Publicly verifiable evidence: None found in repo (no design partner, waitlist, pilot, or usage artifact for a DeFi treasury-rebalance guard).
- If score is 0, explain what is missing: A public artifact a judge can open in five minutes showing that a DeFi treasury operator wants an incident-conditioned execution gate (a signed pilot note, a public issue thread, a waitlist with real entries, or a Safe/DAO forum request).

## Partner multiplier
- Base: **1.00**. `EvaluatorVault` is deployed and exercised on Base Sepolia (`deployments/84532.json`, tx `0xe95910d2…295830`), but that is the Escrow product's action. No Execution Passport contract is deployed or executed, and the rule requires the on-chain action to be shown in the demo of the product being judged.
- Virtuals: **1.00**. `@virtuals-protocol/acp-node-v2` is used by `sim/` for escrow jobs; the passport design does not involve ACP, and no passport demo exists.
- Final multiplier: **1.00**

## Final factual score
- Formula: `(rubric subtotal + PMF bonus) × multiplier`
- Score: **Not scoreable** / 137.5 maximum theoretical points (gate failed; per brief, no hypothetical total is estimated).
- Do not apply a multiplier without the required evidence.

## Strongest aspect
The design is unusually concrete for a spec: it names the exact obligation set, the passport field list, the EIP-712 domain requirements, and the deletion behavior (`docs/superpowers/specs/2026-09-09-execution-passport-design.md:84-123, 159-163`). The repository also already contains a working, tested Sibyl-backed pattern (Escrow Firewall: recall → stricter policy → explicit generic fallback, `agent/agent/escrow_firewall.py:94-175`) that could be ported to the Control Hypothesis model. None of that earns points today, but it lowers the cost of building the MVP.

## Three highest-risk weaknesses
1. **Zero implementation.** Every scoreable claim in the brief (verifier, obligations, passport, deletion test, demo) is unmet; the last two commits (`da3868e`, `f46e0cc`) are documentation only.
2. **Product pivot with no bridge.** The repo's real code, README, deployment, and video script are all for REFERI / Escrow Firewall (ERC-8183 deliverable evaluation). A judge opening the repo would see a different product from the one the brief describes; nothing in `README.md` mentions Execution Passport.
3. **Clean-checkout test run is not green.** `uv run pytest` fails 7 tests unless `pnpm install` is first run at the repo root (`agent/tools/memory_root_check.mjs:49`). `make test` runs `forge test` and `pytest` before `pnpm -r test`, so the documented command fails on a fresh clone without a prior root install.

## Minimum changes required to improve the score materially
1. Implement the narrow slice end to end: `MockOracle`, `MockTreasury`, `PassportVerifier` (EIP-712, nonce, expiry, allowlisted target+selector) with the Foundry tests listed in the spec §"Contract tests"; plus an `agent/agent/execution_passport.py` that writes/reads a Control Hypothesis via `sibyl_memory_client` and evaluates the four MVP obligations with `satisfied | unsatisfied | unverifiable` results.
2. Add a README section "Execution Passport: memory reads and writes" with `file:line` pointers to the Control Hypothesis write, the fresh-process read, and the bootstrap fallback, and a `make demo-passport` that runs the sequence twice deterministically (including the memory-deleted run).
3. Record the 2–5 minute demo video with a continuous, unedited fresh-session recall segment showing an on-screen commit hash; deploy the verifier to Base Sepolia and execute one permitted rebalance on chain if the Base multiplier is to be claimed. Also fix `make test` so it passes on a clean checkout (add root `pnpm install` to the target or vendor `keccak256` for the node script).

## Claims that must not be made yet
- "Execution Passport is implemented" or "runnable" in any form.
- "Sibyl Memory is load-bearing for Execution Passport" (no write, read, or deletion test exists for it).
- "The verifier rejects expired / reused / mismatched passports" (no verifier).
- "Stale oracle cannot receive a passport" (no obligation evaluator).
- "Base deployment" or "Virtuals integration" for Execution Passport (existing deployment and ACP usage belong to the Escrow product).
- "All tests pass on a clean checkout" (7 pytest failures without a prior root `pnpm install`).
- Any PMF claim.
