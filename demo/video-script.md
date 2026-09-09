# Demo video script — TAKE-1

This is the **one** script for the recording. It is **operational**: read it while recording the screen,
not as prose. Every row names **what is typed/clicked**, **what appears on screen**, and **what is said**.
The whole take is in **English** — documents, the web UI, and the demo output are all English now.

- Target duration: **4 minutes 35 seconds** (safe range 4:20–4:50; rubric requires 2–5 minutes).
- Flow = `docs/spec.md` §7 steps 1–5. Steps 1–4 = one `make demo` command; step 5 = three routes in the browser.
- What gets recorded is **frozen code** (ADR-030). Do not edit anything between takes.
- Recording hard stop: **9 Sep 18:00** (ADR-028 decision 2).

### The three places that are still Indonesian — and why that is a feature

Almost everything on screen is English. Three things are deliberately not, and all three are the **same
reason**: they are bytes that were keccak-hashed into a `reasonHash` that is already on chain.

1. The text **inside the parentheses** of the `gate=` fields in the demo output —
   `REJECTED (budget 2000000 melebihi cap milestone provider ini …)` and `pass (budget dalam batas cap)`.
   The label outside the parentheses is English; the quoted `GateDecision.reason` is not.
2. The bundle strings on `/verdict/[jobId]`: the gate `reason`, each criterion's text, and every
   `reason`/`proof` line.
3. The sample deliverable text itself (`# Summary`, `## Cara kerja`, `## Catatan lanjutan`).

**Rule on camera:** quote them as they are, explain them in English, never paraphrase them into something
the screen does not say. If it feels awkward, say the one-liner in Section 3 — the verdict page already
makes this argument for you in English, at `web/src/app/verdict/[jobId]/page.jsx:50-56`
("Bundle strings are quoted, not translated … rewording it here would stop matching the chain").

---

## A. Pre-flight (do this BEFORE pressing record)

| # | Command / action | What must happen | If it fails |
|---|---|---|---|
| A1 | `cd /home/zirambayam/referi && make doctor` | exits with code 0 | do not record; toolchain does not match `docs/versions.md` |
| A2 | Make sure you have internet access to `https://sepolia.base.org` | `make demo` checks this in a PREFLIGHT step in its first second (`Makefile:50-54`, `sim/src/demo.ts:304-357`) | with no network `make demo` stops with exit 1 before Anvil starts |
| A2b | **If PREFLIGHT fails on a run that worked before** — e.g. `PREFLIGHT FAILED — the frozen vault 0x5c6E… cannot be read (TypeError: fetch failed)` | this is **correct behaviour**, and it is transient: the RPC hiccuped. It failed in the first second, before Anvil started, so **nothing was left half-built** | **change nothing, fix nothing, do not edit any file** — just run `make demo` again. This happened once during the two verification runs and the immediate re-run succeeded |
| A3 | **Timed dry run**: `time make demo 2>&1 \| tee /tmp/dryrun-demo.log`, wait for it to finish | exit 0; the lines `VARIANT A:` and `VARIANT B:` are printed; write down the runtime — measured at **3m23s**, **3m40.8s**, and **3m56s**, so expect **Plan B** | if it fails for any reason other than A2b, fix the environment first — never record a failure and narrate it as a success |
| A3b | **Determinism check** (already done twice): run it a second time and diff the deterministic block | the 32-line deterministic diff is **empty** — same summary, same numbers | if the diff is not empty, stop: Plan B in section G assumes the pre-recorded run and the narrated run agree |
| A4 | `pnpm --filter web build` | build finishes without errors | — |
| A5 | Terminal B: `DEMO_MODE=1 pnpm --filter web start` | server on `http://127.0.0.1:3000` (`-H 127.0.0.1` is pinned in `web/package.json:9`) | — |
| A6 | Open 4 browser tabs, ordered left→right: (1) `http://127.0.0.1:3000/`, (2) `http://127.0.0.1:3000/verdict/420`, (3) `http://127.0.0.1:3000/verdict/422`, (4) `https://base-sepolia.blockscout.com/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384?tab=logs` | all four fully loaded before recording starts; **Blockscout**, not BaseScan — that is where event names are decoded (see the Section 4 note) | a tab still loading eats seconds you do not have |
| A7 | Terminal A: `cd /home/zirambayam/referi && clear`, large font (≥ 16pt), width ≥ 120 columns | clean prompt | — |
| A8 | Close notifications, personal tabs, and wallet extensions | clean screen | — |
| A9 | **Rehearse section 5 first**: `/panel` → button "deliverable job 422" → run `sampling`, then `full` | `sampling` → `format.no-placeholder` **pass**; `full` → **fail** | if that is not the result, cut section 5 from the script and move its 30 seconds into section 6 — do not narrate a result that does not appear |

