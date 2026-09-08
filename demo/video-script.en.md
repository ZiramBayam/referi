# Demo video script — TAKE-1 (English)

English pair of `demo/video-script.md` (Indonesian). Same timings, same sections, same evidence.
Only the **spoken** column and the recorder-facing guidance are translated. If the two files ever
disagree, this one is the recording script for the submitted video; the Indonesian one stays as the
operator's reference.

This is an **operational** script: read it while recording the screen, not as prose. Every row names
**what is typed/clicked**, **what appears on screen**, and **what is said**.

- Target duration: **4 minutes 35 seconds** (safe range 4:20–4:50; rubric requires 2–5 minutes).
- Flow = `docs/spec.md` §7 steps 1–5. Steps 1–4 = one `make demo` command; step 5 = three routes in the browser.
- What gets recorded is **frozen code** (ADR-030). Do not edit anything between takes.
- Recording hard stop: **9 Sep 18:00** (ADR-028 decision 2).

### Reading Indonesian output on an English take

The program's terminal output and the web UI labels are **in Indonesian** and are **left untranslated
in this script on purpose** — they will appear on screen exactly as written here. Where a line is
quoted verbatim, an English gloss follows in parentheses. Speak the gloss; do not read the Indonesian
line aloud, and do not paraphrase the Indonesian line into something the screen does not say.

---

## A. Pre-flight (do this BEFORE pressing record)

| # | Command / action | What must happen | If it fails |
|---|---|---|---|
| A1 | `cd /home/zirambayam/referi && make doctor` | exits with code 0 | do not record; toolchain does not match `docs/versions.md` |
| A2 | Make sure you have internet access to `https://sepolia.base.org` | `make demo` checks this in a PREFLIGHT step in its first second (`Makefile:50-54`) | with no network `make demo` stops with exit 1 before Anvil starts |
| A3 | **Timed dry run**: `time make demo 2>&1 \| tee /tmp/dryrun-demo.log`, wait for it to finish | exit 0; the lines `VARIAN A:` and `VARIAN B:` are printed; write down the runtime — measured at **3m23s** and **3m56s**, so expect **Plan B** | if not, fix the environment first — never record a failure and narrate it as a success |
| A4 | `pnpm --filter web build` | build finishes without errors | — |
| A5 | Terminal B: `DEMO_MODE=1 pnpm --filter web start` | server on `http://127.0.0.1:3000` (`-H 127.0.0.1` is pinned in `web/package.json:9`) | — |
| A6 | Open 4 browser tabs, ordered left→right: (1) `http://127.0.0.1:3000/`, (2) `http://127.0.0.1:3000/verdict/420`, (3) `http://127.0.0.1:3000/verdict/422`, (4) `https://base-sepolia.blockscout.com/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384?tab=logs` | all four fully loaded before recording starts; **Blockscout**, not BaseScan — that is where event names are decoded (see the Section 4 note) | a tab still loading eats seconds you do not have |
| A7 | Terminal A: `cd /home/zirambayam/referi && clear`, large font (≥ 16pt), width ≥ 120 columns | clean prompt | — |
| A8 | Close notifications, personal tabs, and wallet extensions | clean screen | — |
| A9 | **Rehearse section 5 first**: `/panel` → button "deliverable job 422" → run `sampling`, then `full` | `sampling` → `format.no-placeholder` **pass**; `full` → **fail** | if that is not the result, cut section 5 from the script and move its 30 seconds into section 6 — do not narrate a result that does not appear |

**Note on `DEMO_MODE=1`:** with that gate on, `/panel` also renders the **memory-wipe control**, which is
**out of scope for TAKE-1**: it is not in this script and not rehearsed in A9. While recording, **do not
click it and do not scroll down to it** (this script stops at the "Hasil" card). If you do not need the
gate at all, run A5 without `DEMO_MODE=1` — the entire script still works.

> Scope note, not a safety note: that surface once carried a **BLOCK** verdict from the security review.
> The block has since been **lifted** — the re-review returned zero CRITICAL and zero HIGH, and the last
> MEDIUM (TOCTOU on ancestor path components) was closed via the `dir_fd` path. README limitation 36 now
> records the full history, including the LOW risk still accepted. It is left out of TAKE-1 because the
> script is full at 4:35 and the control was never rehearsed, not because it is unsafe. On camera: do not
> comment on it in either direction.

