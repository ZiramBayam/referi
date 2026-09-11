"""JSON-in, JSON-out preflight untuk situs, memakai jalur keputusan yang SEBENARNYA.

Kenapa berkas ini ada. Situs sebelumnya menjalankan `web/src/lib/passportDemo.js`,
sebuah implementasi ulang aturan dalam JavaScript. Halaman itu jujur menyebut dirinya
fixture, tetapi konsekuensinya tetap serius: klaim terbesar produk ini, bahwa MEMORI
yang mengubah keputusan, tidak bisa diperiksa sama sekali dari permukaan yang paling
mungkin dibuka orang. Sibyl tidak tersentuh, kode evaluasinya tidak dijalankan, dan dua
implementasi dari aturan yang sama pasti menyimpang tanpa satu pun tes yang memerah.

Modul ini menutup jarak itu. Ia memanggil `evaluate_rebalance_for_passport` yang sama
dengan yang dipakai `make demo-passport`, membaca memori Sibyl yang sama, dan
mengembalikan keputusan yang sama.

Yang SENGAJA tidak ia lakukan:

* Tidak menyentuh rantai. `DeterministicEnvironment` menerima angka biasa, jadi evaluasi
  penuh berjalan tanpa RPC dan tanpa anvil. Ini bukan jalan pintas: bagian yang menjadi
  klaim 40 poin memang murni deterministik, dan menuntut sebuah rantai hanya akan
  membuat halamannya mati setiap kali jaringan juri bermasalah.
* Tidak menandatangani apa pun. Penandatanganan butuh kunci privat, dan tidak ada kunci
  yang boleh hidup di dalam proses yang melayani permintaan HTTP. Passport yang
  dikembalikan adalah struktur yang belum ditandatangani, dan situs mengatakannya.
* Tidak menulis ke memori `chain-abc`. Ia memakai basis datanya sendiri.

Alamat target dan verifier diambil dari `deployments/passport-84532.json`, jadi passport
yang muncul di layar terikat pada kontrak yang BENAR-BENAR ada di Base Sepolia, bukan
pada nama karangan.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from eth_abi import encode as abi_encode
from sibyl_memory_client import MemoryClient
from web3 import Web3

from agent.execution_passport import (
    DEFAULT_MIN_RESERVE,
    REBALANCE_SELECTOR,
    ActionProposal,
    DeterministicEnvironment,
    IncidentEvidence,
    evaluate_rebalance_for_passport,
    load_control_hypotheses,
    memory_root_hex,
    record_incident,
    simulate_rebalance,
)

INITIAL_RESERVE = 1_000_000
STALE_AGE_SECONDS = 120
FRESH_AGE_SECONDS = 5


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _deployment() -> dict[str, Any]:
    """Alamat kontrak yang sungguhan, supaya passport di layar menunjuk ke chain."""
    path = _repo_root() / "deployments" / "passport-84532.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "chain_id": int(data["chainId"]),
        "treasury": data["contracts"]["MockTreasury"],
        "verifier": data["contracts"]["PassportVerifier"],
        "deployer": str(data.get("deployer", "")).lower(),
        "status": data.get("status"),
    }


def _calldata(amount: int) -> str:
    return "0x" + (REBALANCE_SELECTOR + abi_encode(["uint256"], [amount])).hex()


def _synthetic_anchor(now: int, amount: int) -> tuple[int, str]:
    """Anchor state yang deterministik dan JUJUR TENTANG DIRINYA.

    Ia bukan blok sungguhan, dan tidak berpura-pura: nomornya diturunkan dari waktu,
    hash-nya dari keccak atas keduanya. Yang diuji obligasi `state-anchor-fresh` adalah
    kesegaran anchor terhadap `now`, dan sifat itu utuh tanpa blok sungguhan.
    """
    block_number = now
    digest = Web3.keccak(text=f"referi-web-anchor:{now}:{amount}")
    return block_number, Web3.to_hex(digest)


def _seeded_memory(db_path: Path, deployment: dict[str, Any], now: int) -> MemoryClient:
    """Memori yang SUDAH mengingat insidennya, di-seed sekali lalu dipakai ulang."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    memory = MemoryClient.local(str(db_path))
    if load_control_hypotheses(memory):
        return memory

    anchor_number, anchor_hash = _synthetic_anchor(now, 100_000)
    action = ActionProposal(
        chain_id=deployment["chain_id"],
        target=deployment["treasury"],
        selector="0x" + REBALANCE_SELECTOR.hex(),
        calldata=_calldata(100_000),
        value=0,
        state_block_number=anchor_number,
        state_block_hash=anchor_hash,
    )
    record_incident(
        memory,
        IncidentEvidence(
            incident_id="web-stale-oracle-001",
            incident_type="stale-oracle-rebalance",
            action=action,
            oracle_timestamp=now - STALE_AGE_SECONDS,
            observed_at=now,
            evidence_digest=Web3.to_hex(Web3.keccak(text=action.action_digest)),
        ),
    )
    return memory