**Note on `DEMO_MODE=1`:** with that gate on, `/panel` also renders the **"Demo control — wipe memory"**
section, which is **out of scope for TAKE-1**: it is not in this script and not rehearsed in A9. While
recording, **do not click it and do not scroll down to it** (this script stops at the "Result" card). If
you do not need the gate at all, run A5 without `DEMO_MODE=1` — the entire script still works.

> Scope note, not a safety note: that surface once carried a **BLOCK** verdict from the security review.
> The block has since been **lifted** — the re-review returned zero CRITICAL and zero HIGH, and the last
> MEDIUM (TOCTOU on ancestor path components) was closed via the `dir_fd` path. `docs/limitations.md`
> item 36 records the full history, including the LOW risk still accepted. It is left out of TAKE-1
> because the script is full at 4:35 and the control was never rehearsed, not because it is unsafe.
> On camera: do not comment on it in either direction.

---

## B. Screen layout

- **Terminal A** (left / fullscreen during sections 1 and 6): where `make demo` runs.
- **Browser** (sections 2–5): the four tabs from A6.
- **START FROM THE ASSUMPTION THAT YOU ARE USING PLAN B (section G).** The **measured** runtime of
  `make demo` is **3m23s, 3m40.8s, and 3m56s** — longer than the ± 2 minute 35 second window that
  sections 2–5 provide. So if you run it live, it will most likely **not be finished** when you return to
  Terminal A. The "~2m20s" figure that used to circulate comes from task 3.3, before the two destructive
  variants and the network preflight were added; do not plan a recording around it.
- Plan A (live) only makes sense if dry run A3 **on your machine** finishes under ± 2m30s. Measure it
  (`time make demo`); do not guess.

---

## C. Script

### Section 1 — The problem + start the demo (0:00 – 0:40, 40 s)

| Time | Action (type/click) | Screen | Spoken |
|---|---|---|---|
| 0:00 | Nothing; Terminal A is clean | empty prompt inside the repo | "ERC-8183 gives one role total power: the evaluator. It decides whether a job is paid in full or refunded in full — there is no partial payment. And a standard evaluator has no memory: the same provider can repeat the same trick tomorrow, and the referee will not know." |
| 0:20 | Type and run: `make demo 2>&1 \| tee /tmp/take1-demo.log` | lines `[demo] start …`, `[demo] anvil.up …` start scrolling | "This is REFERI: an ERC-8183 referee whose memory of each provider can be recomputed from files. This single command builds the chain from scratch on local Anvil, then reads one frozen vault on Base Sepolia — only two `eth_call` view calls: **no funds, no transactions**. While it runs, let me show you what already landed on chain." |

> On-screen evidence: `Makefile:62-63`; internet requirement `Makefile:50-54`; `sim/src/demo.ts:610-611`
> ("only two `eth_call` view calls").

### Section 2 — Job timeline 418–422 (0:40 – 1:25, 45 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 0:40 | Switch to tab 1 (`/`) | heading "Job timeline 418–422 (Base Sepolia)" | "Five jobs that really landed on Base Sepolia. Jobs 418 and 419: the same provider, the deterministic `format` check failed twice — two incidents from two different jobs." |
| 1:00 | Move the cursor over rows 418, 419, then 420 | the "Verdict" column reads `reject`; the "VerdictPosted tx" column holds Blockscout links | "Job 420 is the interesting one: it was rejected **while still `Funded`** — before the provider had submitted anything at all. Its bundle shape is `gate-rejection`." |
| 1:15 | In the "Evidence" column of row **420**, click **open evidence** (or switch to tab 2) | page `/verdict/420` loads | "Why? The full evidence is on this page." |

