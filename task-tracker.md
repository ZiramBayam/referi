# Execution Passport — Implementation Tracker

Status: `[ ]` not started · `[-]` in progress · `[x]` complete · `[!]` blocked by an explicit decision or external dependency.

This is the active plan. It supersedes the former Escrow Firewall tracker; the former product stays in Git history and `docs/superpowers/specs/2026-09-09-escrow-firewall-design.md`, but **must not be extended in this plan**.

## 0. Agent briefing — read before changing anything

### Objective

Build the **Execution Passport** MVP: an incident-conditioned control plane for one high-stakes DeFi action. Deterministic `stale-oracle-rebalance` evidence is stored as a Sibyl-backed **Control Hypothesis**. A fresh process with another executor identity retrieves it, evaluates the required proofs, and signs a short-lived EIP-712 passport only when every blocking proof passes. A narrow Solidity verifier accepts the passport once and only for the exact allowlisted mock treasury rebalance.

> Execution Passport turns incident memory into a required execution condition. It asks what a prior failure proved must be true before this exact action may move value again.

### Required reading and source of truth

Read these files completely. If they conflict, the first file wins.

1. `docs/superpowers/specs/2026-09-09-execution-passport-design.md` — approved MVP scope and acceptance criteria.
2. `docs/research/2026-09-09-execution-passport-control-plane.md` — rationale, threats, rejected alternatives.
3. `docs/agent-evaluations/execution-passport-hackathon-review.md` — memory/deletion proof requirements.
4. This tracker — task order and definitions of done.

### Non-negotiable MVP boundary

- Enforce **only** `treasury-rebalance`.
- Use only a purpose-built `MockTreasury`; never real funds, Safe, Safe Guard, Safe Module, or AccessManager.
- Allow only one target and one rebalance selector in the verifier.
- Make every decision deterministic. No LLM decides whether a proof passes.
- `unverifiable` never passes; map it to `review-required` or `block`.
- `rollback-route` exists as a typed roadmap field only; do not enforce it here.
- Do not build or edit frontend/UI unless separately requested.
- Never claim production security, general DeFi coverage, economic safety, or arbitrary Safe support.

### Success condition

One reproducible local command, with commit hash and timestamps, proves:

1. stale-oracle evidence creates a Control Hypothesis in Sibyl;
2. a fresh agent process under a different executor identity reads it;
3. that retrieved memory—not a hard-coded strict default—selects proof obligations and thresholds;
4. the verifier rejects a stale, invalid, reused, or mismatched passport;
5. a compliant passport executes the exact mock rebalance precisely once;
6. deleted/unreadable memory returns `bootstrap: human-review-required` and never issues an incident-conditioned passport.

### Existing extension points

| Area | Existing location | Passport responsibility |
|---|---|---|
| Sibyl agent integration | `agent/agent/memory_policy.py` | New Control Hypothesis namespace/lifecycle; do not overload Firewall types. |
| Existing fail-closed precedent | `agent/agent/escrow_firewall.py` | Reuse serialization/fallback patterns only; never couple Passport to escrow terms. |
| Chain-client precedent | `agent/agent/vault_client.py` | Add a narrow Passport client here only if appropriate; otherwise create `passport_client.py`. |
| Solidity project | `contracts/src/`, `contracts/test/` | Mock oracle, mock treasury, verifier, Foundry tests; leave `EvaluatorVault` and `IACP` untouched. |
| Local scenario | `sim/src/client_min.ts`, `sim/package.json`, root `Makefile` | Add a non-UI reproducible demo only after tests are stable. |

## 1. Frozen decisions

