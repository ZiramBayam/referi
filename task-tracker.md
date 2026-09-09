# Escrow Firewall — Task Tracker

Status legend: `[ ]` not started · `[-]` in progress · `[x]` complete · `[!]` blocked/decision required

This tracker implements the approved design in `docs/superpowers/specs/2026-09-09-escrow-firewall-design.md`.
The scope is the deterministic MVP: pre-funding safeguards from persistent failure-pattern memory. PMF work, LLM scoring, and new dispute mechanisms are excluded.

## 0. Baseline and design constraints

- [x] Approved product design committed (`285c443`).
- [x] Record existing workspace state; preserve unrelated untracked Bun lockfiles.
- [x] Map existing evaluator, simulator, contract, and UI extension points.
- [x] Run focused baseline tests before modifying behavior.
- [x] Record existing test/toolchain blockers: full suite exceeds the interactive 30-second tool window; Node root-hash parity tests also lack their expected keccak dependency and run under Node 22 while the repo pins Node 24.

## 1. Domain model: failure-pattern memory

- [x] Define canonical `FailurePattern`, `Countermeasure`, `TermsPolicy`, and `PolicyProposal` models.
- [x] Add the three MVP pattern templates:
  - [x] `missing-reproducible-evidence`
  - [x] `incomplete-deliverable`
  - [x] `requirement-ambiguity`
- [x] Persist failure patterns, observations, mitigation outcomes, and confidence in Sibyl-backed memory.
- [x] Include decision-relevant failure-pattern data in the canonical memory-root snapshot, via the compatible `pattern:firewall.*` reference namespace.
- [-] Add unit tests for validation, serialization, migration-free reads, and root determinism (validation, recall, and root-change covered; canonical vector still pending).

## 2. Pattern lifecycle

- [x] Implement deterministic extraction from existing evaluation evidence.
- [x] Implement cross-provider retrieval by task category, requirement/evidence signature, and pattern ID.
- [x] Implement confidence and outcome updates (`worked`, `failed`, `inconclusive`).
- [x] Ensure generic rejects cannot create a pattern without deterministic evidence.
- [-] Add tests for fresh-process recall, irrelevant-pattern exclusion, false-positive handling, and deletion behavior (all except false-positive handling covered).

## 3. Pre-funding policy and terms

- [x] Implement deterministic policy synthesis from retrieved patterns.
- [x] Generate canonical acceptance criteria, required evidence, milestone recommendation, review level, and rationale.
- [x] Define canonical terms encoding and `keccak256` terms commitment.
- [x] Bind the terms commitment to the ACP job flow before funding without breaking existing ACP compatibility (immutable ACP description suffix).
- [x] Reject/require review on unreadable memory, ambiguous policy, or post-funding terms mutation.
- [x] Add policy and canonical-hash unit tests.

## 4. Integration with evaluator and simulator

- [x] Extend simulator job creation to carry generic terms plus a memory-informed terms artifact.
- [x] Extend evaluator planning/evidence bundles with terms commitment and applied countermeasures.
- [x] Keep existing verdict, memory-root, cap, and deterministic-check guards intact.
- [ ] Add an end-to-end local Anvil scenario:
  - [ ] first job produces evidence and a failure pattern;
  - [ ] fresh second process retrieves it for a different provider;
  - [ ] terms change before funding;
  - [ ] outcome updates the pattern;
  - [ ] deletion control falls back safely.
- [ ] Update `make demo` only after the focused scenario is stable.

## 5. Judge-facing web experience

- [ ] Add a terms comparison view: generic terms vs memory-informed terms.
- [ ] Show recalled pattern, confidence, evidence, countermeasure, and terms hash.
- [ ] Keep all content safe to render and distinguish recommendations from enforced policy.
- [ ] Add API/UI tests for canonical display and deletion control.

## 6. Verification and handoff

- [-] Run agent tests (feature and all non-Node-parity suites pass; 7 existing Node-parity failures are blocked by missing root dependency/Node version).
- [x] Run web tests and lint/type checks.
- [x] Run Foundry tests when contract changes are necessary (159 passed; no contract change required).
- [ ] Run end-to-end local demo twice; compare deterministic evidence.
- [ ] Update README, reproduction guide, and video script to make the fresh-session moment unmistakable.
- [ ] Re-score against the official rubric with evidence links, not estimates.

## Decision log

- 2026-09-09: The product shifts from provider reputation/cap gating to Escrow Firewall: failure evidence → pattern → countermeasure → pre-funding terms.
- 2026-09-09: PMF bonus is intentionally not pursued; the target is product novelty and demonstrable load-bearing memory.