> On-screen evidence: `web/src/app/page.jsx:13` (heading), `:63` ("open evidence"); data from
> `web/public/jobs.json`; this page makes zero RPC calls — it only renders repo artifacts.

### Section 3 — The cap gate: what memory decided (1:25 – 2:05, 40 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 1:25 | Scroll to the card **"Gate decision (no deliverable evaluated)"** | `accepted? reject`, `budget 2000000`, `provider cap 250000 (basis baseline-constant, sample_size 0)`, `risk level 2`, `incident jobs behind it 418, 419` | "Budget two million units, cap two hundred and fifty thousand, rejected. The two underlying incident jobs are written into the bundle — 418 and 419 — and you can click them." |
| 1:40 | Point at the `reason` field (still Indonesian) | `reason` reads `budget 2000000 melebihi cap milestone provider ini (250000; riwayat: 2 insiden terkonfirmasi)` | "One field is not in English, and that is on purpose: this `reason` string is the agent's own bytes, and those exact bytes were hashed into the `reasonHash` on chain. Translating it here would stop it matching the chain. It says: the budget exceeds this provider's milestone cap of two hundred fifty thousand — history: two confirmed incidents." |
| 1:48 | Point the cursor at `sample_size 0` | same card | "One piece of honesty we wrote into the bundle ourselves: `sample_size` is zero. The **number** two hundred and fifty thousand is a team constant divided by four — what is learned from memory is the **risk level**, and the risk level is what picks the divisor. Memory here can only **tighten** the cap, never loosen it." |
| 1:58 | Point at `memory_root (from the agent)` and `VerdictPosted tx` in the top card | `memory_root 0xcfdab1b0…`, tx link | "And this reasoning is hash-bound: everything on this page is the bundle that gets keccak-hashed into the `reasonHash` in that transaction." |

> On-screen evidence: bundle `web/public/verdicts/420.json`; the "quoted, not translated" paragraph is
> rendered on the page itself (`web/src/app/verdict/[jobId]/page.jsx:50-56`); `docs/limitations.md` item 8
> (`basis: baseline-constant`, `sample_size: 0`), item 17 (enforcement lives in the agent; the contract
> only publishes the cap).

