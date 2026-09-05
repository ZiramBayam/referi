"""Klien minimal EvaluatorVault (task 1.3b).

Lingkup: `post_verdict()` + `finalize()` + `set_provider_cap()` lewat web3.py, penjaga
pra-baca status job di ACP, dan — sejak task 2.4a, dikoreksi 2.4a-fix — GERBANG MODE AMAN
yang menahan ketiganya.

MODE AMAN (spec §3 aturan 5 sebagaimana dibaca ulang ADR-023 dan DIKOREKSI ADR-024;
ADR-007 + amandemennya, ADR-011, ADR-020 keputusan 8). Presedensi `decide_mode`, tepat ini:

  (1) kunci single-instance gagal, ATAU pembacaan memori MELEMPAR  → AMAN;
  (2) `memory.db` HILANG: root on-chain nol → NAIF; selain itu     → AMAN;
  (3) selebihnya                                                   → NORMAL, TERMASUK
      memori kosong dengan nol job outcome.

Dalam mode aman agen BERHENTI TOTAL: tidak ada `postVerdict`, tidak ada `finalize`, tidak
ada `setProviderCap`. Akibatnya diucapkan apa adanya dan DILARANG diperhalus: job
MENGGANTUNG sampai `expiredAt`, lalu siapa pun boleh `claimRefund` (ADR-014) dan client
menerima refund penuh — dan barisnya WAJIB menyebut jalan keluarnya (pulihkan `memory.db`
dari backup), karena menyebut akibat tanpa pemulihan membuat operator menyangka agennya
rusak, bukan sedang menolak.

DUA HAL YANG DICABUT, jangan dikembalikan tanpa ADR baru:
  - perbandingan root memori lokal dengan `lastMemoryRoot()`, dan pemakaian `knownRoots`
    (ADR-023). Vault submission beku ADR-022 menyimpan root konstanta pipa 1.3d yang tidak
    bisa diturunkan dari `memory.db` mana pun, dan spec §5 langkah 5 menulis memori SESUDAH
    `postVerdict` sehingga root lokal selalu satu langkah di depan → mode aman permanen.
  - aturan "DB ada tapi NOL job outcome + root non-nol → AMAN" (ADR-024). Ia memindahkan
    self-brick ke job A: di vault beku root SELALU non-nol, jadi `postVerdict` job A ditahan
    dan outcome pertama tidak pernah lahir (`tx = []`). Ia juga dipenuhi DB tiga baris
    buatan tangan, jadi yang ditegakkannya "DB tidak kosong", bukan asal-usul apa pun.
`lastMemoryRoot()` DIBACA HANYA di cabang (2) — untuk membedakan "hari pertama" dari "vault
yang sudah hidup" — dan di luar itu ia konteks log/UI saja.

BOOTSTRAP job A TIDAK punya jalur khusus (ADR-024 keputusan 3): memori kosong = mode normal
tanpa kalibrasi, yang perilakunya memang sama dengan evaluator stateless (spec §3 aturan 6).

GERBANG DIBACA ULANG SETIAP TX, bukan sekali saat start. Alasannya diukur reviewer: dengan
pembacaan sekali, memori yang diracuni SESUDAH start (kunci `memory.db` bersifat kooperatif)
dan root on-chain yang berubah di tengah jalan tidak pernah terlihat, dan tx tetap terkirim.

`decide_mode` di `memory_policy` hanya mengembalikan NILAI; penegakannya ada DI SINI, di
`_send()` — satu-satunya tempat transaksi ditandatangani dan dikirim.

Acuan:
  - docs/api-facts.md §A: signature `jobs(uint256)`, enum status, `reason` = bytes32.
  - contracts/src/EvaluatorVault.sol: `postVerdict`, `finalize`, `setProviderCap`,
    `lastMemoryRoot`, `verdicts`, event `FinalizeFailed`.
  - deployments/84532.json: alamat vault/ACP, CHALLENGE_WINDOW = 120, MIN_ACP_GAS = 300000.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

from eth_account import Account
from sibyl_memory_client import MemoryClient
from web3 import Web3
from web3.logs import DISCARD

from agent.memory_lock import MemoryLockError
from agent.memory_policy import (
    MODE_NAIVE,
    MODE_SAFE,
    ZERO_ROOT,
    LocalMemoryEvidence,
    ModeDecision,
    decide_mode,
    local_memory_evidence,
)

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

# Kode keluar untuk "gerbang menahan agen SESUDAH sebagian tx mendarat". Sengaja BUKAN 0
# dan BUKAN 1: mode aman di awal run adalah perilaku yang diinginkan (0), kegagalan teknis
# adalah 1, dan pipa yang berhenti separuh jalan adalah keadaan KETIGA — job menggantung
# sampai `expiredAt` sementara verdictnya sudah diumumkan. Otomasi 2.5 harus bisa
# membedakannya; exit 0 di sini adalah laporan sukses palsu.
EXIT_STOPPED_MIDWAY = 3
EXIT_STOPPED_MIDWAY_MESSAGE = "PIPA BERHENTI DI TENGAH"

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

# ----------------------------------------------------------------------
# Konstanta mode aman (task 2.4a)
# ----------------------------------------------------------------------

# Path DB memori. Default sama dengan `.env.example`. Nilai RELATIF dijangkarkan ke
# `agent_root()` (direktori paket agen), BUKAN ke direktori kerja — lihat `memory_db_path()`.
DEFAULT_DB_PATH = "./data/memory.db"

# "Memori dihapus" WAJIB dibaca sebagai TIGA file (api-facts §C: `local()` menghasilkan
# `memory.db` + `-wal` + `-shm`). Daftar ini dipakai untuk MELAPORKAN apa yang ada, bukan
# untuk menambal: file utama hilang = memori hilang, titik.
MEMORY_DB_SUFFIXES = ("", "-wal", "-shm")

# Dicetak apa adanya saat gerbang menahan agen. Tiga bagian, semuanya WAJIB:
#   1. penanda `MODE AMAN` + root on-chain sebagai KONTEKS (ADR-023 keputusan 1) dan asal
#      memori lokal (TASKS 2.4a-fix);
#   2. apa yang ditolak — KETIGANYA (ADR-020 keputusan 8, AC (f));
#   3. AKIBATNYA apa adanya (AC (g)) — dilarang diperhalus jadi "ditolak dengan aman";
#   4. JALUR PEMULIHANNYA (ADR-024 konsekuensi terakhir): `rm -rf agent/data` pada vault
#      beku memang berarti mode aman permanen, dan menyebut akibat tanpa menyebut jalan
#      keluarnya membuat operator menyangka agennya rusak, bukan sedang menolak.
SAFE_MODE_TEMPLATE = (
    "MODE AMAN: root onchain={onchain} (konteks saja); memori lokal {origin} di {db}; "
    "menolak postVerdict/finalize/setProviderCap; "
    "job menggantung sampai expiredAt, refund lewat claimRefund publik; "
    "pulihkan memory.db dari backup untuk melanjutkan"
)
# Baris untuk mode yang BERJALAN. Root on-chain ikut dicetak — ia konteks audit, bukan
# syarat eksekusi (ADR-023 keputusan 1), dan penandanya `(konteks saja)` ada supaya tidak
# ada pembaca yang menyangka ia sedang dibandingkan dengan apa pun.
NORMAL_MODE_TEMPLATE = (
    "MODE NORMAL: root onchain={onchain} (konteks saja); memori lokal {jobs} job di {db}"
)
NAIVE_MODE_TEMPLATE = (
    "MODE NAIF: root onchain={onchain} (konteks saja, nol = belum ada verdict diumumkan); "
    "memori lokal {jobs} job di {db}; evaluasi stateless"
)
MISSING_LOCAL_MEMORY = "HILANG/TIDAK TERBACA"

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
        "name": "lastMemoryRoot",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "bytes32"}],
    },
    {
        "type": "function",
        "name": "setProviderCap",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "provider", "type": "address"},
            {"name": "capUsdc", "type": "uint256"},
        ],
        "outputs": [],
    },
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


# Penanda akar repo. `.git` bisa berupa direktori (klon biasa) maupun FILE (worktree/submodule),
# jadi keduanya diperiksa dengan `exists()`, bukan `is_dir()`.
REPO_MARKERS = (".git",)


def repo_root(start: Path | None = None) -> Path:
    """Akar repo: leluhur PERTAMA yang memuat penanda repo, bukan hitungan `.parent` tetap.

    Versi lama menghitung `parent.parent` dan MELESET tepat setelah paket dipindah ke
    `agent/agent/` (task 2.0): ia menunjuk `…/agent`, sehingga `.env` di akar repo TIDAK
    PERNAH terbaca. Akibatnya terukur: `AGENT_PRIVATE_KEY` gagal dimuat justru SESUDAH
    gerbang memori lolos, dan `SIBYL_DB_PATH` diabaikan diam-diam. Penelusuran ke atas
    membuat kesalahan yang sama mustahil terulang saat paket dipindah lagi.
    """
    here = (Path(__file__) if start is None else Path(start)).resolve()
    for candidate in here.parents:
        if any((candidate / marker).exists() for marker in REPO_MARKERS):
            return candidate
    # Tanpa penanda (mis. dipasang sebagai wheel di luar repo): leluhur terjauh yang masuk
    # akal. Ia hanya menentukan DI MANA `.env` dicari; tidak ada rahasia yang dikarang.
    return here.parents[-1]


def env_file_path(start: Path | None = None) -> Path | None:
    """`.env` TERDEKAT dari modul ini ke atas, berhenti di akar repo. `None` bila tidak ada.

    Dikembalikan sebagai path (bukan isinya) supaya tes bisa membuktikan FILE MANA yang
    dibaca — tes yang menyuntik nilai lewat `monkeypatch.setenv` tidak pernah membuktikan
    apa pun tentang jalur file ini, dan itulah sebabnya cacatnya lolos sekian lama.
    """
    here = (Path(__file__) if start is None else Path(start)).resolve()
    for candidate in here.parents:
        env = candidate / ".env"
        if env.is_file():
            return env
        if any((candidate / marker).exists() for marker in REPO_MARKERS):
            break  # jangan naik melewati akar repo
    return None


def _env_file_values() -> dict[str, str]:
    path = env_file_path()
    if path is None:
        return {}
    try:
        return parse_env_file(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def config_value(name: str, default: str) -> str:
    """Ambil konfigurasi dari environment, lalu file `.env` repo, lalu default."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    value = _env_file_values().get(name, "")
    return value.strip() or default


