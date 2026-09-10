# Demo video script, Execution Passport (TAKE-1)

This is the **one** script for the submission recording. It is **operational**: read it while
recording, not as prose. Every row names what is typed or clicked, what appears on screen, and what
is said.

- Target duration: **4 minutes 45 seconds** (safe range 4:30 to 5:00; the rubric requires 2 to 5).
- The rubric asks for **fresh-session recall**. Section 2 is where that is proved, on camera, by a
  line the demo prints itself. Do not skip it and do not paraphrase it.
- The rubric weights are **memory 40, innovation 25, technical 20, pitch 15, PMF 10 = 110**, times an
  integration multiplier. Every section below names which weight it serves. Those notes are **for the
  recorder, never spoken**. Sections 2 and 3 together are 2 minutes of a 4:45 take, because memory is
  the largest single weight and it is the one that has to be **proved**, not described.
- Everything on screen is English except the three hashed-bytes exceptions listed at the bottom.
  Section 3 now opens `/verdict/421` and `/verdict/422`, so exception 2 **is** on screen in this take:
  read section E before recording and follow its rule.
- The earlier direction (escrow referee) has its own script at
  `demo/video-script-earlier-direction.md`. It is **not** what we submit.

---

## A. Pre-flight (before pressing record)

| # | Command or action | Must happen |
|---|---|---|
| A1 | `make doctor` | exits 0 |
| A2 | `cd contracts && forge test --summary` | 175 passed, 0 failed |
| A3 | `cd agent && uv run pytest -q` | 790 passed, 0 failed |
| A4 | `make demo-passport` as a timed dry run | finishes, and you have read every line once |
| A5 | `pnpm --filter web build && pnpm --filter web start` | server on `http://127.0.0.1:3000` |
| A5b | On `/execution`, run one preflight and confirm the badge reads `LIVE AGENT` | if it reads `RULE SIMULATION`, the Python venv is not reachable from the web process. Fix before recording, that badge is a section of the script |
| A6 | Open 4 tabs, left to right: `/execution`, `/verdict/421`, `/verdict/422`, and the CTA card | all render |
| A7 | Terminal: `clear`, font at least 16pt, width at least 100 columns | output does not wrap |
| A8 | Close notifications, personal tabs, wallet extensions | clean screen |
| A9 | `make virtuals-evidence` as a dry run | ends `jobs_confirmed_onchain=5/5` and `transactions_sent=0 keys_used=0`. It reads Base Sepolia, so it **needs network**: without it the command prints `rpc_unreachable=…` and exits 1 (`agent/agent/virtuals_evidence.py:85-88`) |
| A10 | `make dual-gate` as a dry run | ends `root_covers_both_gates=True` (`agent/agent/dual_gate_report.py:89`). No network, no key |
| A11 | Prepare the section 6 CTA card as a static full-screen page or slide | text is in section 6, verbatim |

**A12, rehearse this once:** on `/execution`, press `Run agent preflight` with the oracle still
stale, watch it block, then `Refresh oracle fixture`, then `Run preflight again`. You must be able to
do it without hunting for buttons.

---

## B. Screen layout

- Section 0: no terminal and no browser. Talking head, one slide, or a plain title card, your choice
  (see the options in section 0). Whatever you pick, nothing technical is on screen yet.
- Sections 1 to 2: terminal, full screen.
- Section 3: browser, `/verdict/421` then `/verdict/422`.
- Section 4: browser, `/execution`, full screen.
- Section 5: terminal again, then one explorer tab.
- Section 6: the static CTA card, full screen, held still.
- Never split the screen. Switching windows is cheaper to follow than two half-size panes.

---

## C. Script

### Time budget

| Section | Span | Length | Serves (recorder note, never spoken) |
|---|---|---|---|
| 0. The situation, before any screen | 0:00 to 0:35 | 35 s | PMF 10, pitch 15 |
| 1. One command | 0:35 to 0:50 | 15 s | pitch 15 |
| 2. Memory is load-bearing, run live | 0:50 to 2:20 | 90 s | **memory 40** |
| 3. Identical text, opposite verdicts, on chain | 2:20 to 2:50 | 30 s | **memory 40** + multiplier |
| 4. The same decision you can click | 2:50 to 3:45 | 55 s | innovation 25, technical 20 |
| 5. Numbers a judge can check without us | 3:45 to 4:25 | 40 s | technical 20, multiplier |
| 6. CTA | 4:25 to 4:45 | 20 s | pitch 15, PMF 10 |

