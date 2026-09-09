# Execution Passport Control Plane

## Research question

Can incident-conditioned memory create a defensible control plane for high-stakes DeFi agent actions, rather than another transaction checklist or agent reputation system?

## Conclusion

Yes, with a narrow definition. The product should not attempt to replace a Safe guard, a timelock, a simulator, an oracle, or governance. Those primitives already handle execution restriction, delay, state simulation, data feeds, and authorization. Execution Passport should connect them through a missing loop:

```text
incident evidence → reusable control hypothesis → typed proof obligations
→ signed, bounded execution passport → outcome calibration
```

The differentiated unit is not a transaction approval and not a static rule. It is a **control hypothesis**: a versioned statement that a specific historical failure mode requires specific evidence for a specified class of future action, together with measured evidence of whether that safeguard reduced or failed to reduce risk.

## What existing primitives solve

| Primitive | What it solves | Material limitation for this product |
|---|---|---|
| Safe Guard | Can inspect a Safe transaction before and after execution; can block it. | A guard has no native incident memory or semantic method for deriving a new policy from prior operational failure. It is also security-critical and can cause denial of service if wrong. [1] |
| Safe Module | Can execute transactions from a module. | Modules are powerful and can execute arbitrary transactions; they are not themselves a reasoned safety policy. [2] |
| OpenZeppelin Timelock / AccessManager | Delays, roles, cancellation, ordering, and target/function restrictions. | Delay answers *when* a known operation may happen. It does not determine which proof should be required because of a prior near-miss. [3][4] |
| Transaction simulation | Predicts transaction or bundle outcomes against a fork/state. | Simulation is an observation at a point in time; it does not preserve learned conditions across incidents or decide when its output is sufficient. [5] |
| EIP-712 / EAS | Typed, domain-separated signed messages and structured attestations. | They bind a chosen claim. They do not produce the claim or calibrate it from operational outcomes. [6][7] |

## The actual gap

High-stakes DeFi operations fail through combinations that are often absent from the final transaction record: stale assumptions, a missing simulation condition, an incorrect order of calls, an unsafe tolerance, a missing role check, or an unavailable rollback path. The chain can show that a transaction executed or reverted, but it cannot by itself express the causal operational lesson:

> “For this action class, a valid simulation alone was not sufficient because the risk depended on an oracle freshness window and a post-action reserve invariant.”

Today, that lesson lives in a postmortem, a human runbook, or nowhere. A static guard cannot tell whether the rule is justified, scoped correctly, or becoming stale. A generic “agent reputation” score also cannot tell the next executor what proof it must provide.

## Proposed product primitive: Control Hypothesis

Each Control Hypothesis is structured, versioned, and scoped. It contains no free-form executable instruction.

```text
hypothesis_id          e.g. stale-oracle-rebalance/v1
action_class           treasury-rebalance | parameter-change | migration
scope                  target contracts, selector, assets, chain
incident_predicates    deterministic evidence that justified the hypothesis
required_obligations   typed proof requirements
enforcement_mode       recommend | review-required | block
validity_window        maximum age for volatile proofs
counterfactual         what prior policy missed
outcome_history        worked | failed | inconclusive, by action id
confidence             bounded calibration value, never ground truth
status                 active | retired
```

The critical distinction is that `required_obligations` are not prose terms. Each must be machine-checkable or explicitly routed to human review.

## Execution Passport

An Execution Passport is an ephemeral, action-bound proof bundle created immediately before execution.

```text
action digest
  + target / selector / calldata hash / value / chain id
  + state anchor (block number and block hash)
  + ordered obligation results
  + active control-hypothesis ids and memory root
  + expiry
  + policy version
  = EIP-712 typed passport digest
```

The passport must be bound to target, calldata, chain, state anchor, and expiry. Binding only a narrative policy hash would permit replay against a different action. EIP-712 provides a standard typed, domain-separated representation for this signing step, but replay protection and expiry remain product responsibilities. [6]

## Five MVP proof obligations

The MVP should implement only deterministic obligations. No LLM should decide whether an action is safe.

| Obligation | Machine-checkable claim | Example failure it prevents |
|---|---|---|
| `simulation-match` | Fork simulation of the exact action digest succeeds and reports the expected state delta. | An action whose calldata is different from the reviewed simulation. |
| `state-anchor-fresh` | Passport block hash/number equals an allowed recent chain state. | Executing after a materially changed market or governance state. |
| `oracle-freshness` | Referenced feed timestamp/round is within the policy window. | Rebalance based on stale price data. |
| `post-state-invariant` | Simulation output satisfies a bounded invariant such as minimum reserve ratio or maximum slippage. | A technically successful but economically unacceptable execution. |
| `rollback-route` | A predeclared, allowed recovery action exists and simulation establishes its executability. | Executing an irreversible operation with no tested recovery path. |

