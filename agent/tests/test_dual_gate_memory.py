"""Kedua gerbang berbagi SATU memori, dan root yang diumumkan on-chain mengikat keduanya.

Ini properti yang sudah benar di kode hari ini tetapi tidak dibuktikan di mana pun. Tanpa
tes ini, memindahkan Control Hypothesis keluar dari namespace `pattern:` akan memutus
klaim terbesar submission tanpa satu pun tes memerah.
"""

from __future__ import annotations

import pathlib

from eth_abi import encode as abi_encode
from sibyl_memory_client import MemoryClient
from web3 import Web3

import agent.execution_passport as ep
import agent.memory_policy as mp

# Provider Beta dari `.env.example`. HURUF KECIL wajib: `load_snapshot` menolak alamat
# ber-checksum karena ia akan dijangkar root tetapi tidak pernah dibaca jalur keputusan.
PROVIDER = "0x20212e4d95a75e6716575ed26e884cdeff66b321"
TREASURY = "0x68Cca28DceFAd1c7a73f97FACC74cD51B145772B"


def build_incident(target: str, amount: int) -> ep.IncidentEvidence:
    """Bukti insiden oracle basi yang deterministik, dipakai kedua tes lintas gerbang."""
    calldata = "0x" + (ep.REBALANCE_SELECTOR + abi_encode(["uint256"], [amount])).hex()
    action = ep.ActionProposal(
        chain_id=84532,
        target=target,
        selector="0x" + ep.REBALANCE_SELECTOR.hex(),
        calldata=calldata,
        value=0,
        state_block_number=100,
        state_block_hash=Web3.to_hex(Web3.keccak(text=f"anchor:{amount}")),
    )
    return ep.IncidentEvidence(
        incident_id=f"dual-gate-{amount}",
        incident_type="stale-oracle-rebalance",
        action=action,
        oracle_timestamp=1_000,
        observed_at=1_120,
        evidence_digest=Web3.to_hex(Web3.keccak(text=action.action_digest)),
    )


def _store(tmp_path: pathlib.Path) -> MemoryClient:
    return MemoryClient.local(str(tmp_path / "dual-gate.db"))


def test_one_store_holds_both_gates(tmp_path):
    client = _store(tmp_path)
    mp.save_provider(client, mp.ProviderProfile(address=PROVIDER, risk_level=1))
    ep.record_incident(client, build_incident(TREASURY, 100_000))

    snapshot = mp.load_snapshot(client)

    assert PROVIDER in snapshot.providers, "profil provider gerbang ACP hilang dari snapshot"
    assert ep.HYPOTHESIS_KEY in snapshot.patterns, "hipotesis gerbang passport hilang dari snapshot"


def test_onchain_root_commits_to_the_passport_gate(tmp_path):
    client = _store(tmp_path)
    mp.save_provider(client, mp.ProviderProfile(address=PROVIDER, risk_level=1))
    root_before = mp.memory_root_for_onchain(client)

    ep.record_incident(client, build_incident(TREASURY, 100_000))
    root_after = mp.memory_root_for_onchain(client)

    # Kalau ini pernah gagal, artinya hipotesis passport keluar dari preimage root, dan
    # root yang diumumkan `postVerdict` berhenti mengikat kebijakan gerbang Base.
    assert root_before != root_after
    assert len(root_after) == 32


def test_passport_hypothesis_lives_in_the_shared_pattern_namespace():
    # Bukan detail penamaan: prefix inilah yang membuat hipotesis masuk `MemorySnapshot`
    # (ADR-020 keputusan 7). Memindahkannya keluar memutus jangkar on-chain.
    assert ep.HYPOTHESIS_KEY.startswith(mp.REFERENCE_PATTERN_PREFIX)


def test_deleting_the_hypothesis_moves_the_root_back(tmp_path):
    client = _store(tmp_path)
    mp.save_provider(client, mp.ProviderProfile(address=PROVIDER, risk_level=1))
    baseline = mp.memory_root_for_onchain(client)

    ep.record_incident(client, build_incident(TREASURY, 100_000))
    assert mp.memory_root_for_onchain(client) != baseline

    ep.delete_control_hypothesis(client)
    assert mp.memory_root_for_onchain(client) == baseline


def test_report_names_both_gates_and_one_root(tmp_path):
    from agent.dual_gate_report import report

    client = _store(tmp_path)
    mp.save_provider(client, mp.ProviderProfile(address=PROVIDER, risk_level=1))
    ep.record_incident(client, build_incident(TREASURY, 100_000))

    lines = report(str(tmp_path / "dual-gate.db"))
    joined = "\n".join(lines)

    assert "gate_acp_providers=1" in joined
    assert "gate_passport_hypotheses=1" in joined
    assert "shared_memory_root=0x" in joined
    assert "root_covers_both_gates=True" in joined
