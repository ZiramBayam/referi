# Execution Passport — Evidence-Based Implementation Assessment

Assessment date: 2026-09-10  
Reviewed implementation/evidence commit: `bb74f01a3592d89e32287eb701b319f37f71faff`  
Official rules: <https://hack.sibyllabs.org/rules>, accessed 2026-09-10.

This document evaluates the non-UI Execution Passport MVP that is actually implemented
in the repository. It is separate from the idea-only review in
`execution-passport-concept-assessment.md`. Scores below are an evidence-based estimate,
not an official panel decision.

## Verdict

- Review mode: IMPLEMENTED NON-UI MVP — code and local evidence assessed.
- Local memory-gate evidence: **PASS candidate**. The repository demonstrates every gate
  behavior locally; the official panel still decides the gate after inspecting the
  submitted video/repository.
- Concept verdict: **strong, deliberately narrow prototype**.
- One-sentence reason: Sibyl memory is on the execution decision's critical path: a fresh
  process reads the stored Control Hypothesis and its thresholds, while targeted deletion
  removes the ability to issue an incident-conditioned Passport and returns human review.

## Evidence inspected

| Claim | Evidence | Fact or inference | Confidence |
|---|---|---|---|
| A deterministic incident creates structured Passport memory | `agent/agent/execution_passport.py::record_incident`; namespace `pattern:passport.control-hypothesis.stale-oracle-rebalance.v1` | Fact | High |
| A separate process reads the hypothesis | `agent/agent/passport_demo.py::run` spawns a child Python process; output includes `fresh_process_recall=stale-oracle-rebalance/v1 executor_identity=child-process` | Fact | High |
| Runtime proof selection and thresholds come from memory | `evaluate_rebalance_for_passport` uses the loaded hypothesis; demo prints `thresholds_from_memory=oracle=60 reserve=250000` | Fact | High |
| Deletion is behaviorally load-bearing | `delete_control_hypothesis` deletes only the Passport reference; the demo prints `passport_memory_deleted=True after_delete_decision=human-review-required` and asserts no Passport is returned | Fact | High |
| Exact calldata is enforced on chain | `contracts/src/PassportVerifier.sol`; `contracts/test/ExecutionPassportVerifier.t.sol`; demo reports `invalid_passport_rejected=calldata-mismatch` | Fact | High |
| Valid execution is exactly once | `usedNonces` plus the replay test; demo prints `accepted_rebalance=exactly-once` and a local transaction hash | Fact | High |
| Python behavior is covered | `28 passed` from `uv run pytest tests/test_execution_passport.py tests/test_execution_passport_integration.py -q` | Fact | High |
| Existing Solidity behavior remains intact | `175 tests passed, 0 failed, 0 skipped` from `cd contracts && forge test` | Fact | High |
| The contract is production-ready or proves economic safety | Mock contracts, one trusted signer, and off-chain attestations are explicit limitations in `docs/execution-passport/reproduction.md` | Inference: unsupported claim; should not be made | High |

## Memory-gate analysis

The local evidence satisfies the three required behaviors in the official rules:

1. **Write:** `record_incident` accepts only stale-oracle evidence where age is strictly
   greater than 60 seconds. It writes a structured hypothesis containing scope,
   obligations, counterfactual, incident IDs, observed action digests, timestamps,
   outcome counts, confidence, and status.
2. **Read:** a child process opens the same Sibyl database under a different executor
   identity. The decision path reads the hypothesis and uses its obligation list and
   thresholds before a Passport is constructed.
3. **Delete:** `delete_control_hypothesis` atomically removes only the Passport reference.
   A new client then returns `human-review-required` with no signature/passport. The unit
   test also verifies that unrelated `pattern:firewall-survivor` memory remains.

The strongest proof is behavioral, not the presence of a database row: removing the
targeted record changes the execution outcome from eligible-for-Passport to human review.
The remaining caveat is that the MVP has one supported incident/hypothesis shape. That is
appropriate for the narrow demo, but future action classes need independently defined
schemas and controls.

## Conditional rubric score

The rules define a 100-point rubric only after the memory gate: Memory 40, Innovation &
originality 25, Technical execution 20, and Pitch & presentation 15. Because the panel's
score is subjective and the required public video is not present in this repository, the
table gives a defensible range and a point estimate.

| Criterion | Maximum | Evidence-based estimate | Reason for estimate |
|---|---:|---:|---|
| Memory is load-bearing | 40 | **37 / 40** | Fresh-process recall, runtime memory-derived thresholds, targeted deletion, and no hidden strict fallback are all demonstrated. Deduction: one narrow hypothesis shape and no public video segment yet. |
| Innovation & originality | 25 | **20 / 25** | The causal loop incident → Control Hypothesis → typed obligations → action-bound Passport → outcome calibration is more specific than a notepad or static allowlist. Deduction: the verifier trusts one policy signer and the MVP does not yet prove a broad class of incidents/actions. |
| Technical execution | 20 | **17 / 20** | Solidity EIP-712 binding, target/selector/calldata/value/chain/expiry/nonce checks, atomic treasury behavior, fuzzed calldata mutation, 28 Python tests, and 175 Foundry tests are concrete. Deduction: mocks only; Sibyl/oracle/simulation attestations are off-chain trusted inputs; no audit or production deployment. |
| Pitch & presentation | 15 | **9 / 15** | The non-UI demo has a clear A–E sequence, commit hash, memory root, rejection reason, receipt/nonce, and deletion result; README and reproduction guide point to the critical path. Deduction: no 2–5 minute public demo video or partner-stack demonstration is included here. |
| **Rubric subtotal** | **100** | **83 / 100** | Point estimate from the evidence above; a reasonable judge variance is approximately 77–88 depending on presentation quality and how strongly the panel values the narrow scope. |

