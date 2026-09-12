# Actor standing: Virtuals verdicts change Base permissions, and the Base contract enforces it

Date: 2026-09-11. Status: approved in chat, implementation follows via a written plan.

## Goal

Earn the 1.25 multiplier honestly. The rubric (`docs/spec.md:58`) applies it only when judges
confirm the Base plus Virtuals integration is "doing real work". Today both gates share one Sibyl
store and one root, but no decision on either gate changes because of data from the other. This
design adds one flow, in one direction, that a judge can click through on Base Sepolia:

> A provider's verdict history on Virtuals ACP decides whether the Base gate issues that provider
> an Execution Passport, and `PassportVerifier` refuses to let anyone else use it.

## Non-goals

- No change to `derive_cap`, `promote_suspicions`, or ADR-002. The Base gate only READS provider
  profiles that the ACP gate wrote. Nothing flows Base to Virtuals.
- No change to `EvaluatorVault` (frozen, ADR-022).
- No new memory categories. Provider profiles and the Control Hypothesis are the only inputs.
- No claim that Execution Passport sends transactions to ACP. It still guards `MockTreasury`.

## Section 1: contracts

`contracts/src/PassportVerifier.sol`:

- `struct ExecutionPassport` gains `address executor` immediately after `target`. The EIP-712
  typehash string is updated in the same position. `PASSPORT_VERSION` becomes `2`.
- `execute()` gains `if (msg.sender != passport.executor) revert WrongExecutor();` placed after
  the `WrongTarget` check and before the signature check.
- `event PassportConsumed` gains `address indexed executor` as the third indexed topic.
- Nothing else changes. The verifier still does not read Sibyl, ACP, or an oracle.

`contracts/src/MockTreasury.sol` is unchanged in source but must be redeployed, because
`configureVerifier` is one-shot (`MockTreasury.sol:33-39`). `MockOracle` is redeployed by the same
script for simplicity; the script already deploys all three.

Tests (`contracts/test/ExecutionPassportVerifier.t.sol`): wrong executor reverts with
`WrongExecutor`; correct executor succeeds and the event carries it; the fixed digest vector is
regenerated for v2 and must match the Python side byte for byte.

Deploy: `DeployPassport.s.sol` unchanged. Run with the `0xfA4F11Ec…9911` keystore so
`policySigner` stays the same. `deployments/passport-84532.json` is rewritten with the new
addresses; the v1 addresses move into a `previous` block in the same file so nothing is lost.

## Section 2: the obligation, in memory

New proof id `PROOF_ACTOR: Final = "actor-standing"`, added to `MVP_PROOF_IDS`.

`ObligationDefinition` gains one optional field `max_risk_level: int | None`. It is only
meaningful for `actor-standing`; the constructor rejects it on other ids.

`ExecutionPassport` gains `executor: str` (lowercase, validated like `target`), placed after
`target` in the EIP-712 message. `ActionProposal` and the action digest are unchanged, so incident
evidence and hypothesis scope matching are untouched. `evaluate_rebalance_for_passport` takes
`executor` as a required keyword.

`evaluate_obligations` takes `executor_profile: ProviderProfile | None` as a keyword. The decision
path reads the profile itself (see Section 3) and passes it in, so the evaluator stays pure.

Evaluation rule for `actor-standing`, with no default pass:

| Observation | Result |
|---|---|
| profile not read (`executor_profile_read=False`) | `unverifiable` |
| profile read, no entity for this address | `satisfied`, observed `risk_level=0, acp_history=none` |
| `risk_level > max_risk_level` | `unsatisfied` |
| `confirmed_patterns` non-empty | `unsatisfied` |
| otherwise | `satisfied` |

"No entity means satisfied" is deliberate and stated: a clean provider and an unknown address
look the same to ACP too. The block reason names the ACP jobs that decided it:
`actor-standing: executor 0x2021…b321 risk_level=2 incident_jobs=418,419 > max 0`.

`initial_control_hypothesis` adds `ObligationDefinition(PROOF_ACTOR, max_risk_level=0)` as the
fifth obligation. The threshold lives in the stored hypothesis, not in code: a store whose
hypothesis lacks the obligation does not check actors, and `make demo-passport` proves that by
deleting the hypothesis the same way it does today.

`ControlHypothesis.from_body` accepts bodies with or without the fifth obligation, so the
existing `agent/data/web/memory.db` keeps loading.

## Section 3: reading the profile, and which store

