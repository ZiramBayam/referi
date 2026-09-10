# Execution Passport — Concept-Stage Hackathon Assessment

Reviewed HEAD: `7f77929c5759d1d12cc9e982173cdc1342189d41` (`docs: make passport review concept-focused`).
Review date: 2026-09-09. Brief followed: `docs/agent-evaluations/execution-passport-hackathon-review.md`.
Objects under review: `docs/superpowers/specs/2026-09-09-execution-passport-design.md` (cited below as `design.md`) and `docs/research/2026-09-09-execution-passport-control-plane.md` (cited as `research.md`).
Rules source: <https://hack.sibyllabs.org/rules>, fetched during this review. Submission deadline stated on that page: September 10, 23:59 UTC.

A separate build-state review of the same product exists at `docs/agent-evaluations/execution-passport-hackathon-assessment.md`. It is not superseded by this document; it answers a different question (what exists at HEAD), and this document answers only what the idea could earn if built as specified.

## Verdict
- Review mode: IDEA ONLY — implementation intentionally not assessed
- Official gate status: NOT YET ASSESSABLE (do not write PASS or FAIL)
- Concept verdict: **strong** (not exceptional)
- One-sentence reason: The design turns a remembered incident into a machine-checkable, transaction-bound execution condition with a defined fail-closed deletion behavior, which is the exact shape the gate rewards, but the MVP carries only one hypothesis with a fixed obligation set, so a judge can reasonably ask whether a config file would produce the same behavior.

## Evidence inspected
| Claim about the idea | Design/research/external source | Fact or inference | Confidence |
|---|---|---|---|
| Judging is gated: deletion test, cold-start recall in one unedited segment with timestamp/commit, README pointers findable in under two minutes | <https://hack.sibyllabs.org/rules> (fetched 2026-09-09) | Fact | High |
| Rubric is 40 / 25 / 20 / 15; PMF up to +10 only with a five-minute-verifiable public artifact; multiplier +15% first stack, +10% second, cap ×1.25, must be exercised in the demo | Same rules page | Fact | High |
| "Memory used trivially passes the gate but scores at the floor and will not place" | Same rules page (quoted by WebFetch) | Fact | High |
| The MVP enforces exactly one action class (`treasury-rebalance`) against a mock treasury | `design.md:13-24` | Fact (design statement) | High |
| Memory stores a structured Control Hypothesis, not a text note | `design.md:52-66`, `research.md:36-54` | Fact (design statement) | High |
| Deletion must produce a bootstrap policy requiring human approval; no fabricated strict passport | `design.md:159-163`, `research.md:99` | Fact (design statement) | High |
| Passport binds chain, target, selector, calldata hash, state anchor, expiry, nonce, signer; EIP-712 typed | `design.md:100-123`, `research.md:60-71` | Fact (design statement) | High |
| EIP-712 gives typed, domain-separated hashing with `chainId` and `verifyingContract`, and explicitly does not include replay protection | <https://eips.ethereum.org/EIPS/eip-712> ("It does not include replay protection") | Fact | High |
| The design correctly assigns nonce and expiry to the verifier rather than to EIP-712 | `design.md:121`, `research.md:71` | Fact (design statement); consistent with the EIP | High |
| A Safe Guard can block execution and a broken Guard can cause denial of service | <https://docs.safe.global/advanced/smart-account-guards> ("a broken Guard can cause a denial of service for a Safe") | Fact | High |
| Choosing a narrow verifier over a general Safe Guard is the safer hackathon scope | `research.md:117-135`; Safe warning above | Inference from the Safe warning | High |
| Chainlink feeds expose `updatedAt` for freshness checks; `latestAnswer` gives no timestamp | <https://docs.chain.link/data-feeds/api-reference> | Fact | High |
| Oracle staleness and misconfiguration cause real losses without any oracle hack | Moonwell cbETH, Feb 2026, ~$1.78M bad debt: <https://forum.moonwell.fi/t/mip-x43-cbeth-oracle-incident-summary/2068>, <https://www.theblock.co/post/390302/defi-lending-protocol-moonwell-hit-with-1-8-million-bad-debt-after-oracle-misconfiguration>. Aave CAPO wstETH, Mar 2026, ~$26–27M liquidations from a stale `snapshotTimestamp`: <https://cryptonews.com/news/aave-oracle-glitch-wsteth-liquidations-capo/>, <https://crypto-economy.com/aave-post-mortem-details-wsteth-liquidation-wave/> | Fact (secondary reporting; Moonwell forum is primary) | Medium-High |
| Those incidents match the "stale assumption absent from the transaction record" problem statement | `research.md:30-34` vs the incidents above | Inference | Medium |
| Static policy engines (Fireblocks, Turnkey, Safe/Zodiac) already enforce allowlists, spend limits, time windows, and pre-sign simulation | <https://www.fireblocks.com/platforms/security>, <https://fast.io/resources/top-crypto-wallets-autonomous-agents/> | Fact (vendor and secondary sources) | Medium |
| None of those primitives derive a new obligation set from a prior incident or calibrate it from outcomes | `research.md:18-26`; absence of such a feature in the sources above | Inference (absence of evidence, not a survey of every vendor) | Medium |
| The MVP obligation set is fixed to four items, and `rollback-route` is deferred | `design.md:70-82, 90-96` | Fact (design statement) | High |
| The verifier contract does not read Sibyl, simulate, or query an oracle; it trusts the policy signer | `design.md:123` | Fact (design statement) | High |
| The two documents disagree on which obligations the demo hypothesis requires (four in design, two in research demo step 3) | `design.md:74-78` vs `research.md:145` | Fact | High |

