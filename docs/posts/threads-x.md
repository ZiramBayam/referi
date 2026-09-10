---
title: "X (Twitter) threads — paste-ready"
date: 2026-09-11
project: REFERI (Sibyl hackathon, Base Sepolia)
repo: https://github.com/ZiramBayam/referi
source: docs/posts/03-2026-09-10-*.md and docs/posts/04-2026-09-10-*.md
---

# X threads

Two threads, condensed from the two most recent build-in-public posts. They follow the current framing
in `README.md`: **proof before permission, one memory system with two enforcement gates.** Every number,
address, and output line below also appears in `README.md`, `deployments/passport-84532.json`,
`deployments/84532.json`, or `docs/limitations.md` — nothing new is claimed here. Character counts
(including the `n/ ` prefix) are at the bottom; the limit is 280.

The earlier threads, written from the escrow-referee framing, are superseded by these; the reasoning for
the change is thread 1.

## Thread 1 — changing direction on day nine

Source: `docs/posts/03-2026-09-10-kenapa-kami-mengganti-arah-produk.md`

```text
1/ We changed the product on day nine. The escrow referee still runs, still deployed, five jobs really landed on Base Sepolia. We stopped building it because memory only changed how carefully we graded a document. Nobody's money moved because of it.

2/ The uncomfortable question, in one sentence: is memory doing work, or decorating a decision that would have been fine anyway? So we moved memory to where being wrong is expensive: the transaction boundary.

3/ Execution Passport takes one incident — an agent moved value on an oracle reading two minutes stale — stores it in Sibyl as a Control Hypothesis, and compiles it into four proof obligations that must hold before that class of action moves value again.

4/ The four: state-anchor-fresh, oracle-freshness, simulation-match, post-state-invariant. Only if all four hold does the agent sign a 60-second EIP-712 passport bound to the exact target, selector, calldata hash, chain, memory root and nonce. Accepted once.

5/ The test we could not run before: delete the hypothesis and the same action returns to human review. Not a permissive default, not a cached answer, a stop. There is no fallback threshold in the code — the run prints thresholds_from_memory=oracle=60 reserve=250000.

6/ Two more lines from the same run: fresh_process_recall=stale-oracle-rebalance/v1 executor_identity=child-process, a new process recalls it. invalid_passport_rejected=calldata-mismatch, one changed byte and the passport is void. Whole run: 4.62 s.

7/ The bill for changing direction: our only on-chain evidence belonged to the product we had just left. Fixed now. PassportVerifier, MockTreasury and MockOracle are on Base Sepolia at block 46629087, all three verified on Sourcify, for 0.0000088 ETH.

8/ The other cost: we had to drop the impressive version. The passport only reaches failures you can write down as a checkable precondition — oracle staleness, a reserve floor, an exact simulation match. Not bad judgement, not a novel exploit, not mispriced risk.

9/ Enforced today: one action class, treasury-rebalance, against a mock treasury and a mock oracle on testnet. Safe integration and production oracles are roadmap, so they are not in the pitch. Run it on local Anvil: make demo-passport. https://github.com/ZiramBayam/referi
```

## Thread 2 — one memory, two gates

Source: `docs/posts/04-2026-09-10-satu-memori-dua-gerbang.md`

```text
1/ We spent a day calling this project a pivot. That was wrong, and the correction is a one-line command. Referi is one memory system with two enforcement gates: one on Virtuals ACP, one on Base. They were never two memories.

2/ Gate 1, on Virtuals ACP: an evaluator reads a provider's history out of Sibyl and sets check depth and budget cap from it. Jobs 421 and 422 carry byte-for-byte identical deliverables. 421 passed, 422 was rejected. Memory was the only difference.

3/ Gate 2, on Base: the Execution Passport reads an incident out of the same Sibyl store and turns it into four proof obligations a treasury action must satisfy before it moves value. Different protocols, different failure modes, different contracts.

4/ The passport gate stores its Control Hypothesis at pattern:passport.control-hypothesis.stale-oracle-rebalance.v1. The preimage of the on-chain memory root covers every provider entity and every reference:pattern:* entry. Read those two together.

5/ The consequence: the memory root that EvaluatorVault.postVerdict announces on the ACP gate already commits to the Base gate's policy. Change the passport's hypothesis and the root the evaluator announces changes. We did not build that link this week.

6/ It has been true since the passport gate was written, because both gates use the same memory primitives. We just never showed it. Now you can check: make dual-gate prints the shared root and root_covers_both_gates=True. No network, no key.

7/ What we are not claiming: the passport does not send transactions to ACP, it guards treasury actions, not escrow jobs. And the ACP gate cannot post new verdicts: we rotated the agent wallet and EvaluatorVault.agent() is immutable at the old address.

8/ Verify gate 1 without a key: make virtuals-evidence reads the real ACP contract on Base Sepolia and confirms all five jobs against the file the site serves. Two surfaces, one memory, one root on chain that binds both. https://github.com/ZiramBayam/referi
```

## Character count

Counted including the `n/ ` prefix; the em dash `—` counts as one character. Counted by hand, segment by
segment.

| Tweet | Thread 1 | Thread 2 |
|---|---|---|
| 1/ | 249 | 225 |
| 2/ | 208 | 248 |
| 3/ | 254 | 250 |
| 4/ | 258 | 248 |
| 5/ | 267 | 253 |
| 6/ | 249 | 242 |
| 7/ | 251 | 252 |
| 8/ | 263 | 257 |
| 9/ | 273 | — |
| **longest** | **273** | **257** |

Thread 1 has nine tweets, thread 2 has eight. Zero emoji, zero hashtags, repo link in the last tweet of
each thread.

## Claims deliberately left out

Not written here because the repo does not support them:

- That the web app enforces anything on chain. It never sends a transaction; the execution-room incident
  is seeded (`_seeded_memory`, `web-stale-oracle-001`) and its anchor is synthetic. Both threads point at
  the terminal path `make demo-passport` instead.
- That the passport prevents bad judgement, a novel exploit, or mispriced risk. It reaches only failures
  expressible as a checkable precondition, and thread 1 tweet 8 says so.
- That `MockTreasury` holds real funds or that this is a Safe integration or a production vault
  (`deployments/passport-84532.json` → `boundary`).
- That the ACP gate can post new verdicts today (`EvaluatorVault.agent()` is immutable at the rotated-away
  address; the five jobs are history).
- That the memory root proves the memory file is legitimate — the anchor is circular
  (`docs/limitations.md` item 16).
- Any per-obligation coverage number, severity score, or performance figure beyond the measured 4.62 s
  wall time of `make demo-passport`.