---

## B. Screen layout

- **Terminal A** (left / fullscreen during sections 1 and 6): where `make demo` runs.
- **Browser** (sections 2–5): the four tabs from A6.
- **START FROM THE ASSUMPTION THAT YOU ARE USING PLAN B (section G).** The **measured** runtime of
  `make demo` is **3m23s and 3m56s** across two runs — longer than the ± 2 minute 35 second window that
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
| 0:20 | Type and run: `make demo 2>&1 \| tee /tmp/take1-demo.log` | lines `[demo] start …`, `[demo] anvil.up …` start scrolling | "This is The Evaluator: an ERC-8183 referee whose memory of each provider can be recomputed from files. This single command builds the chain from scratch on local Anvil, then reads one frozen vault on Base Sepolia — only two `eth_call` view calls: **no funds, no transactions**. While it runs, let me show you what already landed on chain." |

> On-screen evidence: `Makefile:62-63`; internet requirement `Makefile:50-54`; `sim/src/demo.ts:610-611`
> ("only two `eth_call` view calls").

### Section 2 — Timeline of jobs 418–422 (0:40 – 1:25, 45 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 0:40 | Switch to tab 1 (`/`) | table "Timeline job 418–422 (Base Sepolia)" (timeline of jobs 418–422) | "Five jobs that really landed on Base Sepolia. Jobs 418 and 419: the same provider, the deterministic `format` check failed twice — two incidents from two different jobs." |
| 1:00 | Move the cursor over rows 418, 419, then 420 | Verdict column reads `reject`, the "tx VerdictPosted" column holds BaseScan links | "Job 420 is the interesting one: it was rejected **while still `Funded`** — before the provider had submitted anything at all. Its bundle shape is `gate-rejection`." |
| 1:15 | Click "buka bukti" ("open evidence") on row **420** (or switch to tab 2) | page `/verdict/420` loads | "Why? The full evidence is on this page." |

> On-screen evidence: `web/src/app/page.jsx:13`; data from `web/public/jobs.json`; this page makes zero RPC
> calls — it only renders repo artifacts.

### Section 3 — The cap gate: what memory decided (1:25 – 2:05, 40 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 1:25 | Scroll to the "Keputusan gerbang" (gate decision) card | `diterima? reject` (accepted? reject), `budget 2000000`, `cap provider 250000 (basis baseline-constant, sample_size 0)`, `risk level 2`, `job insiden yang mendasarinya: 418, 419` (underlying incident jobs: 418, 419) | "Budget two million units, cap two hundred and fifty thousand, rejected. The two underlying incident jobs are written into the bundle — 418 and 419 — and you can click them." |
| 1:45 | Point the cursor at `sample_size 0` | same field | "One piece of honesty we wrote into the bundle ourselves: `sample_size` is zero. The **number** two hundred and fifty thousand is a team constant divided by four — what is learned from memory is the **risk level**, and the risk level is what picks the divisor. Memory here can only **tighten** the cap, never loosen it." |
| 1:57 | Point at the `memory_root` field and the `tx VerdictPosted` link in the top card | `memory_root 0xcfdab1b0…`, tx link | "And this reasoning is hash-bound: everything on this page is the bundle that gets keccak-hashed into the `reasonHash` in that transaction." |

> On-screen evidence: bundle `web/public/verdicts/420.json`; README item 8 (`basis: baseline-constant`,
> `sample_size: 0`), item 17 (enforcement lives in the agent; the contract only publishes the cap).

