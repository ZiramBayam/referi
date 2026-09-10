"""Minta, tandatangani, dan (opsional) eksekusi SATU Execution Passport untuk SATU executor.

Kenapa berkas ini ada. Jembatan Virtuals -> Base baru terbukti kalau seseorang bisa
meminta passport atas nama sebuah alamat, dan jawabannya berubah sesudah alamat itu
ditolak di ACP. Perintah ini adalah cara memintanya, dan barisnya dikutip di dokumentasi.

Kunci TIDAK PERNAH masuk lewat argumen. `--signer-key-env` dan `--executor-key-env` hanya
menyebut NAMA variabel lingkungan; tanpa keduanya perintah ini nol transaksi dan nol tanda
tangan. Store default adalah `SIBYL_DB_PATH` dari `.env`, yaitu memori operasional gerbang
ACP, supaya yang dibaca gerbang Base memang memori yang ditulis gerbang Virtuals.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from eth_abi import encode as abi_encode
from eth_account import Account
from sibyl_memory_client import MemoryClient
from web3 import Web3

from agent.execution_passport import (
    DEFAULT_MIN_RESERVE,
    PROOF_ACTOR,
    REBALANCE_SELECTOR,
    ActionProposal,
    DeterministicEnvironment,
    PassportDecision,
    evaluate_rebalance_for_passport,
    generate_nonce,
    memory_root_hex,
    simulate_rebalance,
)
from agent.memory_policy import normalize_address
from agent.passport_client import artifact, passport_tuple

EXIT_ISSUED = 0
EXIT_ERROR = 1
EXIT_BLOCK = 3
EXIT_REVIEW = 4
DEFAULT_RPC = "https://sepolia.base.org"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_deployment() -> dict[str, Any]:
    """Alamat fixture yang sungguhan di Base Sepolia, dibaca dari catatan deploy."""
    path = _repo_root() / "deployments" / "passport-84532.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "chain_id": int(data["chainId"]),
        "treasury": data["contracts"]["MockTreasury"].lower(),
        "verifier": data["contracts"]["PassportVerifier"].lower(),
        "oracle": data["contracts"]["MockOracle"].lower(),
        "rpc": data.get("rpcUrl", DEFAULT_RPC),
    }


def _calldata(amount: int) -> str:
    return "0x" + (REBALANCE_SELECTOR + abi_encode(["uint256"], [int(amount)])).hex()


def request(
    client: Any,
    *,
    executor: str,
    amount: int,
    deployment: dict[str, Any],
    now: int,
    oracle_timestamp: int,
    anchor_number: int,
    anchor_hash: str,
    nonce: int,
    current_reserve: int = 1_000_000,
) -> tuple[PassportDecision, list[str]]:
    """Jalur keputusan yang sama dengan demo dan situs. Murni: nol RPC, nol tanda tangan."""
    executor = normalize_address(executor)
    action = ActionProposal(
        chain_id=deployment["chain_id"],
        target=deployment["treasury"],
        selector="0x" + REBALANCE_SELECTOR.hex(),
        calldata=_calldata(amount),
        value=0,
        state_block_number=anchor_number,
        state_block_hash=anchor_hash,
    )
    simulation = simulate_rebalance(
        action, current_reserve=current_reserve, minimum_reserve=DEFAULT_MIN_RESERVE
    )
    decision = evaluate_rebalance_for_passport(
        client,
        action,
        DeterministicEnvironment(
            now=now,
            current_block_number=anchor_number,
            current_block_hash=anchor_hash,
            state_block_timestamp=now,
            oracle_timestamp=oracle_timestamp,
            simulation_action_digest=simulation.action_digest,
            simulation_succeeded=simulation.success,
            simulated_post_reserve=simulation.simulated_post_reserve,
        ),
        executor=executor,
        verifier_address=deployment["verifier"],
        issued_at=now,
        nonce=nonce,
    )
    actor = next((r for r in decision.results if r.obligation_id == PROOF_ACTOR), None)
    lines = [f"executor={executor}"]
    if actor is None:
        lines.append("acp_profile=unread")
        lines.append("actor_standing=unverifiable max_risk_level=none")
    else:
        obs = actor.observed
        lines.append(
            f"acp_profile={obs.get('acp_history', 'unread')} risk_level={obs.get('risk_level', 0)} "
            f"incident_jobs={','.join(str(j) for j in obs.get('incident_jobs', [])) or 'none'} "
            f"confirmed_patterns={','.join(obs.get('confirmed_patterns', [])) or 'none'}"
        )
        lines.append(
            f"actor_standing={actor.result} max_risk_level={actor.threshold.get('max_risk_level')}"
        )
    lines.append(f"decision={decision.decision}")
    lines.append(f"reason={decision.reason}")
    lines.append(f"memory_root={memory_root_hex(client)}")
    return decision, lines


def exit_code_for(decision: PassportDecision) -> int:
    return {"passport-issued": EXIT_ISSUED, "block": EXIT_BLOCK}.get(decision.decision, EXIT_REVIEW)


def _contract(w3: Web3, address: str, name: str) -> Any:
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=artifact(name)["abi"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor", required=True, help="alamat yang akan mengeksekusi passport")
    parser.add_argument("--amount", type=int, default=100_000)
    parser.add_argument("--db", default=os.environ.get("SIBYL_DB_PATH", "./data/memory.db"))
    parser.add_argument("--rpc", default=None)
    parser.add_argument("--signer-key-env", default=None, help="NAMA env var kunci policy signer")
    parser.add_argument("--executor-key-env", default=None, help="NAMA env var kunci executor")
    parser.add_argument("--out", default=None, help="tulis passport + tanda tangan ke berkas JSON")
    args = parser.parse_args()

    deployment = load_deployment()
    rpc = args.rpc or deployment["rpc"]
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        print(f"rpc_unreachable={rpc}")
        return EXIT_ERROR
    latest = w3.eth.get_block("latest")
    oracle = _contract(w3, deployment["oracle"], "MockOracle")
    treasury = _contract(w3, deployment["treasury"], "MockTreasury")
    client = MemoryClient.local(str(Path(args.db)))
    decision, lines = request(
        client,
        executor=args.executor,
        amount=args.amount,
        deployment=deployment,
        now=int(latest["timestamp"]),
        oracle_timestamp=int(oracle.functions.timestamp().call()),
        anchor_number=int(latest["number"]),
        anchor_hash=Web3.to_hex(latest["hash"]),
        nonce=generate_nonce(),
        current_reserve=int(treasury.functions.reserve().call()),
    )
    print(f"memory_db={Path(args.db)}")
    print(f"passport_verifier={deployment['verifier']}")
    for line in lines:
        print(line)
    if not decision.issued or decision.passport is None:
        return exit_code_for(decision)

    if args.signer_key_env is None:
        print("signed=False (beri --signer-key-env untuk menandatangani)")
        return EXIT_ISSUED
    signer_key = os.environ[args.signer_key_env]
    signature = decision.passport.sign(deployment["verifier"], signer_key)
    print(f"signed=True signer={Account.from_key(signer_key).address.lower()}")
    calldata = _calldata(args.amount)
    if args.out:
        Path(args.out).write_text(
            json.dumps(
                {"passport": decision.passport.to_message(), "signature": signature, "calldata": calldata},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"passport_file={args.out}")

    if args.executor_key_env is None:
        return EXIT_ISSUED
    executor_account = Account.from_key(os.environ[args.executor_key_env])
    if executor_account.address.lower() != normalize_address(args.executor):
        print("executor_key_mismatch=True")
        return EXIT_ERROR
    verifier = _contract(w3, deployment["verifier"], "PassportVerifier")
    tx = verifier.functions.execute(
        passport_tuple(decision.passport), bytes.fromhex(signature[2:]), bytes.fromhex(calldata[2:])
    ).build_transaction(
        {
            "from": executor_account.address,
            "nonce": w3.eth.get_transaction_count(executor_account.address, "pending"),
            "chainId": deployment["chain_id"],
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = executor_account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        print(f"execute_tx={tx_hash.hex()} status=reverted")
        return EXIT_ERROR
    consumed = verifier.events.PassportConsumed().process_receipt(receipt)
    executor_topic = consumed[0]["args"]["executor"].lower() if consumed else "none"
    print(f"execute_tx={tx_hash.hex()} consumed_executor={executor_topic}")
    return EXIT_ISSUED


if __name__ == "__main__":
    raise SystemExit(main())
