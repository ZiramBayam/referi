# Reproduction & destructive test

Item numbers on this page refer to [`docs/limitations.md`](limitations.md).

## Core commands

```
make doctor    # print toolchain versions, exit 1 if they do not match docs/versions.md
make test      # forge test + uv run pytest + pnpm -r test (the third = 5 parity tests in web/;
               # sim/ still has no tests — item 18)
make demo      # §7 steps 1-4 from SCRATCH on local Anvil, deterministic summary, then TWO
               # destructive variants; variant B READS the frozen Sepolia vault — needs internet
               # (read only: no funds, no transactions — item 34)
               # MEASURED RUNTIME: 3m23s and 3m56s across two runs. The "~2m20s" figure that was
               # once written down comes from task 3.3, BEFORE the two destructive variants and the
               # network preflight were added — do not use it to plan a recording.
```

`make doctor` reads `node`/`forge` from a PATH that only an interactive shell loads — run it from a
normal terminal, not from a non-interactive hook (its red message explains this itself).

## Running the A/B/C chain yourself

The A/B/C chain runs through explicit commands, one job per invocation. These commands run a **new**
chain on **your own** vault; they do not reproduce jobs 418/419/420 on the submission vault, whose
`agent` is immutable and ours (item 20):

```
# 1. jobs A/B: createJob → setBudget → fund → submit (all three via the Virtuals SDK)
DELIVERABLE_TEXT=... pnpm --filter sim run job:min

# 2. job C: stop after fund, so gating happens while the status is Funded
BUDGET_RAW=2000000 STOP_AFTER=fund pnpm --filter sim run job:min

# 3. the agent evaluates one job (without --kind: exit 2, zero RPC, zero tx)
cd agent && uv run python -m agent.vault_client --job-id <jobId> --kind reject

# 4. audit the memory root from an export file, without touching the DB
cd agent && uv run python -m agent.memory_export --check /tmp/mem.json

# 5. (OPTIONAL, outside `make demo`) UI: judge panel + memory-wipe button.
#    Terminal 1 — web:
DEMO_MODE=1 pnpm --filter web start          # http://127.0.0.1:3000/panel
#    Terminal 2 — the DEMO memory-wipe server; WITHOUT it the button answers 503
#    reset_server_unreachable (the same command is shown inside the panel):
cd agent && DEMO_MODE=1 uv run python -m agent.demo_reset --host 127.0.0.1 --port 8010
```

**Step 5 is not run by `make demo` and is deliberately NOT used in the demo video.** The judge panel
(`/panel`) works without it — the **only** thing that needs a second process is the memory-wipe button,
because the database lives in `agent/`, outside the frontend folder boundary
(`web/src/app/panel/MemoryControl.jsx:27-28` shows the same command in the UI). The button has power
**only** over demo memory, and its security-review history is in item 36. The destructive test that
serves as submission evidence is run by `make demo`, not by this button.

A verdict cannot be overridden by a flag: if a deterministic check fails (`Evaluation.passed == False`)
or the cap gate rejects, the result is REJECT whatever `--kind` says.

## Reproducing the depth demo (item 25)

This needs TWO providers, because the only difference between jobs 421 and 422 is the provider's history.
The selector is `PROVIDER_SLOT` (`sim/src/client_min.ts:102,160-162`), with two valid values: `alpha`
(default, key `PROVIDER_PRIVATE_KEY` — the provider that already has two incidents on our chain) and
`beta` (`PROVIDER2_PRIVATE_KEY` — a clean provider):

```
# CLEAN provider → depth sampling → first two sections only → PASS
PROVIDER_SLOT=beta  BUDGET_RAW=250000 DELIVERABLE_FILE=sim/scenarios/depth-demo.md \
  pnpm --filter sim run job:min

# RISKY provider (2 incidents) → depth full → the third section is read → REJECTED
PROVIDER_SLOT=alpha BUDGET_RAW=250000 DELIVERABLE_FILE=sim/scenarios/depth-demo.md \
  pnpm --filter sim run job:min
```

As with the A/B/C chain, this runs **new** jobs on your own vault and does **not** reproduce jobs 421/422
on the submission vault (item 20). What decides the outcome is not any flag but whether that provider's
memory already holds two incidents — so the order you run them in matters.

## Troubleshooting: exit code 4 on a fresh vault

**On a FRESH vault, step 3 needs TWO invocations, and the first exits with code 4.** That is not a
malfunction: the first invocation creates `memory.db` midway, so the planned mode (`naive`) no longer
matches the mode read just before signing (`normal`), and the `MODE_DRIFT` guard refuses to transact —
**zero tx, fail-closed**. The second invocation on the same job runs to completion and exits 0.

**That exit 4 CANNOT be avoided by creating the DB first.** An earlier README version suggested
`memory_export --db … --out …` for that; that recipe **cannot be run**, because the export tool
deliberately refuses to create a new DB (see item 7):