`evaluate_rebalance_for_passport` reads the executor's profile through the existing
decision-path reader (`load_snapshot(client).providers.get(executor)`), inside the same memory
lock, before evaluating obligations. This is the only new read. It never reads `suspicion`
entities, matching ADR-002 rule 1.

The store is whatever `client` the caller passes. For the dual-gate claim to be true on the
operational path, the passport CLI and the web preflight must read the SAME database the ACP gate
writes:

- `agent.passport_preflight` keeps `REFERI_WEB_MEMORY_DB` and defaults to `agent/data/web/memory.db`
  (the web demo store). No change.
- New CLI `agent.passport_request` (Section 4) takes `--db`, defaulting to `SIBYL_DB_PATH` from
  `.env`, which is the ACP operational store. That is the path the testnet demo uses.

## Section 4: demo flow and commands

New module `agent/agent/passport_request.py`, a thin CLI over the existing decision function:

```
uv run python -m agent.passport_request --executor 0x… --amount 100000 [--db PATH] [--rpc URL]
    [--sign] [--execute-with-keystore NAME]
```

- Without `--sign`: prints the decision lines and exits 0 on `passport-issued`, 3 on `block`,
  4 on `human-review-required`. Zero transactions.
- With `--sign`: also signs the passport with the policy signer keystore (Foundry keystore, ADR-016
  style, never a raw key) and writes `passport-<nonce>.json`.
- With `--execute-with-keystore NAME`: submits `PassportVerifier.execute` from that keystore, which
  must be the executor. Prints the tx hash and the `PassportConsumed` executor topic.

Printed lines (quoted by docs, so fixed):

```
executor=0x…
acp_profile=found|none risk_level=N incident_jobs=… confirmed_patterns=…
actor_standing=satisfied|unsatisfied|unverifiable max_risk_level=0
decision=passport-issued|block|human-review-required
reason=…
memory_root=0x…
```

Testnet sequence for the judge-facing proof, run once by hand and recorded in
`docs/evidence.md`:

1. `make demo` style ACP jobs are NOT reused. Instead, two new ACP jobs for Beta with a
   deterministic defect (`sim/scenarios/coarse-defect.md`), each rejected by the vault via
   `agent.vault_client --job-id N --kind reject`. After the second, Beta's profile holds
   `incident_jobs` of two jobs and `risk_level=2`.
2. Before step 1, Beta requests and executes a passport: `PassportConsumed` on the new verifier
   with `executor=Beta`. This is the "clean provider gets permission" transaction.
3. After step 1, the same request for Beta prints `decision=block` with the two job ids. Alpha,
   whose history is rebuilt by the same mechanism or simply absent, is not needed for the proof
   and is not claimed.
4. `make dual-gate` is extended to print the executor lines for the seeded demo provider so the
   zero-network command shows the same mechanism.

Order matters and is stated in the docs: the passport must be consumed BEFORE the two rejections,
otherwise there is no "before" transaction to point at.

## Section 5: tests

- `agent/tests/test_execution_passport.py`: obligation table above, one test per row; digest
  fixed vector for v2; `from_body` accepts old bodies.
- `agent/tests/test_dual_gate_memory.py`: `test_acp_rejections_block_the_base_passport`. Seed a
  store, issue for Beta, add two incident jobs through `_add_confirmed_pattern`'s public path
  (`promote_suspicions` with two deterministic quarantine entries), issue again, expect `block`
  naming both jobs. This is the test that locks the multiplier claim.
- `agent/tests/test_passport_request.py`: CLI formatting against a temp store, no network.
- Foundry: Section 1.
- Web: `web/test` parity tests updated for the new `executor` field in the passport message.

## Section 6: docs

- ADR-035 in `docs/decisions.md`: actor standing, why read-only, why "unknown is satisfied", why
  the verifier needed a v2, and the v1 addresses retained.
- `README.md`: the Gate 2 section names `actor-standing` as the fifth obligation and the
  `passport_request` command; "If you only have 3 minutes" gains one line.
- `docs/posts/05-2026-09-11-verdict-virtuals-mengubah-izin-base.md`: the flow with the tx links.
- `docs/evidence.md`: the four transactions.
- `docs/limitations.md` gains one item: the executor binding proves who used the passport, not
  that the executor is the same legal party as the ACP provider; it is the same key, which is the
  strongest identity link available without ERC-8004.
- `demo/video-script.md`: one beat replacing the 3:52 row with the block line.

## What this does not fix

Item 16 of `docs/limitations.md` still holds for `EvaluatorVault`: the ACP root has no on-chain
consequence. This design does not touch that. The passport side is different: `PassportVerifier`
now enforces two things the memory decided (the calldata and the executor).
