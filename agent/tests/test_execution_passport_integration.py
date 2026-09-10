"""Local-chain A–E acceptance test for the Execution Passport MVP."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time

import pytest
from web3 import Web3

from agent.passport_demo import run


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# Kunci akun 0 Anvil, diterbitkan Foundry. Di berkas tes ia boleh ditulis apa adanya:
# pemindai konstanta 32-byte di `test_verdict_root.py` sengaja hanya melihat modul di
# bawah `agent/agent/`, karena yang dijaganya adalah jalur keputusan, bukan alat uji.
ANVIL_ACCOUNT_0_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


@pytest.mark.skipif(shutil.which("anvil") is None, reason="Anvil is required for local-chain integration")
def test_demo_proves_memory_recall_rejection_execution_and_deletion(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PASSPORT_DEMO_KEY", ANVIL_ACCOUNT_0_KEY)
    port = _free_port()
    rpc_url = f"http://127.0.0.1:{port}"
    anvil = subprocess.Popen(
        ["anvil", "--chain-id", "84532", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            if Web3(Web3.HTTPProvider(rpc_url)).is_connected():
                break
            time.sleep(0.1)
        else:
            pytest.fail("Anvil did not become available")

        run(rpc_url, tmp_path / "memory-one.db")
        first_output = capsys.readouterr().out
        run(rpc_url, tmp_path / "memory-two.db")
        output = capsys.readouterr().out
    finally:
        anvil.terminate()
        anvil.wait(timeout=5)

    assert "before_memory_decision=human-review-required" in output
    assert "stored_hypothesis=stale-oracle-rebalance/v1" in output
    assert "fresh_process_recall=stale-oracle-rebalance/v1" in output
    assert "thresholds_from_memory=oracle=60 reserve=250000" in output
    assert "invalid_passport_rejected=calldata-mismatch" in output
    assert "accepted_rebalance=exactly-once" in output
    assert "passport_memory_deleted=True" in output
    assert "after_delete_decision=human-review-required" in output
    stable_lines = (
        "stored_hypothesis=stale-oracle-rebalance/v1",
        "fresh_process_recall=stale-oracle-rebalance/v1",
        "thresholds_from_memory=oracle=60 reserve=250000",
        "accepted_rebalance=exactly-once",
        "passport_memory_deleted=True after_delete_decision=human-review-required",
    )
    for line in stable_lines:
        assert line in first_output
        assert line in output
