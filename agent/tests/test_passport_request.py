"""CLI permintaan passport: yang diuji adalah barisnya dan kode keluarnya, tanpa jaringan."""

from __future__ import annotations

from eth_abi import encode as abi_encode
from sibyl_memory_client import MemoryClient
from web3 import Web3

import agent.execution_passport as ep
import agent.memory_policy as mp
from agent.passport_request import EXIT_BLOCK, EXIT_ISSUED, exit_code_for, request

BETA = "0xc3c6bf20dde1a547a35f6479d54b08e1548daeff"
TREASURY = "0x68cca28dcefad1c7a73f97facc74cd51b145772b"
DEPLOYMENT = {"chain_id": 84532, "treasury": TREASURY, "verifier": TREASURY}
ANCHOR = Web3.to_hex(Web3.keccak(text="anchor:100000"))


def _client(tmp_path):
    client = MemoryClient.local(str(tmp_path / "m.db"))
    calldata = "0x" + (ep.REBALANCE_SELECTOR + abi_encode(["uint256"], [100_000])).hex()
    action = ep.ActionProposal(
        chain_id=84532,
        target=TREASURY,
        selector="0x" + ep.REBALANCE_SELECTOR.hex(),
        calldata=calldata,
        value=0,
        state_block_number=100,
        state_block_hash=ANCHOR,
    )
    ep.record_incident(
        client,
        ep.IncidentEvidence(
            incident_id="request-test",
            incident_type=ep.INCIDENT_TYPE,
            action=action,
            oracle_timestamp=1_000,
            observed_at=1_120,
            evidence_digest=Web3.to_hex(Web3.keccak(text=action.action_digest)),
        ),
    )
    return client


def _request(client):
    return request(
        client,
        executor=BETA,
        amount=100_000,
        deployment=DEPLOYMENT,
        now=2_000,
        oracle_timestamp=1_990,
        anchor_number=100,
        anchor_hash=ANCHOR,
        nonce=5,
    )


def test_clean_executor_is_issued_and_lines_are_fixed(tmp_path):
    decision, lines = _request(_client(tmp_path))
    joined = "\n".join(lines)
    assert decision.decision == "passport-issued"
    assert f"executor={BETA}" in joined
    assert "acp_profile=none risk_level=0" in joined
    assert "actor_standing=satisfied max_risk_level=0" in joined
    assert "decision=passport-issued" in joined
    assert "memory_root=0x" in joined
    assert exit_code_for(decision) == EXIT_ISSUED


def test_risky_executor_is_blocked_with_job_ids(tmp_path):
    client = _client(tmp_path)
    mp.record_suspicion(client, BETA, "format.bad", mp.Evidence(job_id=423, check_id="format"))
    mp.record_suspicion(client, BETA, "format.bad", mp.Evidence(job_id=424, check_id="format"))
    mp.promote_suspicions(client, BETA)

    decision, lines = _request(client)
    joined = "\n".join(lines)
    assert decision.decision == "block"
    assert "acp_profile=found risk_level=2 incident_jobs=423,424" in joined
    assert "actor_standing=unsatisfied" in joined
    assert exit_code_for(decision) == EXIT_BLOCK