- [x] Wedge: incident-conditioned execution control, not reputation or generic transaction screening.
- [x] Action: `treasury-rebalance` only.
- [x] Incident seed: `stale-oracle-rebalance` only.
- [x] Architecture: a narrow executor/verifier, not advisory signing and not a general Safe Guard.
- [x] Passport: EIP-712 typed data with on-chain expiry and one-time nonce consumption.
- [x] One configured trusted policy signer for the mock MVP.
- [x] Enforced proofs: `state-anchor-fresh`, `oracle-freshness`, `simulation-match`, `post-state-invariant`.
- [x] Initial oracle window: 60 seconds, loaded from the retrieved Control Hypothesis at runtime.
- [x] Missing/deleted/unreadable memory: human review; no invented strict policy and no auto-execution.
- [x] Post-hackathon: vault migration, risk parameter change, contract upgrade, then reviewed Safe/AccessManager integrations.

## 2. Baseline, interfaces, and canonical formats

### 2.1 Baseline without behavior changes

- [x] Inspect `README.md`, root `Makefile`, `agent/README.md`, `agent/pyproject.toml`, `contracts/foundry.toml`, and `sim/package.json`.
  - Record actual Python, Foundry, and local-demo commands.
  - Record Anvil, Node/Bun, Python/uv, and signing dependencies already available.
- [x] Inspect `agent/agent/memory_policy.py` and tests for Sibyl read/write API, canonical serialization/hash, memory-root export, deletion behavior, and fixture style.
- [x] Inspect Solidity source/tests for version, remappings, EIP-712/ECDSA availability, test conventions, and deployment fixtures.
- [x] Run focused baseline tests and record pre-existing failures precisely. Preserve known unrelated Node parity/dependency issues; do not weaken tests to hide them. `forge test` baseline passed; `make doctor` remains environment-red because this shell has pnpm 10 and no matching uv Python discovery.

**Done:** a subsequent agent can name commands, conventions, and pre-existing failures before modifying Passport behavior.

### 2.2 Canonical formats (must precede business logic)

- [x] Create `docs/execution-passport/canonical-formats.md`.
- [x] Freeze exact enum strings:
  - action `treasury-rebalance`; incident `stale-oracle-rebalance`;
  - proof result `satisfied`, `unsatisfied`, `unverifiable`;
  - decision `passport-issued`, `block`, `human-review-required`;
  - outcome `worked`, `failed`, `inconclusive`;
  - status `active`, `retired`.
- [x] Define canonical action payload order: `chain_id`, `target`, `selector`, `calldata`, `value`, `state_block_number`, `state_block_hash`.
- [x] Define hashes precisely:
  - `calldata_hash = keccak256(full ABI-encoded rebalance calldata)`;
  - `action_digest` binds all canonical action fields;
  - `obligation_results_hash` hashes ordered canonical proof results;
  - `memory_root` follows the repository’s existing deterministic root convention.
- [x] Define EIP-712 `ExecutionPassport` field names/types/order identically for Solidity and Python: `passport_version`, `action_class`, `chain_id`, `target`, `selector`, `calldata_hash`, `value`, state anchor, `control_hypothesis_ids_hash`, `obligation_results_hash`, `memory_root`, `issued_at`, `expires_at`, `nonce`.
- [x] State verification ownership:
  - Solidity verifies signature/domain, action class, target, selector, calldata hash, value, chain, expiry, nonce, signer, allowlist.
  - Solidity does not query Sibyl, oracle, chain state, or simulation; those are signed, action-bound attestations.
- [x] Add one fixed cross-language test vector for calldata hash and EIP-712 digest.

**Done:** no agent must guess byte order, enum spelling, timestamp unit, hash input, or verification layer.

## 3. Control Hypothesis memory slice

### 3.1 Isolated model and namespace

- [x] Create a dedicated module, preferably `agent/agent/execution_passport.py`, plus a narrow helper only when it improves isolation.
- [x] Define validated structures for `IncidentEvidence`, `ControlHypothesis`, `ObligationDefinition`, `ObligationResult`, `ActionProposal`, `PassportDecision`, `PassportEvidenceBundle`, and `OutcomeRecord`.
- [x] Require Control Hypothesis fields: ID/version, action class, scope (chain/target/selector/assets), incident predicates, proofs, enforcement mode, counterfactual, validity window, outcome history/counts, confidence BPS, status, created/updated timestamps.
- [x] Recognize `rollback-route` in the type system but prevent it entering this MVP’s enforced list by accident.
- [x] Validate: positive windows/expiry, confidence `0..10_000`, nonempty scope, unique proof IDs, known enums only.
- [x] Use a separate namespace such as `pattern:passport.control-hypothesis.*`; never collide with `pattern:firewall.*`.
- [x] Canonicalize all serialization so memory-root results are stable across processes.

