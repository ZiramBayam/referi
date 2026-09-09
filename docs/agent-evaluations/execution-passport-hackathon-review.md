# Concept-Stage Hackathon Review Brief — Execution Passport

## Mandatory instruction to the reviewing AI agent

Act as an independent product and hackathon-idea reviewer. Evaluate the **Execution Passport idea and approved MVP design**, not the current repository implementation state. This review is intentionally requested before development is complete.

Your task is to produce an objective, evidence-backed **concept-stage assessment** of Execution Passport, the proposed evolution of Escrow Firewall. It must estimate how strongly the idea could score against the official rubric **if the documented MVP were implemented and demonstrated exactly as designed**.

This is not an official current-build score. A concept cannot pass the official memory gate, earn a partner multiplier, or earn implementation credit until it exists and is demonstrated. Do not convert this conditional assessment into a claim that the project is currently eligible or complete.

You MUST:

1. Read the official rules at <https://hack.sibyllabs.org/rules> before scoring.
2. Treat these as the primary evidence: `docs/superpowers/specs/2026-09-09-execution-passport-design.md` and `docs/research/2026-09-09-execution-passport-control-plane.md`.
3. Use external sources to test whether the problem, primitives, competitor gap, and technical claims are credible. Prefer official protocol documentation and primary sources.
4. Do **not** reduce the idea score because a verifier, demo video, README bridge, test suite, or deployment has not been built yet. Those are delivery gaps, not evidence against the idea's novelty or design quality.
5. Do distinguish sourced fact from inference. Cite every material claim about the market, existing primitive, or official rule.
6. Score each criterion as a **conditional potential score**: the score the idea could plausibly earn if the documented MVP works exactly as specified and the demo proves it.
7. Do not award PMF points without a publicly verifiable artifact; report it as `0 / 10` and assess PMF *potential* separately in prose.
8. Do not apply Base or Virtuals multiplier. Report multiplier as `not assessed` because this is an idea review, not an exercised build review.
9. State assumptions, risks, and the specific proof that would be required to turn each conditional score into a real judge score. Do not manufacture precision; use a range where warranted.

