# Escrow Firewall — Development Design Guide

Status: approved concept and MVP design  
Date: 2026-09-09  
Scope: hackathon-focused product evolution of The Evaluator

## 1. Product thesis

Escrow Firewall is a memory-powered control plane for agent commerce. It remembers how previous work failed, then uses those failure patterns to improve the acceptance criteria, evidence requirements, milestones, and evaluation policy of the next job before escrow funding.

The product is not primarily a provider reputation score. Its central loop is:

```text
failure evidence → reusable failure pattern → countermeasure → safer next-job terms
```

The key product claim is that memory changes the contract of future work, not only the verdict of past work.

## 2. Problem and target user

Target user: a platform, developer, or agent that pays another agent/provider for technical work where the result must be verifiable and reproducible.

Initial task domain:

- smart-contract audit;
- software implementation or review.

The current generic evaluator catches defects after delivery and adjusts provider risk. Escrow Firewall moves part of the protection before funding by learning which terms and evidence requirements previously allowed a failure.

## 3. Why Sibyl Memory is load-bearing

The public chain can provide provider, budget, lifecycle status, completion/rejection, and hashes. It does not directly provide the semantic failure explanation, evidence excerpts, missing proof, contextual task type, or the effectiveness of a countermeasure.

Sibyl must persist the evolving relationship:

```text
failure → pattern → countermeasure → outcome
```

The deletion test must produce a different product behavior:

- with memory, a fresh session retrieves a relevant failure pattern and proposes stricter terms;
- without memory, the session cannot retrieve the pattern and falls back to generic terms or requires human approval.

This is stronger than storing a provider's reject count. A different provider can trigger the same safeguard because the system remembers the failure mechanism, not only the wallet address.

Implementation note: Sibyl is the required memory layer for the hackathon, but the lasting moat is the failure-pattern data model and the closed feedback loop. A generic database could technically imitate storage; the product must therefore make retrieval, provenance, policy synthesis, and outcome updates inseparable from the job flow.

## 4. Core memory model

Each failure pattern is a structured reference, not an opaque text note.

```text
pattern_id
task_category
trigger_signature
failure_description
evidence_required
recommended_countermeasure
affected_scope
confidence
observed_jobs
successful_mitigations
failed_mitigations
last_observed_at
status
```

Example:

```yaml
pattern_id: missing-reproducible-evidence
task_category: smart-contract-audit
trigger_signature: output claims tests passed but provides no reproducible artifact
failure_description: evaluator cannot independently rerun the claimed test result
evidence_required:
  - commit hash
  - test command
  - test output
  - environment version
recommended_countermeasure: require reproducible evidence before milestone release
confidence: 0.82
observed_jobs: [418]
successful_mitigations: 0
failed_mitigations: 0
status: active
```

The MVP starts with three deterministic patterns:

- `missing-reproducible-evidence`;
- `incomplete-deliverable`;
- `requirement-ambiguity`.

Confidence must not be treated as truth. A low-confidence pattern may produce a recommendation, but it must not automatically change terms without the configured policy allowing it.

## 5. System components

### PatternExtractor

Reads deterministic evaluation evidence and creates or updates a failure pattern. It must include the job ID and evidence references. It must not infer a pattern from a generic reject alone.

### PatternRetriever

Finds relevant patterns using task category, requirements, evidence type, and failure signature. Retrieval must work across providers; provider identity is context, not the primary key.

### PolicySynthesizer

Converts retrieved patterns into a proposed policy:

- acceptance criteria;
- required evidence;
- milestone structure;
- budget/cap recommendation;
- evaluator depth;
- human-review requirement.

For MVP, synthesis is template-driven and deterministic. LLM scoring is out of scope.

### TermsCommitter

Creates canonical terms, computes a terms hash, and makes the commitment before funding. Terms must not silently change after funding.

### OutcomeUpdater

After the next job, records whether the countermeasure worked, failed, or was inconclusive. It updates confidence and mitigation counters.

### MemoryIntegrityLayer

Produces the memory root for the state read by the decision path. A corrupt, unreadable, or unavailable memory state must fail closed or require human approval; it must never result in invented terms.

## 6. Data flow

```text
Job delivered
    ↓
Deterministic evaluator produces evidence
    ↓
PatternExtractor records failure pattern
    ↓
Sibyl stores pattern and proposed countermeasure
    ↓
Fresh session receives a similar job
    ↓
PatternRetriever finds relevant memory
    ↓
PolicySynthesizer proposes safer terms
    ↓
Client approves terms
    ↓
TermsCommitter hashes terms before funding
    ↓
Provider delivers against committed terms
    ↓
Evaluator produces verdict
    ↓
OutcomeUpdater evaluates countermeasure effectiveness
```

## 7. ACP and blockchain responsibilities