**Done:** malformed or ambiguous hypotheses cannot be stored or used to mint a passport.

### 3.2 Deterministic incident ingestion

- [x] Implement a single ingestion route that accepts only deterministic stale-oracle evidence:
  - correct action/scope;
  - oracle timestamp present;
  - observed age strictly exceeds configured freshness window;
  - action ID/digest and observation time recorded.
- [x] Reject generic rejection prose, missing timestamp, wrong action class, and fresh-oracle inputs.
- [x] Valid evidence creates/updates only `stale-oracle-rebalance/v1` with the four approved proofs and `block` mode.
- [x] Make repeated ingestion of identical evidence idempotent: no extra counts, no nondeterministic root change.
- [x] Store the counterfactual: simulation alone was insufficient because oracle freshness and post-state reserve were unproven.

**Done:** only deterministic stale-oracle evidence can create the initial hypothesis, and duplicate ingestion is stable.

### 3.3 Retrieval, fallback, deletion, calibration

- [x] Retrieve by action class plus chain, target, selector, optional assets; executor identity must not affect matching.
- [x] Deterministic selection:
  - zero match → bootstrap human review;
  - one unambiguous active match → apply it;
  - conflicting/equally specific matches → review, no passport;
  - retired match → ignore with reason.
- [x] Read runtime proof selection and thresholds from retrieved memory. Schema validation defaults may exist, but never a hidden strict fallback reproducing this policy.
- [x] Distinguish `memory-unavailable` from `no-matching-hypothesis`; both require review, but reason/evidence differs.
- [x] Record deterministic outcomes:
  - `worked`: verifier execution and expected fixture result;
  - `failed`: authorized execution reaches a defined bad fixture postcondition;
  - `inconclusive`: result cannot be classified.
- [x] Do not auto-retire, blacklist, or relax controls. Update outcome counts/timestamp/confidence only by documented deterministic rules.
- [x] Add a real-adapter delete/test helper which deletes Passport records, not merely an in-memory cache.

**Done:** a different fresh executor applies the same policy; deleting records eliminates it and forces review.

## 4. Deterministic proof engine and simulation fixture

### 4.1 Proof evaluator

- [x] Implement one evaluator receiving `ActionProposal`, selected hypothesis, deterministic environment, and injected clock.
- [x] Return ordered `ObligationResult`s containing ID/type, enum result, observed values, threshold/version, evidence digest, and safe explanation.
- [x] Implement exact proof semantics:
  - `state-anchor-fresh`: present block number/hash and age within hypothesis window;
  - `oracle-freshness`: oracle age `<=` the hypothesis window (seeded as 60 seconds);
  - `simulation-match`: successful fixture simulation for exact action digest/calldata hash;
  - `post-state-invariant`: simulated mock treasury reserve `>=` configured minimum.
- [x] Document timestamp unit and boundary rule once; use it in all languages/tests.
- [x] Missing/malformed inputs, unavailable environment, and unknown proof types become `unverifiable`.
- [x] Any blocking `unsatisfied`/`unverifiable` maps to `block`, never signing.

**Done:** each permit comes from inspectable deterministic evidence; all absence/ambiguity fails closed.

### 4.2 Minimal local simulation fixture

- [x] Use a deterministic local fixture, not a third-party API, as correctness source.
- [x] Define mock rebalance ABI/state transition once and share its semantics with `MockTreasury`.
- [x] Inputs: target, calldata/value, pre-state reserve, amount, oracle observation.
- [x] Outputs: input action digest, success/revert, expected post-state reserve, canonical simulation evidence digest.
- [x] Cases: normal rebalance; reserve invariant at/below/above boundary; calldata changed after simulation; stale state; stale oracle.
- [x] Never call live oracle/treasury/simulator in correctness path. Optional later integration is non-authoritative.

