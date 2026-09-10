# Execution Passport — MVP Design

## Product thesis

Execution Passport is an incident-conditioned control plane for high-stakes DeFi agent actions. It remembers why a prior operation was unsafe, converts that lesson into deterministic proof obligations, and permits a later action only when a short-lived passport binds those proofs to that exact action.

The product does not answer “is this agent reputable?” It answers:

> What did the previous failure prove must be true before this exact action can move value again?

## Scope

### MVP

The only enforced action class is `treasury-rebalance` against a mock treasury. This is a real product boundary, not merely a simplified video scene.

The MVP demonstrates:

1. deterministic incident evidence creates a Sibyl-backed Control Hypothesis;
2. a fresh process retrieves the hypothesis for a different executor;
3. the hypothesis selects stricter proof obligations;
4. an Execution Passport binds those proof results to a mock rebalance transaction;
5. a narrow verifier rejects an invalid, expired, reused, or mismatched passport;
6. deleting memory removes the incident-conditioned policy and safely falls back to human review.

### Explicit non-goals

- production Safe Guard or arbitrary Safe transaction support;
- use with real funds;
- a guarantee that simulation or oracle freshness makes an operation economically safe;
- automated exploit detection or recovery;
- LLM safety decisions;
- general DeFi transaction support in the verifier.

## Roadmap after the hackathon

The memory and passport model are intentionally action-class extensible. Each later class needs its own deterministic obligations, invariants, verifier scope, and recovery analysis.

1. `vault-migration`: accounting equality, role/allowance transfer, and executable rollback route.
2. `risk-parameter-change`: parameter bounds, simulated protocol impact, and a time-bounded state anchor.
3. `contract-upgrade`: implementation hash, storage-layout evidence, and timelock operation state.
4. Safe or AccessManager integration: only after independent review of verifier failure and recovery modes.

## Core concepts

### Incident

An Incident is deterministic evidence that an attempted rebalance was unsafe. The initial scenario is `stale-oracle-rebalance`: the oracle data timestamp exceeds the configured freshness window. A generic reject is not an incident and cannot create a Control Hypothesis.

### Control Hypothesis

A Control Hypothesis is a structured Sibyl memory object, not a text instruction.

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
created_at / updated_at
```

Initial hypothesis:

```text
id: stale-oracle-rebalance/v1
action_class: treasury-rebalance
incident: oracle data exceeded allowed age
proof obligations:
  - state-anchor-fresh
  - oracle-freshness
  - simulation-match
  - post-state-invariant
enforcement: block without a valid passport
```

`rollback-route` is represented in the data model but is not enforced by the first contract slice; it is a mandatory roadmap obligation before migration/upgrade actions are supported.

### Proof obligation

Each obligation returns exactly one of `satisfied`, `unsatisfied`, or `unverifiable`.

`unverifiable` is never treated as a pass. The Control Hypothesis maps it to `review-required` or `block`.

| Obligation | Deterministic MVP interpretation |
|---|---|
| `state-anchor-fresh` | Passport anchors to a recent block number/hash, within the configured age window. |
| `oracle-freshness` | Fixture oracle timestamp is no older than 60 seconds at passport issuance. |
| `simulation-match` | The simulator result is bound to the exact rebalance action digest. |
| `post-state-invariant` | Simulated post-rebalance mock treasury reserve remains at or above its configured minimum. |
| `rollback-route` | Modelled but deferred from verifier enforcement in this action class. |

## Execution Passport

The agent constructs an action-bound, one-time passport immediately before execution.

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

The passport uses EIP-712 typed data. Its signing domain includes chain ID and verifier address. The verifier consumes the nonce, preventing replay. It also rejects a passport when the target, calldata hash, chain, signer, or expiry is wrong.

The contract does not read Sibyl, run a simulation, or query an oracle. It verifies the compact passport; the agent creates the deterministic proof bundle and records it locally/Sibyl.

## Components

```text
MockOracle
  supplies timestamped fixture price

MockTreasury
  exposes only approved rebalance function

PassportVerifier
  verifies typed signed passport and consumes nonce

ExecutionPassport agent module
  evaluates obligations, reads/writes Control Hypotheses in Sibyl,
  creates typed passport and deterministic evidence bundle

OutcomeUpdater
  records worked / failed / inconclusive result against the hypothesis
```

## Flow

```text
1. Rebalance proposal arrives.
2. Agent reads Sibyl Control Hypotheses for treasury-rebalance.
3. No relevant hypothesis: bootstrap policy requires explicit human approval.
4. Relevant hypothesis: agent evaluates required obligations.
5. Any unsatisfied/unverifiable blocking obligation: no passport is issued.
6. All obligations satisfy: agent signs a short-lived EIP-712 passport.
7. Caller submits passport plus exact rebalance action to PassportVerifier.
8. Verifier validates and consumes nonce, then invokes MockTreasury.
9. Result is recorded as an outcome for the Control Hypothesis.
```

## Memory load-bearing and deletion behavior

Sibyl stores the causal link from incident to required proof. On a fresh process, a different executor retrieves the same active Control Hypothesis for the same action class.

When memory is deleted or unreadable, the product must not invent a strict passport or silently execute. It falls back to bootstrap policy, which requires human approval. The incident-conditioned blocking policy is absent; this observable change is the deletion control.

## Safety

- The verifier is allowlisted to one target contract and rebalance selector.
- The verifier binds `chain_id`, target, selector, calldata hash, state anchor, expiry, and nonce.
- The verifier accepts only one configured policy signer.
- A failed or missing obligation never becomes `satisfied` through a default.
- No automatic blacklisting follows an incident.
- Passport expiry is short and must be enforced on-chain.
- The mock verifier must not be represented as production-ready Safe infrastructure.

## Tests and demo acceptance

### Contract tests

- valid passport executes exactly one matching rebalance;
- wrong target, calldata hash, signer, chain, expiry, or reused nonce reverts;
- direct mock treasury rebalance bypass is impossible;
- action outside allowlisted selector reverts.

### Memory and agent tests

- stale oracle deterministic evidence creates one Control Hypothesis;
- generic reject creates none;
- fresh second process and different executor retrieve the hypothesis;
- stale oracle cannot receive a blocking passport;
- fresh oracle plus matching simulation/invariant can receive one;
- worked/failed/inconclusive outcome updates are deterministic;
- deletion produces bootstrap-review behavior.

### Demo sequence

1. Show a stale-oracle rebalance incident and its evidence.
2. Show the Control Hypothesis stored in Sibyl.
3. Restart the agent with a different executor identity.
4. Attempt the same class of action using an old/invalid passport; verifier rejects it.
5. Satisfy the current obligations; verifier permits the exact rebalance once.
6. Delete memory; demonstrate bootstrap human-review state instead of a fabricated strict passport.

## Judge-facing claim

> Execution Passport turns incident memory into a required execution condition. It does not infer agent trust from a score; it requires proof that the previous failure mechanism has been addressed before the same class of action can move value again.
