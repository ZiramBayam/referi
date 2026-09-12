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
import json
import tempfile
from pathlib import Path
from typing import Any

from sibyl_memory_client import MemoryClient
from web3 import Web3

import agent.execution_passport as ep
import agent.memory_policy as mp
from agent.memory_lock import locked_client

DEMO_PROVIDER = "0x20212e4d95a75e6716575ed26e884cdeff66b321"
DEMO_TREASURY = "0x68Cca28DceFAd1c7a73f97FACC74cD51B145772B"


def _seed_demo_store(db_path: Path) -> None:
    """Isi store contoh: satu provider gerbang ACP, satu hipotesis gerbang passport."""
    from eth_abi import encode as abi_encode

    client = MemoryClient.local(str(db_path))
    # Riwayat provider dibangun lewat jalur ACP yang asli (karantina dua job, lalu promosi),
    # bukan dengan menulis risk_level langsung, supaya angka yang dilaporkan bisa ditelusuri.
    mp.save_provider(client, mp.ProviderProfile(address=DEMO_PROVIDER, passed_budgets=(1_000,)))
    mp.record_suspicion(client, DEMO_PROVIDER, "format.bad", mp.Evidence(job_id=418, check_id="format"))
    mp.record_suspicion(client, DEMO_PROVIDER, "format.bad", mp.Evidence(job_id=419, check_id="format"))
    mp.promote_suspicions(client, DEMO_PROVIDER)
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


def _executor_standing_lines(
    providers: dict[str, Any], patterns: dict[str, Any], hypotheses: list[str]
) -> list[str]:
    """Nilai standing provider pertama terhadap obligasi `actor-standing` di hipotesis.

    Ini pembacaan yang sama dengan jalur keputusan passport (profil provider + ambang dari
    memori), diulang di sini hanya untuk dilaporkan. Tidak ada keputusan yang diambil.
    """
    if not providers or not hypotheses:
        return []
    executor = sorted(providers)[0]
    profile = mp.ProviderProfile.from_body(executor, providers[executor])
    body = patterns.get(hypotheses[0])
    if isinstance(body, str):
        # Body reference disimpan sebagai teks JSON oleh Sibyl; profil provider sudah dict.
        body = json.loads(body)
    if not isinstance(body, dict):
        return []
    hypothesis = ep.ControlHypothesis.from_body(body)
    actor = next(
        (o for o in hypothesis.required_obligations if o.obligation_id == ep.PROOF_ACTOR), None
    )
    if actor is None or actor.max_risk_level is None:
        return [f"demo_executor={executor}", "demo_executor_standing=unverifiable"]
    disqualified = profile.risk_level > actor.max_risk_level or bool(profile.confirmed_patterns)
    return [
        f"demo_executor={executor}",
        f"demo_executor_risk_level={profile.risk_level} incident_jobs="
        f"{','.join(str(j) for j in profile.incident_jobs) or 'none'}",
        f"demo_executor_standing={'unsatisfied' if disqualified else 'satisfied'} "
        f"max_risk_level={actor.max_risk_level}",
    ]


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
        # Satu kunci mengikat pembacaan daftar dan root ke keadaan store yang sama.
        with locked_client(client):
            view = mp.DecisionMemoryView(client)
            providers = {name: body for name, body in view.raw_providers()}
            patterns = view.raw_references(mp.REFERENCE_PATTERN_PREFIX)
            root = mp.memory_root_for_onchain(client)
        hypotheses = [k for k in patterns if k.startswith(ep.HYPOTHESIS_KEY)]
        covers_both = bool(providers) and bool(hypotheses)
        standing_lines = _executor_standing_lines(providers, patterns, hypotheses)

        return [
            f"memory_db={path}",
            f"gate_acp_providers={len(providers)}",
            f"gate_acp_provider_ids={','.join(sorted(providers)) or 'none'}",
            f"gate_passport_hypotheses={len(hypotheses)}",
            f"gate_passport_keys={','.join(sorted(hypotheses)) or 'none'}",
            f"shared_pattern_namespace={mp.REFERENCE_PATTERN_PREFIX}",
            f"shared_memory_root=0x{root.hex()}",
            f"root_covers_both_gates={covers_both}",
            *standing_lines,
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