**Done:** any action-bound input mutation makes `simulation-match` fail deterministically.

## 5. Solidity enforcement slice

### 5.1 Mocks and ownership boundary

- [x] Add `contracts/src/MockOracle.sol` with minimal fixture timestamp/price state and test-restricted mutation.
- [x] Add `contracts/src/MockTreasury.sol` with mock reserve/minimum-reserve and exactly one rebalance entry point.
- [x] Restrict rebalance caller to `PassportVerifier` after setup; direct execution reverts. Emit compact `Rebalanced` event.
- [x] Decide native internal accounting vs ERC-20 test token before coding; choose the smallest model that clearly proves reserve behavior.
- [x] Keep all setup/administration test-only in purpose; no public bypass method.

**Done:** direct callers cannot move mock value; configured verifier can.

### 5.2 Narrow `PassportVerifier`

- [x] Add `contracts/src/PassportVerifier.sol` using compatible EIP-712/ECDSA helpers.
- [x] Mirror `canonical-formats.md` in a Solidity `ExecutionPassport` struct. Pass raw rebalance calldata separately; compare `keccak256` to signed hash.
- [x] Constructor/configuration fixes policy signer, mock treasury target, rebalance selector, and maximum lifetime.
- [x] Provide one `(passport, signature, rebalanceCalldata)` execution entry point.
- [x] Verify before treasury call:
  1. canonical action class;
  2. configured target;
  3. selector from supplied calldata;
  4. calldata hash;
  5. chain/domain;
  6. issued/expiry window and maximum lifetime;
  7. unused nonce;
  8. recovered configured signer;
  9. signed/executed value (zero-only unless mock needs native value).
- [x] Consume nonce before external call; rely on atomic revert if treasury rejects; add reentrancy protection if call pattern warrants it.
- [x] Emit `PassportConsumed` with nonce, passport digest, calldata/action digest, hypothesis-ID hash, proof-results hash, and memory root.
- [x] Use clear custom errors for signer, time, nonce, target, selector, calldata, action class, and value failures.
- [x] Do not put Sibyl/oracle/simulation verification in Solidity; verifier enforces trusted signer’s compact action-bound assertion.

**Done:** a valid signature performs exactly one matching rebalance; all altered/replayed/time-invalid calls revert before treasury changes.

### 5.3 Foundry tests

- [x] Add focused `contracts/test/ExecutionPassport*.t.sol` tests using project conventions.
- [x] Positive: exact passport executes once, emits events, updates reserve as simulated, marks nonce used.
- [x] Direct treasury bypass reverts.
- [x] Independent negative tests: wrong signer, target, selector, one-byte calldata mutation, value, chain/domain, not-yet-valid, expired, replay, non-rebalance action class.
- [x] Test treasury revert atomicity and document expected nonce behavior.
- [x] Test invariant-breaking rebalance cannot be reached through fixture-valid passport; direct path still reverts.
- [x] Add cheap fuzz/property checks: nonce executes at most once; any calldata mutation breaks signature binding.
- [x] Confirm all existing EvaluatorVault/IACP tests remain passing.

**Done:** every rejection proves no state change before it; full Foundry suite passes.

## 6. Passport assembly, signing, and chain client

### 6.1 Decision/assembly API

- [x] Implement `evaluate_rebalance_for_passport(...)` as the single application entry point.
- [x] Required sequence:
  1. normalize/validate proposal;
  2. read Control Hypotheses from Sibyl;
  3. select bootstrap review or one hypothesis;
  4. on review/block return decision, never construct/sign passport;
  5. evaluate ordered proofs;
  6. when all pass, create canonical evidence bundle and root snapshot;
  7. construct short-expiry passport with fresh nonce;
  8. build/sign EIP-712 typed data through test-local policy signer;
  9. return decision, passport, signature, and evidence—never a private key.
