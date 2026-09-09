# Idea Comparison Brief — Escrow Firewall vs Execution Passport

## Mandatory instruction to the reviewing AI agent

Act as an independent product strategist and Sibyl Labs Hackathon idea reviewer. Compare the two ideas below **only as product concepts and proposed MVP designs**.

Do NOT inspect, mention, reward, or penalize:

- repository implementation status;
- test coverage, contracts, deployments, demo videos, README quality, commit history, or UI;
- whether either idea is currently runnable.

This is not a current-build audit. It is a decision memo for choosing which idea has the stronger problem framing, niche, memory role, originality, and potential against the official hackathon criteria **if each idea were built exactly as described**.

You MUST:

1. Read the official rules: <https://hack.sibyllabs.org/rules>.
2. Treat this document and the linked product/design documents as primary evidence of the ideas.
3. Separate factual claims about the official rules or existing primitives from your own inference about product quality.
4. Identify where each idea risks being reducible to an ordinary database, blockchain history, static policy, reputation score, transaction simulator, or generic checklist.
5. Use conditional potential scores/ranges, not an official current-project score.
6. Keep PMF at `0 / 10` unless independently supplied public validation exists. Do not assess partner multipliers in an idea comparison.
7. Make a clear recommendation. “Both are good” is not sufficient.

---

## Official evaluation context