## Conditional gate analysis: would memory be load-bearing if built as designed?
- Intended Sibyl write: A deterministic `stale-oracle-rebalance` incident creates one versioned Control Hypothesis with predicates, obligations, enforcement mode, counterfactual, and outcome counters (`design.md:46-80`). A generic reject creates nothing (`design.md:48`), which is a good guard against notepad-style writes.
- Intended fresh-process read: A restarted agent with a different executor identity reads the active hypothesis for the action class before deciding obligations (`design.md:20, 149-151, 161`). This is cross-identity recall, not reputation, which matches what the brief asks for.
- Intended deletion behavior: With memory gone, the agent falls back to a bootstrap policy that requires human approval and cannot issue the incident-conditioned passport (`design.md:159-163`). Fail-closed, not fail-open. [Inference] This satisfies the rules' deletion test in spirit, because the claimed core function (permitting a rebalance on proof) materially degrades.
- Risk that strict policy could be hardcoded/reconstructible: **Real and the main gate risk.** The MVP has exactly one hypothesis whose four obligations and thresholds (60-second oracle window, minimum reserve) also appear as literals in the spec (`design.md:92-95`). If the evaluator ships those thresholds as code constants and memory only toggles "strict on/off", a judge can argue the hypothesis is a boolean flag stored in Sibyl. `research.md:91-97` names the right test (memory must change selection, thresholds, enforcement mode, counterfactual, and later calibration), but the MVP as written exercises selection and enforcement mode only.
- Required implementation proof before a real gate decision: (1) thresholds, obligation list, and enforcement mode read from the stored hypothesis at runtime, with no code-level default that reproduces them; (2) a fresh-process run whose log shows the Sibyl read before obligation selection, on screen with a commit hash, in one unedited segment; (3) a deletion run in the same recording showing bootstrap review and a refused passport; (4) a README section pointing to the write, read, and fallback by file and line; (5) at least one outcome write (`worked`/`failed`) that changes a later run's behavior, otherwise the calibration loop is a claim without a demo.

## Conditional idea score
Score the potential of the idea if the specified MVP is fully implemented and demonstrated. This is not a score for the current repository.

