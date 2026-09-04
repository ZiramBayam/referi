"""Klien minimal EvaluatorVault (task 1.3b).

Lingkup SENGAJA sempit: hanya `post_verdict()` + `finalize()` lewat web3.py, plus penjaga
pra-baca status job di ACP. Tidak ada memori, watcher, cap provider, atau anggaran waktu —
semuanya milik task 2.0/2.4.

Acuan:
  - docs/api-facts.md §A: signature `jobs(uint256)`, enum status, `reason` = bytes32.
  - contracts/src/EvaluatorVault.sol: `postVerdict`, `finalize`, `verdicts`, event `FinalizeFailed`.
  - deployments/84532.json: alamat vault/ACP, CHALLENGE_WINDOW = 120, MIN_ACP_GAS = 300000.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from eth_account import Account
from web3 import Web3
from web3.logs import DISCARD

log = logging.getLogger("vault_client")

# ----------------------------------------------------------------------
# Konstanta jaringan (deployments/84532.json)
# ----------------------------------------------------------------------

DEFAULT_RPC_URL = "https://sepolia.base.org"
DEFAULT_CHAIN_ID = 84532
DEFAULT_VAULT_ADDRESS = "0x5c6EE4586ACABcb6326069c229E58091B21ef384"
DEFAULT_ACP_ADDRESS = "0x0b93793923CD5De81850aF8604a233f3f24d461e"

# Status job ACP — docs/api-facts.md: "Status enum: Open=0, Funded=1, Submitted=2,
# Completed=3, Rejected=4, Expired=5".
JOB_STATUS_NAMES: dict[int, str] = {
    0: "Open",
    1: "Funded",
    2: "Submitted",
    3: "Completed",
    4: "Rejected",
    5: "Expired",
}

# Status yang TIDAK bisa lagi menerima complete/reject dari evaluator: verdict kita yatim.
TERMINAL_JOB_STATUSES: frozenset[int] = frozenset({3, 4, 5})

# Pesan yang dicetak apa adanya saat penjaga menganulir verdict (TASKS 1.3b AC (b)).
VOIDED_MESSAGE_TEMPLATE = "VERDICT DIANULIR PIHAK KETIGA jobId={job_id} status={status}"

# `kind` di vault: 1 = complete, 2 = reject.
KIND_COMPLETE = 1
KIND_REJECT = 2

# ----------------------------------------------------------------------
# Konstanta selftest
# ----------------------------------------------------------------------

# jobId sintetis dari rentang tinggi. `jobCounter()` ACP Base Sepolia masih ratusan
# (408 pada 3 Sep 2026), jadi id >= 9.000.000 dijamin BUKAN job nyata: `jobs()` mengembalikan
# struct nol dan `finalize` PASTI ditolak ACP → `FinalizeFailed`. Id persis yang terpakai
# dicetak di output selftest.
SELFTEST_JOB_ID_BASE = 9_000_000
SELFTEST_JOB_ID_MAX_PROBE = 64

# memory_root uji TETAP = keccak256("the-evaluator/selftest/memory-root/v1").
# PERINGATAN: `postVerdict` menulis root ini ke `knownRoots` dan TIDAK ADA penghapusnya
# (ADR-011), jadi konstanta ini MENJANGKARKAN root uji di vault SECARA PERMANEN. Karena itu
# ia satu nilai tetap dan dicatat di sini, bukan diacak per run.
SELFTEST_MEMORY_ROOT = bytes.fromhex("5ff921fda73362d23f66dcac204d1ace7a287fa0a2cf3bde12e4b37c6812a19e")

# reasonHash uji TETAP = keccak256("the-evaluator/selftest/reason/v1").
SELFTEST_REASON_HASH = bytes.fromhex("a5bd14a91be2154eef37dbc7ef79f1fca1ec71454832bce0e16a82807085e87e")

# ----------------------------------------------------------------------
# Konstanta pipa hidup (task 1.3d)
# ----------------------------------------------------------------------

# SENGAJA BERBEDA dari konstanta selftest supaya jejak on-chain job NYATA tidak tertukar
# dengan jejak jobId sintetis. 1.3d mengizinkan verdict hardcoded + memori kosong.
# LIVE_MEMORY_ROOT = keccak256("the-evaluator/live/memory-root/v1")
LIVE_MEMORY_ROOT = bytes.fromhex("1fa62c3db5c16f4c831ee1d9ee4c083745b8c8bae86bda3587b8b02ba52f7bf0")
# LIVE_REASON_HASH = keccak256("the-evaluator/live/reason/v1")
LIVE_REASON_HASH = bytes.fromhex("6478e788a7953cf990091291d8d1b4f3f046567a915e5158d4dcf57d9fd845b0")

# Ambang gas `finalize` di vault (MIN_ACP_GAS = 300000) + kepala untuk sisa eksekusi.
FINALIZE_GAS_FLOOR = 420_000
TX_RECEIPT_TIMEOUT_SECONDS = 180

# ----------------------------------------------------------------------
# Fragmen ABI (disalin dari sumber, tidak dikarang)
# ----------------------------------------------------------------------

# docs/api-facts.md §A: jobs(uint256) returns
# (address client, uint8 status, address provider, uint48 expiredAt,
#  address evaluator, address hook, uint256 budget, string description)
ACP_ABI = [
    {
        "type": "function",
        "name": "jobs",
        "stateMutability": "view",
        "inputs": [{"name": "", "type": "uint256"}],
        "outputs": [
            {"name": "client", "type": "address"},
            {"name": "status", "type": "uint8"},
            {"name": "provider", "type": "address"},
            {"name": "expiredAt", "type": "uint48"},
            {"name": "evaluator", "type": "address"},
            {"name": "hook", "type": "address"},
            {"name": "budget", "type": "uint256"},
            {"name": "description", "type": "string"},
        ],
    }
]

# contracts/src/EvaluatorVault.sol
VAULT_ABI = [
    {
        "type": "function",
        "name": "postVerdict",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "jobId", "type": "uint256"},
            {"name": "kind", "type": "uint8"},
            {"name": "reasonHash", "type": "bytes32"},
            {"name": "memoryRoot", "type": "bytes32"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "finalize",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "jobId", "type": "uint256"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "verdicts",
        "stateMutability": "view",
        "inputs": [{"name": "", "type": "uint256"}],
        "outputs": [
            {"name": "kind", "type": "uint8"},
            {"name": "reasonHash", "type": "bytes32"},
            {"name": "memoryRoot", "type": "bytes32"},
            {"name": "readyAt", "type": "uint64"},
            {"name": "finalized", "type": "bool"},
            {"name": "challenger", "type": "address"},
        ],
    },
    {
        "type": "event",
        "name": "FinalizeFailed",
        "anonymous": False,
        "inputs": [{"name": "jobId", "type": "uint256", "indexed": True}],
    },
    {
        "type": "event",
        "name": "Finalized",
        "anonymous": False,
        "inputs": [
            {"name": "jobId", "type": "uint256", "indexed": True},
            {"name": "kind", "type": "uint8", "indexed": False},
            {"name": "reasonHash", "type": "bytes32", "indexed": False},
        ],
    },
    {
        "type": "event",
        "name": "VerdictPosted",
        "anonymous": False,
        "inputs": [
            {"name": "jobId", "type": "uint256", "indexed": True},
            {"name": "kind", "type": "uint8", "indexed": False},
            {"name": "reasonHash", "type": "bytes32", "indexed": False},
            {"name": "memoryRoot", "type": "bytes32", "indexed": False},
            {"name": "readyAt", "type": "uint64", "indexed": False},
        ],
    },
]


# ----------------------------------------------------------------------
# Fungsi murni (diuji unit)
# ----------------------------------------------------------------------


def status_name(status: int) -> str:
    """Nama status job ACP; status di luar enum dilaporkan apa adanya, tidak ditebak."""
    return JOB_STATUS_NAMES.get(status, f"Unknown({status})")


def is_terminal_status(status: int) -> bool:
    """True bila job sudah Completed/Rejected/Expired — verdict evaluator tidak bisa dieksekusi lagi."""
    return status in TERMINAL_JOB_STATUSES


def voided_message(job_id: int, status: int) -> str:
    return VOIDED_MESSAGE_TEMPLATE.format(job_id=job_id, status=status)


def parse_env_file(text: str) -> dict[str, str]:
    """Parser .env kecil (tanpa dependensi baru): `KEY=VALUE`, `#` = komentar, kutip dilepas."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        # Komentar sebaris: `#` di awal nilai, atau `#` yang didahului spasi (agar `#` di
        # tengah nilai tetap utuh). Kasus nyata di .env repo ini: `VAULT_ADDRESS=# diisi ...`
        # yang tanpa cabang "awal nilai" akan terbaca sebagai alamat.
        if value.startswith("#"):
            value = ""
        else:
            for marker in (" #", "\t#"):
                idx = value.find(marker)
                if idx != -1:
                    value = value[:idx]
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