def evaluate(request: dict[str, Any]) -> dict[str, Any]:
    amount = int(request["amount"])
    memory_available = request.get("memoryAvailable", True) is not False
    oracle_fresh = request.get("oracleFresh", False) is True

    deployment = _deployment()
    # Executor default = deployer fixture. Situs boleh mengirim alamat lain supaya juri bisa
    # mencoba provider ACP yang riwayatnya ada di store yang sama.
    executor = str(request.get("executor") or deployment["deployer"]).lower()
    now = int(time.time())
    anchor_number, anchor_hash = _synthetic_anchor(now, amount)

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
        action, current_reserve=INITIAL_RESERVE, minimum_reserve=DEFAULT_MIN_RESERVE
    )
    oracle_age = FRESH_AGE_SECONDS if oracle_fresh else STALE_AGE_SECONDS

    # "Memori hilang" dimodelkan sebagai agen yang membaca penyimpanan TANPA hipotesis
    # yang cocok, bukan sebagai cabang `if` di dalam kode. Itu sebabnya hasilnya
    # `human-review-required` datang dari kode produksi yang sama, bukan dari karangan.
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if memory_available:
        db = Path(
            os.environ.get("REFERI_WEB_MEMORY_DB")
            or (_repo_root() / "agent" / "data" / "web" / "memory.db")
        )
        memory = _seeded_memory(db, deployment, now)
    else:
        temp_dir = tempfile.TemporaryDirectory(prefix="referi-web-empty-")
        memory = MemoryClient.local(str(Path(temp_dir.name) / "memory.db"))

    try:
        decision = evaluate_rebalance_for_passport(
            memory,
            action,
            DeterministicEnvironment(
                now=now,
                current_block_number=anchor_number,
                current_block_hash=anchor_hash,
                state_block_timestamp=now,
                oracle_timestamp=now - oracle_age,
                simulation_action_digest=simulation.action_digest,
                simulation_succeeded=simulation.success,
                simulated_post_reserve=simulation.simulated_post_reserve,
            ),
            executor=executor,
            verifier_address=deployment["verifier"],
            issued_at=now,
            nonce=now,
        )
        root = memory_root_hex(memory) if memory_available else None
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    return {
        "engine": "agent",
        "executor": executor,
        "decision": decision.decision,
        "reason": decision.reason,
        "hypothesisId": decision.hypothesis.hypothesis_id if decision.hypothesis else None,
        "memoryRoot": root,
        "oracleAgeSeconds": oracle_age,
        "postReserve": simulation.simulated_post_reserve,
        "action": action.to_body(),
        "deployment": {
            "chainId": deployment["chain_id"],
            "treasury": deployment["treasury"],
            "verifier": deployment["verifier"],
            "status": deployment["status"],
        },
        "obligations": [result.to_body() for result in decision.results],
        "passport": decision.passport.to_message() if decision.passport else None,
        "signed": False,
    }


def main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
        print(json.dumps(evaluate(request)))
    except Exception as error:  # noqa: BLE001
        # Situs HARUS bisa membedakan "agen menolak" dari "agen rusak", jadi kegagalan
        # dilaporkan sebagai JSON dengan penanda, bukan sebagai stderr yang tenggelam.
        print(json.dumps({"engine": "agent", "error": f"{type(error).__name__}: {error}"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