def load_private_key() -> str:
    """Kunci privat dari `AGENT_PRIVATE_KEY` (env), fallback file `.env` repo.

    Nilainya TIDAK PERNAH dicetak/di-log. Pemanggil wajib meneruskannya ke `redact()`
    bila menyusun pesan error yang mungkin memuatnya.
    """
    key = os.environ.get("AGENT_PRIVATE_KEY", "").strip()
    if not key:
        key = _env_file_values().get("AGENT_PRIVATE_KEY", "").strip()
    if not key:
        raise RuntimeError(
            f"AGENT_PRIVATE_KEY kosong (env maupun {env_file_path() or '.env (tidak ditemukan)'}) "
            "— tidak bisa menandatangani tx"
        )
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


# ----------------------------------------------------------------------
# Gerbang mode aman (task 2.4a) — spec §3 aturan 5, ADR-007/011/020
# ----------------------------------------------------------------------


class SafeModeStop(RuntimeError):
    """Mode aman menahan sebuah transaksi. BUKAN kegagalan teknis: agen memang berhenti.

    Pesannya adalah baris `MODE AMAN: …` apa adanya, termasuk akibatnya (job menggantung
    sampai `expiredAt`, refund lewat `claimRefund` publik). Jangan diringkas oleh pemanggil.
    """