An obligation may return `satisfied`, `unsatisfied`, or `unverifiable`. `unverifiable` is not success; the policy maps it to human review or block.

## Why memory is load-bearing

A static safety policy can require all five obligations forever. That is not the product. It produces either excessive friction or a lowest-common-denominator rule set.

Memory is load-bearing when it changes all of these values for a later action:

1. which obligations are selected;
2. thresholds and validity windows;
3. whether the result is recommendation, review, or block;
4. the counterfactual explanation shown to a signer; and
5. the later update to the hypothesis when the control succeeds, fails, or is inconclusive.

Deleting the Sibyl memory must remove the incident-conditioned obligation set and yield the intentionally weaker bootstrap policy. That is a demonstrable behavioral change, not merely a missing dashboard record.

## Architecture options

### A. Advisory passport

The agent produces a signed passport and a human/Safe signer decides whether to execute. No new guard contract is required.

- Strength: smallest, safest hackathon MVP; directly supports a proof-heavy demo.
- Weakness: cannot truthfully claim automatic on-chain prevention.

### B. Passport verifier with a narrow executor

A dedicated verifier accepts an EIP-712 passport only for an allowlisted target/selector/action digest and checks expiry, nonce, and policy signer. A Safe module or a controlled executor calls through it.

- Strength: the passport becomes an actual execution gate; strong technical novelty.
- Weakness: security-critical contract surface and recovery design are mandatory.

### C. General Safe Guard

A Safe Guard examines all relevant Safe transactions and requires a passport for matched calls.

- Strength: closest to an enterprise control plane.
- Weakness: guards can lock a Safe if flawed; scope is too broad for a hackathon without an audited recovery path. [1]

## Recommendation

Build **B in a deliberately narrow form**, but demo it as a local mock target rather than a production Safe integration:

- one action class: a treasury rebalance call;
- one mock executor target and one selector;
- a passport verifier that checks action digest, state anchor age, expiry, nonce, and authorized signer;
- obligations evaluated by a deterministic local simulation fixture;
- Sibyl stores and retrieves the Control Hypothesis;
- a deletion control reverts to bootstrap policy and therefore cannot mint the stricter passport.

This creates a credible enforcement moment while respecting the Safe documentation warning: a generic Safe Guard is security-critical and can cause denial of service. [1]

## Product narrative

> Execution Passport turns incident memory into an execution requirement. It does not ask, “Do we trust this agent?” It asks, “What did the last failure prove must be true before this exact action can move value again?”

## Demo sequence

1. A mock rebalance is proposed with a generic bootstrap policy.
2. A deterministic incident establishes that stale-oracle conditions made the earlier action unsafe.
3. The Control Hypothesis is stored in Sibyl with evidence and a required `oracle-freshness` plus `simulation-match` obligation.
4. In a fresh process and for another executor, the same action class retrieves that hypothesis.
5. An old/incorrect passport is rejected by the verifier because its state anchor, obligation set, or nonce does not match.
6. A fresh passport satisfying both obligations executes the mock rebalance.
7. Deleting memory causes the system to use bootstrap policy; the stricter passport cannot be issued, visibly proving that the incident knowledge changed control behavior.

## Risks and explicit non-claims

- A simulation is not a guarantee of production execution or economic safety.
- Oracle freshness does not establish oracle correctness.
- A local evaluator/signer remains trusted in the MVP.
- The demo verifier is not an audited Safe Guard and must not control real funds.
- Memory confidence is calibration metadata, not a risk model.
- The MVP does not detect exploits, replace DAO governance, or autonomously recover funds.

## Sources

1. Safe. “[Safe Guards](https://docs.safe.global/advanced/smart-account-guards).” Accessed September 2026.
2. Safe. “[Safe Modules](https://docs.safe.global/advanced/smart-account-modules).” Accessed September 2026.
3. OpenZeppelin. “[Governance: TimelockController](https://docs.openzeppelin.com/contracts/4.x/api/governance).” Accessed September 2026.
4. OpenZeppelin. “[Access Control / AccessManager](https://docs.openzeppelin.com/contracts/5.x/access-control).” Accessed September 2026.
5. Tenderly. “[Tenderly SDK](https://github.com/Tenderly/tenderly-sdk).” Accessed September 2026.
6. Ethereum Improvement Proposals. “[EIP-712: Typed structured data hashing and signing](https://eips.ethereum.org/EIPS/eip-712).” Accessed September 2026.
7. Ethereum Attestation Service. “[Schemas](https://docs.attest.org/docs/core--concepts/schemas).” Accessed September 2026.
