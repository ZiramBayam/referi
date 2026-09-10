"""Small local-chain client for the Execution Passport MVP.

This client is intentionally not a generic wallet or Safe integration. It deploys the
three mock contracts from Foundry artifacts and submits one exact PassportVerifier call.
It never prints or persists the private key.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from eth_account import Account
from web3 import Web3
from web3.contract import Contract

from agent.execution_passport import ExecutionPassport


class PassportClientError(RuntimeError):
    """Local-chain client setup or transaction error."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def artifact(contract_name: str) -> dict[str, Any]:
    path = repo_root() / "contracts" / "out" / f"{contract_name}.sol" / f"{contract_name}.json"
    if not path.exists():
        completed = subprocess.run(
            ["forge", "build"],
            cwd=repo_root() / "contracts",
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0 or not path.exists():
            raise PassportClientError(f"forge build failed: {completed.stderr[-1000:]}")
    return json.loads(path.read_text(encoding="utf-8"))


def passport_tuple(passport: ExecutionPassport) -> tuple[Any, ...]:
    """ABI tuple in the exact Solidity struct declaration order."""

    message = passport.to_message()
    return (
        message["passportVersion"],
        bytes.fromhex(message["actionClass"][2:]),
        message["chainId"],
        Web3.to_checksum_address(message["target"]),
        bytes.fromhex(message["selector"][2:]),
        bytes.fromhex(message["calldataHash"][2:]),
        message["value"],
        message["stateBlockNumber"],
        bytes.fromhex(message["stateBlockHash"][2:]),
        bytes.fromhex(message["hypothesisIdsHash"][2:]),
        bytes.fromhex(message["obligationResultsHash"][2:]),
        bytes.fromhex(message["memoryRoot"][2:]),
        message["issuedAt"],
        message["expiresAt"],
        message["nonce"],
    )


class LocalPassportClient:
    """Transaction client bound to one Anvil account and one local RPC."""

    def __init__(self, rpc_url: str, private_key: str) -> None:
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise PassportClientError(f"cannot connect to {rpc_url}")
        self.account = Account.from_key(private_key)
        self.private_key = private_key

    @property
    def address(self) -> str:
        return self.account.address

    @property
    def chain_id(self) -> int:
        return int(self.w3.eth.chain_id)

    def _transaction(self, function: Any, *, value: int = 0) -> dict[str, Any]:
        nonce = self.w3.eth.get_transaction_count(self.address, "pending")
        return function.build_transaction(
            {
                "from": self.address,
                "value": value,
                "nonce": nonce,
                "chainId": self.chain_id,
                "gas": 2_000_000,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

    def send(self, function: Any, *, value: int = 0) -> Any:
        transaction = self._transaction(function, value=value)
        signed = self.account.sign_transaction(transaction)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise PassportClientError(f"transaction reverted: {tx_hash.hex()}")
        return receipt

    def deploy(self, contract_name: str, *constructor_args: Any) -> Contract:
        data = artifact(contract_name)
        contract = self.w3.eth.contract(abi=data["abi"], bytecode=data["bytecode"]["object"])
        receipt = self.send(contract.constructor(*constructor_args))
        address = receipt.contractAddress
        if not address:
            raise PassportClientError(f"deployment of {contract_name} returned no address")
        return self.w3.eth.contract(address=address, abi=data["abi"])

    def execute(
        self,
        verifier: Contract,
        passport: ExecutionPassport,
        signature: str,
        calldata: str,
    ) -> Any:
        return self.send(
            verifier.functions.execute(
                passport_tuple(passport),
                bytes.fromhex(signature[2:]),
                bytes.fromhex(calldata[2:]),
            ),
            value=passport.value,
        )

    @staticmethod
    def decode_events(
        verifier: Contract, treasury: Contract, receipt: Any
    ) -> dict[str, list[dict[str, Any]]]:
        """Decode only the Passport/Treasury events from a successful receipt."""

        logs = receipt["logs"]
        consumed_event = verifier.events.PassportConsumed()
        rebalanced_event = treasury.events.Rebalanced()
        consumed = [
            consumed_event.process_log(log)
            for log in logs
            if log["address"].lower() == verifier.address.lower()
        ]
        rebalanced = [
            rebalanced_event.process_log(log)
            for log in logs
            if log["address"].lower() == treasury.address.lower()
        ]
        return {
            "passport_consumed": [dict(event["args"]) for event in consumed],
            "rebalanced": [dict(event["args"]) for event in rebalanced],
        }