### Section 4 — Identical text, different verdict + on-chain trace (2:05 – 2:45, 40 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 2:05 | Switch to tab 3 (`/verdict/422`) | heading "Verdict for job 422 — reject", `check depth full`, `deliverable hash 0x246071b3…0a51` | "Jobs 421 and 422 use the **byte-for-byte same** deliverable — identical keccak hash, same budget. Job 421 passed. Job 422 was rejected." |
| 2:18 | Scroll to **"Per-criterion evidence"** | check `format.no-placeholder` **fail**, `section 2`, `depth full`; the `reason`/`proof` lines are Indonesian bundle text | "The only difference is the provider: one is clean, the other has two incidents. That history raised the check depth from `sampling` to `full`, and the defect — a `TODO` in the third section — is only visible at `full`. The reason and the proof excerpt are again quoted from the hashed bundle, so they stay in the agent's own words." |
| 2:30 | Scroll slightly to the yellow card **"Criteria that were NOT scored"** | `qualitative.0` + the `unscored_reason` line | "I should say this plainly: there is no qualitative scoring and no LLM anywhere in the path. Qualitative criteria are recorded as `unscored`, as-is." |
| 2:37 | Switch to tab 4 (Blockscout, the vault's **Logs** page); point at the top entry: `MemoryRootUpdated` with root `0x999a9570…9b7d` (tx `0xe95910d2…5830`) | the vault log list with **decoded event names**: `MemoryRootUpdated`, `VerdictPosted`, `Finalized`, `ProviderCapSet` | "And here is the on-chain trail. The event name is readable — `MemoryRootUpdated` — because the contract is verified on Sourcify, `exact_match`, from commit `8d3e596`. This is the root that was announced **before** execution." |

> On-screen evidence: `docs/limitations.md` item 25 (the 421 vs 422 table plus four tx hashes), item 33
> (`unscored`), item 7 (the `MemoryRootUpdated` history), item 15 (Sourcify `exact_match` from commit
> `8d3e596`).
>
> **Why Blockscout and not BaseScan:** Blockscout imported the Sourcify verification, so the event names
> actually render on camera; Etherscan/BaseScan does not import from Sourcify and verifying there needs an
> API key this repo does not have — so we claim **nothing in either direction** about BaseScan's status
> (`deployments/84532.json:32`). The web UI links to Blockscout for the same reason
> (`web/src/lib/chain.js:20-21`). Valid alternative if you trust a terminal more than an explorer: run
> `cast logs` over the blocks listed in `docs/limitations.md` item 7 — but its output is raw topics, so
> the event name will not be visible on screen.

### Section 5 — Judge panel: try it yourself (2:45 – 3:15, 30 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 2:45 | Open `http://127.0.0.1:3000/panel` (heading "Judge panel — try it yourself"), and next to **"Load a sample:"** click the button **deliverable job 422** | textarea fills with three sections: `# Summary`, `## Cara kerja`, `## Catatan lanjutan` — the deliverable text is Indonesian because that is the exact text that was hashed | "The judge panel. Load the job 422 deliverable — the document itself is in Indonesian, and it is the byte-identical text that was hashed on chain — then pick the depth yourself." |
| 2:55 | In the **Depth** dropdown pick `sampling (first 2 sections)` → click **Run checks** | the **"Result"** card: `verdict (kind) COMPLETE (kind=1)`, `failed_checks [] (empty)`, `format.no-placeholder` **pass** | "At `sampling`: it passes." |
| 3:03 | Pick `full (all sections)` → click **Run checks** | the "Result" card: `REJECT (kind=2)`, `failed_checks ["format"]`, `format.no-placeholder` **fail** in the third section | "At `full`: it fails. Same text, different depth. Let me state the limit: this panel runs only the `format` and `links` checks inside the local Next process — it does not read memory and it does not send transactions." |

> On-screen evidence: `web/src/app/panel/page.jsx:40-47` (the limits card), `PanelForm.jsx:73-81`
> (depth options and the "Run checks" button); check-port parity is guarded by
> `web/test/checks-parity.test.js` (5 tests, `pnpm -r test`).

### Section 6 — The peak: delete the memory (3:15 – 4:10, 55 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 3:15 | Back to Terminal A; `make demo` has finished | last line `[demo] done …` | "That command has finished. The most reasonable question a judge can ask: if the memory is deleted, does anything actually change?" |
| 3:22 | Type: `grep -E '^(VARIANT \|\[demo\] claim )' /tmp/take1-demo.log` | four blocks of lines are printed | — |
| 3:28 | Highlight the `claim step=C-vs-D` line | `budgetRaw=2000000`, `gateWithMemory="REJECTED (budget 2000000 melebihi cap milestone provider ini (250000; riwayat: 2 insiden terkonfirmasi))"`, `gateWithoutMemory="pass (budget dalam batas cap)"`, `note="IDENTICAL budget, only the memory differs — that is the cap"` | "Here is the line. The budget is **identical** — two million units. With memory: REJECTED, and the quoted reason — the same hashed bundle string you just saw — names two confirmed incidents. Without memory: it passes. The only thing that differs is the memory. And the agent is invoked as a **fresh process** for every job — that recall comes from files, not from one long-lived session." |
| 3:44 | Highlight the `claim step=D-vs-E` line | `depth="sampling"`, `subtle="PASS"`, `coarse="FAIL ['format']"`, `note="wiping memory lowers the DEPTH, it does not switch the evaluator off"` | "And the demo says it in its own output: wiping the memory lowers the depth; it does not switch the evaluator off." |
| 3:50 | Highlight the `VARIANT A:` line | `VARIANT A: ONCHAIN ROOT RESET, cap gone (NO CAP), mode sampling, subtle defect PASSES (job 4: PASS), coarse defect REJECTED (job 5: FAIL ['format']), 5 new tx, nonce 9 -> 14` | "What is lost when memory is deleted is **calibration**: the cap is gone, the depth drops to `sampling`, and the subtle defect gets through. What is **not** lost: the coarse defect is still rejected — the evaluator does not die, it goes shallow. Delete our memory, and you get an ordinary stateless evaluator — exactly our competitors." |
| 4:00 | Highlight the `VARIANT B:` line | `VARIANT B: SAFE MODE, 0 new tx, nonce 89 -> 89, job hangs until expiredAt, recover with memory.db from backup` | "That was on a fresh vault. On a vault that is already live, missing memory triggers **safe mode**: zero transactions — measured from the agent wallet's nonce, not just asserted — the job hangs until it expires, and the client gets a full refund." |

> On-screen evidence: `make demo` output lines (`sim/src/demo.ts:902-949`); the safe-mode run is aborted if
> its evidence does not appear (`sim/src/demo.ts:672-687`); the agent is invoked per job
> (`docs/limitations.md` item 9).
> **Never** call variant A "naive mode": the mode label is `normal`; what shows the degradation is
> `depth=sampling` and `cap=NO CAP` (ADR-026, `docs/limitations.md` item 34).

### Section 7 — Honesty + closing (4:10 – 4:35, 25 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 4:10 | Open `README.md` in the editor or on GitHub, scroll to **"Limitations & trust assumptions"** | the numbered list is visible on screen (full 36-item list: `docs/limitations.md`) | "Last, and this is not a footnote: this project lists its own limitations — a summary in the README, the full thirty-six items in `docs/limitations.md` — a wrong verdict cannot be undone by anyone, the evaluator's bond today is zero, and funds that enter the vault are stuck permanently." |
| 4:25 | Scroll to the **"How to run"** section | the `make doctor` / `make test` / `make demo` block | "You can run all of it yourself: `make doctor`, `make test`, `make demo`. Public repo, MIT licence. Thank you." |

---

## D. Sentences you must NOT say (the take fails if one of these comes out)

| Do not say | Why | Say instead |
|---|---|---|
| "naive mode" for variant A | the mode label is `normal`; "naive" is only the first invocation log line, which ends in zero transactions (ADR-026, `docs/limitations.md` item 34) | "`depth=sampling`, `cap=NO CAP`" |
| "scores quality", "an LLM judges it", "AI rubric" | the LLM rubric was cut; qualitative criteria are recorded `unscored` (`docs/limitations.md` item 33) | "deterministic `format`, `links`, and `chain` checks" |
| "the evaluator stakes a bond" | `MIN_BOND` is 0 on the deployed contract (`docs/limitations.md` items 1, 28) | "what is at stake today is zero — that is on the limitations list" |
| "the challenge window protects you" | `challenge`/`resolve` are stubs; the 120-second window is pure latency, and a wrong verdict cannot be undone by anyone (`docs/limitations.md` items 2, 26) | do not mention the window at all, except as a limitation |
| "autonomous agent", "a watcher monitors the chain" | the agent is invoked per job with `--job-id` (ADR-022, `docs/limitations.md` item 9) | "the agent runs per job, as a fresh process" |
| "audited", "production-ready", "100% coverage", any performance number | no report produces them | — |
| "paid the same whether it passes or rejects" | the up-front fee via x402 is an ADR-004 **design**, not a shipped feature (`docs/limitations.md` items 14, 23; ADR-025 decision 3) | "we have not fixed the fee incentive yet, and it is on our limitations list" |
| "providers build trust through a good history" | the cap is one-way; it can only tighten (`docs/limitations.md` item 8) | "memory can only tighten the cap" |
| any English paraphrase of the Indonesian `reason`/`proof` strings that the screen does not show | those bytes are what `reasonHash` commits to | quote them as-is, then explain in English |

## E. Must be said at least once

1. `make demo` needs internet access to `sepolia.base.org` — **two `eth_call` view calls, no funds, no transactions** (section 1).
2. The budget is **identical**; the only difference is the memory (section 6, `claim step=C-vs-D` line).
3. The coarse defect is **still rejected** without memory (section 6, `VARIANT A` line).
4. The sentence: "Delete our memory, and you get an ordinary stateless evaluator — exactly our competitors." (section 6).
5. The self-declared limitations: verdict cannot be undone, zero bond, funds stuck (section 7).
6. No LLM and no qualitative scoring (section 4).
7. Why some strings stay Indonesian: they are the hashed bundle bytes (section 3, and again briefly in 4 and 5).

## F. Post-recording checklist (before upload)

- [ ] Total duration 2:00–5:00 (target 4:35).
- [ ] Not a single sentence from table D was spoken.
- [ ] No private key, `.env` contents, or personal address visible on screen (check the terminal title bar too).
- [ ] The `claim step=C-vs-D` line is legible at upload resolution (test by watching at 720p).
- [ ] The `/panel` memory-wipe control never appears and is never clicked.
- [ ] `make demo` exits 0 inside the recording.
- [ ] Every Indonesian string read on screen was explained in English, and the explanation matches the bytes.

## G. Plan B — the NORMAL path for TAKE-1 (not a contingency)

The measured runtime of **3m23s–3m56s** does not fit the window sections 2–5 provide (± 2m35s), so treat
this section as the **primary** path, not a fallback. `make demo` is deterministic — two runs produced an
**empty** diff over the 32 deterministic lines — so Plan B changes no number at all, only where the screen
content comes from:

1. Run `make demo 2>&1 | tee /tmp/take1-demo.log` **before** recording, and leave Terminal A holding the
   full output. If it dies in PREFLIGHT (A2b), just run it again; do not change anything.
2. In section 1, replace "while it runs" with: **"I ran this command right before recording; this is its
   output verbatim."** — say it out loud; do not let the viewer think it is live.
3. Section 6 is unchanged: `grep` over that same `/tmp/take1-demo.log`.

What you **must not** do: cut out the part that failed and still narrate its result, or paste output from a
run other than the one named on screen.

## H. Claim → evidence (for judges checking the video line by line)

| Claim in the video | Evidence |
|---|---|
| five real jobs on Base Sepolia, 418–422 | `web/public/jobs.json`; tx links in the "VerdictPosted tx" column; `docs/limitations.md` item 25 |
| job 420 rejected while `Funded` because budget > cap | `/verdict/420` gate card; `JobRejected` tx `0x78a3a65d…989e` (`docs/evidence.md` "Rantai A → B → C") |
| cap 250,000, `sample_size` 0, incidents 418 & 419 | bundle `web/public/verdicts/420.json`; `docs/limitations.md` item 8 |
| the gate `reason` is quoted, not translated, because it is hashed | `web/src/app/verdict/[jobId]/page.jsx:50-56`; bundle `web/public/verdicts/420.json` |
| deliverable 421 == 422 byte for byte, different verdicts | `sha_keccak` `0x246071b3…0a51` in `demo/deliverables/421.json` & `422.json`; `docs/limitations.md` item 25 |
| `MemoryRootUpdated` for job 422, root `0x999a9570…9b7d` | tx `0xe95910d2…5830`; topic0 `0xc6028d32…7923` (`docs/limitations.md` items 7 & 22) |
| the panel runs genuinely deterministic checks | `web/src/lib/checks.js`, `POST /api/evaluate`; parity guarded by `web/test/checks-parity.test.js` |
| qualitative criteria `unscored`, zero LLM | `agent/agent/criteria.py:121-124`, locked by `agent/tests/test_criteria.py:336-337`; `docs/limitations.md` item 33 |
| identical budget, only the memory differs | line `[demo] claim step=C-vs-D` (`sim/src/demo.ts:902-908`) |
| wiping memory lowers the depth, it does not switch the evaluator off | line `[demo] claim step=D-vs-E` (`sim/src/demo.ts:909-915`) |
| without memory: `depth=sampling`, `cap=NO CAP`, coarse defect still rejected | line `VARIANT A:` (`sim/src/demo.ts:929-935`) |
| memory lost on a live vault → safe mode, zero tx | line `VARIANT B:` (`sim/src/demo.ts:946-949`); guard aborts at `sim/src/demo.ts:672-687` |
| `make demo` only reads Sepolia, no funds/tx | `Makefile:50-54`; `sim/src/demo.ts:610-611`; before/after nonce in the `VARIANT B` line |
| PREFLIGHT fails hard, in the first second, before Anvil | `sim/src/demo.ts:304-357` |
| limitations are self-declared | `README.md` section "Limitations & trust assumptions" (summary); `docs/limitations.md` items 1, 4, 26 |
| MIT licence | `LICENSE` |