def agent_root() -> Path:
    """Direktori paket agen (`…/agent`), yaitu jangkar path memori yang RELATIF.

    Ditemukan lewat `pyproject.toml`, bukan hitungan `.parent` tetap — kesalahan yang sama
    persis yang membuat `.env` tidak pernah terbaca. Jatuh ke akar repo bila tidak ketemu.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
        if any((candidate / marker).exists() for marker in REPO_MARKERS):
            break
    return repo_root()


def memory_db_path() -> Path:
    """Path ABSOLUT `memory.db` dari `SIBYL_DB_PATH` (env → .env → default `.env.example`).

    Path RELATIF (`.env` repo ini berisi `./data/memory.db`) dijangkarkan ke `agent_root()`,
    BUKAN ke direktori kerja. Ini temuan TINGGI review 2.4a-fix, dan akibatnya nyata di
    kedua arah:
      - dari cwd lain, `data/memory.db` palsu berisi satu baris cukup untuk membuat gerbang
        NORMAL sekaligus membuat profil provider korban terbaca KOSONG → `derive_cap` →
        `NO_CAP` → `cap_to_onchain` = 0 = TANPA BATAS (ADR-001);
      - dari akar repo, file yang benar tidak ketemu → MODE AMAN diam-diam, exit 0, dan
        seluruh demo berhenti tanpa alasan yang terlihat.
    Yang memutuskan file mana yang berlaku karena itu adalah konfigurasi, bukan `cd`.
    """
    raw = Path(config_value("SIBYL_DB_PATH", DEFAULT_DB_PATH)).expanduser()
    return raw if raw.is_absolute() else (agent_root() / raw).resolve()


def memory_files_report(db: Path) -> dict[str, bool]:
    """Keberadaan KETIGA file memori — `memory.db`, `-wal`, `-shm` (api-facts §C).

    Dilaporkan bertiga karena "hapus memori" di tes destruktif (task 3.3b) berarti bertiga;
    keputusan mode TETAP hanya melihat file utama, supaya `-wal` yatim tidak pernah bisa
    menyamar sebagai memori yang utuh.
    """
    return {f"{db.name}{suffix}": db.with_name(db.name + suffix).is_file() for suffix in MEMORY_DB_SUFFIXES}


def close_memory_client(client) -> None:
    """Menutup handle sqlite milik satu pembacaan gerbang.

    `MemoryClient` 0.7.0 TIDAK punya `close()` maupun protokol `with` (diperiksa dengan
    `dir`/`hasattr`, bukan diasumsikan). Yang ada adalah `MemoryClient.storage.close()` —
    diverifikasi `inspect.signature(Storage.close) -> (self) -> None`, "Close all tracked
    connections (mainly for tests / shutdown)". Itu yang dipakai di sini, lewat `getattr`
    supaya versi SDK yang tidak punya `storage` tidak membuat gerbang gagal.

    Perlu karena gerbang dibaca beberapa kali per transaksi dan tiap pembacaan membuka
    `MemoryClient` baru; tanpa ini fd/WAL handle menumpuk sepanjang proses hidup.
    """
    storage = getattr(client, "storage", None)
    tutup = getattr(storage, "close", None)
    if callable(tutup):
        try:
            tutup()
        except Exception as exc:  # noqa: BLE001 — menutup handle tidak boleh menggagalkan gerbang
            log.debug("menutup klien memori gagal: %s: %s", type(exc).__name__, exc)


def read_local_memory(db: Path) -> LocalMemoryEvidence:
    """Keadaan memori lokal untuk `decide_mode`. Kegagalan = nilai, bukan traceback.

    TIGA keadaan gagal dipisahkan, dan pemisahannya menentukan mode (ADR-024 keputusan 2):
      - FILE UTAMA TIDAK ADA → `missing`. Hanya keadaan INI yang boleh berujung NAIF, dan
        hanya bila vault belum pernah mengumumkan root. `-wal`/`-shm` yatim TIDAK PERNAH
        bisa menyamar sebagai memori yang utuh; sebaliknya, ketiadaan `-wal`/`-shm` juga
        BUKAN tanda memori hilang — pada DB yang ditutup bersih keduanya memang tidak ada,
        dan menuntut keberadaannya akan mengunci agen setiap kali ia idle.
      - KUNCI TIDAK DIDAPAT → `lock_failed`. Ini bukan pernyataan tentang isi memori
        melainkan tentang adanya INSTANS AGEN LAIN; `decide_mode` menolaknya lebih dulu
        daripada apa pun, termasuk sebelum cabang NAIF.
      - PEMBACAAN MELEMPAR → `error`: `MemoryIntegrityError` (nama entity provider tidak
        kanonik, hasil `search` terpotong, `reference:pattern` yang dirujuk provider hilang),
        galat I/O, DB rusak. Kita tidak tahu isi memori, dan ketidaktahuan TIDAK PERNAH
        boleh memberi izin lebih besar.
    Agen yang CRASH di sini juga tidak mengirim tx, tetapi ia kehilangan baris `MODE AMAN`
    yang menjadi bukti, dan exit code-nya bukan 0.
    """
    if not db.is_file():
        return LocalMemoryEvidence.missing(f"file {db} tidak ada")
    client = None
    try:
        client = MemoryClient.local(str(db))
        evidence = local_memory_evidence(client)
    except MemoryLockError as exc:
        log.warning("kunci memory.db tidak didapat: %s", exc)
        return LocalMemoryEvidence.lock_failed(f"MemoryLockError: {exc}")
    except Exception as exc:  # noqa: BLE001 — SEMUA kegagalan lain = memori tidak dipercaya
        log.warning("memori lokal tidak bisa dipercaya: %s: %s", type(exc).__name__, exc)
        return LocalMemoryEvidence.error(f"{type(exc).__name__}: {exc}")
    finally:
        if client is not None:
            close_memory_client(client)
    return replace(evidence, detail=f"{evidence.detail} di {db}")


@dataclass(frozen=True)
class MemoryGate:
    """Root on-chain (konteks) + keadaan memori lokal, beserta keputusan modenya."""

    decision: ModeDecision
    onchain: bytes | None
    local: LocalMemoryEvidence
    db_path: Path
    onchain_reason: str

    @property
    def is_safe(self) -> bool:
        return self.decision.mode == MODE_SAFE

    @property
    def onchain_hex(self) -> str:
        return "TIDAK TERBACA" if self.onchain is None else "0x" + self.onchain.hex()

    @property
    def local_hex(self) -> str:
        """Root memori lokal — KONTEKS/`postVerdict`, bukan bahan perbandingan (ADR-023)."""
        return self.local.root_hex

    @property
    def origin(self) -> str:
        """Keadaan memori lokal untuk baris keluaran — apa adanya, tanpa klaim tambahan."""
        if self.local.local_memory_readable:
            return f"{self.local.job_outcomes} job"
        return f"{MISSING_LOCAL_MEMORY} ({self.local.status})"

    @property
    def line(self) -> str:
        """Satu baris keadaan gerbang — satu-satunya bentuk yang boleh dicetak."""
        # Path memori ABSOLUT ikut dicetak: tanpa itu tidak ada juri/auditor yang bisa
        # membuktikan FILE MANA yang memberi izin NORMAL (temuan TINGGI review 2.4a-fix).
        if self.is_safe:
            return SAFE_MODE_TEMPLATE.format(
                onchain=self.onchain_hex, origin=self.origin, db=self.db_path
            )
        template = NAIVE_MODE_TEMPLATE if self.decision.mode == MODE_NAIVE else NORMAL_MODE_TEMPLATE
        return template.format(
            onchain=self.onchain_hex, jobs=self.local.job_outcomes, db=self.db_path
        )

    def log_summary(self) -> None:
        log.info("%s", self.line)
        log.info(
            "gerbang memori: mode=%s onchain=%s (%s) lokal-root=%s (%s)",
            self.decision.mode,
            self.onchain_hex,
            self.onchain_reason,
            self.local_hex,
            self.local.detail,
        )
        log.info("file memori di %s: %s", self.db_path.parent, memory_files_report(self.db_path))
        if self.is_safe:
            log.info("alasan: %s", self.decision.reason)


def evaluate_memory_gate(client: VaultClient, db_path: Path | None = None) -> MemoryGate:
    """Membaca konteks on-chain + bukti memori lokal, lalu memutuskan mode (fungsi TUNGGAL).

    Dipanggil ulang SEBELUM SETIAP transaksi lewat `VaultClient.refresh_memory_gate()`;
    hasilnya dipasang ke `VaultClient.memory_gate` sehingga `_send()` — satu-satunya tempat
    tx ditandatangani — menolak semua yang lewat saat mode aman. Gerbang yang dibaca sekali
    saat start TIDAK cukup: root on-chain bisa berubah dan `memory.db` bisa diracuni sesudah
    start (kuncinya kooperatif), dan keduanya tidak akan pernah terlihat.
    """
    db = memory_db_path() if db_path is None else Path(db_path)
    onchain, onchain_reason = client.onchain_memory_root()
    local = read_local_memory(db)
    return MemoryGate(
        decision=decide_mode(onchain, local),
        onchain=onchain,
        local=local,
        db_path=db,
        onchain_reason=onchain_reason,
    )


class VaultClient:
    """Pembungkus tipis EvaluatorVault + pra-baca status job di ACP."""

    def __init__(
        self,
        w3: Web3,
        vault_address: str,
        acp_address: str,
        account,
        chain_id: int,
        memory_gate: MemoryGate | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self.w3 = w3
        self.chain_id = chain_id
        self.account = account
        self.vault = w3.eth.contract(address=Web3.to_checksum_address(vault_address), abi=VAULT_ABI)
        self.acp = w3.eth.contract(address=Web3.to_checksum_address(acp_address), abi=ACP_ABI)
        # Path memori WAJIB eksplisit. `None` bukan "pakai default": ia berarti klien ini
        # tidak bisa membaca ulang gerbangnya, dan `_send()` menolak semua tx. Fail-closed
        # di sini disengaja — klien yang dibangun tanpa memori tidak boleh menghasilkan tx.
        self.db_path: Path | None = None if db_path is None else Path(db_path)
        # Hasil pembacaan TERAKHIR, untuk log/UI. Ia BUKAN izin: `_send()` selalu membaca
        # ulang lebih dulu, jadi gerbang basi tidak pernah bisa meloloskan transaksi.
        self.memory_gate: MemoryGate | None = memory_gate
        # Tx yang BENAR-BENAR terkirim dari klien ini. Dipakai `main()` untuk membedakan
        # "berhenti bersih" dari "berhenti di tengah pipa" — dua keadaan yang akibatnya
        # sangat berbeda bagi client yang dananya masih di escrow.
        self.sent_transactions: list[str] = []

    # -- gerbang mode aman ----------------------------------------------

    def onchain_memory_root(self) -> tuple[bytes | None, str]:
        """Root terakhir yang diumumkan vault. Gagal baca = `None` = mode aman, bukan crash.

        Nilainya dipakai HANYA sebagai konteks (nol = belum ada verdict yang diumumkan);
        ia tidak pernah dibandingkan dengan root memori lokal (ADR-023 keputusan 1).
        """
        try:
            raw = self.vault.functions.lastMemoryRoot().call()
        except Exception as exc:  # noqa: BLE001 — RPC apa pun yang gagal = kita tidak tahu
            log.warning("root on-chain tidak terbaca: %s: %s", type(exc).__name__, exc)
            return None, f"{type(exc).__name__}: {exc}"
        root = bytes(raw)
        return root, ("nol (belum ada verdict diumumkan)" if root == ZERO_ROOT else "dibaca dari vault")

    def refresh_memory_gate(self) -> MemoryGate:
        """Membaca ULANG gerbang (chain DAN memori lokal) dan memasangnya ke klien ini."""
        if self.db_path is None:
            raise SafeModeStop(
                "klien vault dibangun tanpa path memori — gerbang tidak bisa dibaca, jadi "
                "tidak ada transaksi yang boleh dikirim (spec §3 aturan 5, ADR-023)"
            )
        gate = evaluate_memory_gate(self, self.db_path)
        self.memory_gate = gate
        return gate

    def _require_memory_gate(self, action: str) -> None:
        """Penjaga WAJIB sebelum tx APA PUN. Melempar `SafeModeStop`, tidak mengirim apa-apa.

        Gerbangnya DIBACA ULANG di sini, setiap kali. Memakai hasil pembacaan saat start
        berarti memori yang diracuni sesudahnya — kunci `memory.db` kooperatif, penulis lain
        tidak terhalang — dan root on-chain yang berubah di tengah jalan tidak pernah
        terlihat; reviewer memperagakan tx yang tetap terkirim di bawah gerbang basi.
        """
        gate = self.refresh_memory_gate()
        log.info("%s", gate.line)
        if gate.is_safe:
            log.info("alasan: %s", gate.decision.reason)
            raise SafeModeStop(f"{action}: {gate.line}")

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
        # SATU-SATUNYA tempat transaksi dibangun & dikirim, jadi SATU-SATUNYA tempat yang
        # harus menegakkan mode aman. Penjaga ini berjalan SEBELUM `build_transaction`,
        # sebelum `get_transaction_count`, dan sebelum penandatanganan.
        self._require_memory_gate(getattr(func, "fn_name", "tx"))
        if self.account is None:
            raise RuntimeError(
                "klien vault dibangun tanpa kunci privat (baca-saja) — tidak ada tx yang bisa dikirim"
            )
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
        self.sent_transactions.append(tx_hash.hex())
        return tx_hash.hex()

    def post_verdict(self, job_id: int, kind: int, reason_hash: bytes, memory_root: bytes) -> str:
        """Mengumumkan verdict di vault. Gerbang memori lebih dulu, lalu penjaga status job.

        Urutannya disengaja (task 2.4a AC (d)): saat agen berhenti karena memorinya, yang
        dilaporkan HARUS `MODE AMAN`, bukan `VERDICT DIANULIR PIHAK KETIGA` yang kebetulan
        ikut benar. `_send()` membaca gerbangnya SEKALI LAGI — itu yang mengikat; pembacaan
        di sini hanya menentukan pesan mana yang muncul.
        """
        self._require_memory_gate("postVerdict")
        self.guard(job_id, "postVerdict")
        tx_hash = self._send(self.vault.functions.postVerdict(job_id, kind, reason_hash, memory_root))
        log.info("postVerdict terkirim: 0x%s", tx_hash)
        return tx_hash

    def set_provider_cap(self, provider: str, cap_usdc: int) -> str:
        """`setProviderCap` (spec §3 aturan 4). ADR-020 keputusan 8: ikut ditahan mode aman.

        Ia tidak menyentuh job tertentu, jadi TIDAK ada penjaga status job di sini —
        penjaga yang berlaku untuknya adalah gerbang memori di `_send()`.
        """
        tx_hash = self._send(
            self.vault.functions.setProviderCap(Web3.to_checksum_address(provider), int(cap_usdc))
        )
        log.info("setProviderCap terkirim: 0x%s", tx_hash)
        return tx_hash

    def finalize(self, job_id: int) -> str:
        """Mengeksekusi verdict ke ACP. Gerbang memori lebih dulu (alasan sama seperti
        `post_verdict`), lalu penjaga status job."""
        self._require_memory_gate("finalize")
        self.guard(job_id, "finalize")
        tx_hash = self._send(self.vault.functions.finalize(job_id), {"gas": FINALIZE_GAS_FLOOR})
        log.info("finalize terkirim: 0x%s", tx_hash)
        return tx_hash

    def wait_receipt(self, tx_hash: str):
        return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=TX_RECEIPT_TIMEOUT_SECONDS)


def build_client(private_key: str | None = None) -> VaultClient:
    """Klien vault. `private_key=None` = BACA-SAJA: cukup untuk gerbang memori, tidak untuk tx.

    Urutannya disengaja (task 2.4a): memutuskan MODE AMAN tidak boleh menuntut kunci
    penandatangan. Agen yang harus membuka kuncinya dulu untuk mengetahui bahwa ia tidak
    boleh menandatangani apa pun adalah agen yang memaparkan kunci tanpa sebab.
    """
    rpc_url = config_value("RPC_URL", DEFAULT_RPC_URL)
    chain_id = int(config_value("CHAIN_ID", str(DEFAULT_CHAIN_ID)))
    vault_address = config_value("VAULT_ADDRESS", DEFAULT_VAULT_ADDRESS)
    acp_address = config_value("ACP_ADDRESS", DEFAULT_ACP_ADDRESS)
    db_path = memory_db_path()
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    account = Account.from_key(private_key) if private_key else None
    onchain_chain_id = w3.eth.chain_id
    if onchain_chain_id != chain_id:
        raise RuntimeError(f"chainId RPC {onchain_chain_id} != CHAIN_ID {chain_id}")
    log.info("rpc=%s chainId=%d vault=%s acp=%s", rpc_url, chain_id, vault_address, acp_address)
    log.info("memori=%s (.env=%s)", db_path, env_file_path() or "tidak ada")
    log.info("agen=%s", account.address if account else "(kunci belum dimuat; klien baca-saja)")
    return VaultClient(w3, vault_address, acp_address, account, chain_id, db_path=db_path)


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
    dibangun: dict[str, VaultClient] = {}
    try:
        # Klien BACA-SAJA lebih dulu: gerbang memori tidak butuh kunci penandatangan.
        client = build_client()
        dibangun["client"] = client

        # GERBANG MODE AMAN — dijalankan SAAT START, sebelum sub-perintah apa pun dan
        # sebelum satu pun pembacaan job. Urutannya penting untuk task 2.4a AC (d): job
        # terminal milik pihak lain HARUS melaporkan MODE AMAN, bukan "VERDICT DIANULIR",
        # karena yang menahan agen adalah memorinya, bukan status job itu.
        # Pembacaan ini untuk MANUSIA (baris ringkasan + exit lebih awal); yang mengikat
        # transaksi adalah pembacaan ULANG di `_send()`, bukan hasil di sini.
        gate = client.refresh_memory_gate()
        gate.log_summary()
        if gate.is_safe:
            # exit 0: mode aman adalah perilaku yang DIINGINKAN, bukan kegagalan. Nol tx —
            # dan kunci privat bahkan tidak pernah dimuat ke memori proses ini.
            return 0

        private_key = load_private_key()
        client.account = Account.from_key(private_key)
        log.info("agen=%s", client.account.address)

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
    except SafeModeStop as exc:
        # Jaring kedua: gerbang di atas sudah menahan, jadi ini hanya terjadi bila sebuah
        # jalur baru mencoba mengirim tx tanpa lewat sana.
        log.info("%s", exc)
        terkirim = dibangun["client"].sent_transactions if "client" in dibangun else []
        if terkirim:
            # BERHENTI DI TENGAH PIPA. Ini BUKAN "berhenti bersih": sebagian tx sudah
            # mendarat (mis. postVerdict) sementara sisanya (finalize) tidak akan pernah,
            # jadi job menggantung sampai `expiredAt`. Exit 0 di sini membuat otomasi 2.5
            # melaporkan sukses palsu — karena itu kode keluarnya BERBEDA.
            log.error(
                "%s: %d transaksi sudah mendarat sebelum gerbang menahan sisanya (%s) — "
                "job MENGGANTUNG sampai expiredAt, dan run ini TIDAK selesai",
                EXIT_STOPPED_MIDWAY_MESSAGE,
                len(terkirim),
                ", ".join("0x" + h for h in terkirim),
            )
            return EXIT_STOPPED_MIDWAY
        return 0
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
