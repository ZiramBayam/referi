---
title: "Why an escrow referee needs memory, not just a single-job scorer"
date: 2026-09-08
project: REFERI (Sibyl hackathon, Base Sepolia)
repo: EvaluatorVault 0x5c6EE4586ACABcb6326069c229E58091B21ef384
---

# Why an escrow referee needs memory, not just a single-job scorer

ERC-8183 puts all its trust in one party: the evaluator. It is "fully trusted", its payment is
all-or-nothing (Completed = 100% to the provider, Rejected = 100% refund to the client, no partial
payment), and — this is the part we attack — it is **stateless**. Every job is judged as if the provider
were born today. A provider who submits half-finished work on job A meets the same evaluator on job B
with a clean record.

We built an evaluator that **remembers**, and whose memory other people can recompute from files rather
than simply trust.

## Today's decision is shaped by history, and there is a tx for it

The strongest evidence we have is not a diagram. It is two jobs on Base Sepolia with **byte-for-byte
identical deliverable text** (`keccak256(text)` = `0x246071b3…0a51` in `demo/deliverables/421.json` and
`422.json`), the same budget (250,000), the same evaluator — but different providers:

- **Job 421**, a provider with no incident history → check depth `sampling` (only the first 2 sections are
  read; `SAMPLING_SECTION_LIMIT = 2` in `agent/agent/checks/base.py:78`) → **passed**.
  `postVerdict` `0x02356b079fa3bfcd32e62d7e2bb61d3f4eb8b66d29fac578cd6318b2028a1467`.
- **Job 422**, a provider with two recorded incidents (jobs 418 and 419) → risk 2 → depth `full` → the
  `TODO` defect in the **third section** is read → **rejected**.
  `postVerdict` `0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830`.

Same text, different verdicts, and the only difference is history. That is a claim you can open in an
explorer yourself.

The honest limits, because without them the sentence above sounds better than reality: both providers are
**our own simulators**, the defect is **one word** caught by one regex
(`agent/agent/checks/format.py:47-50`), and there is no LLM anywhere in the evaluation path — what runs is
the deterministic `format`, `links`, and `chain` checks. Qualitative criteria are recorded as `unscored`
in every evidence bundle and are **never** treated as passed (`agent/agent/criteria.py:121-124`).

## Memory you cannot audit is just a confident guess

Memory that only lives inside our own process has no right to change a financial decision. So every
`postVerdict` announces a `memoryRoot` — a canonical hash over the memory state — and the contract emits
`MemoryRootUpdated`. The function that computes it is the **same single implementation** the export tool
uses (`agent/agent/memory_policy.py` → `memory_root_for_onchain`), its encoding is locked by a frozen
vector (`agent/tests/fixtures/memory_root_vector.json`), and there is a cross-language recomputation in
`agent/tools/memory_root_check.mjs`.

Two things must be said in the same breath, and we refuse to hide them:

1. **The anchor is circular.** The root proves "the agent hashed a file", not "that file is legitimate
   memory". On chain, `postVerdict` only rejects a **zero** root
   (`contracts/src/EvaluatorVault.sol:303`). What holds back a fabricated root sits on the agent side
   (`_require_derived_root`, `agent/agent/vault_client.py:1339`), not in the contract.
2. **Only one of the eight vault roots can be recomputed today**, namely job 418's — and that is
   precisely because the memory was still empty at the time. Memory is written **after** `postVerdict`, so
   every on-chain root is the state before that job wrote its result, and intermediate states are lost
   permanently once memory moves on. A per-job root log for backward audits is v2 (ADR-023).

What you **can** verify today is the root ↔ evidence-bundle binding: the bundle's filename = the on-chain
`reasonHash` = `keccak256` of the file's contents, and inside that file is a `memory_root` equal to the
announced one. All five bundles (418-422) satisfy it. Verdict, reason, and root are bound in one hash
announced **before** execution.

## Quarantine is separated from the decision path — and why that is unusual

The design question we get asked most: our memory has a `suspicion` entity (quarantine) that the
**decision path is forbidden to read**. Why store something you are not allowed to use?

It starts from a real constraint: Sibyl only has HOT/WARM/COLD/REFERENCE/ARCHIVE tiers — **there is no
FLAGGED tier**. So we built quarantine as a convention, not as a DB feature (ADR-002). And once quarantine
is only a convention, the only way it does not turn into "an accusation that quietly punishes" is to
forbid it from touching decisions at all. A suspicion may only change something after it is **promoted**:
at least 2 distinct jobs, with evidence from a deterministic check.

That ban is not a code comment. Three tests guard it, and all three are needed
(`agent/tests/test_memory_policy.py`):

- an **AST** scan over the decision path's source — because a category name can be disguised, a substring
  scanner is not enough;
- a **property** test: two twin DBs with identical write histories, one poisoned with quarantine data,
  then 240 random inputs (known and unknown addresses, odd and even budgets, up to `2**200 + 1`, all
  modes) must give **identical** output — this is what kills mutants that only trigger on specific inputs;
- a **spy client** that inspects the reads that actually happen at runtime, so the shape of the call does
  not matter.

That test has its own negative control (the poisoned DB really does contain ≥ 13 quarantine rows), so its
green is not a false green.

## What is not there, stated up front

The incentive is not fixed: `evaluatorFeeBP` = 5% and the fee is only paid out on `Completed`, so this
referee is still paid only when it passes work — exactly the bias we criticise. The evaluator stakes
nothing (`MIN_BOND` = 0), and `challenge`/`resolve` are stubs, so that 120-second window is pure latency:
a wrong verdict cannot be undone by anyone. All of it is written out in `docs/limitations.md` and
summarised in the README's "Limitations & trust assumptions" section.

The repo, the contract, and all its transactions are public — and since 8 Sep the contract is **verified
on Sourcify with `exact_match`** (creation and runtime), verified from source at commit `8d3e596`, not
from HEAD, which already differs from the on-chain bytecode. The practical effect for you: on Blockscout
Base Sepolia the vault's events appear under their own names — `MemoryRootUpdated`, `VerdictPosted`,
`Finalized` — instead of raw topics.

Next post: what broke while building it.
