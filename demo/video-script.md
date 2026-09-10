# Demo video script, Execution Passport (TAKE-1)

This is the **one** script for the submission recording. It is **operational**: read it while
recording, not as prose. Every row names what is typed or clicked, what appears on screen, and what
is said.

- Target duration: **4 minutes 15 seconds** (safe range 4:00 to 4:30; the rubric requires 2 to 5).
- The rubric asks for **fresh-session recall**. Section 2 is where that is proved, on camera, by a
  line the demo prints itself. Do not skip it and do not paraphrase it.
- Everything on screen is English except the three hashed-bytes exceptions listed at the bottom, and
  none of those appear in this take.
- The earlier direction (escrow referee) has its own script at
  `demo/video-script-earlier-direction.md`. It is **not** what we submit.

---

## A. Pre-flight (before pressing record)

| # | Command or action | Must happen |
|---|---|---|
| A1 | `make doctor` | exits 0 |
| A2 | `cd contracts && forge test --summary` | 175 passed, 0 failed |
| A3 | `cd agent && uv run pytest -q` | 774 passed, 0 failed |
| A4 | `make demo-passport` as a timed dry run | finishes, and you have read every line once |
| A5 | `pnpm --filter web build && pnpm --filter web start` | server on `http://127.0.0.1:3000` |
| A5b | On `/execution`, run one preflight and confirm the badge reads `LIVE AGENT` | if it reads `RULE SIMULATION`, the Python venv is not reachable from the web process. Fix before recording, that badge is a section of the script |
| A6 | Open 3 tabs, left to right: `/`, `/execution`, `/timeline` | all render |
| A7 | Terminal: `clear`, font at least 16pt, width at least 100 columns | output does not wrap |
| A8 | Close notifications, personal tabs, wallet extensions | clean screen |

**A9, rehearse this once:** on `/execution`, press `Run agent preflight` with the oracle still
stale, watch it block, then `Refresh oracle fixture`, then `Run preflight again`. You must be able to
do it without hunting for buttons.

---

## B. Screen layout

- Sections 1 to 2: terminal, full screen.
- Sections 3 to 4: browser, full screen.
- Section 5: browser, `/timeline`.
- Never split the screen. Switching windows is cheaper to follow than two half-size panes.

---

## C. Script

### Section 1, the problem (0:00 to 0:30)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 0:00 | Terminal, cleared | empty prompt | "An agent moved value on a price that was already two minutes stale. It got fixed. Then the next run did it again, because nothing about the first failure was standing between the agent and the transaction." |
| 0:15 | Type `make demo-passport`, do not press enter yet | command visible | "Referi turns that incident into a condition. This one command runs the whole thing from scratch on a local chain. Watch five lines." |

### Section 2, memory is load-bearing (0:30 to 2:00)

This is the highest-value 90 seconds in the video. Slow down here.

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 0:30 | Press enter | contracts deploy, then the run begins | "It deploys a mock treasury, a mock oracle, and the verifier, then seeds the incident." |
| 0:45 | Point at `before_memory_decision=human-review-required` | that line | "First: with no memory, the agent does not decide. It asks for a human. It does not guess a safe default, because a guessed default is how you get the same failure twice." |
| 1:05 | Point at `thresholds_from_memory=oracle=60 reserve=250000` | that line | "Then the incident is stored as a Control Hypothesis. These two limits, sixty seconds and the reserve floor, are read out of memory. They are not constants in the code." |
| 1:25 | Point at `fresh_process_recall=... executor_identity=child-process` | that line | "This is a different process. A new executor, cold, recalls the hypothesis and gets the same four obligations. That is the fresh-session recall the rules ask for, and the demo prints it rather than claiming it." |
| 1:40 | Point at `invalid_passport_rejected=calldata-mismatch` then `accepted_rebalance=exactly-once` | both lines | "The passport is bound to the exact calldata. Change one byte and the verifier refuses it. The correct call goes through once, and the nonce is spent." |
| 1:52 | Point at `passport_memory_deleted=True after_delete_decision=human-review-required` | last two lines | "And when the memory is deleted, the same action goes straight back to human review. That is the test that matters: take the memory away and the behaviour changes." |