- [x] Keep memory loading, policy decision, proof evaluation, and signing as isolated testable functions.
- [x] Inject clock, signer, memory adapter, and fixture into tests.
- [x] Use collision-resistant nonce generation; local tracking prevents accidental pre-submit reuse but chain state is authoritative.

**Done:** one unit-testable path maps an action to review/block or signed passport.

### 6.2 EIP-712 parity and submit client

- [x] Implement typed data precisely from canonical format: domain name/version, chain ID, verifier address.
- [x] Prove off-chain and Solidity recovered signer/digest parity with fixed vector and live Anvil demo.
- [x] Add narrow local-chain submit client for passport + raw rebalance calldata.
- [x] Decode verifier/treasury events into structured receipt.
- [x] Use only Anvil account/ephemeral test key; never print/persist real private keys.

**Done:** E2E path yields a real local transaction receipt/events from agent-signed Passport data.

## 7. Cross-process integration proof

### 7.1 Automated A–E scenario

- [x] Create a focused integration test from clean Passport memory and deployed mock environment.
- [x] A — Incident: action with oracle age `> 60s` returns no passport; ingest evidence; assert one active `stale-oracle-rebalance/v1` hypothesis.
- [x] B — Fresh recall: instantiate a new agent/process with different executor identity/no memory cache; assert same hypothesis, proof list, and threshold were read from Sibyl.
- [x] C — Reject: submit stale, expired, reused, or calldata-mismatched passport; assert revert and unchanged treasury.
- [x] D — Permit once: fresh/matching/invariant-satisfying evidence → new passport → one state transition/event → identical retry reverts.
- [x] E — Delete: delete hypothesis with real adapter; start new process; same action returns `human-review-required`, supplies no signature/passport.

**Done:** repeatable clean-checkout test proves every memory-gate behavior without UI.

### 7.2 Determinism/failure tests

- [x] Run A–E twice with fixed inputs; compare canonical hypothesis, proof-results hash, passport digest where time/nonce fixed, and events. Unit + repeatable `make demo-passport` runs cover stable behavior; transaction hashes intentionally vary.
- [x] Test malformed memory, conflicting hypotheses, missing oracle timestamp, failed simulation, simulation digest mismatch, stale state, and invariant failure. The direct test suite covers the deterministic failure classes.
- [x] Assert all map to block/review, never a passport.
- [x] Confirm unrelated Firewall memory cannot select Passport policy and Passport deletion cannot remove Firewall records.

**Done:** only an unambiguous memory-retrieved hypothesis plus satisfied proof bundle can sign.

## 8. Reproduction, demo, and evidence

### 8.1 Developer guide and README pointers

- [x] Add `docs/execution-passport/reproduction.md`: prerequisites, non-secret environment, setup, exact tests, expected output.
- [x] Explain three boundaries: incident writer, fresh executor reader, local verifier.
- [x] State mock/trust assumptions: local chain, mock oracle/treasury, configured signer, signer-attested evidence, no real funds.
- [x] Add troubleshooting: Anvil unavailable, wrong chain, expired clock, memory adapter unavailable, missing test dependency/key.
- [x] Update `README.md` minimally with Passport section linking exact memory write/read/delete locations, demo command, reproduction guide, limitations.

**Done:** a judge finds memory write/read/delete paths from README in under two minutes.

### 8.2 Non-UI demo

- [x] Add `make demo-passport` (or repository-consistent equivalent) only after it runs A–E reliably.
- [x] Ordered output must show: commit hash; timestamps/oracle age; incident digest; stored/recalled hypothesis and root; fresh executor label; proofs/thresholds loaded from memory; rejection reason; accepted transaction/event and nonce; deletion and review/no-passport result.
- [x] Start from clean fixture state; never depend on previous shell process cache.
- [x] Run twice. Save only small non-secret deterministic artifacts where project convention permits.
- [x] Do not edit UI/video. If video is later requested, update `demo/video-script.md` factually from this proven flow.