Blockchain responsibilities:

- hold the ACP escrow lifecycle;
- identify client, provider, and evaluator;
- record budget, status, and deliverable hash;
- commit the terms hash and verdict/evidence hash;
- provide an auditable settlement trail.

Sibyl responsibilities:

- store semantic failure patterns;
- preserve evidence references and context;
- retrieve patterns in a genuinely fresh process;
- drive the pre-funding policy proposal;
- track whether a countermeasure worked.

Local evidence responsibilities:

- preserve the deliverable text and reproducible proof needed by deterministic checks;
- provide the preimage for hashes committed on-chain;
- remain separate from the memory decision state.

## 8. User and job flow

### First job

The client starts with generic terms. A provider claims tests passed but does not provide a reproducible artifact. The evaluator rejects the job and records `missing-reproducible-evidence`.

### Fresh-session second job

The agent restarts as a new process. A different provider proposes similar technical work. The agent retrieves the pattern and proposes commit hash, test command, output, and environment evidence, plus a milestone gate before payment release.

The client reviews and accepts the proposed terms. The final terms are hashed before funding.

### Deletion control

With Sibyl memory deleted, the same class of job receives generic terms. The UI and demo must show this difference directly.

## 9. Safety and failure handling

- Unreadable memory: stop or require human approval; do not fabricate a policy.
- Low-confidence pattern: recommend only unless explicit policy permits automatic enforcement.
- Conflicting patterns: prefer the stricter evidence requirement and surface the conflict.
- False positive: lower confidence and record the reason.
- Unproven countermeasure: mark `pending`; do not present it as effective.
- Terms changed after funding: reject the mutation or create a new job.
- Evidence/hash mismatch: refuse verdict and finalization.
- Automatic blacklist: not allowed in MVP.

The system should distinguish `reject`, `needs-review`, and `insufficient-evidence` internally even if ACP settlement remains complete/reject.

## 10. MVP scope

In scope:

- one or two technical task categories;
- three deterministic failure patterns;
- structured Sibyl storage and retrieval;
- deterministic policy templates;
- terms preview;
- pre-funding terms hash;
- fresh-session recall;
- deletion test;
- evidence bundle and memory-root binding;
- UI comparison of generic versus memory-informed terms.

Out of scope:

- global reputation marketplace;
- multi-chain indexing;
- machine-learning model training;
- automatic blacklist;
- decentralized jury;
- insurance;
- full autonomous watcher;
- qualitative LLM scoring;
- new dispute-resolution protocol.

## 11. Tests and acceptance criteria

### Memory tests

- pattern survives process restart;
- relevant pattern is retrieved for a different provider;
- irrelevant pattern is not applied;
- confidence and mitigation counters update correctly;
- malformed or missing memory fails closed;
- deletion removes the safeguard behavior.

### Policy tests

- each pattern generates the expected evidence requirements;
- low confidence produces recommendation-only behavior;
- client approval is required when configured;
- terms are canonical and hash-stable;
- terms cannot change after funding.

### Integration tests

- first job creates a pattern;
- fresh second job changes terms before funding;
- second job outcome updates the pattern;
- on-chain terms hash matches the displayed terms;
- verdict evidence matches its committed hash;
- deletion control produces generic terms.

### Demo acceptance

The recording must show, in one understandable sequence:

1. a failure and its evidence;
2. the persisted pattern;
3. a fresh process recalling it;
4. changed terms before escrow funding;
5. a successful or rejected outcome;
6. deletion causing the safeguard to disappear.

## 12. Hackathon evaluation target

The official rubric is Memory 40, Innovation 25, Technical Execution 20, Pitch 15, plus a PMF bonus up to 10. PMF is intentionally not pursued for this scope.

Evidence-based target after implementation:

| Criterion | Target |
|---|---:|
| Memory load-bearing | 37/40 |
| Innovation & originality | 23–24/25 |
| Technical execution | 15–17/20 |
| Pitch & presentation | 13–15/15 |
| PMF bonus | 0/10 |
| Total | 88–96/110 |

The target assumes the demo shows a real pre-funding terms change, not merely a different risk label. Partner multipliers are separate and depend on the judge verifying real Base and Virtuals usage.

## 13. Product language

Use:

- “memory-powered escrow firewall”;
- “failure-pattern memory”;
- “pre-funding safeguards”;
- “the agent remembers how work failed and changes the next contract.”

Avoid:

- “generic reputation score”;
- “AI judges everything”;
- “fully autonomous”;
- “Sibyl is impossible to replace.”

The honest claim is that Sibyl is load-bearing in this architecture because the persisted, structured failure-policy loop is part of the product’s critical path. The technology can be replaced in theory; the product must prove that replacing it removes the accumulated operational intelligence and changes the outcome.