| Criterion | Maximum | Conditional potential score or range | Evidence | Assumption required to realize it |
|---|---:|---:|---|---|
| Memory is load-bearing | 40 | 28–34 | Write, cross-identity read, and fail-closed deletion are all specified (`design.md:159-163`); memory selects obligations and enforcement mode (`research.md:87-99`). Upper bound withheld because only one hypothesis exists and thresholds are spec literals. | Thresholds and obligation list come only from the stored hypothesis; the outcome-calibration write visibly changes a later decision. Without both, expect the low end or below. |
| Innovation & originality | 25 | 16–20 | Incident → hypothesis → typed obligations → action-bound passport → outcome calibration is not what Fireblocks/Turnkey/Safe Guards do (they enforce static policy). Reputation-free framing (`design.md:7-9`) is a clear differentiator. Withheld: judges may read it as "policy-as-code with a database", and the loop's novelty is only visible if calibration is demonstrated. | The demo shows the causal lesson changing policy, not just a stored rule being applied. |
| Technical execution | 20 | 13–16 | Plan is narrow, testable, and names contract and agent tests (`design.md:175-192`). Correct handling of EIP-712 limits (nonce and expiry on-chain). `unverifiable` never passes (`design.md:86-88`). Withheld: the on-chain gate proves only that the trusted signer signed; `memory_root` and `obligation_results_hash` are bound but never checked against anything; state-anchor checks via `blockhash()` only work for the last 256 blocks and the spec does not say how the anchor age is verified; `rollback-route` deferred; the two documents disagree on the demo obligation set. | The verifier is delivered with the listed negative tests passing, and the spec's inconsistencies are resolved before build. |
| Pitch & presentation | 15 | 10–12 | One-sentence claim and judge-facing claim are crisp (`design.md:203-205`); demo sequence is six steps with an explicit deletion scene (`design.md:194-201`). Withheld: the pitch has to explain why a signed policy assertion is stronger than a static allowlist, and the current repo's public face is a different product (Escrow Firewall), which is a delivery gap but will shape judge perception. | A README bridge and a video that keeps the recall segment continuous. |
| Conditional subtotal | 100 | 67–82 (midpoint ≈ 74) | | |

Reasoning for the range rather than a point: the memory criterion alone swings 6 points on one implementation choice (where thresholds live), and innovation swings 4 on whether calibration is shown. Those are design-realization questions, not delivery questions, so the brief allows them to affect the conditional score.

## PMF bonus
- Actual score: 0 / 10
- Publicly verifiable evidence: None found in the two documents or the repository. No design partner, pilot, waitlist, or usage artifact for an incident-conditioned rebalance gate.
- PMF potential and what would validate it: [Inference] The pain is real and recent: Moonwell (Feb 2026) and Aave CAPO (Mar 2026) were operational misconfigurations and stale references, exactly the class the design targets, and both were followed by public postmortems that read like a Control Hypothesis in prose. That is evidence of the problem, not of demand for this product. Validation would be one treasury or risk team (a DAO risk steward, a Chaos Labs-style risk provider, or a Safe-using treasury) publicly agreeing to pilot the passport on a testnet rebalance, or a governance-forum thread requesting incident-derived execution checks.

## Partner multiplier
- Not assessed in idea mode.
- Base: would require the `PassportVerifier` and `MockTreasury` deployed on Base (Sepolia at minimum), plus one permitted rebalance executed through the verifier on-chain and shown in the demo. The existing `EvaluatorVault` deployment belongs to the Escrow product and would not count.
- Virtuals: the design does not involve ACP or a Virtuals agent. Claiming it would require the rebalance proposer or executor to be a registered Virtuals agent, or the passport issuance to be an ACP job, exercised in the demo. [Inference] Forcing this in would dilute the narrative; pursue only if it fits naturally.

## Conditional idea score summary
- Conditional rubric potential: 67–82 / 100 (midpoint ≈ 74)
- Actual PMF score today: 0 / 10
- Multiplier: not assessed
- This is not a current official score and must not be represented as one.