**Done:** one unedited screen recording can prove fresh-session recall and deletion control.

### 8.3 Evidence-based self-assessment

- [ ] Add/update an implementation assessment separate from idea-only evaluations.
- [ ] Cite exact paths, tests, demo output, local transaction hashes, commit hash; label facts vs inferences.
- [ ] Score official rubric only after gate evidence exists. Do not claim PMF/multiplier without verifiable external proof.
- [ ] Audit public language against unsupported claims in the review brief.

**Done:** an independent evaluator can reproduce claims without trusting narrative.

## 9. Required sequence and commit boundaries

Do not start a group before its prerequisites pass.

1. [ ] Section 2: baseline + formats. Commit: `docs: define execution passport canonical formats`.
2. [ ] Section 3: memory model/lifecycle + unit tests. Commit: `feat(agent): add control hypothesis memory`.
3. [ ] Section 4: proof engine/fixture + unit tests. Commit: `feat(agent): evaluate passport proof obligations`.
4. [ ] Section 5: mocks/verifier + Foundry tests. Commit: `feat(contracts): add narrow passport verifier`.
5. [ ] Section 6: assembly/signing/client parity. Commit: `feat(agent): mint and submit execution passports`.
6. [ ] Section 7: fresh-process and deletion E2E. Commit: `test: prove passport memory control loop`.
7. [ ] Section 8: reproducibility/demo/assessment. Commit: `docs: add execution passport reproduction evidence`.

Before every commit:

- [ ] Run relevant focused tests plus affected complete suite.
- [ ] Inspect `git diff`/`git status`; preserve unrelated user and untracked files.
- [ ] Never stage secrets, credentialed RPC URLs, chain databases, or recordings.
- [ ] Document demonstrated acceptance criteria and unrelated blockers in commit body/notes.

## 10. Definition of done

- [ ] No Safe/general-DeFi/real-funds scope creep.
- [ ] Deterministic incident creates structured Sibyl Control Hypothesis.
- [ ] Fresh different executor retrieves it.
- [ ] Memory selects runtime proofs/thresholds; deletion cannot be recreated by hidden strict fallback.
- [ ] Missing/deleted/malformed/conflicting/unreadable memory is review/block, never automatic execution.
- [ ] Four MVP proofs are evaluated and bound into signed passport evidence.
- [ ] EIP-712 verifier binds exact target, selector, calldata, value, chain, expiry, signer, nonce.
- [ ] Rejected transaction changes no MockTreasury state; valid transaction changes it exactly once.
- [ ] Direct bypass, altered calldata, signature mismatch, expiry, wrong chain, replay all have automated negative tests.
- [ ] One reproducible non-UI command proves recall/deletion with timestamp and commit hash.
- [ ] README gives direct memory read/write/delete/demo pointers.
- [ ] Relevant tests pass, or named pre-existing blockers remain unmasked.

## 11. Deferred backlog — exclude from MVP

- [ ] Enforce `rollback-route` for migration/upgrade actions.
- [ ] `vault-migration`: accounting, role/allowance, rollback evidence.
- [ ] `risk-parameter-change`: bounded parameters, protocol-impact simulation, state anchor.
- [ ] `contract-upgrade`: implementation hash, storage-layout evidence, timelock state.
- [ ] Safe Guard/Module/AccessManager integration only after independent failure/recovery review.
- [ ] Production oracle/simulation/attestation design only after threat model/audit.
- [ ] Dashboard/UI, notifications, multi-operator approval, PMF/market validation.

## Decision log

- 2026-09-09: Focus changed from Escrow Firewall to Execution Passport: an incident-derived hard execution condition is more distinct than an advisory escrow-term proposal.
- 2026-09-09: Treasury rebalance is a real MVP product boundary, not merely a video shortcut; other DeFi actions are roadmap items.
- 2026-09-09: Use a narrow mock verifier, not production Safe infrastructure, because guard failure/recovery is out of scope.
- 2026-09-10: This replaces the active tracker. Frontend/UI is excluded until separately requested.
