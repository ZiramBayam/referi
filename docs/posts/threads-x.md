---
title: "X (Twitter) threads — paste-ready"
date: 2026-09-09
project: The Evaluator (Sibyl hackathon, Base Sepolia)
repo: https://github.com/ZiramBayam/referi
source: docs/posts/01-2026-09-08-*.md and docs/posts/02-2026-09-08-*.md
---

# X threads

Two threads, condensed from the two build-in-public posts. Every number, address, and transaction below
also appears in `README.md`, `docs/evidence.md`, or `docs/limitations.md` — nothing new is claimed here.
Character counts (including the `n/` prefix) are listed at the bottom; the limit is 280.

## Thread 1 — why an escrow referee needs memory

Source: `docs/posts/01-2026-09-08-kenapa-wasit-escrow-butuh-memori.md`

```text
1/ ERC-8183 makes the escrow evaluator fully trusted — and stateless. Every job is judged as if the provider were born today. Cheat on job A, meet the same referee on job B with a clean record. We built a referee that remembers. Its memory is recomputable from files.

2/ The evidence isn't a diagram. Two jobs on Base Sepolia with byte-for-byte identical deliverable text (keccak256 = 0x246071b3…0a51), same budget 250,000, same evaluator, different providers. 421 passed. 422 was rejected. The only difference is history.

3/ Job 421's provider had no incidents → depth `sampling`, only the first 2 sections are read → passed. Job 422's provider had 2 recorded incidents → depth `full` → the TODO defect in the third section is read → rejected. postVerdict: 0xe95910d2…295830

4/ The honest limits in the same breath: both providers are our own simulators, the defect is one word caught by one regex, and there is no LLM anywhere in the evaluation path. Qualitative criteria are recorded as unscored and never counted as passed.

5/ Memory you cannot audit is just a confident guess. So every postVerdict announces a memoryRoot and the vault emits MemoryRootUpdated. The root function is the same single implementation the export tool uses, its encoding locked by a frozen test vector.

6/ And its limit, said out loud: the anchor is circular. The root proves the agent hashed a file, not that the file is legitimate memory — on chain only a ZERO root is rejected. Of eight vault roots, only job 418's can be recomputed today.

7/ Sibyl has no FLAGGED tier, so our quarantine is a convention, not a DB feature — and the decision path is forbidden to read it. A suspicion changes nothing until it is promoted: at least 2 distinct jobs, with evidence from a deterministic check.

8/ That ban is not a code comment. Three tests hold it: an AST scan over the decision path's source, a property test where two twin DBs (one poisoned with quarantine rows) must give identical output on 240 random inputs, and a spy client on runtime reads.

9/ What is NOT fixed: evaluatorFeeBP is 500 (5%) and the fee is only paid on Completed, so this referee is still paid only when it passes work. MIN_BOND is 0. challenge/resolve are stubs. Vault 0x5c6EE45…f384 on Base Sepolia. https://github.com/ZiramBayam/referi
```

## Thread 2 — what broke while building it

Source: `docs/posts/02-2026-09-08-apa-yang-patah-saat-membangunnya.md`

```text
1/ 2 days before the submission deadline, the honest list: four things that broke while building our ERC-8183 evaluator, who found them, and what we did. Starting with the one where our own destructive test was rigged to win.

2/ The first version ran only the variant guaranteed to look good: fresh vault, empty memory, so a job that was REJECTED with memory now passes at the same budget. But delete memory.db on a live vault (non-zero on-chain root) and you get safe mode instead.

3/ `make demo` now runs BOTH variants, and variant B runs against the frozen Sepolia vault, so the non-zero root is real state. It aborts the whole run if the safe-mode evidence is missing, if any tx is sent, or if the agent wallet's nonce moves.

4/ Two things we will not smooth over. In variant A the mode the agent reports is `normal`, not naive mode; the degradation shows in depth=sampling and cap=NO CAP. And the demo now needs internet, so without network it does not finish. Recorded as a limitation.

5/ Second break: our static guard over the memory-root path only saw import statements. A module fetched via importlib, __import__ or sys.modules, or a rebinding as small as `alt = mp`, walked straight past it. Six bypasses, zero red tests.

6/ An adversarial review found it, not us. The scanner now recognises modules obtained without an import statement and tracks aliases; the six forms are tests that must go red. Lesson: a guard that never goes red guards nothing.

7/ Third break: we froze the vault before it was finished. sweepToken exists in the source but is NOT in the deployed bytecode, so 62,500 token units of fees are permanently stranded. arbiter() == agent() there, permanently — the contract is immutable.

8/ We froze it anyway because all our on-chain evidence — jobs 417-422, eight MemoryRootUpdated events, job 420's JobRejected — hangs on that address. We chose evidence that is flawed but whole over evidence that is clean but new. That can be judged wrong.

9/ Still not fixed: the incentive (fee only on Completed), MIN_BOND = 0, challenge/resolve stubs, zero tests in sim/. All 36 limitations — including the security review our judge panel failed, then closed — are in the repo: https://github.com/ZiramBayam/referi
```

## Character count

Counted including the `n/ ` prefix; the em dash, the ellipsis `…`, and the `→` arrow each count as one
character.

| Tweet | Thread 1 | Thread 2 |
|---|---|---|
| 1/ | 267 | 225 |
| 2/ | 254 | 256 |
| 3/ | 252 | 246 |
| 4/ | 251 | 261 |
| 5/ | 255 | 240 |
| 6/ | 239 | 228 |
| 7/ | 248 | 252 |
| 8/ | 255 | 256 |
| 9/ | 262 | 260 |
| **longest** | **267** | **261** |

Nine tweets per thread, zero emoji, zero hashtags, repo link in the last tweet of each thread.

## Claims deliberately left out

Not written here because the repo does not support them: that the evaluator is paid the same when it
rejects (ADR-004 is a design, and `evaluatorFeeBP` is only paid on `Completed` — `docs/limitations.md`
item 14); that `challenge`/`resolve` protect anything (they `revert NotImplemented()` — item 2); that the
memory root proves the memory file is legitimate (item 16); that the destructive test leaves artifacts you
can diff (item 19); and any severity scoring behind the demo's "coarse defect" wording (item 19).
