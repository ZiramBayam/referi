# Execution Passport — Reproduction Guide

This guide runs the non-UI MVP on a local Anvil chain. It never uses real funds, a real
oracle, a real treasury, or the frozen Base Sepolia deployment.

## Prerequisites

- Foundry `forge`/`anvil` compatible with `contracts/foundry.toml`.
- Python and `uv` compatible with `docs/versions.md`.
- The dependencies in `agent/pyproject.toml` installed by `uv`.

The demo uses Anvil’s first test account only. Its private key is embedded solely as an
Anvil fixture value in `agent/agent/passport_demo.py`; it is not a production key.

## One-command demo

From the repository root:

```sh
make demo-passport
```

The command starts an isolated Anvil chain at chain ID `84532`, deploys `MockTreasury` and
`PassportVerifier`, runs the memory/control loop, and stops Anvil when complete.

## Expected sequence

The output must contain these labelled facts:

```text
before_memory_decision=human-review-required
incident_timestamps=oracle=<unix-seconds> observed=<unix-seconds>
stored_hypothesis=stale-oracle-rebalance/v1
fresh_process_recall=stale-oracle-rebalance/v1
fresh_timestamps=oracle=<unix-seconds> observed=<unix-seconds>
thresholds_from_memory=oracle=60 reserve=250000
invalid_passport_rejected=calldata-mismatch
accepted_rebalance=exactly-once
passport_memory_deleted=True after_delete_decision=human-review-required
```

The transaction hash and commit hash vary per run. The sequence is the acceptance evidence:

1. A stale oracle observation (`120` seconds old) is rejected by bootstrap policy and then
   written as deterministic incident evidence.
2. Sibyl stores `pattern:passport.control-hypothesis.stale-oracle-rebalance.v1`.
3. A child Python process opens the same database as a different executor and reads the
   hypothesis. This is a real process boundary, not an in-memory object handoff.
4. The agent evaluates the four obligations from that stored hypothesis and signs an
   EIP-712 Passport.
5. The verifier rejects the same Passport if one calldata amount changes, then executes
   the exact original rebalance once.
6. Only the Passport Control Hypothesis reference is deleted atomically. A fresh client
   still sees unrelated shared memory but no Passport hypothesis, and returns
   `human-review-required` without creating a Passport.

## Direct tests

```sh
rtk sh -lc 'cd contracts && forge test --match-path test/ExecutionPassportVerifier.t.sol'
rtk sh -lc 'cd agent && uv run pytest tests/test_execution_passport.py -q'
rtk sh -lc 'cd agent && uv run ruff check agent/execution_passport.py agent/passport_client.py agent/passport_demo.py tests/test_execution_passport.py'
```

The full Foundry suite must also pass after contract changes:

```sh
rtk sh -lc 'cd contracts && forge test'
```

## Memory read/write/delete locations

- Write: `agent/agent/execution_passport.py::record_incident` calls
  `save_control_hypothesis` and writes the `pattern:passport.*` reference through Sibyl.
- Read: `load_control_hypotheses` enumerates the existing decision-path `pattern:` references
  and `evaluate_rebalance_for_passport` selects the exact action-scoped hypothesis.
- Delete control: `agent/agent/execution_passport.py::delete_control_hypothesis` removes
  only the Passport reference in an atomic Sibyl storage transaction, creates a fresh client,
  and verifies `human-review-required` with no passport.
- Root: Passport references remain inside the repository’s existing
  `memory_root_for_onchain` gate; the new module does not call `memory_root` directly.

## Trust and scope limitations

- `MockTreasury` is internal accounting, not a token vault.
- `MockOracle` is a timestamp fixture, not an oracle security model.
- The configured policy signer attests to off-chain proof results; the verifier does not
  query Sibyl, simulation, oracle data, or chain state.
- The contract is not an audited Safe Guard and must not control real funds.
- Simulation success, oracle freshness, and a reserve invariant do not prove economic safety.
- The MVP supports only `treasury-rebalance`; migration, parameter-change, and upgrade
  obligations remain roadmap work.