Memory-serving time is sections 2 and 3, 120 seconds of 285, the largest block in the take. That is
deliberate: it is the largest weight and the only one that can be **shown failing** on camera.

### Section 0, the situation (0:00 to 0:35)

**Serves: PMF 10, pitch 15.** No terminal, no browser, no architecture. This section only has to earn
the next four minutes. Pick one of three, in order of preference:

- **(a) Talking head.** Highest trust, no assets needed, and it makes the whole take feel authored.
- **(b) One static slide** with three lines of text and nothing else, if you would rather not be on
  camera.
- **(c) A plain title card**, black background, the sentence appearing a phrase at a time.

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 0:00 | Hold still, do not cut | (a) you, (b) slide line 1, or (c) black card | "You pay someone to do a job. A contractor, a freelancer, and lately an AI agent with your money in reach. The work comes back looking finished, and it isn't. A price it acted on was two minutes old. A check nobody re-ran." |
| 0:14 | Reveal line 2 | slide line 2 | "Someone reviews it and misses it, because the reviewer only ever sees this one job. No history, no pattern, no memory. So the same provider does the same thing next week, and it gets graded from zero all over again." |
| 0:26 | Reveal line 3 | slide line 3 | "Referi is the reviewer that remembers, and the memory doesn't write a report. It decides. Here is what that looks like." |

> **Recorder note.** Nothing in section 0 is a claim about the repo, so nothing here needs evidence.
> The moment a number appears on screen, you are in section 1. Do not smuggle one in early.

### Section 1, one command (0:35 to 0:50)

**Serves: pitch 15.**

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 0:35 | Cut to terminal, cleared | empty prompt | "One incident: an agent moved value on an oracle reading two minutes stale. Referi turns that incident into a condition that has to hold before the same class of action can move money again." |
| 0:44 | Type `make demo-passport`, do not press enter yet | command visible | "One command, from scratch, on a local chain. No network, no funds, no key. Watch what memory does, and then watch what happens when I take it away." |

### Section 2, memory is load-bearing (0:50 to 2:20)

**Serves: memory 40.** This is the highest-value 90 seconds in the video. Slow down here. Read what is
on the screen; the rows below are in the order `agent/agent/passport_demo.py` prints them.

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 0:50 | Press enter | contracts build and deploy, then the run begins | "It deploys a mock treasury, a mock oracle and the verifier, then seeds the incident. The run finishes in seconds, so I will hold on each line." |
| 1:00 | Point at `before_memory_decision=human-review-required` | that line (`passport_demo.py:150`) | "First, with no memory yet, the agent does not decide. It asks for a human. It does not fall back to a permissive default, because a guessed default is exactly how you get the same failure twice." |
| 1:15 | Point at `stored_hypothesis=… memory_root=…` | that line (`:152`) | "The incident is now stored in Sibyl as a Control Hypothesis, and that is the memory root over the store that holds it." |
| 1:28 | Point at `fresh_process_recall=stale-oracle-rebalance/v1 executor_identity=child-process` | that line (`:187`) | "This is a different process. A cold executor, no shared state, recalls the hypothesis by itself. That is the fresh-session recall the rules ask for, and the demo prints it instead of claiming it." |
| 1:42 | Point at `thresholds_from_memory=oracle=60 reserve=250000` | that line (`:213-217`) | "And these two limits, sixty seconds of oracle age and the reserve floor, are read out of memory. They are not constants in the code. A different incident produces different numbers here." |
| 1:56 | Point at `invalid_passport_rejected=calldata-mismatch` then `accepted_rebalance=exactly-once` | both lines (`:226`, `:237`) | "The passport it issues is bound to the exact calldata. Change one byte and the real verifier reverts. The correct call goes through once and the nonce is spent." |
| 2:06 | Point at `passport_memory_deleted=True after_delete_decision=human-review-required` | last lines (`:258-259`) | "Now the destructive test, and it just ran in front of you: the hypothesis is deleted, the same action is proposed again, and it goes straight back to human review. Delete the memory and the behaviour changes. That is the whole claim, and it is one line of output." |

> **Recorder note, ordering.** `fresh_process_recall` prints **before** `thresholds_from_memory` in the
> real run (`passport_demo.py:187` then `:213`). The rows above follow the real order. An earlier take
> had them the other way round; if the screen disagrees with this table, the screen wins.
>
> **Recorder note, what not to say.** Do not say "naive mode". Do not say the agent scores quality or
> uses a model: there is no LLM anywhere in the path (`docs/limitations.md` item 33). Do not say the
> evaluator stakes anything: the bond is zero (item 1). Do not say the challenge window protects
> anyone: `challenge`/`resolve` revert, so it is latency (items 2 and 26).

