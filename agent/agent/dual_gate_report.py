"""Laporan baca-saja: satu memori, dua gerbang, satu root.

Kenapa berkas ini ada. Kedua gerbang Referi sudah berbagi satu store Sibyl dan satu
fungsi root, tetapi tidak ada satu pun perintah yang menunjukkannya. Argumen terbesar
submission karena itu hanya bisa dipercaya, tidak bisa diperiksa. Modul ini mengubahnya
jadi keluaran yang bisa dijalankan siapa pun.

Ia TIDAK menulis apa pun ke memori mana pun kecuali database sementara yang ia buat
sendiri saat dijalankan tanpa argumen, dan ia tidak menyentuh jaringan sama sekali.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from sibyl_memory_client import MemoryClient
from web3 import Web3

import agent.execution_passport as ep
import agent.memory_policy as mp

DEMO_PROVIDER = "0x20212e4d95a75e6716575ed26e884cdeff66b321"
DEMO_TREASURY = "0x68Cca28DceFAd1c7a73f97FACC74cD51B145772B"


def _seed_demo_store(db_path: Path) -> None:
    """Isi store contoh: satu provider gerbang ACP, satu hipotesis gerbang passport."""
    from eth_abi import encode as abi_encode

    client = MemoryClient.local(str(db_path))
    mp.save_provider(
        client, mp.ProviderProfile(address=DEMO_PROVIDER, risk_level=1, passed_budgets=(1_000,))
    )
    calldata = "0x" + (ep.REBALANCE_SELECTOR + abi_encode(["uint256"], [100_000])).hex()
    action = ep.ActionProposal(
        chain_id=84532,
        target=DEMO_TREASURY,
        selector="0x" + ep.REBALANCE_SELECTOR.hex(),
        calldata=calldata,
        value=0,
        state_block_number=100,
        state_block_hash=Web3.to_hex(Web3.keccak(text="dual-gate-anchor")),
    )
    ep.record_incident(
        client,
        ep.IncidentEvidence(
            incident_id="dual-gate-demo",
            incident_type="stale-oracle-rebalance",
            action=action,
            oracle_timestamp=1_000,
            observed_at=1_120,
            evidence_digest=Web3.to_hex(Web3.keccak(text=action.action_digest)),
        ),
    )


def report(db_path: str | None = None) -> list[str]:
    """Kembalikan baris laporan. Tanpa `db_path`, buat store contoh sementara."""
    temp_dir = None
    if db_path is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="referi-dual-gate-")
        path = Path(temp_dir.name) / "dual-gate.db"
        _seed_demo_store(path)
    else:
        path = Path(db_path)

    try:
        client = MemoryClient.local(str(path))
        snapshot = mp.load_snapshot(client)
        hypotheses = [k for k in snapshot.patterns if k.startswith(ep.HYPOTHESIS_KEY)]
        root = mp.memory_root_for_onchain(client)
        covers_both = bool(snapshot.providers) and bool(hypotheses)

        return [
            f"memory_db={path}",
            f"gate_acp_providers={len(snapshot.providers)}",
            f"gate_acp_provider_ids={','.join(sorted(snapshot.providers)) or 'none'}",
            f"gate_passport_hypotheses={len(hypotheses)}",
            f"gate_passport_keys={','.join(sorted(hypotheses)) or 'none'}",
            f"shared_pattern_namespace={mp.REFERENCE_PATTERN_PREFIX}",
            f"shared_memory_root=0x{root.hex()}",
            f"root_covers_both_gates={covers_both}",
            "root_function=agent.memory_policy.memory_root_for_onchain",
            "announced_onchain_by=EvaluatorVault.postVerdict(jobId,kind,reasonHash,memoryRoot)",
        ]
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="store Sibyl yang mau diperiksa")
    args = parser.parse_args()
    for line in report(args.db):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