The required output format appears in [Required review output](#required-review-output).

---

## Official judging standard

Source of truth: [Sibyl Labs Hackathon Rules](https://hack.sibyllabs.org/rules), accessed 2026-09-09.

Judging is sequential:

1. **Memory gate — pass/fail.** Sibyl Memory must be load-bearing. Judges apply a deletion test: removing the memory layer must make the claimed core function fail or materially degrade. The demo must show cold-start recall in a fresh session, continuously and with an on-screen timestamp or commit hash. The README must point judges to critical-path memory reads and writes.
2. **Rubric — 100 points, only after gate pass.**
   - Memory is load-bearing: 40
   - Innovation & originality: 25
   - Technical execution: 20
   - Pitch & presentation: 15
3. **PMF bonus — up to +10.** Default is zero. Any non-zero value needs publicly verifiable evidence of real audience pain, usage, pilot, design partner, or comparable validation.
4. **Partner multiplier.** Final score is `(rubric + PMF) × multiplier`. A verified Base stack earns +15%; a second verified partner stack earns +10%, capped at `×1.25`. Sibyl Memory is mandatory and never a multiplier. Base requires deployment plus an executed on-chain action shown in the demo. Virtuals requires an ACP job, registered/transacting agent, or other Virtuals-native integration exercised in the demo.

The official rules state that a memory notepad may pass the gate but score at the floor; utility and a real problem matter.

---

## Product under review

### One-sentence claim

**Execution Passport turns a remembered DeFi operational incident into a required, transaction-specific proof bundle before a high-stakes agent action may execute.**

### Problem

For high-value DeFi operations, a final transaction record does not by itself encode the operational lesson from a failed or near-miss action: which condition was stale, which precondition was absent, which safeguard should apply next time, or whether that safeguard later worked.

Examples include a treasury rebalance performed with stale oracle data, an unsafe slippage assumption, a missing simulation condition, or a post-action reserve constraint that was not checked.

### Proposed mechanism

```text
deterministic incident evidence
  → Sibyl Control Hypothesis
  → deterministic proof obligations
  → short-lived Execution Passport for one exact transaction
  → verifier permits/rejects execution
  → outcome calibrates the Control Hypothesis in Sibyl
```

The agent is not supposed to produce a generic provider reputation score. It should remember a causal operational lesson, such as:

```text
Earlier failure: rebalance used stale oracle data.
Required next-time proof: oracle freshness + exact simulation + safe post-state reserve.
Effect: a rebalance without those proofs cannot receive a valid passport.
```

### MVP boundary

The MVP should enforce exactly one action class: `treasury-rebalance` against a mock treasury. This is intentionally narrow because a verifier/guard that blocks arbitrary DeFi actions is security-critical.

The long-term roadmap may add vault migration, risk-parameter changes, and contract upgrades, but those are not scoreable as completed until they have their own deterministic invariants, verifier scope, tests, and demo evidence.

### Why Sibyl Memory is claimed to be load-bearing

Sibyl is meant to store the **Control Hypothesis**:

```text
action class + incident predicates + required obligations + scope
+ enforcement mode + counterfactual + outcome history + confidence
```

A fresh agent process must read that memory to select stricter obligations for a later, similar action—even when a different executor/provider performs it. If memory is deleted, the system must not silently issue the same incident-conditioned passport. It must visibly fall back to a weaker bootstrap policy that requires human review.

The intended product-critical behavioral difference is:

```text
with Sibyl memory:    strict passport conditions are selected and enforced
without Sibyl memory: bootstrap policy requires human review; strict passport is unavailable
```

This claim fails if the same strict conditions are hardcoded, reconstructible without Sibyl, or unused by the verifier/executor path.

---

## Required technical model

### Control Hypothesis

The anticipated Sibyl entity/reference must be structured and versioned, rather than an opaque note. Expected fields:

```text
hypothesis_id
action_class
scope: chain, target, selector, assets
incident_predicates
required_obligations
enforcement_mode
counterfactual
observed_actions
worked / failed / inconclusive counts
confidence_bps
status
```

### Execution Passport

The anticipated passport must be bound to the exact action and short-lived state:

```text
passport_version
action_class
chain_id
target
selector
calldata_hash
value
state_block_number
state_block_hash
control_hypothesis_ids
obligation_results_hash
memory_root
issued_at
expires_at
nonce
policy_signer
```

EIP-712 is the proposed typed, domain-separated signing format. It does not itself provide replay protection; nonce consumption and expiry must be verified by the contract.

### Deterministic proof obligations proposed for the MVP

| Obligation | Expected meaning | Score only if actually verified |
|---|---|---|
| `state-anchor-fresh` | State block/hash is recent enough for policy. | Contract/agent test proves stale anchor rejection. |
| `oracle-freshness` | Oracle timestamp is within configured window. | Deterministic stale/fresh tests. |
| `simulation-match` | Simulation result belongs to the exact action digest. | Mismatched calldata/action test. |
| `post-state-invariant` | Simulated post-action reserve stays above bound. | Failing invariant test. |
| `rollback-route` | Recovery action is known and executable. | Deferred from first verifier slice; do not credit as enforced until present. |

An obligation result must be `satisfied`, `unsatisfied`, or `unverifiable`. `unverifiable` must never be interpreted as pass.

---

## Review boundary: implementation is deliberately out of scope

At the time this brief was written, the Execution Passport architecture is approved and documented in:

- `docs/superpowers/specs/2026-09-09-execution-passport-design.md`
- `docs/research/2026-09-09-execution-passport-control-plane.md`

Those documents are deliberately the object under review. Do not search for a PassportVerifier, Control Hypothesis code, video, test, or deployment in order to score the idea down. You may list their absence only in a separate “delivery proof required” section, never as a reason to lower the conditional idea score.

Existing Escrow Firewall code is relevant only as contextual proof that the team has previously explored failure-pattern memory. It neither proves nor weakens the conceptual value of Execution Passport.

---

## Concept-evaluation checklist

The reviewing agent should determine whether the design specifies each item clearly enough to be built and judged. Do not require the item to already exist.

### Gate evidence

- [ ] The design makes a Control Hypothesis a critical Sibyl write.
- [ ] The design requires fresh-process recall before the later rebalance decision.
- [ ] The design applies the hypothesis across executor identities rather than as reputation.
- [ ] The design defines a deletion behavior that materially changes policy without fail-open execution.
- [ ] The design identifies how README and demo evidence would prove the critical path.

### Verifier evidence

- [ ] The verifier scope is narrow enough to be credible for an MVP.
- [ ] The design binds signer, chain/domain, target/selector/calldata, expiry, and nonce.
- [ ] The design prevents direct treasury bypass.
- [ ] The design specifies behavior for stale anchor, stale oracle, failed invariant, and mismatched simulation.

### Integrity evidence

- [ ] Passport uses an appropriate typed/canonical encoding plan.
- [ ] Passport binds the memory root and applicable hypothesis IDs.
- [ ] Outcome calibration has a deterministic, duplicate-safe plan.
- [ ] The design names the test and repeatability evidence required before submission.

### Partner evidence

- [ ] The design identifies what real Base and Virtuals action would be needed if those bonuses are pursued later.

---

## Required review output

Use this exact structure. Cite files and commands directly.

```md
# Execution Passport — Concept-Stage Hackathon Assessment

## Verdict
- Review mode: IDEA ONLY — implementation intentionally not assessed
- Official gate status: NOT YET ASSESSABLE (do not write PASS or FAIL)
- Concept verdict: weak / plausible / strong / exceptional
- One-sentence reason:

## Evidence inspected
| Claim about the idea | Design/research/external source | Fact or inference | Confidence |
|---|---|---|---|

## Conditional gate analysis: would memory be load-bearing if built as designed?
- Intended Sibyl write:
- Intended fresh-process read:
- Intended deletion behavior:
- Risk that strict policy could be hardcoded/reconstructible:
- Required implementation proof before a real gate decision:

## Conditional idea score
Score the potential of the idea if the specified MVP is fully implemented and demonstrated. This is not a score for the current repository.

| Criterion | Maximum | Conditional potential score or range | Evidence | Assumption required to realize it |
|---|---:|---:|---|---|
| Memory is load-bearing | 40 | | | |
| Innovation & originality | 25 | | | |
| Technical execution | 20 | | | |
| Pitch & presentation | 15 | | | |
| Conditional subtotal | 100 | | | |

For technical execution and pitch, score the quality and feasibility of the documented plan, not missing code/video. Explicitly reduce the potential score if the design itself is unsafe, incoherent, untestable, or does not explain how to prove the claim.

## PMF bonus
- Actual score: 0 / 10 unless public validation evidence exists
- Publicly verifiable evidence:
- PMF potential and what would validate it:

## Partner multiplier
- Not assessed in idea mode.
- State which implementation evidence would be required for each multiplier.

## Conditional idea score summary
- Conditional rubric potential: __ / 100
- Actual PMF score today: 0 / 10 unless independently verified otherwise
- Multiplier: not assessed
- This is not a current official score and must not be represented as one.

## Strongest aspect

## Three highest-risk concept weaknesses
1.
2.
3.

## Design improvements most likely to improve conditional potential
1.
2.
3.

## Delivery proof required before making implementation claims
-
```

---

## Reference sources

1. Sibyl Labs. [Hackathon Rules](https://hack.sibyllabs.org/rules). Accessed 2026-09-09.
2. Safe. [Safe Guards](https://docs.safe.global/advanced/smart-account-guards). Accessed 2026-09-09.
3. OpenZeppelin. [AccessManager and access control](https://docs.openzeppelin.com/contracts/5.x/access-control). Accessed 2026-09-09.
4. Ethereum Improvement Proposals. [EIP-712: Typed structured data hashing and signing](https://eips.ethereum.org/EIPS/eip-712). Accessed 2026-09-09.
5. Tenderly. [Tenderly SDK](https://github.com/Tenderly/tenderly-sdk). Accessed 2026-09-09.
