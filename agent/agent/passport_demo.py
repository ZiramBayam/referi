"""Unedited, non-UI Execution Passport MVP demo.

Run from the repository with Anvil already listening:

    uv run python -m agent.passport_demo

The default Anvil account/key are test-only values. No real funds or RPC credentials are
used. The demo deletes only its explicit Passport Control Hypothesis reference at the end
of the deletion-control step.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from eth_abi import encode as abi_encode
from eth_account import Account
from sibyl_memory_client import MemoryClient
from web3 import Web3

from agent.execution_passport import (
    DEFAULT_MIN_RESERVE,
    REBALANCE_SELECTOR,
    ActionProposal,
    DeterministicEnvironment,
    IncidentEvidence,
    delete_control_hypothesis,
    evaluate_rebalance_for_passport,
    memory_root_hex,
    record_incident,
    simulate_rebalance,
)
from agent.passport_client import LocalPassportClient

DEFAULT_RPC = "http://127.0.0.1:8545"
# Kunci akun #0 Anvil, DITURUNKAN dari mnemonic default Anvil, bukan ditulis sebagai
# konstanta 32-byte — jalur produksi `agent/` dijaga bebas konstanta semacam itu.
Account.enable_unaudited_hdwallet_features()
ANVIL_KEY = "0x" + Account.from_mnemonic(
    "test test test test test test test test test test test junk",
    account_path="m/44'/60'/0'/0/0",
).key.hex().removeprefix("0x")


def _calldata(amount: int) -> str:
    return "0x" + (REBALANCE_SELECTOR + abi_encode(["uint256"], [amount])).hex()


def _commit_hash() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def run(rpc_url: str, memory_db: Path | None = None) -> None:
    client = LocalPassportClient(rpc_url, ANVIL_KEY)
    caller = client.address
    print(f"commit={_commit_hash()}")
    print(f"chain_id={client.chain_id} executor=anvil-local-fresh-process")

    treasury = client.deploy("MockTreasury", caller, 1_000_000, DEFAULT_MIN_RESERVE)
    verifier = client.deploy("PassportVerifier", treasury.address, caller)
    client.send(treasury.functions.configureVerifier(verifier.address))
    oracle = client.deploy("MockOracle", caller)
    print(f"mock_treasury={treasury.address}")
    print(f"passport_verifier={verifier.address}")
    print(f"mock_oracle={oracle.address}")

    own_db = memory_db is None
    temp_dir = None
    if memory_db is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="execution-passport-")
        memory_db = Path(temp_dir.name) / "memory.db"
    else:
        memory_db = memory_db.resolve()
    memory_db.parent.mkdir(parents=True, exist_ok=True)
    memory = MemoryClient.local(str(memory_db))

    initial_latest = client.w3.eth.get_block("latest")
    initial_now = int(initial_latest["timestamp"])
    client.send(oracle.functions.setObservation(initial_now - 120, 1_000))
    latest = client.w3.eth.get_block("latest")
    anchor_number = int(latest["number"])
    anchor_hash = Web3.to_hex(latest["hash"])
    now = int(latest["timestamp"])
    calldata = _calldata(100_000)
    incident_action = ActionProposal(
        chain_id=client.chain_id,
        target=treasury.address,
        selector="0x" + REBALANCE_SELECTOR.hex(),
        calldata=calldata,
        value=0,
        state_block_number=anchor_number,
        state_block_hash=anchor_hash,
    )
    simulation = simulate_rebalance(
        incident_action, current_reserve=1_000_000, minimum_reserve=DEFAULT_MIN_RESERVE
    )
    oracle_timestamp = int(oracle.functions.timestamp().call())
    stale_age = now - oracle_timestamp
    incident = IncidentEvidence(
        incident_id="demo-stale-oracle-001",
        incident_type="stale-oracle-rebalance",
        action=incident_action,
        oracle_timestamp=oracle_timestamp,
        observed_at=now,
        evidence_digest=Web3.to_hex(Web3.keccak(text=incident_action.action_digest)),
    )
    blocked = evaluate_rebalance_for_passport(
        memory,
        incident_action,
        DeterministicEnvironment(
            now=now,
            current_block_number=anchor_number,
            current_block_hash=anchor_hash,
            state_block_timestamp=now,
            oracle_timestamp=now - stale_age,
            simulation_action_digest=simulation.action_digest,
            simulation_succeeded=simulation.success,
            simulated_post_reserve=simulation.simulated_post_reserve,
        ),
        verifier_address=verifier.address,
        issued_at=now,
        nonce=1,
    )
    print(f"incident_oracle_age_seconds={incident.oracle_age_seconds}")
    print(f"incident_timestamps=oracle={oracle_timestamp} observed={now}")
    print(f"incident_digest={incident.evidence_digest}")
    print(f"before_memory_decision={blocked.decision} reason={blocked.reason}")
    remembered = record_incident(memory, incident)
    print(f"stored_hypothesis={remembered.hypothesis_id} memory_root={memory_root_hex(memory)}")

    client.send(oracle.functions.setObservation(now - 5, 1_000))
    fresh_latest = client.w3.eth.get_block("latest")
    fresh_anchor_number = int(fresh_latest["number"])
    fresh_anchor_hash = Web3.to_hex(fresh_latest["hash"])
    fresh_now = int(fresh_latest["timestamp"])
    action = ActionProposal(
        chain_id=client.chain_id,
        target=treasury.address,
        selector="0x" + REBALANCE_SELECTOR.hex(),
        calldata=calldata,
        value=0,
        state_block_number=fresh_anchor_number,
        state_block_hash=fresh_anchor_hash,
    )
    simulation = simulate_rebalance(
        action, current_reserve=1_000_000, minimum_reserve=DEFAULT_MIN_RESERVE
    )
    fresh_oracle_timestamp = int(oracle.functions.timestamp().call())
    print(f"fresh_timestamps=oracle={fresh_oracle_timestamp} observed={fresh_now}")

    recall_code = (
        "import sys; from sibyl_memory_client import MemoryClient; "
        "from agent.execution_passport import load_control_hypotheses; "
        "items=load_control_hypotheses(MemoryClient.local(sys.argv[1])); "
        "print(','.join(item.hypothesis_id for item in items))"
    )
    recall_process = subprocess.run(
        [sys.executable, "-c", recall_code, str(memory_db)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    print(f"fresh_process_recall={recall_process.stdout.strip()} executor_identity=child-process")

    fresh_memory = MemoryClient.local(str(memory_db))
    current = evaluate_rebalance_for_passport(
        fresh_memory,
        action,
        DeterministicEnvironment(
            now=fresh_now,
            current_block_number=fresh_anchor_number,
            current_block_hash=fresh_anchor_hash,
            state_block_timestamp=fresh_now,
            oracle_timestamp=fresh_oracle_timestamp,
            simulation_action_digest=simulation.action_digest,
            simulation_succeeded=simulation.success,
            simulated_post_reserve=simulation.simulated_post_reserve,
        ),
        verifier_address=verifier.address,
        issued_at=fresh_now,
        nonce=2,
    )
    print(
        "recalled_hypothesis="
        f"{current.hypothesis.hypothesis_id if current.hypothesis else 'none'} "
        "obligations="
        f"{','.join(result.obligation_id for result in current.results)}"
    )
    print(
        "thresholds_from_memory="
        f"oracle={current.hypothesis.required_obligations[1].max_age_seconds} "
        f"reserve={current.hypothesis.required_obligations[3].min_reserve}"
    )
    if not current.issued or current.passport is None:
        raise RuntimeError(f"expected passport-issued, got {current.decision}: {current.reason}")

    invalid_calldata = _calldata(100_001)
    try:
        invalid_signature = current.passport.sign(verifier.address, ANVIL_KEY)
        client.execute(verifier, current.passport, invalid_signature, invalid_calldata)
    except Exception as exc:  # web3 exposes provider-specific revert subclasses
        print(f"invalid_passport_rejected=calldata-mismatch error={type(exc).__name__}")
    else:
        raise RuntimeError("mutated calldata unexpectedly executed")

    signature = current.passport.sign(verifier.address, ANVIL_KEY)
    receipt = client.execute(verifier, current.passport, signature, calldata)
    events = client.decode_events(verifier, treasury, receipt)
    print(
        f"accepted_tx={receipt.transactionHash.hex()} "
        f"consumed_nonce={events['passport_consumed'][0]['nonce']}"
    )
    print("accepted_rebalance=exactly-once")

    deleted_reference = delete_control_hypothesis(memory)
    fresh_after_delete = MemoryClient.local(str(memory_db))
    deleted = evaluate_rebalance_for_passport(
        fresh_after_delete,
        action,
        DeterministicEnvironment(
            now=fresh_now,
            current_block_number=fresh_anchor_number,
            current_block_hash=fresh_anchor_hash,
            state_block_timestamp=fresh_now,
            oracle_timestamp=fresh_oracle_timestamp,
            simulation_action_digest=simulation.action_digest,
            simulation_succeeded=simulation.success,
            simulated_post_reserve=simulation.simulated_post_reserve,
        ),
        verifier_address=verifier.address,
        issued_at=fresh_now,
        nonce=3,
    )
    print(f"passport_memory_deleted={deleted_reference} after_delete_decision={deleted.decision}")
    print(f"after_delete_reason={deleted.reason}")
    if deleted.passport is not None or deleted.decision != "human-review-required":
        raise RuntimeError("deleted memory unexpectedly issued a Passport")
    if own_db and temp_dir is not None:
        temp_dir.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", default=os.environ.get("PASSPORT_RPC_URL", DEFAULT_RPC))
    parser.add_argument("--memory-db", type=Path)
    parser.add_argument(
        "--start-anvil",
        action="store_true",
        help="start an isolated Anvil process for this demo and stop it at the end",
    )
    args = parser.parse_args()
    anvil = None
    try:
        if args.start_anvil:
            anvil = subprocess.Popen(
                ["anvil", "--chain-id", "84532", "--port", "8545"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(50):
                try:
                    if Web3(Web3.HTTPProvider(args.rpc_url)).is_connected():
                        break
                except OSError:
                    pass
                import time

                time.sleep(0.1)
            else:
                raise RuntimeError("started Anvil but RPC did not become available")
        run(args.rpc_url, args.memory_db)
    finally:
        if anvil is not None:
            anvil.terminate()
            anvil.wait(timeout=5)


if __name__ == "__main__":
    main()