### Section 3, the same thing you can click (2:00 to 3:10)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 2:00 | Switch to browser, tab `/` | landing | "Same scenario in the browser, and the same agent behind it." |
| 2:08 | Click `Open the execution room` | `/execution` | "Four steps, in the order the agent runs them." |
| 2:15 | Point at step 01, the seeded incident card | `120 seconds old` vs `60 seconds` | "The oracle reading is a hundred and twenty seconds old. Memory says sixty." |
| 2:25 | Click `Run agent preflight` | obligations resolve, one BLOCK | "Three obligations pass. Oracle freshness does not, and it opens itself, so you can see the observed value against the required one. No passport is issued." |
| 2:38 | Point at the green `LIVE AGENT` badge | badge with memory root and verifier address | "This badge matters. The page is not simulating the rules, it called the same Python agent, read the same Sibyl memory, and that is the memory root it read. If the agent were not running it would say so instead of pretending." |
| 2:45 | Click `Refresh oracle fixture`, then `Run preflight again` | all four PASS, `PASSPORT READY` | "Fix the condition the incident was about, and the same action is allowed. The passport is bound to this target, this calldata, this nonce, and it lives sixty seconds." |
| 3:00 | Click `Execute exact fixture action` | step 04 appears | "It executes once." |

### Section 4, what the verifier refuses (3:10 to 3:35)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 3:10 | Click `Try amount + 1` | row turns REJECT, `calldata-mismatch` | "Same passport, one changed byte: refused." |
| 3:22 | Click `Try replay` | row turns REJECT, `nonce-already-used` | "Same passport, submitted twice: refused. Permission was for one action, not for a class of actions." |

### Section 5, it is on chain and it is bounded (3:35 to 4:05)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 3:35 | Open `base-sepolia.blockscout.com/address/0x43D978e26bEe32A8f2E2DaB1f212F9A36F5937C1` | verified source, not bytecode | "The verifier is on Base Sepolia, source verified. It is bound to that treasury and to one signer, and neither can be changed." |

> **Checked 2026-09-10:** `deployments/passport-84532.json` reads `status: DEPLOYED`, all three
> contracts are `exact_match` on Sourcify. This row is true, record it. Open Blockscout, not
> BaseScan: only Blockscout shows the Sourcify source.
| 3:48 | Switch to `/timeline` | five jobs | "And this is the earlier direction of this project, five evaluation jobs that really landed on chain, kept because the memory argument was proved there first." |
| 3:52 | Terminal: `make dual-gate` | ten lines, ending `root_covers_both_gates=True` | "One memory serves both. The root this evaluator announced on chain commits to the passport policy too, which is why these are two gates and not two projects." |
| 3:56 | Point at the footer boundary line | `no real funds` | "One action class, mock treasury, testnet. Everything else is roadmap, not a claim." |
| 4:10 | Stop | | "Proof before permission." |

---

## D. If something goes wrong on camera

| Symptom | Do this |
|---|---|
| `make demo-passport` hangs at deploy | anvil port is busy. `pkill anvil`, re-run. Cut and restart the take. |
| The gate passes on the first preflight | the oracle fixture was already refreshed from an earlier rehearsal. Reload `/execution` and start again. |
| `Try replay` does nothing | you have not pressed `Execute exact fixture action` yet. |
| A number on screen differs from this script | read what is on screen, never what is written here. The script is the plan, the screen is the evidence. |

---

## E. The three places that stay Indonesian, and why

None of them appear in this take, but if you improvise into `/verdict/[jobId]` they will, and the
reason is the same for all three: they are bytes that were keccak-hashed into a `reasonHash` that is
already on chain.

1. The `GateDecision.reason` text inside the parentheses of the `gate=` fields in `make demo` output.
2. The bundle strings on `/verdict/[jobId]`: the gate `reason`, each criterion's text, and every
   `reason` or `proof` line.
3. The sample deliverable itself (`# Summary`, `## Cara kerja`, `## Catatan lanjutan`).

**Rule on camera:** quote them as they are, explain them in English, never paraphrase them into
something the screen does not say. Rewording them would stop matching the chain, which is the whole
point of hashing them.