The estimate intentionally does not award points for claims that the implementation does
not prove. In particular, the verifier enforces the signed action binding and signer
authorization; it does not independently recompute Sibyl memory, oracle freshness, or
simulation correctness on chain.

## PMF bonus

- Actual score: **0 / 10**.
- Publicly verifiable evidence: none found for a named design partner, waitlist, pilot,
  real usage, or validated audience artifact.
- PMF potential: the obvious audience is a DAO treasury/risk operator that must approve
  high-value rebalances after incidents. A public testnet pilot request, governance
  thread, or named operator agreement would be the minimum credible evidence for a
  non-zero bonus. A market-size claim alone is not evidence.

## Partner multiplier

- Current multiplier estimate: **1.00x**; no partner bonus is claimed.
- The demo uses local Anvil chain ID `84532` and mock contracts. That is not evidence of
  the official Base partner multiplier.
- To claim Base, deploy the Passport product to Base and show an executed Passport-gated
  on-chain action in the submitted demo. An old deployment/action belonging to the former
  Escrow product would not prove this product's partner usage.
- To claim Virtuals, exercise an ACP job, registered/transacting agent, or another
  Virtuals-native integration as part of the Passport product's real function.

## Reproduction record

Command:

```sh
make demo-passport
```

Observed output from the reviewed commit:

```text
commit=bb74f01a3592d89e32287eb701b319f37f71faff
chain_id=84532 executor=anvil-local-fresh-process
incident_oracle_age_seconds=120
incident_timestamps=oracle=1789010674 observed=1789010794
incident_digest=0xc2e11b1d4f715d57cae9cc3ee2349fa85ee27245d2d627633da697c1d6ce053c
before_memory_decision=human-review-required reason=no-matching-hypothesis: bootstrap human review required
stored_hypothesis=stale-oracle-rebalance/v1 memory_root=0xaba14f262d16fb6bbb42f31cab9fe31450e1cfc2f539b72bc09d83cf9afa20f1
fresh_timestamps=oracle=1789010789 observed=1789010794
fresh_process_recall=stale-oracle-rebalance/v1 executor_identity=child-process
thresholds_from_memory=oracle=60 reserve=250000
invalid_passport_rejected=calldata-mismatch error=PassportClientError
accepted_tx=74669bca7a4c11ac2d32d7157bd0b3f96b504138def6db4ee404f54cc579444b consumed_nonce=2
accepted_rebalance=exactly-once
passport_memory_deleted=True after_delete_decision=human-review-required
```

The transaction hash is a local Anvil artifact and is not a public-chain deployment
claim. The command starts with a clean local fixture and stops its own Anvil process.

## Strongest aspect

The deletion test is unusually clear: memory is not merely displayed or used to explain a
decision. It changes whether the system can produce the only artifact that unlocks the
on-chain execution path. The fresh child process also demonstrates that the policy is
shared state rather than an executor-local cache.

## Three highest-risk weaknesses

1. **Trusted signer boundary:** the verifier confirms that the configured signer signed
   the evidence hashes; it does not independently validate the off-chain oracle,
   simulation, or memory contents. A compromised signer can attest to false proofs.
2. **Narrow fixture generalization:** only one mock treasury, one selector, one incident
   seed, and one fixed obligation set are implemented. The roadmap actions must not be
   advertised as supported until each has its own invariant and verifier tests.
3. **Presentation gap:** the repository has a reproducible terminal demo but not the
   required public 2–5 minute video showing the continuous fresh-session recall beat.

## Improvements most likely to raise the score

1. Record the one continuous demo segment required by the rules: show the commit hash,
   incident write, fresh-process read, memory-derived thresholds, rejected mutation,
   valid execution, and deletion-induced human review.
2. Add one public, independently checkable testnet pilot/design-partner artifact without
   implying production safety or PMF that has not been validated.
3. For the next action class, replace the single trusted-attestation path with a reviewed
   threat model for oracle/simulation evidence, signer rotation/recovery, and on-chain or
   independently verifiable proof inputs.

## Unsupported claims audit

The following public-language constraints are now explicit in
`README.md` and `docs/execution-passport/reproduction.md`:

- do not call `PassportVerifier` a production Safe Guard;
- do not claim arbitrary DeFi or real-funds support;
- do not claim that EIP-712 independently proves the off-chain obligations;
- do not treat local Anvil chain ID `84532` as Base partner evidence;
- do not claim PMF or a multiplier without external proof;
- treat vault migration, risk-parameter change, contract upgrade, and UI as roadmap or
  deferred scope.

## Final score summary

- Local memory-gate evidence: **PASS candidate**, official panel decision pending.
- Provisional rubric estimate: **83 / 100** (reasonable range **77–88**).
- PMF bonus: **0 / 10**.
- Partner multiplier: **1.00x / no bonus claimed**.
- Notional arithmetic if a panel awarded the point estimate: **83.0**. This arithmetic is
  not an official leaderboard result.
