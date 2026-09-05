"""Klien minimal EvaluatorVault (task 1.3b).

Lingkup: `post_verdict()` + `finalize()` + `set_provider_cap()` lewat web3.py, penjaga
pra-baca status job di ACP, dan — sejak task 2.4a, dikoreksi 2.4a-fix — GERBANG MODE AMAN
yang menahan ketiganya.

JALUR `--job-id` (task 2.4-min, ADR-022 keputusan 2-3). Watcher (task 2.2) DITURUNKAN dari
jalur kritis: agen tidak lagi mem-polling event, ia DIPANGGIL PER JOB. Karena itu dua hal
yang dulu milik watcher pindah ke sini, dan keduanya WAJIB, bukan hiasan:

  1. `getJob(jobId)` (getter mapping `jobs(uint256)`, api-facts §A) dibaca SEKALI di awal.
     Job yang `evaluator != VAULT` DITOLAK: kita bukan evaluatornya, jadi `complete`/
     `reject` kita pasti ditolak ACP dan verdict apa pun atasnya hanya sampah on-chain.
     Penolakannya bersih — exit 0, NOL transaksi, nonce tidak bergerak.
  2. `client` job diambil dari struct yang sama dan diteruskan ke
     `memory_policy.record_job_outcome(client_address=…)`. Tanpa itu ADR-021 keputusan 2
     (budget job yang didanai provider SENDIRI dibuang dari perhitungan cap) mati diam-diam:
     `client` TIDAK indexed di `JobFunded`, jadi tidak ada sumber lain yang murah.

PENOLAKAN DELIVERABLE (ADR-019 keputusan 2, utang task 2.3-min). `criteria.evaluate_job()`
MELEMPAR `DeliverableUnverifiedError` bila teks lokal tidak bisa dibuktikan sebagai preimage
hash on-chain. Penanganannya SEKELAS mode aman: pemanggil menangkapnya, memasang KUNCI
sekali-jalan lewat `VaultClient.refuse()`, dan sejak itu `_send()` menolak SETIAP transaksi —
nol `postVerdict`, nol `finalize`, nol `setProviderCap`. Latch-nya ada supaya jalur baru yang
lupa memeriksa nilai balik tetap berhenti, persis alasan `SafeModeStop` ditegakkan di `_send()`
dan bukan di pemanggil.

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

from agent.checks.chain import Web3ChainFacts
from agent.checks.source import (
    DEFAULT_DELIVERABLE_DIR,
    DELIVERABLE_DIR_ENV,
    REFUSAL_LINE,
    DeliverableUnverifiedError,
)
from agent.criteria import Evaluation, evaluate_job
from agent.memory_lock import MemoryLockError
from agent.memory_policy import (
    MODE_NAIVE,
    MODE_SAFE,
    ZERO_ROOT,
    DecisionMemoryView,
    GateDecision,
    LocalMemoryEvidence,
    ModeDecision,
    canonical_json,
    decide_mode,
    empty_memory_root,
    gate_job,
    local_memory_evidence,
    record_job_outcome,
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
# Root & reasonHash: TIDAK ADA KONSTANTA (task 2.4b)
# ----------------------------------------------------------------------

# Yang DIHAPUS di sini, dan alasannya — jangan dikembalikan tanpa ADR baru:
#   - pasangan root/reasonHash tetap milik jalur `--selftest` (task 1.3b), berikut jalurnya.
#     Ia mengumumkan root hasil keccak atas sebuah label uji, atas jobId sintetis, dan
#     `postVerdict` menulis setiap root ke `knownRoots` TANPA penghapus (ADR-011): satu
#     konstanta uji menjadi root sah selamanya di vault yang dibekukan ADR-022.
#   - pasangan root/reasonHash tetap milik pipa hidup (task 1.3d). Keduanya konstanta yang
#     tidak bisa diturunkan dari `memory.db` mana pun, sehingga klaim "memori yang bisa
#     diaudit" tidak punya jangkar sama sekali — temuan T2 laporan fase-1.
# SATU-SATUNYA sumber `memory_root` sekarang adalah `memory_policy.memory_root` lewat
# gerbang `memory_root_for_onchain`, yaitu nilai yang sudah dibawa `MemoryGate.local.root`
# dan fungsi yang SAMA yang dipakai `agent/memory_export.py` (task 2.1b). Penegakannya ada
# di `_send()` (`_require_derived_root`), bukan di pemanggil.

# Label versi bundel bukti `reasonHash`. Ikut ter-hash supaya bentuk bundel yang berbeda
# tidak pernah bisa menghasilkan hash yang sama dengan bentuk lama. Bentuk PENUH (bukti
# per-kriteria + pin IPFS) milik task 2.5; yang ada di sini adalah bundel MINIMAL yang
# seluruh isinya lahir dari `Evaluation` job itu — bukan konstanta.
VERDICT_EVIDENCE_VERSION = "evaluator-verdict-evidence/v1"

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
# Konstanta jalur --job-id (task 2.4-min)
# ----------------------------------------------------------------------

# Status ACP paling awal yang PUNYA deliverable (api-facts §A: Submitted=2). Di bawah itu
# provider belum `submit()`, jadi tidak ada hash on-chain untuk diverifikasi dan tidak ada
# yang bisa dinilai — bukan kegagalan, hanya belum waktunya (spec §5 langkah 2 vs 3).
STATUS_SUBMITTED = 2

# Jendela `eth_getLogs`. RPC publik Base Sepolia membatasi SELISIH `toBlock - fromBlock`:
# <= 10.000 diterima, >= 10.001 ditolak `413 Payload Too Large` + `-32614` (bisection
# 5 Sep 2026, docs/api-facts.md §E). Karena itu pencarian dilakukan MUNDUR per jendela,
# bukan sekali jalan. 9.999 dipakai sebagai margin sengaja di bawah ambang 10.000.
# Lewat web3.py galat itu muncul sebagai `requests.exceptions.HTTPError`, BUKAN
# `ValueError`/`Web3RPCError`: `HTTPProvider` memanggil `raise_for_status()` lebih dulu.
LOG_WINDOW_BLOCKS = 9_999
# Sejauh apa mundurnya. 100.000 blok Base Sepolia (~2 detik/blok) ≈ 2,3 hari; cukup untuk
# job demo yang di-`submit` beberapa menit sebelumnya, dan tetap terbatas supaya jalur ini
# tidak pernah berubah menjadi pemindaian rantai penuh.
LOG_LOOKBACK_BLOCKS = 100_000

# Baris keadaan job — SATU-SATUNYA bentuk yang boleh dicetak. `client`/`provider`/`evaluator`
# ada di dalamnya karena ketiganya adalah bukti AC: client dipakai ADR-021 keputusan 2, dan
# evaluator adalah dasar penolakan di bawah.
JOB_LINE_TEMPLATE = (
    "JOB jobId={job_id} client={client} provider={provider} evaluator={evaluator} "
    "status={status} ({status_name}) budget={budget} expiredAt={expired_at}"
)

# Penolakan "job ini bukan milik kita" (ADR-022 keputusan 2 — validasinya off-chain, karena
# vault v1 yang dibekukan tidak punya pemeriksa on-chain-nya). Bentuknya menyebut KEDUA
# alamat supaya juri bisa membandingkannya sendiri dengan `cast call <ACP> "getJob(...)"`.
FOREIGN_JOB_TEMPLATE = (
    "JOB BUKAN MILIK VAULT INI: jobId={job_id} evaluator={evaluator} != vault={vault}; "
    "menolak menilai; nol postVerdict/finalize/setProviderCap"
)

# Baris ringkas hasil keputusan memori atas satu job (spec §5 langkah 2-3). Ia LAPORAN,
# bukan perintah: pemilihan verdict dan pengiriman `setProviderCap` bukan milik task ini.
JOB_PLAN_TEMPLATE = (
    "RENCANA jobId={job_id} mode={mode} depth={depth} cap={cap} gate={gate} ({reason}) "
    "evaluasi={evaluation}"
)

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
    },
    # docs/api-facts.md §A, daftar event "APA ADANYA dari ABI": hanya `jobId` dan `provider`
    # yang indexed; `deliverable` ada di `data`. topic0 yang dihasilkan ABI ini WAJIB sama
    # dengan nilai terverifikasi `0x80c17db7…538e` — dijaga tes, bukan diasumsikan.
    #
    # Ini SATU-SATUNYA sumber hash deliverable: struct `Job` TIDAK punya field
    # `deliverable` (lihat daftar output `jobs` di atas), jadi nilai yang dibandingkan
    # dengan artefak lokal ADR-019 hanya ada di log ini.
    {
        "type": "event",
        "name": "JobSubmitted",
        "anonymous": False,
        "inputs": [
            {"name": "jobId", "type": "uint256", "indexed": True},
            {"name": "provider", "type": "address", "indexed": True},
            {"name": "deliverable", "type": "bytes32", "indexed": False},
        ],
    },
]

# Nilai terverifikasi topic0 `JobSubmitted` (docs/api-facts.md §A, `cast sig-event`,
# 2026-09-03) ada di `tests/test_job_pipeline.py`, BUKAN di modul ini: task 2.4b melarang
# konstanta 32-byte apa pun di jalur produksi, dan nilai itu memang hanya dipakai untuk
# membuktikan bahwa fragmen ABI di atas menghasilkan topic yang sama. Penjaganya tetap ada
# (salah ketik nama/urutan tipe = filter log diam-diam kosong = setiap deliverable ditolak),
# hanya pindah ke tempat yang memang memakainya.

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


@dataclass(frozen=True)
class JobView:
    """Struct `Job` ACP apa adanya (api-facts §A) — SATU pembacaan, dipakai bersama.

    Bidangnya diberi nama sesuai ABI, kecuali `client` yang menjadi `client_address`:
    di modul ini "client" sudah berarti `VaultClient`/`MemoryClient`, dan menamainya sama
    adalah cara termurah membuat argumen `record_job_outcome(client=…, client_address=…)`
    tertukar. `evaluator` di sini adalah SATU-SATUNYA dasar pemeriksaan "job ini milik kita".
    """

    job_id: int
    client_address: str
    status: int
    provider: str
    expired_at: int
    evaluator: str
    hook: str
    budget: int
    description: str

    @classmethod
    def from_tuple(cls, job_id: int, raw) -> JobView:
        client_address, status, provider, expired_at, evaluator, hook, budget, description = raw
        return cls(
            job_id=int(job_id),
            client_address=str(client_address),
            status=int(status),
            provider=str(provider),
            expired_at=int(expired_at),
            evaluator=str(evaluator),
            hook=str(hook),
            budget=int(budget),
            description=str(description),
        )

    def is_for_evaluator(self, vault_address: str) -> bool:
        """Perbandingan case-insensitive; checksum berbeda TIDAK boleh berarti job lain.

        Job yang tidak dikenal ACP mengembalikan struct NOL (api-facts §A: `getJob` tidak
        revert), jadi `evaluator` = `0x0…0` dan pemeriksaan ini menolaknya juga — tepat
        seperti yang diinginkan: jobId salah ketik tidak boleh menghasilkan transaksi.
        """
        return self.evaluator.lower() == str(vault_address).lower()

    @property
    def line(self) -> str:
        return JOB_LINE_TEMPLATE.format(
            job_id=self.job_id,
            client=self.client_address,
            provider=self.provider,
            evaluator=self.evaluator,
            status=self.status,
            status_name=status_name(self.status),
            budget=self.budget,
            expired_at=self.expired_at,
        )


def configured_deliverable_dir() -> Path:
    """Direktori artefak ADR-019 dari `DELIVERABLE_DIR` (env → `.env` repo → default).

    Nilainya diteruskan ke `criteria.evaluate_job(deliverable_dir=…)` sebagai ARGUMEN.
    `checks.source.deliverable_dir()` sengaja hanya membaca environment sungguhan supaya
    modul cek tidak perlu mengimpor `vault_client` (impor melingkar: `vault_client` sendiri
    memakai `criteria.evaluate_job`), jadi pola `config_value` harus diterapkan DI SINI.

    Path relatif dijangkarkan ke akar repo — alasannya sama dengan `memory_db_path()`:
    yang menentukan artefak mana yang berlaku adalah konfigurasi, bukan `cd`.
    """
    raw = Path(config_value(DELIVERABLE_DIR_ENV, DEFAULT_DELIVERABLE_DIR)).expanduser()
    return raw if raw.is_absolute() else (repo_root() / raw).resolve()


# ----------------------------------------------------------------------
# Gerbang mode aman (task 2.4a) — spec §3 aturan 5, ADR-007/011/020
# ----------------------------------------------------------------------


class SafeModeStop(RuntimeError):
    """Mode aman menahan sebuah transaksi. BUKAN kegagalan teknis: agen memang berhenti.

    Pesannya adalah baris `MODE AMAN: …` apa adanya, termasuk akibatnya (job menggantung
    sampai `expiredAt`, refund lewat `claimRefund` publik). Jangan diringkas oleh pemanggil.
    """


class MemoryRootMismatch(SafeModeStop):
    """`postVerdict` dipanggil dengan root yang BUKAN `memory_root` saat itu (task 2.4b).

    Turunan `SafeModeStop` dengan sengaja: akibatnya identik — nol transaksi, berhenti
    bersih, dan `main()` tetap bisa membedakan "berhenti sebelum apa pun terkirim" dari
    "berhenti di tengah pipa". Ia BUKAN kegagalan teknis melainkan penolakan: root yang
    tidak bisa direkonstruksi dari `memory.db` akan tertanam PERMANEN di `knownRoots`
    (ADR-011, tidak ada penghapus) dan membatalkan seluruh klaim memori yang bisa diaudit.
    """


# Nama fungsi vault yang membawa `memory_root` + posisi argumennya. Diambil dari
# `contracts/src/EvaluatorVault.sol`: `postVerdict(uint256 jobId, uint8 kind,
# bytes32 reasonHash, bytes32 memoryRoot)` → indeks 3.
POST_VERDICT_FN = "postVerdict"
POST_VERDICT_ROOT_ARG = 3
POST_VERDICT_ROOT_KWARG = "memoryRoot"

ROOT_MISMATCH_TEMPLATE = (
    "ROOT BUKAN TURUNAN MEMORI: postVerdict membawa {given} sementara memory_root atas "
    "{db} saat ini {derived}; menolak mengumumkan root yang tidak bisa direkonstruksi dari "
    "memori; nol postVerdict/finalize/setProviderCap"
)
ROOT_UNREADABLE_TEMPLATE = (
    "ROOT TIDAK BISA DITURUNKAN: memori lokal di {db} {status}, jadi tidak ada memory_root "
    "untuk diumumkan; nol postVerdict/finalize/setProviderCap"
)


def contract_call_root(func) -> bytes | None:
    """`memoryRoot` yang BENAR-BENAR masuk calldata `postVerdict`, dibaca dari fungsi kontrak.

    web3.py 7.16.0 menyimpan argumen pemanggilan di `ContractFunction.args`/`.kwargs`
    (`web3/_utils/contracts.py:404` — `copy_contract_function` menyalin keduanya ke klon
    yang dikembalikan `ContractFunction.__call__`). Yang diperiksa karena itu adalah nilai
    yang akan di-encode, bukan salinan yang dioper terpisah ke penjaga — penjaga yang
    memeriksa variabel lain adalah penjaga yang bisa dilewati dengan satu salah ketik.
    """
    args = getattr(func, "args", None) or ()
    kwargs = getattr(func, "kwargs", None) or {}
    if POST_VERDICT_ROOT_KWARG in kwargs:
        return bytes(kwargs[POST_VERDICT_ROOT_KWARG])
    if len(args) > POST_VERDICT_ROOT_ARG:
        return bytes(args[POST_VERDICT_ROOT_ARG])
    return None


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
        # KUNCI SEKALI-JALAN. Sekali diisi, `_send()` menolak setiap transaksi sampai proses
        # ini mati. Diisi oleh dua penolakan yang bukan verdict: job milik evaluator lain,
        # dan deliverable yang tidak terverifikasi (ADR-019 keputusan 2). Ia ada karena
        # alasan yang sama seperti gerbang mode aman ditegakkan di `_send()` dan bukan di
        # pemanggil: jalur baru yang lupa memeriksa nilai balik tetap harus berhenti.
        self.refusal: str | None = None

    # -- penolakan sekali-jalan -----------------------------------------

    def refuse(self, reason: str) -> None:
        """Memasang kunci penolakan. Alasan PERTAMA yang menang — ia yang paling dekat
        dengan sebabnya; alasan berikutnya hanya akibat."""
        if self.refusal is None:
            self.refusal = reason
            log.error("%s", reason)

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

    def derived_memory_root(self) -> bytes:
        """`memory_root` atas `memory.db` klien ini, dari pembacaan gerbang TERAKHIR.

        Nilainya lahir di `memory_policy.local_memory_evidence()` → `memory_root_for_onchain`
        → `memory_root`, yaitu fungsi yang SAMA yang dipakai `agent/memory_export.py`
        (task 2.1b) — satu implementasi, bukan salinan. Diambil dari snapshot gerbang, bukan
        dari pembacaan DB tersendiri: root dan keputusan mode WAJIB menggambarkan satu
        keadaan DB yang sama (Sibyl 0.7.0 tanpa transaksi, api-facts §C).

        Pemanggil WAJIB memastikan gerbangnya baru (`refresh_memory_gate()`); di jalur tx
        hal itu dilakukan `_require_memory_gate()` satu baris sebelum penjaga ini.
        """
        gate = self.memory_gate
        if gate is None:
            gate = self.refresh_memory_gate()
        if gate.local.root is not None:
            return gate.local.root
        # SATU cabang yang tidak punya root dari file: MODE NAIF (ADR-024 keputusan 2
        # cabang 2) — `memory.db` belum ada DAN vault belum pernah mengumumkan root. Agen
        # di sana benar-benar tidak punya profil, jadi yang diumumkan adalah root memori
        # KOSONG: dihitung dari encoding beku, bukan konstanta. Semua cabang lain yang
        # kehilangan root sudah MODE AMAN dan tidak pernah sampai ke sini.
        if gate.decision.mode == MODE_NAIVE:
            return empty_memory_root()
        raise MemoryRootMismatch(
            ROOT_UNREADABLE_TEMPLATE.format(db=gate.db_path, status=gate.local.status)
        )

    def _require_derived_root(self, given: bytes | None) -> None:
        """Penjaga WAJIB sebelum `postVerdict`: root yang diumumkan == `memory_root`."""
        derived = self.derived_memory_root()
        if given is None or bytes(given) != derived:
            raise MemoryRootMismatch(
                ROOT_MISMATCH_TEMPLATE.format(
                    given="(tidak ada)" if given is None else "0x" + bytes(given).hex(),
                    db=self.db_path,
                    derived="0x" + derived.hex(),
                )
            )

    # -- pembacaan ------------------------------------------------------

    def job(self, job_id: int) -> JobView:
        """Struct `Job` LENGKAP dari getter mapping `jobs(uint256)` (read-only).

        Dulu jalur ini hanya mengambil `status` dan membuang sisanya; `client` dan
        `evaluator` yang ikut terbaca gratis justru dua bidang yang menentukan apakah agen
        boleh bekerja sama sekali (ADR-022 keputusan 2-3).
        """
        return JobView.from_tuple(job_id, self.acp.functions.jobs(job_id).call())

    def job_status(self, job_id: int) -> int:
        """Status job di ACP (satu `eth_call` yang sama dengan `job()`)."""
        return self.job(job_id).status

    def job_deliverable(
        self,
        job_id: int,
        *,
        lookback_blocks: int = LOG_LOOKBACK_BLOCKS,
        window_blocks: int = LOG_WINDOW_BLOCKS,
    ) -> bytes | None:
        """Hash deliverable on-chain dari log `JobSubmitted(jobId)`. `None` bila tak ketemu.

        Ini BUKAN polling (ADR-005 melarang polling API ACP untuk event, dan ADR-022
        keputusan 3 mencabut watcher dari jalur kritis): satu pencarian mundur, sekali,
        atas jobId yang SUDAH kita ketahui. Tidak ada `last_block`, tidak ada loop menunggu.

        Mundur per jendela karena RPC publik membatasi selisih `toBlock - fromBlock` ke
        10.000 (>= 10.001 → `413 Payload Too Large`, docs/api-facts.md §E). Log TERBARU
        yang menang bila provider pernah
        `submit` lebih dari sekali — pencarian memang berjalan dari blok terbaru ke belakang.
        """
        latest = int(self.w3.eth.block_number)
        floor = max(0, latest - int(lookback_blocks))
        high = latest
        while high >= floor:
            low = max(floor, high - int(window_blocks))
            events = list(
                self.acp.events.JobSubmitted().get_logs(
                    argument_filters={"jobId": int(job_id)}, from_block=low, to_block=high
                )
            )
            if events:
                terbaru = max(events, key=lambda e: int(e["blockNumber"]))
                nilai = bytes(terbaru["args"]["deliverable"])
                log.info(
                    "JobSubmitted(jobId=%d) di blok %d: deliverable=0x%s",
                    job_id,
                    int(terbaru["blockNumber"]),
                    nilai.hex(),
                )
                return nilai
            if low <= floor:
                break
            high = low - 1
        log.warning(
            "log JobSubmitted(jobId=%d) tidak ditemukan dalam %d blok terakhir (%d..%d)",
            job_id,
            lookback_blocks,
            floor,
            latest,
        )
        return None

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
        action = getattr(func, "fn_name", "tx")
        self._require_memory_gate(action)
        # Root turunan memori (task 2.4b). Ditegakkan DI SINI, atas nilai yang benar-benar
        # masuk calldata, dan atas gerbang yang BARU SAJA dibaca ulang di baris di atas —
        # bukan di `post_verdict()`, karena jalur baru yang membangun `postVerdict` sendiri
        # tetap harus berhenti. Alasannya sama persis dengan mode aman ditegakkan di sini.
        if action == POST_VERDICT_FN:
            self._require_derived_root(contract_call_root(func))
        # Kunci penolakan (task 2.4-min): job milik evaluator lain, atau deliverable yang
        # tidak terverifikasi (ADR-019 keputusan 2). Diperiksa SESUDAH gerbang memori supaya
        # agen yang berhenti karena memorinya tetap melaporkan `MODE AMAN` — sebab itulah
        # yang lebih dalam; keduanya sama-sama nol transaksi.
        if self.refusal is not None:
            raise SafeModeStop(f"{action}: {self.refusal}")
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

        `memory_root` TETAP argumen, dan `_send()` MENOLAK setiap nilai yang bukan
        `memory_root` atas `memory.db` saat itu (task 2.4b). Argumennya dipertahankan
        justru supaya penolakan itu bisa diuji: pemanggil boleh menyodorkan konstanta apa
        pun, dan yang terjadi adalah `MemoryRootMismatch` + nol transaksi.
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
# Jalur --job-id (task 2.4-min) — baca job dari chain, jalankan keputusan memori
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class JobPlan:
    """Hasil keputusan memori atas satu job. LAPORAN, bukan perintah.

    Task 2.4-min sengaja BERHENTI di sini: memilih verdict dari `gate`/`evaluation` adalah
    task 2.5, dan mengganti `memory_root` konstanta 1.3d dengan root turunan-memori adalah
    task 2.4b (yang ADR-020 keputusan 6 blokir sampai encoding kanoniknya beku). Yang
    dijamin task ini hanyalah: bahan keputusan datang dari chain + memori sendiri, dan
    jalur penolakannya nol transaksi.
    """

    job: JobView
    mode: ModeDecision
    gate: GateDecision
    evaluation: Evaluation | None
    deliverable: bytes | None

    @property
    def line(self) -> str:
        return JOB_PLAN_TEMPLATE.format(
            job_id=self.job.job_id,
            mode=self.mode.mode,
            depth=self.gate.depth,
            cap="TANPA CAP" if self.gate.cap.cap_usdc is None else self.gate.cap.cap_usdc,
            gate="lolos" if self.gate.accept else "DITOLAK",
            reason=self.gate.reason,
            evaluation=(
                "belum ada deliverable"
                if self.evaluation is None
                else ("LOLOS" if self.evaluation.passed else f"GAGAL {list(self.evaluation.failed_checks)}")
            ),
        )


def verdict_evidence(plan: JobPlan, memory_root: bytes) -> dict:
    """Bundel bukti satu verdict — bahan `reasonHash`. NOL konstanta di dalamnya.

    Isinya seluruhnya turunan job itu: hasil cek deterministik (`Evaluation.to_body()`),
    mode memori yang berlaku, dan `memory_root` yang SAMA yang diumumkan `postVerdict`.
    Root ikut masuk supaya `reasonHash` mengikat verdict pada keadaan memori yang
    melahirkannya; dua nilai yang diumumkan terpisah bisa berasal dari dua keadaan berbeda.

    Bentuk PENUH (bukti per-kriteria yang dipublikasikan + pin IPFS) milik task 2.5. Yang
    dijamin di sini hanya: tidak ada satu pun byte hardcoded, dan hasilnya deterministik
    atas masukan yang sama.
    """
    if plan.evaluation is None:
        raise MemoryRootMismatch(
            "tidak ada hasil evaluasi untuk jobId="
            f"{plan.job.job_id} — tidak ada bukti yang bisa di-hash jadi reasonHash, "
            "jadi tidak ada verdict yang boleh diumumkan"
        )
    return {
        "version": VERDICT_EVIDENCE_VERSION,
        "mode": plan.mode.mode,
        "memory_root": "0x" + bytes(memory_root).hex(),
        "evaluation": plan.evaluation.to_body(),
    }


def verdict_reason_hash(bundle: dict) -> bytes:
    """`reasonHash` = keccak256 dari bundel bukti dalam JSON KANONIK.

    `canonical_json` (memory_policy) dipakai apa adanya: kunci terurut, tanpa spasi, ASCII
    murni, dan setiap integer sebagai STRING DESIMAL — sehingga bundel yang sama menghasilkan
    hash yang sama di Python maupun di alat audit lain, termasuk untuk angka di atas 2^53.
    """
    return bytes(Web3.keccak(text=canonical_json(bundle)))


def plan_job(
    client: VaultClient,
    job: JobView,
    *,
    deliverable_dir: str | os.PathLike[str] | None = None,
    lookback_blocks: int = LOG_LOOKBACK_BLOCKS,
) -> JobPlan:
    """Keputusan memori atas satu job (spec §5 langkah 2-3), TANPA transaksi apa pun.

    Langkah 2 (`gate_job`) selalu dijalankan: ia hanya butuh `provider` + `budget` dari
    struct job dan memori sendiri. Langkah 3 (cek deterministik) hanya jalan bila job sudah
    `Submitted` — sebelum itu belum ada hash deliverable on-chain untuk dibandingkan.

    MELEMPAR `DeliverableUnverifiedError` bila job sudah `Submitted` tetapi hash on-chain
    tidak terbaca atau teks lokal bukan preimage-nya. Pemanggil WAJIB menangkapnya dan
    memasang `client.refuse()`.
    """
    if client.db_path is None:
        raise SafeModeStop(
            "klien vault dibangun tanpa path memori — keputusan memori tidak bisa diambil"
        )
    gate = client.refresh_memory_gate()
    memori = MemoryClient.local(str(client.db_path))
    try:
        decision = gate_job(
            DecisionMemoryView(memori), job.provider, int(job.budget), gate.decision
        )
    finally:
        close_memory_client(memori)

    evaluation: Evaluation | None = None
    onchain: bytes | None = None
    if job.status >= STATUS_SUBMITTED:
        onchain = client.job_deliverable(job.job_id, lookback_blocks=lookback_blocks)
        if onchain is None:
            raise DeliverableUnverifiedError(
                f"{REFUSAL_LINE}: log JobSubmitted(jobId={job.job_id}) tidak ditemukan, "
                "jadi tidak ada hash on-chain untuk membuktikan teks deliverable"
            )
        evaluation = evaluate_job(
            job.job_id,
            onchain,
            depth=decision.depth,
            facts=Web3ChainFacts(client.w3, client.acp.address),
            description=job.description,
            deliverable_dir=(
                configured_deliverable_dir() if deliverable_dir is None else deliverable_dir
            ),
        )
    return JobPlan(job=job, mode=gate.decision, gate=decision, evaluation=evaluation, deliverable=onchain)


def record_outcome(client: VaultClient, plan: JobPlan) -> None:
    """Menulis hasil job ke memori (spec §5 langkah 5) — SESUDAH `postVerdict`, SEBELUM
    `finalize`.

    `client_address` datang dari `getJob`, bukan dari log: `client` TIDAK indexed di
    `JobFunded` (api-facts §A). Tanpa argumen itu ADR-021 keputusan 2 mati diam-diam dan
    provider bisa mendanai jobnya sendiri untuk mengangkat capnya sendiri.

    Yang ditulis HANYA hasil cek deterministik agen (`failed_checks` selalu subset
    `DETERMINISTIC_CHECK_IDS`) — tidak ada jalur dari teks pihak ke memori (spec §3 aturan 3).
    """
    if plan.evaluation is None or client.db_path is None:
        return
    memori = MemoryClient.local(str(client.db_path))
    try:
        profile = record_job_outcome(
            memori,
            plan.job.provider,
            plan.job.job_id,
            int(plan.job.budget),
            plan.evaluation.passed,
            failed_checks=plan.evaluation.failed_checks,
            client_address=plan.job.client_address,
        )
    finally:
        close_memory_client(memori)
    log.info(
        "memori diperbarui: provider=%s jobs=%d pass=%d reject=%d risk=%d insiden=%s",
        profile.address,
        profile.stats_jobs,
        profile.stats_pass,
        profile.stats_reject,
        profile.risk_level,
        list(profile.incident_jobs),
    )


def run_job(
    client: VaultClient,
    job_id: int,
    kind: int,
    *,
    deliverable_dir: str | os.PathLike[str] | None = None,
    lookback_blocks: int = LOG_LOOKBACK_BLOCKS,
) -> int:
    """Jalur `--job-id`: `getJob` → saring evaluator → keputusan memori → pipa verdict.

    Dua jalur berhenti bersih dengan NOL transaksi dan exit 0, dan keduanya memasang kunci
    `client.refuse()` supaya tidak ada jalur lain yang bisa mengirim tx sesudahnya:
      - `evaluator != VAULT` (ADR-022 keputusan 2);
      - `DeliverableUnverifiedError` (ADR-019 keputusan 2, utang task 2.3-min).
    """
    job = client.job(job_id)
    log.info("%s", job.line)
    vault_address = client.vault.address
    if not job.is_for_evaluator(vault_address):
        client.refuse(
            FOREIGN_JOB_TEMPLATE.format(
                job_id=job.job_id, evaluator=job.evaluator, vault=vault_address
            )
        )
        return 0
    try:
        plan = plan_job(
            client, job, deliverable_dir=deliverable_dir, lookback_blocks=lookback_blocks
        )
    except DeliverableUnverifiedError as exc:
        client.refuse(str(exc) if str(exc).startswith(REFUSAL_LINE) else f"{REFUSAL_LINE}: {exc}")
        return 0
    log.info("%s", plan.line)
    return run_live(client, job_id, kind, plan=plan)


# ----------------------------------------------------------------------
# Pipa verdict (jalur --job-id)
# ----------------------------------------------------------------------


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


def run_live(client: VaultClient, job_id: int, kind: int, plan: JobPlan | None = None) -> int:
    """Pipa atas jobId ACP NYATA: postVerdict -> tunggu CHALLENGE_WINDOW -> finalize.

    Hasil yang diharapkan: `Finalized` ADA dan `FinalizeFailed` TIDAK ADA.

    `plan` (task 2.4-min) menyisipkan tulisan memori DI ANTARA `postVerdict` dan `finalize`,
    persis urutan spec §5 langkah 5→6.

    `memory_root` DITURUNKAN dari `memory.db` (task 2.4b, ADR-020 keputusan 6): ia
    `memory_policy.memory_root` atas snapshot gerbang yang baru dibaca — fungsi yang SAMA
    yang dipakai `agent/memory_export.py`. `reason_hash` diturunkan dari bundel bukti job
    itu. Tidak ada satu pun konstanta di jalur ini, dan `_send()` menolak setiap `postVerdict`
    yang membawa root lain.

    Karena root dibaca SEBELUM `record_outcome`, yang diumumkan adalah memori PADA SAAT
    verdict diputuskan — bukan memori sesudah job ini ditulis. Itu memang urutan spec §5
    (langkah 5 sesudah langkah 4), dan konsekuensinya sudah dicatat ADR-023: root lokal
    selalu satu tulisan di depan root on-chain, jadi keduanya TIDAK PERNAH dibandingkan.

    `plan` WAJIB ada dan WAJIB punya `evaluation`: tanpa itu tidak ada bukti yang bisa
    di-hash menjadi `reasonHash`, dan verdict tanpa bukti adalah persis yang dicabut 2.4b.
    """
    kind_name = "complete" if kind == KIND_COMPLETE else "reject"
    log.info("LIVE jobId ACP NYATA=%d kind=%d (%s)", job_id, kind, kind_name)
    if plan is None:
        raise MemoryRootMismatch(
            f"run_live jobId={job_id} tanpa rencana job — tidak ada bukti dan tidak ada "
            "keadaan memori yang bisa diumumkan; nol postVerdict/finalize/setProviderCap"
        )
    # Gerbang dibaca ULANG lebih dulu supaya root yang dicetak/diumumkan adalah root yang
    # SAMA yang akan diperiksa `_send()`. `_send()` tetap membacanya lagi — itu yang mengikat.
    client.refresh_memory_gate()
    memory_root = client.derived_memory_root()
    reason_hash = verdict_reason_hash(verdict_evidence(plan, memory_root))
    log.info("memory_root TURUNAN memory.db di %s = 0x%s", client.db_path, memory_root.hex())
    log.info("reason_hash (TURUNAN bukti job)=0x%s", reason_hash.hex())

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
        post_hash = client.post_verdict(job_id, kind, reason_hash, memory_root)
        post_receipt = client.wait_receipt(post_hash)
        log.info(
            "TX 1 postVerdict = 0x%s (status=%d, blok=%d)",
            post_hash,
            post_receipt.status,
            post_receipt.blockNumber,
        )
        if post_receipt.status != 1:
            raise RuntimeError(f"postVerdict gagal on-chain: 0x{post_hash}")
        # spec §5 langkah 5: memori ditulis SESUDAH verdict diumumkan, sebelum finalize.
        if plan is not None:
            record_outcome(client, plan)
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
    # `--selftest` DICABUT (task 2.4b): ia mengumumkan root konstanta atas jobId sintetis,
    # dan `postVerdict` menulis setiap root ke `knownRoots` tanpa penghapus (ADR-011).
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

    if args.guard is None and args.job_id is None:
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
                return run_job(client, args.job_id, kind)
            except JobVoidedError as exc:
                # Job NYATA yang sudah terminal = verdict yatim: kegagalan pipa, bukan hasil normal.
                log.error("%s", voided_message(exc.job_id, exc.status))
                return 1
        parser.print_usage(sys.stdout)
        return 2
    except (SafeModeStop, DeliverableUnverifiedError) as exc:
        # Jaring kedua: gerbang di atas sudah menahan, jadi ini hanya terjadi bila sebuah
        # jalur baru mencoba mengirim tx tanpa lewat sana. `DeliverableUnverifiedError`
        # ikut di sini karena ADR-019 keputusan 2 menuntut perlakuan SEKELAS mode aman —
        # termasuk pembedaan "berhenti bersih" dari "berhenti di tengah pipa" di bawah.
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