### Section 3, identical text, opposite verdicts (2:20 to 2:50)

**Serves: memory 40, and the integration multiplier.** Section 2 proves memory changes a decision on a
local chain. This proves it once more on a public one, with two rows a judge can open themselves.

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 2:20 | Browser, tab `/verdict/421` | `PASSED`, deliverable hash `0x246071b3…0a51`, depth `sampling` | "Second proof, on Base Sepolia, from the earlier gate of this project. Job 421: that is the hash of the deliverable text, and it passed." |
| 2:33 | Switch to tab `/verdict/422` | `REJECTED`, the **same** deliverable hash, depth `full`, `VerdictPosted` tx link | "Job 422. Byte for byte the same text, same hash, same budget, same evaluator. Rejected. The only difference is that this provider already had two incidents in memory, so the check ran at full depth instead of sampling, and the third section is where the defect was." |
| 2:44 | Hover the `VerdictPosted tx` link so the hash is readable | `0xe95910d2…295830` | "Both verdicts are transactions you can open, and each one announces the memory root the decision was made under." |

> **Evidence.** `web/public/jobs.json` jobs 421 and 422 both carry `deliverableHash`
> `0x246071b30c435f192b9ffcb064a11178bc2bd25a02819a1ad7c3b8ee24bf0a51`, `acpStatus` 3 versus 4,
> `verdictKind` 1 versus 2, budget `250000` on both. Tx `0xe95910d2…295830`. What this pair does **not**
> prove is in `docs/limitations.md` item 25: the "defect" is one `TODO` token, and the provider is our
> own simulator. Do not oversell it on camera; the sentence above is already the whole claim.

### Section 4, the same decision you can click (2:50 to 3:45)

**Serves: innovation 25, technical 20.**

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 2:50 | Switch to `/execution` | four numbered steps | "Back to today's gate, in a browser, with the same agent behind it." |
| 2:56 | Point at step 01, the seeded incident card | `120 seconds old` against `60 seconds` | "The oracle reading here is a hundred and twenty seconds old. Memory says sixty." |
| 3:04 | Click `Run agent preflight` | four obligations resolve, one BLOCK | "Three obligations hold. Oracle freshness does not, and that row opens itself so you see the observed value against the required one. No passport is issued." |
| 3:16 | Point at the green `LIVE AGENT` badge | badge with memory root and verifier address | "This badge is the point. The page did not re-implement the rules in JavaScript, it called the same Python agent and read the same Sibyl store, and that is the root it read. If the agent were unreachable the badge would say so instead of pretending." |
| 3:26 | Click `Refresh oracle fixture`, then `Run preflight again` | all four PASS, `Passport ready` | "Fix the condition the incident was about, and the same action is allowed. The passport is bound to this target, this selector, this calldata hash, this chain and this nonce, and it lives sixty seconds." |
| 3:36 | Click `Execute exact fixture action`, then `Try amount + 1`, then `Try replay` | step 04, two rows turn REJECT: `calldata-mismatch`, `nonce-already-used` | "One changed byte, refused. The same passport submitted twice, refused. Permission was for one action, not for a class of actions. To be exact: this last step is the fixture walkthrough. The enforcement you actually saw was a minute ago in the terminal, against the real verifier." |

> **Recorder note, honesty.** `Execute exact fixture action`, `Try amount + 1` and `Try replay` are
> client-side state in `web/src/components/ExecutionRoom.jsx:194-207`. They send no transaction and
> do not call the agent. The revert that really happened is `invalid_passport_rejected=calldata-mismatch`
> in section 2, produced by `PassportVerifier` on Anvil. The spoken line above says so out loud; keep
> that sentence, an earlier take dropped it and the browser clicks read as on-chain enforcement.

### Section 5, numbers a judge can check without us (3:45 to 4:25)

**Serves: technical 20, integration multiplier.**

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 3:45 | Terminal: `make virtuals-evidence` | per-job lines, then `jobs_confirmed_onchain=5/5` and `transactions_sent=0 keys_used=0` | "This reads the real Virtuals ACP contract on Base Sepolia right now and matches all five jobs against the file the site serves. No key, no transaction. You can run it yourself." |
| 3:58 | Terminal: `make dual-gate` | ten lines, ending `root_covers_both_gates=True` | "And one memory serves both gates. The root the evaluator announced on chain already commits to the passport policy, which is why this is two gates and not two projects." |
| 4:08 | Browser: `base-sepolia.blockscout.com/address/0x43D978e26bEe32A8f2E2DaB1f212F9A36F5937C1` | verified source, not bytecode | "The verifier is deployed on Base Sepolia at block 46,629,087, source verified, bound to that treasury and to one signer, and neither can be changed." |
| 4:18 | Stay on the page, say the boundary | the contract page | "One action class, a mock treasury, testnet, no real funds. Everything else is roadmap, and I am not going to call it a feature." |