## Strongest aspect
The deletion story is designed as a product behavior, not a dashboard artifact. Removing memory does not break the demo or silently pass; it visibly demotes the system to a human-review bootstrap policy and makes the strict passport unissuable (`design.md:159-163`, `research.md:99`). Combined with cross-identity recall (a different executor inherits the lesson) and the explicit rule that `unverifiable` is never a pass, this is the shape of a load-bearing memory claim rather than a notepad.

## Three highest-risk concept weaknesses
1. **Single-hypothesis MVP makes "memory as a boolean" a fair objection.** One incident, one hypothesis, one fixed obligation set with thresholds written in the spec. If those literals also live in code, the deletion test still passes on paper but the 40-point criterion collapses toward the floor the rules warn about.
2. **The on-chain verifier proves signature, not proof.** The contract trusts a single policy signer and never checks `obligation_results_hash` or `memory_root` (`design.md:123`). Anyone holding the signer key can mint a passport with fabricated obligation results. The design is honest about this (`research.md:155`), but the pitch line "verifier permits/rejects execution" overstates what the chain actually enforces.
3. **Calibration is the novel part and is the least specified.** `OutcomeUpdater` records worked/failed/inconclusive (`design.md:141-142`), but nothing says what a `failed` outcome does to the next decision, how duplicates are prevented, or how `confidence_bps` is computed. Without that, the "learning loop" differentiator from static policy engines is asserted, not demonstrated.

## Design improvements most likely to improve conditional potential
1. **Make the hypothesis the sole source of thresholds and obligation lists, and show two hypotheses.** Add a second cheap incident (for example `reserve-breach-rebalance/v1` with a tighter `post-state-invariant` bound) so the demo shows memory changing *which* obligations and *what* thresholds apply, not just strict-on versus strict-off. Ship the evaluator with no default thresholds; bootstrap policy should be "review required, no obligations known".
2. **Specify calibration deterministically.** Define: outcome keyed by `(hypothesis_id, action digest)` so duplicates are no-ops; a `failed` outcome raises enforcement or tightens a window on the next read; `confidence_bps` as a stated function of counts. Demonstrate one outcome write changing one later decision on screen.
3. **Reconcile the two documents and tighten the verifier's claims.** Pick one demo obligation set (`design.md:74-78` vs `research.md:145`); state how anchor age is checked on-chain (block number delta rather than `blockhash()` beyond 256 blocks); and reword the judge-facing claim so "verifier" means "enforces binding, expiry, nonce, and signer" while obligation evaluation is explicitly the off-chain trusted evaluator.

## Delivery proof required before making implementation claims
- `PassportVerifier`, `MockTreasury`, `MockOracle` contracts with the negative tests in `design.md:177-182` passing (wrong target, calldata, signer, chain, expiry, reused nonce, direct bypass, disallowed selector).
- An agent module that writes a Control Hypothesis to Sibyl on deterministic incident evidence, reads it in a fresh process for a different executor, evaluates the four obligations with `satisfied | unsatisfied | unverifiable`, and issues an EIP-712 passport only when all blocking obligations are satisfied.
- A deletion run, in the same recording as the recall run, showing bootstrap review and no strict passport.
- README section naming the write, read, and fallback locations by file and line, findable in under two minutes.
- A continuous, unedited recall segment with an on-screen commit hash.
- At least one outcome write and a subsequent run whose decision reflects it.
- For Base multiplier only: verifier deployed on Base and one rebalance executed through it on-chain, shown in the demo.
- Resolution of the inconsistency between `design.md:74-78` and `research.md:145`.
- Deadline context: the rules page lists September 10, 23:59 UTC, roughly one day after this review. [Inference] The full MVP as specified is a multi-day build; scoping to the single-hypothesis path with the deletion control is the realistic target if the deadline holds.