# ----------------------------------------------------------------------
# Konfigurasi & rahasia
# ----------------------------------------------------------------------


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _env_file_values() -> dict[str, str]:
    path = repo_root() / ".env"
    try:
        return parse_env_file(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def config_value(name: str, default: str) -> str:
    """Ambil konfigurasi dari environment, lalu file .env root, lalu default."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    value = _env_file_values().get(name, "")
    return value.strip() or default


def load_private_key() -> str:
    """Kunci privat dari `AGENT_PRIVATE_KEY` (env), fallback file .env root.

    Nilainya TIDAK PERNAH dicetak/di-log. Pemanggil wajib meneruskannya ke `redact()`
    bila menyusun pesan error yang mungkin memuatnya.
    """
    key = os.environ.get("AGENT_PRIVATE_KEY", "").strip()
    if not key:
        key = _env_file_values().get("AGENT_PRIVATE_KEY", "").strip()
    if not key:
        raise RuntimeError("AGENT_PRIVATE_KEY kosong (env maupun .env root) — tidak bisa menandatangani tx")
    if not key.startswith("0x"):
        key = "0x" + key
    return key


def redact(text: str, secret: str) -> str:
    """Menyensor kunci privat bila entah bagaimana muncul di teks (pesan error, log)."""
    if not secret:
        return text
    bare = secret[2:] if secret.startswith("0x") else secret
    out = text.replace(secret, "[REDACTED]").replace(bare, "[REDACTED]")
    return out.replace(bare.lower(), "[REDACTED]").replace(bare.upper(), "[REDACTED]")


# ----------------------------------------------------------------------
# Klien
# ----------------------------------------------------------------------


class JobVoidedError(RuntimeError):
    """Job sudah terminal di ACP sebelum tx dikirim; verdict yatim (bukan kegagalan teknis)."""

    def __init__(self, job_id: int, status: int) -> None:
        super().__init__(voided_message(job_id, status))
        self.job_id = job_id
        self.status = status


@dataclass(frozen=True)
class VerdictState:
    kind: int
    reason_hash: bytes
    memory_root: bytes
    ready_at: int
    finalized: bool
    challenger: str


class VaultClient:
    """Pembungkus tipis EvaluatorVault + pra-baca status job di ACP."""

    def __init__(self, w3: Web3, vault_address: str, acp_address: str, account, chain_id: int) -> None:
        self.w3 = w3
        self.chain_id = chain_id
        self.account = account
        self.vault = w3.eth.contract(address=Web3.to_checksum_address(vault_address), abi=VAULT_ABI)
        self.acp = w3.eth.contract(address=Web3.to_checksum_address(acp_address), abi=ACP_ABI)

    # -- pembacaan ------------------------------------------------------

    def job_status(self, job_id: int) -> int:
        """Status job di ACP lewat getter mapping `jobs(uint256)` (read-only)."""
        job = self.acp.functions.jobs(job_id).call()
        return int(job[1])

    def verdict(self, job_id: int) -> VerdictState:
        kind, reason_hash, memory_root, ready_at, finalized, challenger = self.vault.functions.verdicts(
            job_id
        ).call()
        return VerdictState(int(kind), reason_hash, memory_root, int(ready_at), bool(finalized), challenger)

    def guard(self, job_id: int, stage: str) -> int:
        """Penjaga WAJIB sebelum setiap tx: job terminal → tidak ada tx yang dikirim."""
        status = self.job_status(job_id)
        log.info("guard %s: jobId=%d status=%d (%s)", stage, job_id, status, status_name(status))
        if is_terminal_status(status):
            raise JobVoidedError(job_id, status)
        return status

    # -- penulisan ------------------------------------------------------

    def _send(self, func, extra: dict | None = None) -> str:
        tx_params: dict = {
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "chainId": self.chain_id,
        }
        if extra:
            tx_params.update(extra)
        tx = func.build_transaction(tx_params)
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    def post_verdict(self, job_id: int, kind: int, reason_hash: bytes, memory_root: bytes) -> str:
        """Mengumumkan verdict di vault. Penjaga status dijalankan lebih dulu."""
        self.guard(job_id, "postVerdict")
        tx_hash = self._send(self.vault.functions.postVerdict(job_id, kind, reason_hash, memory_root))
        log.info("postVerdict terkirim: 0x%s", tx_hash)
        return tx_hash

    def finalize(self, job_id: int) -> str:
        """Mengeksekusi verdict ke ACP. Penjaga status dijalankan lebih dulu."""
        self.guard(job_id, "finalize")
        tx_hash = self._send(self.vault.functions.finalize(job_id), {"gas": FINALIZE_GAS_FLOOR})
        log.info("finalize terkirim: 0x%s", tx_hash)
        return tx_hash

    def wait_receipt(self, tx_hash: str):
        return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=TX_RECEIPT_TIMEOUT_SECONDS)


def build_client(private_key: str) -> VaultClient:
    rpc_url = config_value("RPC_URL", DEFAULT_RPC_URL)
    chain_id = int(config_value("CHAIN_ID", str(DEFAULT_CHAIN_ID)))
    vault_address = config_value("VAULT_ADDRESS", DEFAULT_VAULT_ADDRESS)
    acp_address = config_value("ACP_ADDRESS", DEFAULT_ACP_ADDRESS)
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    account = Account.from_key(private_key)
    onchain_chain_id = w3.eth.chain_id
    if onchain_chain_id != chain_id:
        raise RuntimeError(f"chainId RPC {onchain_chain_id} != CHAIN_ID {chain_id}")
    log.info("rpc=%s chainId=%d vault=%s acp=%s", rpc_url, chain_id, vault_address, acp_address)
    log.info("agen=%s", account.address)
    return VaultClient(w3, vault_address, acp_address, account, chain_id)


# ----------------------------------------------------------------------
# Selftest
# ----------------------------------------------------------------------


def pick_selftest_job_id(client: VaultClient) -> int:
    """jobId sintetis pertama di rentang tinggi yang belum punya verdict (postVerdict sekali per job)."""
    for offset in range(SELFTEST_JOB_ID_MAX_PROBE):
        job_id = SELFTEST_JOB_ID_BASE + offset
        if client.verdict(job_id).kind == 0:
            return job_id
    raise RuntimeError("tidak ada jobId sintetis bebas di rentang uji")


def read_ready_at(client: VaultClient, job_id: int, post_receipt) -> int:
    """`readyAt` dari event `VerdictPosted` di receipt; cadangan: `verdicts(jobId)` dengan retry."""
    posted = client.vault.events.VerdictPosted().process_receipt(post_receipt, errors=DISCARD)
    for event in posted:
        if int(event["args"]["jobId"]) == job_id:
            return int(event["args"]["readyAt"])
    for _ in range(15):
        state = client.verdict(job_id)
        if state.kind != 0:
            return state.ready_at
        log.info("  verdicts(%d) masih kosong di node RPC ini (lag) — coba lagi", job_id)
        time.sleep(4)
    raise RuntimeError(f"tidak bisa membaca readyAt untuk jobId={job_id}")


def run_selftest(client: VaultClient) -> int:
    job_id = pick_selftest_job_id(client)
    log.info("SELFTEST jobId SINTETIS=%d (bukan job ACP nyata; jobCounter ACP masih ratusan)", job_id)
    log.info("memory_root uji (TETAP)=0x%s", SELFTEST_MEMORY_ROOT.hex())
    log.info("reason_hash uji (TETAP)=0x%s", SELFTEST_REASON_HASH.hex())

    post_hash = client.post_verdict(job_id, KIND_COMPLETE, SELFTEST_REASON_HASH, SELFTEST_MEMORY_ROOT)
    post_receipt = client.wait_receipt(post_hash)
    log.info(
        "TX 1 postVerdict = 0x%s (status=%d, blok=%d)",
        post_hash,
        post_receipt.status,
        post_receipt.blockNumber,
    )
    if post_receipt.status != 1:
        raise RuntimeError(f"postVerdict gagal on-chain: 0x{post_hash}")

    # readyAt DIBACA dari chain, bukan angka hardcode. Sumber utama = event `VerdictPosted`
    # di receipt (tidak bisa basi); `verdicts(jobId)` hanya cadangan, dengan retry karena RPC
    # publik Base Sepolia melayani `eth_call` dari node yang kadang tertinggal beberapa blok
    # (terukur: pembacaan tepat sesudah receipt pernah mengembalikan readyAt = 0).
    ready_at = read_ready_at(client, job_id, post_receipt)
    log.info("menunggu jendela challenge sampai readyAt=%d (dibaca dari verdicts(jobId))", ready_at)
    while True:
        now = client.w3.eth.get_block("latest")["timestamp"]
        if now > ready_at:
            break
        log.info("  block.timestamp=%d, sisa %d detik", now, ready_at - now + 1)
        time.sleep(min(20, max(2, ready_at - now + 1)))

    final_hash = client.finalize(job_id)
    final_receipt = client.wait_receipt(final_hash)
    log.info(
        "TX 2 finalize    = 0x%s (status=%d, blok=%d)",
        final_hash,
        final_receipt.status,
        final_receipt.blockNumber,
    )

    if final_receipt.status != 1:
        raise RuntimeError(f"finalize REVERT on-chain: 0x{final_hash}")

    failed = client.vault.events.FinalizeFailed().process_receipt(final_receipt, errors=DISCARD)
    finalized = client.vault.events.Finalized().process_receipt(final_receipt, errors=DISCARD)
    log.info("log receipt finalize: FinalizeFailed=%d, Finalized=%d", len(failed), len(finalized))
    if failed and not finalized:
        log.info(
            "HASIL: finalize menghasilkan event FinalizeFailed(jobId=%d) — BUKAN JobCompleted. "
            "Ini DIHARAPKAN: jobId %d sintetis, tidak ada di ACP, jadi acp.complete() revert dan "
            "ditangkap `catch` vault (ADR-015). Bukan artefak pipa hidup (JobCompleted milik 1.3d).",
            failed[0]["args"]["jobId"],
            job_id,
        )
    else:
        raise RuntimeError(
            f"receipt finalize tidak sesuai harapan: FinalizeFailed={len(failed)} Finalized={len(finalized)}"
        )

    log.info("SELFTEST SELESAI. postVerdict=0x%s finalize=0x%s", post_hash, final_hash)
    return 0


def run_live(client: VaultClient, job_id: int, kind: int) -> int:
    """Pipa atas jobId ACP NYATA: postVerdict -> tunggu CHALLENGE_WINDOW -> finalize.

    Jalur dan penjaganya sama persis dengan selftest; yang berbeda hanya asal jobId dan
    hasil yang diharapkan: `Finalized` ADA dan `FinalizeFailed` TIDAK ADA.
    """
    kind_name = "complete" if kind == KIND_COMPLETE else "reject"
    log.info("LIVE jobId ACP NYATA=%d kind=%d (%s)", job_id, kind, kind_name)
    log.info("memory_root live (TETAP)=0x%s", LIVE_MEMORY_ROOT.hex())
    log.info("reason_hash live (TETAP)=0x%s", LIVE_REASON_HASH.hex())

    existing = client.verdict(job_id)
    if existing.finalized:
        log.error(
            "verdict jobId=%d SUDAH finalized (kind=%d) — tidak ada yang dikerjakan",
            job_id,
            existing.kind,
        )
        return 1

    post_receipt = None
    if existing.kind != 0:
        # VerdictAlreadyPosted: lanjut ke finalize, jangan gagal total (jalur diminta 1.3d).
        log.info(
            "verdict jobId=%d SUDAH ADA (kind=%d, readyAt=%d) — melewati postVerdict, lanjut finalize",
            job_id,
            existing.kind,
            existing.ready_at,
        )
        ready_at = existing.ready_at
        post_hash = "(sudah ada sebelumnya)"
    else:
        post_hash = client.post_verdict(job_id, kind, LIVE_REASON_HASH, LIVE_MEMORY_ROOT)
        post_receipt = client.wait_receipt(post_hash)
        log.info(
            "TX 1 postVerdict = 0x%s (status=%d, blok=%d)",
            post_hash,
            post_receipt.status,
            post_receipt.blockNumber,
        )
        if post_receipt.status != 1:
            raise RuntimeError(f"postVerdict gagal on-chain: 0x{post_hash}")
        # readyAt dari event di receipt (RPC publik bisa tertinggal di belakang receipt).
        ready_at = read_ready_at(client, job_id, post_receipt)

    log.info("menunggu jendela challenge sampai readyAt=%d", ready_at)
    while True:
        now = client.w3.eth.get_block("latest")["timestamp"]
        if now > ready_at:
            break
        log.info("  block.timestamp=%d, sisa %d detik", now, ready_at - now + 1)
        time.sleep(min(20, max(2, ready_at - now + 1)))

    final_hash = client.finalize(job_id)
    final_receipt = client.wait_receipt(final_hash)
    log.info(
        "TX 2 finalize    = 0x%s (status=%d, blok=%d)",
        final_hash,
        final_receipt.status,
        final_receipt.blockNumber,
    )
    if final_receipt.status != 1:
        log.error("finalize REVERT on-chain: 0x%s", final_hash)
        return 1

    failed = client.vault.events.FinalizeFailed().process_receipt(final_receipt, errors=DISCARD)
    finalized = client.vault.events.Finalized().process_receipt(final_receipt, errors=DISCARD)
    log.info("log receipt finalize: FinalizeFailed=%d, Finalized=%d", len(failed), len(finalized))
    for event in finalized:
        log.info("  Finalized(jobId=%d, kind=%d)", int(event["args"]["jobId"]), int(event["args"]["kind"]))
    for event in failed:
        log.info("  FinalizeFailed(jobId=%d)", int(event["args"]["jobId"]))

    if finalized and not failed:
        log.info("PIPA HIDUP SELESAI. postVerdict=%s finalize=0x%s", post_hash, final_hash)
        return 0

    log.error(
        "HASIL TIDAK SESUAI HARAPAN untuk jobId NYATA %d: FinalizeFailed=%d Finalized=%d "
        "(acp.complete() ditolak dan ditangkap catch vault). receipt finalize=0x%s blok=%d",
        job_id,
        len(failed),
        len(finalized),
        final_hash,
        final_receipt.blockNumber,
    )
    return 1


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vault_client", description="Klien EvaluatorVault minimal")
    parser.add_argument("--selftest", action="store_true", help="postVerdict + finalize atas jobId sintetis")
    parser.add_argument("--guard", type=int, metavar="JOB_ID", help="hanya pra-baca status job di ACP")
    parser.add_argument(
        "--job-id", type=int, metavar="JOB_ID", help="jalankan pipa penuh atas jobId ACP NYATA"
    )
    parser.add_argument(
        "--kind",
        choices=("complete", "reject"),
        default="complete",
        help="verdict untuk --job-id (default: complete)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    if not args.selftest and args.guard is None and args.job_id is None:
        parser.print_usage(sys.stdout)
        return 2

    private_key = ""
    try:
        private_key = load_private_key()
        client = build_client(private_key)
        if args.guard is not None:
            client.guard(args.guard, "guard-only")
            return 0
        if args.job_id is not None:
            kind = KIND_COMPLETE if args.kind == "complete" else KIND_REJECT
            try:
                return run_live(client, args.job_id, kind)
            except JobVoidedError as exc:
                # Job NYATA yang sudah terminal = verdict yatim: kegagalan pipa, bukan hasil normal.
                log.error("%s", voided_message(exc.job_id, exc.status))
                return 1
        return run_selftest(client)
    except JobVoidedError as exc:
        # Penjaga: tidak ada tx yang dikirim, keluar 0 (bukan kegagalan).
        log.info("%s", voided_message(exc.job_id, exc.status))
        return 0
    except Exception as exc:  # noqa: BLE001 — pesan disensor sebelum dicetak
        log.error("GAGAL: %s: %s", type(exc).__name__, redact(str(exc), private_key))
        return 1


if __name__ == "__main__":
    # sys.tracebacklimit tidak diubah: main() menangkap semua exception dan menyensor pesannya,
    # jadi tidak ada traceback yang bisa membawa kunci privat ke stdout/stderr.
    raise SystemExit(main())