> **Evidence.** `deployments/passport-84532.json`: `status: DEPLOYED`, `deployedAtBlock: 46629087`,
> `PassportVerifier 0x43D978e2…37C1`, `MockTreasury 0x68Cca28D…772B`, `MockOracle 0x8b0e7572…bDe3`,
> Sourcify `exact_match`, `boundary` line for the last row. `make virtuals-evidence` needs network
> (`agent/agent/virtuals_evidence.py:85-88`); `make dual-gate` does not. Open Blockscout, not BaseScan:
> only Blockscout carries the Sourcify source.

### Section 6, try it yourself (4:25 to 4:45)

**Serves: pitch 15, PMF 10.** There is **no hosted deployment**: `web/` runs locally only, and no live
URL exists anywhere in the repo. So the call to action is the repo and two commands. Hold this card
still for the full twenty seconds so it can be paused or screenshotted; do not talk over the last five.

Card content, verbatim, nothing else on it:

```
REFERI — proof before permission

github.com/ZiramBayam/referi

git clone https://github.com/ZiramBayam/referi && cd referi
make demo-passport

needs foundry and uv · no network, no key, no funds · runs in seconds
```

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 4:25 | Cut to the CTA card | the card above | "Everything you just saw is one clone and one command. It builds the contracts, starts its own local chain, and prints those lines on your machine, in seconds, with no network and no key." |
| 4:38 | Do not move the card | the card, still | "Delete the memory and it stops deciding. Proof before permission." |
| 4:43 | Hold two more seconds, then stop | the card, still | *(silence)* |

> **Evidence for the card.** Remote from `.git/config` (`git@github.com:ZiramBayam/referi.git`), also
> printed in `web/src/components/Footer.jsx:6`. `make demo-passport` is `Makefile:73-74`; it runs
> `forge build` itself when artifacts are missing (`agent/agent/passport_client.py:30-41`) and starts
> its own Anvil via `--start-anvil`. `uv run` syncs the Python environment from `uv.lock`. The measured
> wall time of the run, 4.62 s, is recorded in `docs/posts/threads-x.md`; "runs in seconds" is the only
> form of it that goes on screen.

---

## D. If something goes wrong on camera

| Symptom | Do this |
|---|---|
| `make demo-passport` hangs at deploy | anvil port is busy. `pkill anvil`, re-run. Cut and restart the take. |
| The gate passes on the first preflight | the oracle fixture was already refreshed from an earlier rehearsal. Reload `/execution` and start again. |
| `Try replay` does nothing | you have not pressed `Execute exact fixture action` yet. |
| `make virtuals-evidence` prints `rpc_unreachable=…` and exits 1 | no network, or the public RPC is refusing you. It is section 5 row one only: cut it, keep `make dual-gate`, which needs nothing. Never re-record it as a still image. |
| A `job=… onchain=NO` or `provider_match=NO` line appears | do not narrate over it. Stop the take and find out why; a command that is allowed to be green while wrong is worth nothing. |
| A number on screen differs from this script | read what is on screen, never what is written here. The script is the plan, the screen is the evidence. |

---

## E. The three places that stay Indonesian, and why

Exception 2 **appears in this take**: section 3 opens `/verdict/421` and `/verdict/422`, and their
bundle strings are Indonesian. Exceptions 1 and 3 do not appear unless you improvise. The reason is
the same for all three: they are bytes that were keccak-hashed into a `reasonHash` that is already on
chain.

In section 3 you only need to name the hash, the depth and the verdict, all of which are English
labels. If a judge's eye lands on an Indonesian line, the rule below is the answer.

1. The `GateDecision.reason` text inside the parentheses of the `gate=` fields in `make demo` output.
2. The bundle strings on `/verdict/[jobId]`: the gate `reason`, each criterion's text, and every
   `reason` or `proof` line.
3. The sample deliverable itself (`# Summary`, `## Cara kerja`, `## Catatan lanjutan`).

**Rule on camera:** quote them as they are, explain them in English, never paraphrase them into
something the screen does not say. Rewording them would stop matching the chain, which is the whole
point of hashing them.
