"""Bukti baca-saja bahwa gerbang Virtuals benar-benar berjalan di chain.

Tanpa perintah ini, integrasi Virtuals hanya bisa dipercaya lewat tangkapan layar. Ia
membaca kontrak ACP Virtuals yang sungguhan di Base Sepolia dan membandingkan isinya
dengan berkas `web/public/jobs.json` yang dipakai situs.

NOL transaksi, NOL kunci, NOL tulisan ke chain maupun ke memori. Satu-satunya syaratnya
adalah akses jaringan ke RPC. Ketidakcocokan DILAPORKAN, tidak disamarkan: perintah yang
selalu hijau tidak membuktikan apa pun.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from web3 import Web3

ACP_ADDRESS = "0x0b93793923CD5De81850aF8604a233f3f24d461e"
EVALUATOR_VAULT = "0x5c6EE4586ACABcb6326069c229E58091B21ef384"
DEFAULT_RPC = "https://sepolia.base.org"
EXPLORER = "https://base-sepolia.blockscout.com"

# Hanya `jobs(uint256)` yang dipakai. ABI sengaja seminimal itu supaya perintah ini tidak
# ikut membeku pada bentuk ABI penuh yang bisa berubah di luar kendali kita.
ACP_MIN_ABI: list[dict[str, Any]] = [
    {
        "name": "jobs",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "jobId", "type": "uint256"}],
        "outputs": [
            {"name": "client", "type": "address"},
            {"name": "phase", "type": "address"},
            {"name": "provider", "type": "address"},
            {"name": "expiredAt", "type": "uint256"},
            {"name": "budget", "type": "uint256"},
            {"name": "status", "type": "uint8"},
        ],
    }
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_jobs() -> list[dict[str, Any]]:
    path = _repo_root() / "web" / "public" / "jobs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["jobs"])


def format_rows(jobs: list[dict[str, Any]], onchain: dict[int, dict[str, Any]]) -> list[str]:
    """Bentuk baris laporan. Murni, jadi ia bisa diuji tanpa jaringan sama sekali."""
    rows: list[str] = []
    confirmed = 0
    for job in jobs:
        job_id = int(job["jobId"])
        found = onchain.get(job_id, {"exists": False, "provider": None})
        if not found.get("exists"):
            rows.append(f"job={job_id} onchain=NO")
            continue
        expected = str(job["provider"]).lower()
        actual = str(found.get("provider") or "").lower()
        match = "yes" if expected == actual else "NO"
        if match == "yes":
            confirmed += 1
        rows.append(
            f"job={job_id} onchain=yes provider_match={match} "
            f"label={job.get('providerLabel', 'unknown')} acp_status={job.get('acpStatus')}"
        )
    rows.append(f"jobs_confirmed_onchain={confirmed}/{len(jobs)}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    args = parser.parse_args()

    w3 = Web3(Web3.HTTPProvider(args.rpc))
    if not w3.is_connected():
        print(f"rpc_unreachable={args.rpc}")
        print("Perintah ini butuh jaringan. Ia tidak pernah mengirim transaksi.")
        return 1

    contract = w3.eth.contract(address=Web3.to_checksum_address(ACP_ADDRESS), abi=ACP_MIN_ABI)
    jobs = load_jobs()
    onchain: dict[int, dict[str, Any]] = {}
    for job in jobs:
        job_id = int(job["jobId"])
        try:
            record = contract.functions.jobs(job_id).call()
            onchain[job_id] = {
                "exists": int(record[4]) > 0 or record[2] != ZERO,
                "provider": record[2],
            }
        except Exception as error:  # noqa: BLE001
            onchain[job_id] = {"exists": False, "provider": None, "error": str(error)}

    print(f"acp_contract={ACP_ADDRESS}")
    print(f"acp_contract_url={EXPLORER}/address/{ACP_ADDRESS}")
    print(f"evaluator_vault={EVALUATOR_VAULT}")
    print(f"chain_id={w3.eth.chain_id}")
    print(f"acp_bytecode_bytes={len(w3.eth.get_code(Web3.to_checksum_address(ACP_ADDRESS)))}")
    for line in format_rows(jobs, onchain):
        print(line)
    print("transactions_sent=0 keys_used=0")
    return 0


ZERO = "0x0000000000000000000000000000000000000000"


if __name__ == "__main__":
    raise SystemExit(main())
