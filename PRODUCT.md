# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are developers and operators building or testing agents that can execute
high-stakes DeFi or treasury actions. They need to verify that an agent does not repeat a
known operational failure before it is allowed to move value.

## Product Purpose

Referi, in its current product direction, is Execution Passport: an incident-conditioned
control plane for agent execution. It records why a previous operation was unsafe, turns that
lesson into deterministic proof obligations, and allows a later action only when a short-lived
passport binds those proofs to the exact action. Success means a user can see, try, and verify
that unsafe execution is blocked while compliant execution is allowed once.

## Positioning

The meaningful mechanism is not a provider score or a history page. Sibyl memory stores a
structured Control Hypothesis that connects an incident to the preconditions and proofs required
before the same action class can move value again. The agent then produces an action-bound,
one-time Execution Passport, and a narrow verifier enforces that passport at the transaction
boundary.

## Operating Context

The primary public experience is a guided testnet/mock treasury-rebalance scenario. A user
chooses a rebalance amount, runs the agent preflight, sees the stale-oracle incident recalled
from memory, observes the action blocked, fixes the fixture condition, reruns the preflight,
reviews the proof obligations and passport, and submits the exact allowed transaction with a
wallet when the testnet flow is available. The site explains each outcome in plain language and
exposes the corresponding evidence.

## Capabilities and Constraints

- The MVP enforces only the `treasury-rebalance` action class.
- The MVP seeds the `stale-oracle-rebalance` incident and uses four deterministic proofs:
  state-anchor freshness, oracle freshness, exact simulation match, and post-state invariant.
- A valid passport is short-lived, EIP-712 typed, bound to the target, selector, calldata hash,
  chain, memory root, proof results, and nonce, and can be consumed only once.
- Missing, deleted, unreadable, or conflicting memory must result in human review or a block; the
  agent must not invent a strict passport.
- The current on-chain fixture is a purpose-built mock treasury/oracle demonstration. It is not
  a production vault, a Safe integration, or permission to move real funds.
- General DeFi actions, Safe integration, production oracles, and real-funds execution are
  explicitly future roadmap items, not MVP claims.
- The website must preserve a clear testnet/mock boundary and must label illustrative or fixture
  values honestly.

## Brand Commitments

- The product name is Referi.
- The current redesign follows the dark protocol-console direction in
  `/Users/scientivan/Programming/VeritasProtocol/Veritas-Uniswap/Veritas-UHI9` as the visual
  reference. The reference supplies visual grammar only; Referi keeps its own product facts,
  terminology, and identity.
- The interface should make the product's enforcement boundary and evidence legible before it
  makes the interface feel decorative.

## Evidence on Hand

- Approved product design: `docs/superpowers/specs/2026-09-09-execution-passport-design.md`.
- Canonical formats: `docs/execution-passport/canonical-formats.md`.
- Reproduction guide and runnable local proof: `docs/execution-passport/reproduction.md` and
  `make demo-passport`.
- Agent implementation: `agent/agent/execution_passport.py` and
  `agent/agent/passport_client.py`.
- Contract fixture: `contracts/src/PassportVerifier.sol`, `MockTreasury.sol`, and
  `MockOracle.sol`.
- The public website currently contains legacy Escrow Firewall pages that must be migrated or
  clearly separated from the current Execution Passport story; no UI may present those legacy
  pages as the current product direction.
- No production user study, customer quote, or real-funds deployment evidence is available.

## Product Principles

- Incident memory must change execution conditions, not merely decorate an explanation.
- Every permission to move value must be bound to the exact action and fresh evidence.
- Uncertainty is a review state, never a silent pass.
- The demo must be independently reproducible and honest about fixture boundaries.
- Explain the agent's decision in the same flow where the user experiences it.

## Accessibility & Inclusion

The web experience must not communicate status by color alone. Blocked, review-required, and
permitted states need text and/or icon labels, all controls must be keyboard reachable, and the
interactive execution flow must remain understandable without relying on animation.