### Section 4 — Identical text, different verdict + on-chain trace (2:05 – 2:45, 40 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 2:05 | Switch to tab 3 (`/verdict/422`) | heading "Verdict job 422 — reject", `kedalaman cek: full` (check depth: full), `hash deliverable 0x246071b3…0a51` | "Jobs 421 and 422 use the **byte-for-byte same** deliverable — identical keccak hash, same budget. Job 421 passed. Job 422 was rejected." |
| 2:18 | Scroll to "Bukti per-kriteria" (per-criterion evidence) | check `format.no-placeholder` **fail**, `section 2`, `depth full` | "The only difference is the provider: one is clean, the other has two incidents. That history raised the check depth from `sampling` to `full`, and the defect — a `TODO` in the third section — is only visible at `full`." |
| 2:30 | Scroll slightly to the yellow "Kriteria yang TIDAK dinilai" (criteria that were NOT scored) card | `qualitative.0` + `unscored_reason` | "I should say this plainly: there is no qualitative scoring and no LLM anywhere in the path. Qualitative criteria are recorded as `unscored`, as-is." |
| 2:37 | Switch to tab 4 (Blockscout, the vault's **Logs** page); point at the top entry: `MemoryRootUpdated` with root `0x999a9570…9b7d` (tx `0xe95910d2…5830`) | the vault log list with **decoded event names**: `MemoryRootUpdated`, `VerdictPosted`, `Finalized`, `ProviderCapSet` | "And here is the on-chain trail. The event name is readable — `MemoryRootUpdated` — because the contract is verified on Sourcify, `exact_match`, from commit `8d3e596`. This is the root that was announced **before** execution." |

> On-screen evidence: README item 25 (the 421 vs 422 table plus four tx hashes), item 33 (`unscored`),
> item 7 (the `MemoryRootUpdated` history), item 15 (Sourcify `exact_match` from commit `8d3e596`).
>
> **Why Blockscout and not BaseScan:** Blockscout imported the Sourcify verification, so the event names
> actually render on camera; Etherscan/BaseScan does not import from Sourcify and verifying there needs an
> API key this repo does not have — so we claim **nothing in either direction** about BaseScan's status
> (`deployments/84532.json:32`). Valid alternative if you trust a terminal more than an explorer: run
> `cast logs` over the blocks listed in README item 7 — but its output is raw topics, so the event name
> will not be visible on screen.

### Section 5 — Judge panel: try it yourself (2:45 – 3:15, 30 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 2:45 | Open `http://127.0.0.1:3000/panel`, click the **"deliverable job 422"** button | textarea fills with three sections: `# Summary`, `## Cara kerja`, `## Catatan lanjutan` | "The judge panel. Load the job 422 deliverable, then pick the depth yourself." |
| 2:55 | Select `sampling (2 bagian pertama)` (first 2 sections) → click **"Jalankan cek"** (run checks) | "Hasil" (result) card: `format.no-placeholder` **pass** | "At `sampling`: it passes." |
| 3:03 | Select `full (seluruh bagian)` (all sections) → click **"Jalankan cek"** | "Hasil" card: `format.no-placeholder` **fail**, third section | "At `full`: it fails. Same text, different depth. Let me state the limit: this panel runs only the `format` and `links` checks inside the local Next process — it does not read memory and it does not send transactions." |

> On-screen evidence: `web/src/app/panel/page.jsx:41-48` (the limits card); check-port parity is guarded by
> `web/test/checks-parity.test.js` (5 tests, `pnpm -r test`).

### Section 6 — The peak: delete the memory (3:15 – 4:10, 55 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 3:15 | Back to Terminal A; `make demo` has finished | last line `[demo] done …` | "That command has finished. The most reasonable question a judge can ask: if the memory is deleted, does anything actually change?" |
| 3:22 | Type: `grep -E '^(VARIAN \|\[demo\] claim )' /tmp/take1-demo.log` | four blocks of lines are printed | — |
| 3:28 | Highlight the `claim step=C-vs-D` line | `budgetRaw=2000000`, `gateWithMemory="DITOLAK (budget 2000000 melebihi cap milestone provider ini (250000; riwayat: 2 insiden terkonfirmasi))"`, `gateWithoutMemory="lolos (budget dalam batas cap)"` — glosses: *with memory = REJECTED, budget exceeds this provider's milestone cap; history: 2 confirmed incidents*; *without memory = passes, budget within the cap* | "Here is the line. The budget is **identical** — two million units. With memory: rejected, and the reason names two confirmed incidents. Without memory: it passes. The only thing that differs is the memory. And the agent is invoked as a **fresh process** for every job — that recall comes from files, not from one long-lived session." |
| 3:48 | Highlight the `VARIAN A:` line | `ROOT ONCHAIN DIRESET, cap hilang (TANPA CAP), mode sampling, cacat halus LOLOS (job 4: LOLOS), cacat kasar DITOLAK (job 5: GAGAL ['format']), 5 tx baru` — gloss: *on-chain root reset, cap gone (NO CAP), sampling mode, the subtle defect PASSES, the blatant defect is still REJECTED, 5 new transactions* | "What is lost when memory is deleted is **calibration**: the cap is gone, the depth drops to `sampling`, and the subtle defect gets through. What is **not** lost: the blatant defect is still rejected — the evaluator does not die, it goes shallow. Delete our memory, and you get an ordinary stateless evaluator — exactly our competitors." |
| 4:00 | Highlight the `VARIAN B:` line | `MODE AMAN, 0 tx baru, nonce 89 -> 89, job menggantung sampai expiredAt, pulih dengan memory.db dari backup` — gloss: *safe mode, 0 new transactions, nonce unchanged 89 to 89, the job hangs until expiredAt, recovery by restoring memory.db from backup* | "That was on a fresh vault. On a vault that is already live, missing memory triggers **safe mode**: zero transactions — measured from the agent wallet's nonce, not just asserted — the job hangs until it expires, and the client gets a full refund." |

> On-screen evidence: `make demo` output lines (`sim/src/demo.ts:902-949`); the safe-mode run is aborted if
> its evidence does not appear (`sim/src/demo.ts:672-687`); the agent is invoked per job (README item 9).
> **Never** call variant A "naive mode": the mode label is `normal`; what shows the degradation is
> `depth=sampling` and `cap=TANPA CAP` (ADR-026, README item 34).

### Section 7 — Honesty + closing (4:10 – 4:35, 25 s)

| Time | Action | Screen | Spoken |
|---|---|---|---|
| 4:10 | Open `README.md` in the editor or on GitHub, scroll to **"Batasan & asumsi kepercayaan"** (limitations & trust assumptions) | the numbered list is visible on screen | "Last, and this sits deliberately at the **very top** of the README, not in a footnote: this project lists its own limitations — a wrong verdict cannot be undone by anyone, the evaluator's bond today is zero, and funds that enter the vault are stuck permanently." |
| 4:25 | Scroll to the "Reproduksi" (reproduction) section | the `make doctor` / `make test` / `make demo` block | "You can run all of it yourself: `make doctor`, `make test`, `make demo`. Public repo, MIT licence. Thank you." |

---

## D. Sentences you must NOT say (the take fails if one of these comes out)

| Do not say | Why | Say instead |
|---|---|---|
| "naive mode" for variant A | the mode label is `normal`; "naive" is only the first invocation log line, which ends in zero transactions (ADR-026, README item 34) | "`depth=sampling`, `cap=TANPA CAP`" |
| "scores quality", "an LLM judges it", "AI rubric" | the LLM rubric was cut; qualitative criteria are recorded `unscored` (README item 33) | "deterministic `format`, `links`, and `chain` checks" |
| "the evaluator stakes a bond" | `MIN_BOND` is 0 on the deployed contract (README items 1, 28) | "what is at stake today is zero — that is on the limitations list" |
| "the challenge window protects you" | `challenge`/`resolve` are stubs; the 120-second window is pure latency, and a wrong verdict cannot be undone by anyone (README items 2, 26) | do not mention the window at all, except as a limitation |
| "autonomous agent", "a watcher monitors the chain" | the agent is invoked per job with `--job-id` (ADR-022, README item 9) | "the agent runs per job, as a fresh process" |
| "audited", "production-ready", "100% coverage", any performance number | no report produces them | — |
| "paid the same whether it passes or rejects" | the up-front fee via x402 is an ADR-004 **design**, not a shipped feature (README items 14, 23; ADR-025 decision 3) | "we have not fixed the fee incentive yet, and that is the first item on the limitations list" |
| "providers build trust through a good history" | the cap is one-way; it can only tighten (README item 8) | "memory can only tighten the cap" |

## E. Must be said at least once

1. `make demo` needs internet access to `sepolia.base.org` — **two `eth_call` view calls, no funds, no transactions** (section 1).
2. The budget is **identical**; the only difference is the memory (section 6, `claim step=C-vs-D` line).
3. The blatant defect is **still rejected** without memory (section 6, `VARIAN A` line).
4. The sentence: "Delete our memory, and you get an ordinary stateless evaluator — exactly our competitors." (section 6).
5. The self-declared limitations: verdict cannot be undone, zero bond, funds stuck (section 7).
6. No LLM and no qualitative scoring (section 4).

## F. Post-recording checklist (before upload)

- [ ] Total duration 2:00–5:00 (target 4:35).
- [ ] Not a single sentence from table D was spoken.
- [ ] No private key, `.env` contents, or personal address visible on screen (check the terminal title bar too).
- [ ] The `claim step=C-vs-D` line is legible at upload resolution (test by watching at 720p).
- [ ] The `/panel` memory-wipe control never appears and is never clicked.
- [ ] `make demo` exits 0 inside the recording.
- [ ] Every Indonesian line read on screen was explained in English, and the explanation matches the line.

## G. Plan B — the NORMAL path for TAKE-1 (not a contingency)

The measured runtime of **3m23s–3m56s** does not fit the window sections 2–5 provide (± 2m35s), so treat
this section as the **primary** path, not a fallback. `make demo` is deterministic (two consecutive runs
give an identical summary), so Plan B changes no number at all — only where the screen content comes from:

1. Run `make demo 2>&1 | tee /tmp/take1-demo.log` **before** recording, and leave Terminal A holding the
   full output.
2. In section 1, replace "while it runs" with: **"I ran this command right before recording; this is its
   output verbatim."** — say it out loud; do not let the viewer think it is live.
3. Section 6 is unchanged: `grep` over that same `/tmp/take1-demo.log`.

What you **must not** do: cut out the part that failed and still narrate its result, or paste output from a
run other than the one named on screen.

## H. Claim → evidence (for judges checking the video line by line)

| Claim in the video | Evidence |
|---|---|
| five real jobs on Base Sepolia, 418–422 | `web/public/jobs.json`; tx links in the "tx VerdictPosted" column; README item 25 |
| job 420 rejected while `Funded` because budget > cap | `/verdict/420` gate card; `JobRejected` tx `0x78a3a65d…989e` (README "Bukti on-chain") |
| cap 250,000, `sample_size` 0, incidents 418 & 419 | bundle `web/public/verdicts/420.json`; README item 8 |
| deliverable 421 == 422 byte for byte, different verdicts | `sha_keccak` `0x246071b3…0a51` in `demo/deliverables/421.json` & `422.json`; README item 25 |
| `MemoryRootUpdated` for job 422, root `0x999a9570…9b7d` | tx `0xe95910d2…5830`; topic0 `0xc6028d32…7923` (README items 7 & 22) |
| the panel runs genuinely deterministic checks | `web/src/lib/checks.js`, `POST /api/evaluate`; parity guarded by `web/test/checks-parity.test.js` |
| qualitative criteria `unscored`, zero LLM | `agent/agent/criteria.py:121-124`, locked by `agent/tests/test_criteria.py:336-337`; README item 33 |
| identical budget, only the memory differs | line `[demo] claim step=C-vs-D` (`sim/src/demo.ts:902-908`) |
| without memory: `depth=sampling`, `cap=TANPA CAP`, blatant defect still rejected | line `VARIAN A:` (`sim/src/demo.ts:929-935`) |
| memory lost on a live vault → safe mode, zero tx | line `VARIAN B:` (`sim/src/demo.ts:946-949`); guard aborts at `sim/src/demo.ts:672-687` |
| `make demo` only reads Sepolia, no funds/tx | `Makefile:50-54`; `sim/src/demo.ts:610-611`; before/after nonce in the `VARIAN B` line |
| limitations are self-declared | `README.md` section "Batasan & asumsi kepercayaan" items 1, 4, 26 |
| MIT licence | `LICENSE` |