According to the [Sibyl Labs Hackathon Rules](https://hack.sibyllabs.org/rules), a build first needs to pass a gate: Sibyl Memory must be load-bearing, demonstrated through fresh-session recall, critical-path memory reads/writes, and a deletion test. Gate-passing projects are scored on Memory (40), Innovation & originality (25), Technical execution (20), and Pitch & presentation (15). PMF can add up to 10 points only with publicly verifiable validation.

This comparison estimates **idea potential**, not whether either idea currently passes that gate.

---

## Idea A — Escrow Firewall

### One-sentence framing

Escrow Firewall remembers how prior agent work failed and uses that memory to make the acceptance terms of the next escrowed job stricter before funding.

### Core loop

```text
failure evidence → reusable failure pattern → countermeasure → safer next-job terms
```

### Target user and initial domain

A platform, developer, or agent paying another agent/provider for technical work whose output must be verifiable and reproducible—initially smart-contract audits, software implementation, or review.

### Example

A provider claims tests passed but supplies no reproducible artifact. The evaluator rejects the work and stores a `missing-reproducible-evidence` pattern. For a later similar job, even with another provider, the system proposes commit hash, test command, output, environment version, and a milestone gate before payment.

### Claimed role of memory

Sibyl stores semantic failure explanation, required evidence, countermeasure, and countermeasure outcome. A new session retrieves the pattern and changes future terms. Deleting memory returns generic terms or human review.

### Strength

The value proposition is easy to explain: avoid paying twice for the same class of bad delivery. The pre-funding terms change is more meaningful than a retrospective provider score.

### Conceptual risks

- The initial task categories are broad and crowded with escrow, reputation, agent-evaluation, and verification products.
- A reviewer may see it as a sophisticated checklist generator if the failure pattern does not materially alter settlement or enforcement.
- Public chain/ACP history can reconstruct parts of provider history, so the differentiation must rest on semantic failure knowledge and cross-provider countermeasures.
- “Better terms before payment” may feel operationally useful but insufficiently surprising without a sharp vertical.

### Source design

- `docs/superpowers/specs/2026-09-09-escrow-firewall-design.md`

---

## Idea B — Execution Passport

### One-sentence framing

Execution Passport turns a remembered DeFi operational incident into a transaction-specific proof bundle required before a high-stakes agent action may execute.

### Core loop

```text
deterministic incident evidence → Control Hypothesis in Sibyl
→ deterministic proof obligations → one-time Execution Passport
→ verifier permits/rejects exact action → outcome calibration
```

### Target user and initial domain

A DeFi treasury/operator agent performing one high-stakes action class: `treasury-rebalance` against a mock treasury in the MVP.

### Example

An earlier rebalance was unsafe because oracle data was stale. Sibyl stores a Control Hypothesis: future rebalances in scope require fresh oracle data, an exact-action simulation, and a safe post-rebalance reserve invariant. A later agent/executor cannot execute the same class of rebalance without a short-lived passport bound to that exact target, calldata, chain, state anchor, expiry, nonce, hypothesis IDs, and memory root.

### Claimed role of memory

Sibyl stores the causal operational lesson—not merely a transaction outcome—and selects proof obligations for a later similar action, including for a different executor. Deleting memory removes the incident-conditioned policy and requires bootstrap human review rather than allowing a strict passport to be invented or reused.

### Relationship to existing primitives

Safe Guards can check and block transactions before/after execution, but Safe warns that a faulty guard can cause denial of service. [Safe Guards](https://docs.safe.global/advanced/smart-account-guards)

OpenZeppelin Timelock/AccessManager handles authorization, role delays, scheduling, and cancellation. It does not itself encode the causal lesson from a specific operational incident. [OpenZeppelin AccessManager](https://docs.openzeppelin.com/contracts/5.x/access-control)

Transaction simulators can model a transaction or bundle against chain state, but simulation by itself does not select incident-conditioned requirements for a later action. [Tenderly SDK](https://github.com/Tenderly/tenderly-sdk)

EIP-712 supports typed, domain-separated signing of the passport, but not the selection/calibration of its obligations. [EIP-712](https://eips.ethereum.org/EIPS/eip-712)

### Strength

The product has a sharp niche: repeated operational failure before a treasury action moves value. It turns memory into an enforcement-relevant condition, rather than a recommendation or reputation signal. The narrow MVP can produce an unambiguous “without the right memory-derived passport, this exact action cannot execute” moment.

### Conceptual risks

- The product must not overclaim that a simulation, oracle freshness, or passport makes DeFi safe.
- The verifier/policy-signing model introduces trusted components and potential liveness/denial-of-service concerns.
- Treasury rebalance is intentionally only an MVP action class; the product must articulate an honest multi-action roadmap without claiming broad coverage.
- If Control Hypotheses become permanently hardcoded obligations, the memory component becomes decorative.

### Source design

- `docs/superpowers/specs/2026-09-09-execution-passport-design.md`
- `docs/research/2026-09-09-execution-passport-control-plane.md`

---

## Comparison dimensions

Evaluate each dimension using only the idea descriptions above and independent market/technical research.

| Dimension | Escrow Firewall | Execution Passport |
|---|---|---|
| Root problem | Repeated payment for similar poor agent deliverables. | Repeated operational failure before high-value DeFi actions move value. |
| Unit protected | Escrowed job/payment. | Exact DeFi action and its state-dependent execution. |
| Memory output | Safer acceptance terms/evidence requirements. | Action-bound proof obligations and passport issuance policy. |
| Enforcement moment | Before escrow funding; may depend on client approval. | Immediately before execution; verifier may reject exact action. |
| Initial niche | Technical agent work, broadly defined. | Treasury rebalance, deliberately narrow. |
| Core counterfactual | “Would we have paid under generic terms?” | “Would this exact action execute without incident-conditioned proof?” |
| Main risk | Seems like generic reputation/checklist/escrow enhancement. | Security/liveness complexity and limited MVP scope. |

---

## Required review output

Use this exact format.

```md
# Escrow Firewall vs Execution Passport — Concept Comparison

## Review mode
- IDEA ONLY. No implementation/codebase evidence assessed.
- Official rubric source:

## Factual constraints from the rules and existing primitives
| Claim | Source | Fact / inference |
|---|---|---|

## Comparative assessment
| Dimension | Escrow Firewall | Execution Passport | Winner | Reason |
|---|---|---|---|---|
| Severity and clarity of root problem | | | | |
| Niche sharpness | | | | |
| Why persistent memory is necessary | | | | |
| Difficulty of replacing memory with chain history/database/static policy | | | | |
| Novelty/originality | | | | |
| User value if the MVP works | | | | |
| Credibility of a 10-day hackathon MVP | | | | |
| Technical/security risk | | | | |
| Demo clarity and “wow” moment | | | | |

## Conditional hackathon-potential score
These are potential scores if each MVP is implemented and demonstrated exactly as described; they are not current official scores.

| Criterion | Max | Escrow Firewall | Execution Passport | Reason and assumptions |
|---|---:|---:|---:|---|
| Memory is load-bearing | 40 | | | |
| Innovation & originality | 25 | | | |
| Technical execution potential | 20 | | | |
| Pitch & presentation potential | 15 | | | |
| Conditional subtotal | 100 | | | |

## PMF and multiplier
- Actual PMF score for both: 0 / 10 unless public validation is independently supplied.
- PMF potential for each:
- Partner multipliers: not assessed in idea mode.

## Recommendation
- Choose: Escrow Firewall / Execution Passport / hybrid only if the hybrid has one coherent core loop.
- Decision rationale:
- What should be explicitly dropped to keep the chosen idea focused:

## Strongest objection to the recommended idea

## The one proof the final demo must show

## Claims that would be misleading or unsupported
```

---

## Reference sources

1. Sibyl Labs. [Hackathon Rules](https://hack.sibyllabs.org/rules). Accessed 2026-09-09.
2. Safe. [Safe Guards](https://docs.safe.global/advanced/smart-account-guards). Accessed 2026-09-09.
3. OpenZeppelin. [AccessManager and access control](https://docs.openzeppelin.com/contracts/5.x/access-control). Accessed 2026-09-09.
4. Tenderly. [Tenderly SDK](https://github.com/Tenderly/tenderly-sdk). Accessed 2026-09-09.
5. Ethereum Improvement Proposals. [EIP-712](https://eips.ethereum.org/EIPS/eip-712). Accessed 2026-09-09.