```
$ cd agent && uv run python -m agent.memory_export --db ./data/baru/memory.db --out /tmp/mem.json
GAGAL: MemoryExportError: DB memori tidak ditemukan: ./data/baru/memory.db — jalankan agen dulu, atau
tunjuk file yang ada dengan --db (alat ini sengaja TIDAK membuat DB baru)
```

So the way through really is to **run the agent twice**: the first invocation creates the DB and exits 4
with zero transactions, the second produces the verdict. `make demo` does exactly that and prints it
as-is (`agent.retry … firstExit=4`) rather than hiding it.

This was decided and measured in **ADR-026** (decision 6 requires the README to mention it), and its
consequence is zero bytes on chain: the root, depth, and cap announced are the same on either path.

## Destructive test

The most reasonable question a judge can ask: if the memory is deleted, does anything change?
Run **6 Sep 2026 on local Anvil** (zero transactions to Base Sepolia; the submission vault and the
A/B/C-chain memory files were unchanged — md5 identical before and after).

> **Read this table as a report, not as evidence.** The script now EXISTS — `make demo` runs both
> destructive variants (item 19) — but it leaves not a single file behind: there is no log, fixture, or
> companion file in the repo you could match against this table, and the md5 above has no companion
> either. What you can verify yourself today: the on-chain A/B/C chain, and a `make demo` run you do
> yourself and then compare by eye.

```
# FRESH vault on Anvil: lastMemoryRoot() = 0, providerCap(provider) = 0
# SIBYL_DB_PATH points at a path that never existed; agent/data/ is NOT deleted
cd agent && uv run python -m agent.vault_client --job-id <job C> --kind reject
```

| Condition | Result |
|---|---|
| **No memory file, FIRST invocation** | the start gate reads `mode=naive`, then `plan_job` **CREATES** `memory.db` when it opens `MemoryClient.local()`; the gate re-read before the tx now sees that file EXISTS → `mode=normal`, while `plan.mode` is still `naive` → the **`MODE_DRIFT`** guard refuses. Result: **`EXIT_REFUSED` (exit code 4)**, `sent_transactions == []`, **zero `postVerdict`**, `cast logs JobRejected` EMPTY |
| **No memory file, SECOND invocation** (same job) | runs to completion: `mode=normal`, `depth=sampling`, `cap=TANPA CAP gate=lolos`, `postVerdict` + `finalize` land, **exit 0** |
| **Memory file restored** (same chain, same command) | `cap=250000 gate=DITOLAK` → `postVerdict(REJECT)` → `Finalized(kind=2)`, `JobRejected` APPEARS, the job moves to status 4, the client is fully refunded |

**The first row is a REFUSAL, not an acceptance — and an earlier README version wrote it up as an
acceptance.** What happens is not "the agent passed the job because its memory was gone"; what happens is
that the agent **refuses to transact at all** because the mode it planned no longer matches the mode it
read just before signing. The behaviour is fail-closed and self-healing on the next invocation. This is
recorded and accepted as-is in **ADR-026**, including its consequence: **on a fresh vault, day one needs
TWO `--job-id` invocations, and the first exits with code 4.** An operator who is not told will read that
exit 4 as a malfunction. ADR-026 decision (e) also measures that the difference is **zero bytes on
chain**: `empty_memory_root()` and the root over a freshly created empty DB are exactly the same value
(`0x4e2a1ca1…ff5a`), and the depth and cap are identical.

A consequence that must be read alongside it: **`MODE NAIF` has never been the mode that produced a
verdict via the CLI.** It only appears as a log line from the first invocation (ADR-026 decision 4 and
consequences). The README, the video, and the build-in-public posts are **forbidden** from presenting it
as a production path.

The empty result on the first row is not a false pass: a positive control for `JobFunded` over an
IDENTICAL range and filter shape still returns logs. And the evidence bundle on the second row names
`cap.usdc 250000` + `incident_jobs [418, 419]` — the **existence** of that cap traces back to jobs A and
B on Base Sepolia, not to a rule firing without history. What must be read with it: the **number**
250,000 is still a team constant divided by 4, with `sample_size: 0` in that same bundle (item 8). What
memory changes is **whether a gate exists at all**, not the size of the number.

> **Delete our memory, and you get an ordinary stateless evaluator — exactly our competitors.**

What does **not** change when memory is gone: the criteria layer and the deterministic checks still run,
so blatant defects are still rejected. What is lost is calibration — check depth, learned cheating
patterns, and cap gating (`docs/spec.md` §3 rule 6). Important note: a "blatant" defect is the
**position** of the same `TODO` token inside the sampling window, not a scored severity — item 19.

An honest note about the environment: the variant above runs on a **fresh** vault (on-chain root = 0). On
the live submission vault, deleting `memory.db` triggers **safe mode**, not degradation — the agent stops
entirely and the job hangs until `expiredAt` (item 10). **Both variants are now run by a single
`make demo` command**: variant A on local Anvil, variant B against the frozen Sepolia vault — read only,
no funds, no transactions, and the run is aborted if the evidence does not appear (items 19 and 34). What
is missing is not the automation but the artifacts: that command leaves no log or fixture in the repo.
