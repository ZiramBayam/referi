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

BUKTI VERDICT PUNYA DUA BENTUK, dan itu bukan kelengkapan melainkan urutan alur ACP.
Gating cap terjadi saat job masih `Funded` (spec §5 langkah 2), yaitu SEBELUM provider
`submit()` — jadi bundel yang menuntut `Evaluation` membuat verdict `budget > cap`
MUSTAHIL diumumkan. Karena itu `verdict_evidence()` menerima keduanya: bukti dari cek
deterministik (`Evaluation`) dan bukti dari `GateDecision` (cap + basisnya + jobId insiden
yang melahirkannya). Penolakan gerbang hanya sah bersama verdict REJECT, dan `verdict_kind()`
memaksanya persis seperti bunyi spec §5 langkah 2. Eksekusinya sah on-chain: api-facts §A
mencatat `reject` boleh dipanggil evaluator saat status Funded MAUPUN Submitted.

TIGA KODE KELUAR, bukan dua (`EXIT_STOPPED_MIDWAY`, `EXIT_REFUSED`, 0). Mode aman SAAT
START adalah keadaan normal ber-ADR dan tetap 0; penolakan yang muncul SESUDAH gerbang
start lolos (root asing di calldata, mode yang berubah di tengah pipa, bukti yang tidak
cocok dengan verdict) TIDAK boleh memakai kode yang sama dengan run yang berhasil.

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

HARI PERTAMA BUTUH DUA INVOKASI, dan itu perilaku yang DISENGAJA (task 2.5a, ADR-026). Pada
vault segar (`lastMemoryRoot() == 0`) dengan `memory.db` belum ada, gerbang start membaca
NAIF dan run diteruskan — tetapi `plan_job` membuka `MemoryClient.local(db)` yang MEMBUAT
filenya, sehingga gerbang yang dibaca ulang di `run_live` sudah `normal`, penjaga MODE_DRIFT
menolak, dan run berakhir `EXIT_REFUSED` dengan NOL transaksi. Invokasi KEDUA berjalan
sampai selesai dalam mode `normal` atas DB kosong itu — depth `sampling`, `TANPA CAP`, dan
root yang diumumkan SAMA PERSIS dengan `empty_memory_root()`. Jadi mode NAIF tidak pernah
mengumumkan apa pun dari jalur ini, dan yang hilang cuma satu invokasi, bukan satu perilaku.
Cabang NAIF tetap load-bearing: tanpanya "DB hilang + root nol" akan jatuh ke mode aman,
run pertama keluar 0 sebelum menyentuh path DB, dan agen tidak pernah bisa bootstrap.

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
import json
import logging
import os
import sys
import time
from collections.abc import Mapping
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
    CapPlan,
    DecisionMemoryView,
    GateDecision,
    LocalMemoryEvidence,
    MemoryIntegrityError,
    ModeDecision,
    ProviderProfile,
    canonical_json,
    cap_to_onchain,
    decanonical_value,
    decide_mode,
    derive_cap,
    empty_memory_root,
    gate_job,
    local_memory_evidence,
    normalize_address,
    promote_suspicions,
    record_job_outcome,
    record_suspicion,
    store_provider_cap,
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

# Kode keluar untuk PENOLAKAN yang bukan mode aman saat start: root asing di calldata,
# mode yang berubah di tengah pipa, bukti yang tidak cocok dengan verdict. Keadaan itu
# BUKAN jalur normal ber-ADR — ia bug atau perusakan — sedangkan `--job-id` yang SUKSES
# juga mengembalikan 0. Tanpa kode tersendiri, otomasi 2.5 tidak bisa membedakan "verdict
# mendarat" dari "agen menolak calldata-nya sendiri". Mode aman SAAT START tetap 0: ia
# perilaku yang diinginkan (spec §3 aturan 5) dan keluar lebih awal, tidak lewat sini.
EXIT_REFUSED = 4
EXIT_REFUSED_MESSAGE = "AGEN MENOLAK MELANJUTKAN"

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
# seluruh isinya lahir dari job itu — bukan konstanta.
#
# NAIK ke v2 saat bundel PENOLAKAN GERBANG ditambahkan: bentuknya berubah (ada field
# `kind`), dan label versi yang tidak ikut berubah membuat dua bentuk berbeda mengaku
# sebagai satu skema di mata auditor.
#
# NAIK ke v3 saat field `verdict` (ARAH verdict yang BENAR-BENAR diumumkan) ditambahkan —
# temuan RENDAH review putaran-3. Sebelumnya satu `reasonHash` cocok untuk DUA arah:
# bundel `gate-rejection+evaluation` membawa `evaluation.verdict = 1 (complete)` karena
# deliverablenya memang lolos cek, sementara yang diumumkan on-chain REJECT (gerbang
# mengalahkan evaluasi). Tidak ada satu pun field yang menyatakan arah FINAL, jadi bukti
# yang sama bisa "membenarkan" verdict complete maupun reject. Label versi ikut naik karena
# bentuknya berubah; encoding `memory_root` TIDAK disentuh (vektor beku 2.1r).
VERDICT_EVIDENCE_VERSION = "evaluator-verdict-evidence/v3"

# DUA bentuk bukti yang sah, dan keduanya WAJIB ada. Alasannya bukan kelengkapan melainkan
# urutan alur ACP: gating cap terjadi saat job masih `Funded` (spec §5 langkah 2), yaitu
# JAUH sebelum provider `submit()`. Bundel yang menuntut `Evaluation` karena itu tidak
# pernah bisa mengumumkan penolakan `budget > cap` — verdict itu mustahil diumumkan, dan
# gagalnya senyap (`SafeModeStop` → exit 0, nol tx). Itu persis klaim inti PRD.
EVIDENCE_KIND_EVALUATION = "evaluation"      # ada deliverable: skor cek deterministik
EVIDENCE_KIND_GATE_REJECTION = "gate-rejection"  # belum ada deliverable: budget > cap

# BENTUK KETIGA (temuan TINGGI-A review putaran-2). Job yang capnya dilanggar TIDAK selalu
# ditemukan saat masih `Funded`: di `sim/` provider `submit()` lebih dulu, jadi ketika
# operator menjalankan agen job itu sudah `Submitted` dan `Evaluation` SUDAH ADA. Bentuk
# lama memilih bundel `evaluation` begitu `Evaluation` ada, sehingga pelanggaran cap —
# satu-satunya sebab verdict ini lahir — TIDAK muncul sama sekali di bukti yang di-hash
# ke `reasonHash`, dan TASKS 2.5 AC (c) gagal setiap kali job C sempat di-`submit`.
# Karena itu penolakan gerbang atas job yang sudah dinilai membawa KEDUA bagian.
EVIDENCE_KIND_GATE_REJECTION_WITH_EVALUATION = "gate-rejection+evaluation"

# Bentuk bukti yang HANYA sah bersama verdict REJECT (spec §5 langkah 2).
EVIDENCE_KINDS_REQUIRING_REJECT: frozenset[str] = frozenset(
    {EVIDENCE_KIND_GATE_REJECTION, EVIDENCE_KIND_GATE_REJECTION_WITH_EVALUATION}
)

# Nama direktori bundel bukti, DI SAMPING `memory.db` (task 2.5 AC (c): bundel yang
# di-hash ke `reasonHash` disimpan lokal). Bukan hiasan: ia satu-satunya cara membuktikan
# bahwa `reasonHash` yang SUDAH ada on-chain punya preimage yang kita kenal ketika memori
# sudah bergerak maju (spec §5 langkah 5 menulis memori SESUDAH `postVerdict`).
VERDICT_BUNDLE_DIRNAME = "verdicts"
VERDICT_BUNDLE_DIR_ENV = "VERDICT_BUNDLE_DIR"

# Nama file bundel BER-ALAMAT-ISI: `<jobId>-0x<reasonHash>.json` (temuan TINGGI-A7 review
# putaran-3). Bentuk lama `<jobId>.json` punya SATU slot per job dan run berikutnya
# MENIMPAnya, sehingga urutan berikut menghapus preimage `reasonHash` on-chain SELAMANYA:
# run 1 menyimpan B1 → `postVerdict` mendarat → `record_outcome` memajukan memori →
# `finalize` gagal (timeout receipt/Ctrl-C); run 2 dimulai selagi node RPC masih tertinggal
# sehingga `verdicts(jobId)` mengembalikan 0 (lag yang memang ditangani `read_ready_at`) →
# cabang "verdict baru" menghitung B2 dengan root yang sudah maju dan menulisnya DI ATAS B1
# SEBELUM `postVerdict` dikirim, jadi `postVerdict` kedua yang REVERT pun tetap
# menghancurkan B1; run 3, node menyusul, dan B1 tidak bisa dihitung ulang karena memori
# sudah berpindah. Nama yang memuat hashnya sendiri membuat "menimpa" mustahil secara
# konstruksi: isi yang berbeda selalu berarti nama file yang berbeda, dan pembacaan tetap
# TEPAT (bukan menebak) karena `reasonHash` on-chain-lah yang menyusun namanya.
VERDICT_BUNDLE_SUFFIX = ".json"

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

# `getJob(jobId).client` yang tidak berbentuk alamat = pembacaan chain yang GAGAL, dan
# satu-satunya masukan filter ADR-021 keputusan 2. Menilai job dengan nilai itu berarti
# menjalankan filternya dalam keadaan mati, jadi run-nya berhenti SEBELUM tx pertama —
# bukan sesudah `postVerdict` mendarat, yang akan meninggalkan job menggantung dengan
# verdict yang diumumkan tetapi tidak pernah difinalisasi (task 2.4a AC (j)).
BROKEN_CLIENT_TEMPLATE = (
    "MODE AMAN: getJob(jobId={job_id}).client={client!r} bukan alamat EVM — pembacaan "
    "chain GAGAL, dan filter ADR-021 keputusan 2 (client == provider -> budget dibuang) "
    "tidak bisa dievaluasi; menolak postVerdict/finalize/setProviderCap; "
    "job menggantung sampai expiredAt, refund lewat claimRefund publik; "
    "ulangi run ini dengan RPC yang sehat untuk melanjutkan"
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
    # docs/api-facts.md §G.4: `providerCap(address)(uint256)` (selector 0x99893d92) ADA di
    # bytecode vault yang TERDEPLOY. Dibaca sebelum menulis supaya cap yang sudah sama tidak
    # dikirim ulang — dan supaya log agen menyebut nilai on-chain, bukan hanya niatnya.
    {
        "type": "function",
        "name": "providerCap",
        "stateMutability": "view",
        "inputs": [{"name": "", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
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


def verdict_kind_name(kind: int) -> str:
    """Nama `kind` verdict vault (1=complete, 2=reject). 0 = belum ada verdict."""
    return {0: "belum ada", KIND_COMPLETE: "complete", KIND_REJECT: "reject"}.get(
        int(kind), f"tidak dikenal ({int(kind)})"
    )


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


class VerdictMismatch(SafeModeStop):
    """Verdict yang akan diumumkan/dieksekusi TIDAK cocok dengan buktinya sendiri.

    Turunan `SafeModeStop` dengan alasan yang sama seperti `MemoryRootMismatch`: akibatnya
    identik (nol transaksi, `EXIT_REFUSED`), dan `main()` sudah membedakan berhenti bersih
    dari berhenti di tengah pipa. Dipakai untuk tiga keadaan: rencana milik job lain,
    memori yang berubah antara rencana dan pengiriman, dan verdict on-chain yang berbeda
    dari hitungan hari ini.
    """


class UnlimitedCapRefused(SafeModeStop):
    """`setProviderCap` dengan nilai 0 = TANPA BATAS (ADR-001) tanpa jalur sadar."""


class CapRaiseRefused(SafeModeStop):
    """`setProviderCap` yang MELONGGARKAN cap yang sedang ditegakkan vault, tanpa jalur sadar.

    Monoton-tidak-naik yang dijanjikan `derive_cap` berjangkar pada `previous` di
    `memory.db` — file lokal yang kuncinya KOOPERATIF (`memory_policy.py`, blok "BATAS YANG
    DIAKUI"). Selama `set_provider_cap` tidak punya pemanggil produksi, memori yang
    dimundurkan tidak bisa menyentuh penegakan on-chain; sejak ia punya, `providerCap()`
    adalah satu-satunya `previous` yang TIDAK bisa dipalsukan penulis file lokal.
    """


# Nama fungsi vault yang membawa `memory_root` + posisi argumennya. Diambil dari
# `contracts/src/EvaluatorVault.sol`: `postVerdict(uint256 jobId, uint8 kind,
# bytes32 reasonHash, bytes32 memoryRoot)` → indeks 3.
POST_VERDICT_FN = "postVerdict"
POST_VERDICT_ROOT_ARG = 3
POST_VERDICT_ROOT_KWARG = "memoryRoot"

# `setProviderCap(address provider, uint256 capUsdc)` (`contracts/src/EvaluatorVault.sol:287`)
# → provider di indeks 0, cap di indeks 1. Dibaca dari calldata dengan alasan yang sama
# seperti `memoryRoot`: yang dijaga adalah nilai yang benar-benar akan di-encode.
SET_PROVIDER_CAP_FN = "setProviderCap"
SET_PROVIDER_CAP_ARGS = (("provider", 0), ("capUsdc", 1))

ROOT_MISMATCH_TEMPLATE = (
    "ROOT BUKAN TURUNAN MEMORI: postVerdict membawa {given} sementara memory_root atas "
    "{db} saat ini {derived}; menolak mengumumkan root yang tidak bisa direkonstruksi dari "
    "memori; nol postVerdict/finalize/setProviderCap"
)
ROOT_UNREADABLE_TEMPLATE = (
    "ROOT TIDAK BISA DITURUNKAN: memori lokal di {db} {status}, jadi tidak ada memory_root "
    "untuk diumumkan; nol postVerdict/finalize/setProviderCap"
)
ROOT_EMPTY_AFTER_READ_TEMPLATE = (
    "ROOT KOSONG DITOLAK: pipa ini SUDAH pernah membaca memori yang ADA di {db}, jadi root "
    "memori KOSONG tidak boleh diumumkan sebagai keadaan yang melahirkan verdict ini; "
    "nol postVerdict/finalize/setProviderCap"
)
# Mode yang dipakai saat RENCANA disusun WAJIB sama dengan mode saat transaksi dikirim.
# Kalau tidak, `reasonHash` mengikat bundel yang menyatakan satu mode sementara root yang
# diumumkan lahir dari mode lain — auditor yang merekonstruksi memori pelahir verdict
# mendapat keadaan yang berbeda dari yang dinyatakan bundel.
MODE_DRIFT_TEMPLATE = (
    "MODE BERUBAH DI TENGAH PIPA: rencana jobId={job_id} disusun dalam mode {planned} "
    "sementara gerbang saat mengirim membaca mode {current} atas {db}; bundel bukti dan "
    "root yang diumumkan akan berasal dari dua keadaan berbeda; "
    "nol postVerdict/finalize/setProviderCap"
)
# Bundel penolakan gerbang hanya boleh menemani verdict REJECT (spec §5 langkah 2:
# "jika budget > cap → postVerdict(REJECT)"). `complete` dengan bukti penolakan adalah
# verdict yang membantah buktinya sendiri.
GATE_REJECTION_KIND_TEMPLATE = (
    "BUKTI PENOLAKAN GERBANG TIDAK COCOK DENGAN VERDICT: jobId={job_id} kind={kind} "
    "({kind_name}) sementara buktinya adalah penolakan cap; hanya reject yang sah; "
    "nol postVerdict/finalize/setProviderCap"
)
# Cermin aturan di atas untuk bukti CEK DETERMINISTIK (temuan TINGGI-B). Bundel yang
# menyatakan `passed=false` di sebelah verdict `complete` adalah verdict yang membantah
# buktinya sendiri — dan ia MEMBAYAR provider atas pekerjaan yang gagal cek agen sendiri.
FAILED_CHECKS_KIND_TEMPLATE = (
    "BUKTI CEK GAGAL TIDAK COCOK DENGAN VERDICT: jobId={job_id} kind={kind} ({kind_name}) "
    "sementara cek deterministik yang GAGAL adalah {failed}; hanya reject yang sah; "
    "nol postVerdict/finalize/setProviderCap"
)
# Rencana WAJIB milik job yang sedang diumumkan (temuan RENDAH review putaran-2:
# `postVerdict(777, …)` terkirim membawa bundel job 43).
PLAN_JOB_MISMATCH_TEMPLATE = (
    "RENCANA MILIK JOB LAIN: run_live dipanggil untuk jobId={job_id} sementara rencananya "
    "disusun untuk jobId={planned}; bukti dan verdict akan menunjuk dua job berbeda; "
    "nol postVerdict/finalize/setProviderCap"
)
# Rencana WAJIB terikat pada ROOT yang dibacanya (temuan SEDANG-1 putaran-2). Nama mode
# saja TIDAK cukup: penulis `memory.db` yang mendarat SESUDAH `plan_job` (kunci memori
# kooperatif — ancaman MINJA yang diakui `memory_lock.py`) membiarkan mode tetap `normal`
# sementara `derived_memory_root()` sudah mengambil root DB BARU, lalu root itu ditempelkan
# pada `gate`/`cap`/`incident_jobs` hasil DB LAMA. Auditor yang merekonstruksi memori pada
# root yang diumumkan mendapat cap yang berbeda.
ROOT_DRIFT_TEMPLATE = (
    "MEMORI BERUBAH DI TENGAH PIPA: rencana jobId={job_id} dibaca dari memori ber-root "
    "{planned} sementara root {db} saat mengirim {current}; bundel bukti dan root yang "
    "diumumkan akan berasal dari dua keadaan berbeda; "
    "nol postVerdict/finalize/setProviderCap"
)
PLAN_WITHOUT_ROOT_TEMPLATE = (
    "RENCANA TIDAK TERIKAT ROOT: rencana jobId={job_id} tidak membawa root memori yang "
    "melahirkannya, jadi tidak ada yang bisa dibandingkan dengan root yang akan diumumkan; "
    "nol postVerdict/finalize/setProviderCap"
)
# Verdict yang SUDAH ADA on-chain WAJIB sama dengan yang baru dihitung (temuan SEDANG-2).
# Cabang ini dulu memfinalisasi apa pun: verdict `complete` yang terlanjur diumumkan tetap
# dieksekusi walau gerbang SEKARANG menolak, dan run melaporkan exit 0 `PIPA HIDUP SELESAI`.
ONCHAIN_KIND_DRIFT_TEMPLATE = (
    "VERDICT ON-CHAIN BERBEDA DARI HITUNGAN SEKARANG: jobId={job_id} sudah diumumkan "
    "kind={onchain} ({onchain_name}) sementara bukti hari ini menuntut kind={fresh} "
    "({fresh_name}); menolak finalize verdict yang bukan hasil cek sendiri; "
    "nol postVerdict/finalize/setProviderCap"
)
# `reasonHash`/`memoryRoot` on-chain yang tidak punya preimage yang kita kenal: jejak audit
# akan menunjuk bundel yang BUKAN yang terikat on-chain. Satu-satunya pengecualian yang sah
# adalah bundel tersimpan milik run yang mengumumkannya — dibuktikan dengan keccak, bukan
# dengan kepercayaan.
ONCHAIN_EVIDENCE_DRIFT_TEMPLATE = (
    "BUKTI ON-CHAIN TIDAK BISA DIREPRODUKSI: jobId={job_id} terikat reasonHash={onchain_hash} "
    "memoryRoot={onchain_root} sementara run ini menghitung reasonHash={fresh_hash} "
    "memoryRoot={fresh_root}, dan tidak ada bundel tersimpan di {store} yang keccak-nya "
    "sama dengan reasonHash on-chain untuk job dan arah verdict ini; menolak finalize bukti "
    "yang tidak bisa ditunjukkan. Toko bukti itu tidak terlacak git — pulihkan berkas "
    "{store}/{job_id}-<reasonHash>.json dari backup yang sama dengan memory.db; "
    "nol postVerdict/finalize/setProviderCap"
)
# Jalur SAH untuk perbedaan di atas: memori maju SESUDAH `postVerdict` (spec §5 langkah 5),
# jadi root hari ini memang lebih baru. Yang mengikat tetap bundel on-chain, dan ia
# DITUNJUKKAN — bukan diklaim.
ONCHAIN_BUNDLE_REPRODUCED_TEMPLATE = (
    "bundel bukti on-chain jobId={job_id} DIREPRODUKSI dari {path}: reasonHash={hash} "
    "memoryRoot={root}. Memori sudah maju sejak verdict itu diumumkan (spec §5 langkah 5), "
    "jadi root hari ini ({fresh_root}) berbeda dan BUKAN yang mengikat verdict ini"
)
# Nama file bundel diturunkan dari keccak isinya, jadi "file itu sudah ada dengan isi LAIN"
# berarti dua teks berbeda dengan keccak sama — tabrakan keccak256, atau (jauh lebih
# mungkin) file yang diedit tangan. Keduanya membuat toko bukti tidak bisa dipercaya, dan
# menimpanya justru menghapus preimage yang mungkin sudah terikat on-chain.
BUNDLE_COLLISION_TEMPLATE = (
    "TOKO BUKTI TIDAK KONSISTEN: {path} sudah ada dengan isi BERBEDA padahal namanya "
    "diturunkan dari keccak isinya (jobId={job_id}); file itu TIDAK ditimpa. Periksa/pindahkan "
    "berkas itu sebelum menjalankan ulang; nol postVerdict/finalize/setProviderCap"
)
# `setProviderCap(provider, 0)` berarti TANPA BATAS di kontrak (ADR-001), dan ia MENIMPA
# cap yang sudah ketat tanpa syarat (`EvaluatorVault.sol:287-291`). Peracun cukup MENGHAPUS
# satu entity `provider` dari `memory.db` — DB tetap ada, mode tetap NORMAL — untuk membuat
# `derive_cap` melihat profil kosong (`risk=0`, `previous=None`) dan mengembalikan `NO_CAP`.
# Penjaganya ada DI BATAS KIRIM, bukan di `derive_cap`: monoton-tidak-naik di sana bersandar
# pada `previous` yang ikut terhapus.
UNLIMITED_CAP_TEMPLATE = (
    "CAP TANPA BATAS DITOLAK: setProviderCap({provider}, {cap}) — nilai 0 berarti TANPA "
    "BATAS di kontrak (ADR-001) dan MENIMPA cap yang sudah ada; memori di {db} mungkin "
    "kehilangan profil provider ini. Kirim hanya lewat jalur sadar "
    "(set_provider_cap(..., allow_unlimited=True)); nol setProviderCap"
)
NEGATIVE_CAP_TEMPLATE = (
    "CAP NEGATIF DITOLAK: setProviderCap({provider}, {cap}) bukan uint256; nol setProviderCap"
)
# LANTAI MONOTON ON-CHAIN. `providerCap()` yang sedang ditegakkan vault MENGIKAT: cap baru
# boleh sama atau lebih ketat, tidak pernah lebih longgar. Tanpa ini, penulis `memory.db`
# (dan operator yang menjalankan ulang dari snapshot lama) bisa MENAIKKAN cap on-chain —
# yaitu melonggarkan satu-satunya penegakan yang didemokan spec §7 langkah 2 — tanpa satu
# baris pun yang mengatakannya. Nilai 0 on-chain BUKAN cap terkecil melainkan TANPA BATAS
# (ADR-001), jadi ia tidak pernah menjadi lantai.
CAP_RAISE_TEMPLATE = (
    "CAP DINAIKKAN DITOLAK: setProviderCap({provider}, {cap}) MELONGGARKAN cap yang sedang "
    "ditegakkan vault ({onchain}); memori di {db} mungkin dimundurkan ke snapshot lama. "
    "Kirim hanya lewat jalur sadar (set_provider_cap(..., allow_raise=True)); nol setProviderCap"
)
# `--kind` TIDAK punya default (temuan TINGGI-B). Default `complete` berarti baris perintah
# terpendek adalah baris yang MEMBAYAR provider; verdict adalah milik cek, dan pilihan
# operator di atasnya harus diketik.
KIND_REQUIRED_MESSAGE = (
    "--kind WAJIB disebut bersama --job-id (complete|reject): tidak ada verdict default. "
    "Gerbang cap dan cek deterministik tetap bisa MEMAKSA reject di atas pilihan itu."
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


def contract_call_cap(func) -> tuple[str, int] | None:
    """`(provider, capUsdc)` yang BENAR-BENAR masuk calldata `setProviderCap`.

    Sumbernya sama dengan `contract_call_root`: `ContractFunction.args`/`.kwargs`, bukan
    salinan yang dioper terpisah ke penjaga.
    """
    args = getattr(func, "args", None) or ()
    kwargs = getattr(func, "kwargs", None) or {}
    keluar: list = []
    for name, index in SET_PROVIDER_CAP_ARGS:
        if name in kwargs:
            keluar.append(kwargs[name])
        elif len(args) > index:
            keluar.append(args[index])
        else:
            return None
    provider, cap = keluar
    return str(provider), int(cap)


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
        # LATCH ASAL-USUL ROOT (temuan SEDANG-1). True begitu klien ini SEKALI saja membaca
        # `memory.db` yang ADA dan terbaca. Sejak itu root memori KOSONG (cabang NAIF)
        # DILARANG diumumkan: kalau file hilang di tengah pipa, gerbang berubah menjadi
        # NAIF dan `postVerdict` akan membawa root DB KOSONG sementara `reasonHash`
        # mengikat bundel yang menyatakan mode sebelumnya. Auditor yang merekonstruksi
        # memori pelahir verdict itu mendapat DB kosong — persis klaim yang ditutup 2.4b.
        # JANGKAUANNYA, diukur bukan diklaim (task 2.5a, ADR-026): latch ini TIDAK PERNAH
        # menggigit lewat `--job-id`. Cabang yang dijaganya menuntut mode NAIF saat tx
        # dikirim, dan mode itu tidak bisa bertahan sampai ke sana: `plan_job` membuka
        # `MemoryClient.local(db)` yang MEMBUAT filenya, sehingga gerbang yang dibaca ulang
        # `run_live` sudah `normal` dan penjaga MODE_DRIFT menolak lebih dulu (exit 4, nol
        # tx). Prasyarat `lastMemoryRoot == 0` juga tidak berlaku di vault beku ADR-022.
        # Yang tersisa adalah pemanggil PUSTAKA yang memanggil `post_verdict()`/
        # `derived_memory_root()` langsung tanpa lewat `run_live` — dan justru untuk merekalah
        # latch ini ada, alasan yang sama seperti mode aman ditegakkan di `_send()`.
        self.observed_readable_memory = False
        # KUNCI SEKALI-JALAN. Sekali diisi, `_send()` menolak setiap transaksi sampai proses
        # ini mati. Diisi oleh TIGA penolakan yang bukan verdict: job milik evaluator lain,
        # deliverable yang tidak terverifikasi (ADR-019 keputusan 2), dan `getJob().client`
        # yang tidak terbaca (task 2.4a AC (j)). Ia ada karena
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
        if gate.local.local_memory_readable:
            self.observed_readable_memory = True
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
        keadaan DB yang sama (pembacaan terpisah tidak berbagi satu transaksi — §C.2).

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
        # JANGKAUAN cabang ini, diukur (task 2.5a, ADR-026): NOL lewat `--job-id`. Sebelum
        # `run_live` sempat memakainya, `plan_job` sudah membuat `memory.db`, jadi gerbang
        # yang mengikat tx membaca `normal` dan MODE_DRIFT menolak (exit 4, nol tx). Yang
        # diumumkan pada vault segar karena itu SELALU root DB kosong yang baru dibuat —
        # dan nilainya SAMA PERSIS dengan `empty_memory_root()` (dijaga tes), sehingga
        # ketidakterjangkauan ini tidak mengubah satu byte pun yang sampai ke chain.
        # Cabang ini tetap ada untuk pemanggil PUSTAKA (`post_verdict()` langsung) dan
        # sebagai nilai yang benar bagi mode NAIF; menghapusnya butuh ADR baru.
        if gate.decision.mode == MODE_NAIVE:
            # SATU pengecualian atas cabang itu: klien yang pernah membaca memori yang ADA
            # tidak boleh "kembali" menjadi naif. Lihat `observed_readable_memory`.
            if self.observed_readable_memory:
                raise MemoryRootMismatch(
                    ROOT_EMPTY_AFTER_READ_TEMPLATE.format(db=gate.db_path)
                )
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

    def provider_cap(self, provider: str) -> int:
        """`providerCap(provider)` di vault (read-only, api-facts §G.4).

        Nilai 0 di sini berarti TANPA BATAS (ADR-001), bukan "diblokir" — jangan pernah
        dibaca sebagai cap terkecil.
        """
        return int(self.vault.functions.providerCap(Web3.to_checksum_address(provider)).call())

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

    def _require_onchain_cap_floor(self, func) -> None:
        """LANTAI MONOTON ON-CHAIN untuk `setProviderCap` (temuan TINGGI-1).

        Ditegakkan DI SINI, atas nilai yang benar-benar masuk calldata, dengan alasan yang
        sama seperti mode aman dan root turunan: pemanggil baru yang membangun
        `setProviderCap` sendiri tetap harus berhenti. `providerCap()` yang sedang
        ditegakkan vault adalah satu-satunya `previous` yang tidak bisa dipalsukan penulis
        `memory.db`; cap yang MELONGGARKANNYA ditolak. Nilai 0 on-chain bukan lantai — ia
        TANPA BATAS (ADR-001), jadi apa pun di atasnya justru mengetatkan.
        """
        panggilan = contract_call_cap(func)
        if panggilan is None:
            return
        provider, cap = panggilan
        onchain = self.provider_cap(provider)
        if onchain > 0 and cap > onchain:
            raise CapRaiseRefused(
                CAP_RAISE_TEMPLATE.format(
                    provider=provider, cap=cap, onchain=onchain, db=self.db_path
                )
            )

    def _send(self, func, extra: dict | None = None, *, allow_raise: bool = False) -> str:
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
        # Lantai cap dibaca SESUDAH gerbang memori dan kunci penolakan: agen yang berhenti
        # karena memorinya tidak boleh membuang panggilan RPC lebih dulu, dan pesannya
        # harus tetap `MODE AMAN`.
        if action == SET_PROVIDER_CAP_FN and not allow_raise:
            self._require_onchain_cap_floor(func)
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

    def set_provider_cap(
        self,
        provider: str,
        cap_usdc: int,
        *,
        allow_unlimited: bool = False,
        allow_raise: bool = False,
    ) -> str:
        """`setProviderCap` (spec §3 aturan 4). ADR-020 keputusan 8: ikut ditahan mode aman.

        Ia tidak menyentuh job tertentu, jadi TIDAK ada penjaga status job di sini —
        penjaga yang berlaku untuknya adalah gerbang memori di `_send()`.

        NILAI 0 DITOLAK di sini, di BATAS KIRIM (temuan SEDANG-3 review putaran-2). Di
        kontrak 0 berarti TANPA BATAS (ADR-001) dan `EvaluatorVault.setProviderCap` menimpa
        nilai lama tanpa syarat, jadi SATU panggilan dengan `cap_to_onchain(CapPlan(None))`
        mematikan gating yang justru sedang didemokan. Penjaganya tidak bisa ditaruh di
        `derive_cap`: monoton-tidak-naik di sana bersandar pada `previous`, dan serangan
        yang membuat `NO_CAP` justru MENGHAPUS profil yang menyimpan `previous` itu.
        `allow_unlimited=True` adalah satu-satunya jalur sadar — ia harus diketik pemanggil.

        NILAI YANG MELONGGARKAN JUGA DITOLAK, dengan alasan yang sepenuhnya sejajar. Klaim
        monoton-tidak-naik `derive_cap` berjangkar pada `previous` yang tersimpan di
        `memory.db`, sementara `providerCap()` adalah keadaan yang tidak bisa disentuh
        penulis file lokal. Jadi cap yang sedang ditegakkan vault dipakai sebagai LANTAI:
        `cap > providerCap(provider)` saat `providerCap` > 0 ditolak kecuali
        `allow_raise=True`. `providerCap == 0` bukan lantai — ia TANPA BATAS (ADR-001), dan
        nilai apa pun di atasnya justru MENGETATKAN. Penjaganya sendiri duduk di `_send()`
        (`_require_onchain_cap_floor`), sesudah gerbang memori: jalur baru yang membangun
        `setProviderCap` tanpa lewat metode ini pun tetap berhenti.
        """
        cap = int(cap_usdc)
        if cap < 0:
            raise UnlimitedCapRefused(NEGATIVE_CAP_TEMPLATE.format(provider=provider, cap=cap))
        if cap == 0 and not allow_unlimited:
            raise UnlimitedCapRefused(
                UNLIMITED_CAP_TEMPLATE.format(provider=provider, cap=cap, db=self.db_path)
            )
        tx_hash = self._send(
            self.vault.functions.setProviderCap(Web3.to_checksum_address(provider), cap),
            allow_raise=allow_raise,
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
    # ROOT memori yang MELAHIRKAN rencana ini (temuan SEDANG-1 review putaran-2). Nama
    # mode saja tidak mengikat apa pun: memori yang ditulis SESUDAH `plan_job` membiarkan
    # mode tetap `normal` sementara root sudah berpindah, dan `run_live` akan menempelkan
    # root BARU pada `gate`/`cap`/`incident_jobs` yang lahir dari DB LAMA. `None` berarti
    # rencana ini tidak terikat root sama sekali — `run_live` menolaknya.
    memory_root: bytes | None = None

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


def gate_rejection_body(plan: JobPlan) -> dict:
    """Isi bukti penolakan GERBANG — lahir dari `GateDecision`, tanpa `Evaluation`.

    Ini bukan ringkasan: ia memuat seluruh rantai sebab yang membuat job ditolak saat masih
    `Funded`, sehingga auditor bisa menghitung ulang keputusannya dari memori yang
    dijangkar `memory_root` di bundel yang sama —
      - `budget` job ini dan `cap` yang dilanggarnya (nilai + `basis` perhitungannya +
        besar sampel + apakah milestone diwajibkan);
      - `risk_level` yang menentukan rumus cap (spec §3 aturan 4);
      - `incident_jobs`, yaitu jobId yang MELAHIRKAN cap itu. Tanpa daftar ini bundelnya
        hanya angka tanpa asal-usul, dan TASKS 2.5 AC (c) menuntut kedua jobId insiden
        ada di dalamnya.
    Semuanya berasal dari entity `provider` + hasil cek deterministik sendiri; tidak ada
    satu pun nilai yang datang dari teks pihak (spec §3 aturan 3).
    """
    cap = plan.gate.cap
    return {
        "job": int(plan.job.job_id),
        "provider": plan.job.provider,
        "budget": int(plan.job.budget),
        "accept": bool(plan.gate.accept),
        "reason": plan.gate.reason,
        "depth": plan.gate.depth,
        "risk_level": int(plan.gate.risk_level),
        "incident_jobs": [int(j) for j in plan.gate.incident_jobs],
        "cap": {
            "usdc": None if cap.cap_usdc is None else int(cap.cap_usdc),
            "basis": cap.basis,
            "sample_size": int(cap.sample_size),
            "require_milestone": bool(cap.require_milestone),
        },
    }


def verdict_evidence(plan: JobPlan, memory_root: bytes, kind: int) -> dict:
    """Bundel bukti satu verdict — bahan `reasonHash`. NOL konstanta di dalamnya.

    DUA bentuk, dan keduanya sah karena verdict lahir di DUA titik alur yang berbeda:

      1. `EVIDENCE_KIND_EVALUATION` — job sudah `Submitted`: isinya hasil cek deterministik
         (`Evaluation.to_body()`).
      2. `EVIDENCE_KIND_GATE_REJECTION` — job masih `Funded` dan gerbang cap MENOLAKnya
         (spec §5 langkah 2). Di sini deliverable belum ada sama sekali, jadi menuntut
         `Evaluation` berarti verdict `budget > cap` tidak pernah bisa diumumkan — bentuk
         lama menolaknya dan agen berhenti dengan NOL transaksi.

    Yang sama di kedua bentuk: `mode` memori yang berlaku dan `memory_root` yang SAMA yang
    diumumkan `postVerdict`. Root ikut masuk supaya `reasonHash` mengikat verdict pada
    keadaan memori yang melahirkannya; dua nilai yang diumumkan terpisah bisa berasal dari
    dua keadaan berbeda.

      3. `EVIDENCE_KIND_GATE_REJECTION_WITH_EVALUATION` — gerbang cap MENOLAK job yang
         KEBETULAN sudah `Submitted`. Di `sim/` urutan itu NORMAL: provider `submit()`
         sebelum agen sempat dijalankan. Bentuk lama memilih bundel `evaluation` begitu
         `Evaluation` ada, sehingga pelanggaran cap — sebab lahirnya verdict ini — hilang
         seluruhnya dari bukti yang di-hash. Bundel ini membawa KEDUANYA: `gate` yang
         menyatakan cap yang dilanggar beserta jobId insidennya, dan `evaluation` yang
         menyatakan apa yang sempat diperiksa atas deliverable itu.

    Yang TETAP ditolak: job tanpa `Evaluation` yang gerbangnya LOLOS. Di sana memang belum
    ada apa pun untuk dinilai, dan verdict tanpa bukti adalah persis yang dicabut 2.4b.

    `kind` = ARAH verdict yang benar-benar diumumkan, dan ia ikut ter-hash (v3, temuan
    RENDAH putaran-3). Tanpanya satu `reasonHash` cocok untuk DUA arah: bundel
    `gate-rejection+evaluation` membawa `evaluation.verdict = complete` (deliverablenya
    memang lolos cek) sementara yang diumumkan REJECT karena gerbang mengalahkan evaluasi.
    Field `evaluation.verdict` TETAP berarti "arah yang disiratkan hasil cek", dan
    `verdict` di puncak berarti "arah yang diumumkan"; keduanya sengaja boleh berbeda,
    tetapi sekarang perbedaannya TERTULIS di bukti, bukan tersirat.
    """
    dasar = {
        "version": VERDICT_EVIDENCE_VERSION,
        "mode": plan.mode.mode,
        "memory_root": "0x" + bytes(memory_root).hex(),
        "verdict": int(kind),
    }
    if not plan.gate.accept:
        # Penolakan gerbang mendahului bentuk `evaluation`, dan tidak pernah MENGGANTIKANnya:
        # bila keduanya ada, keduanya ikut. Urutan `if` inilah temuan TINGGI-A.
        bundel = {**dasar, "kind": EVIDENCE_KIND_GATE_REJECTION, "gate": gate_rejection_body(plan)}
        if plan.evaluation is not None:
            bundel["kind"] = EVIDENCE_KIND_GATE_REJECTION_WITH_EVALUATION
            bundel["evaluation"] = plan.evaluation.to_body()
        return bundel
    if plan.evaluation is not None:
        return {
            **dasar,
            "kind": EVIDENCE_KIND_EVALUATION,
            "evaluation": plan.evaluation.to_body(),
        }
    raise MemoryRootMismatch(
        f"BELUM ADA YANG BISA DIUMUMKAN untuk jobId={plan.job.job_id}: gerbang MELOLOSKAN "
        f"budget {plan.job.budget} (status job {plan.job.status}) dan provider belum "
        "submit(), jadi belum ada hasil cek maupun penolakan cap yang bisa di-hash jadi "
        "reasonHash; tunggu JobSubmitted (spec §5 langkah 2 vs 3). "
        "Nol postVerdict/finalize/setProviderCap"
    )


def evidence_kind(bundle: Mapping[str, object]) -> str:
    """`kind` bundel bukti. Dipakai penjaga di `run_live`, bukan untuk menebak isi."""
    return str(bundle.get("kind", ""))


def verdict_reason_hash(bundle: dict) -> bytes:
    """`reasonHash` = keccak256 dari bundel bukti dalam JSON KANONIK.

    `canonical_json` (memory_policy) dipakai apa adanya: kunci terurut, tanpa spasi, ASCII
    murni, dan setiap integer sebagai STRING DESIMAL — sehingga bundel yang sama menghasilkan
    hash yang sama di Python maupun di alat audit lain, termasuk untuk angka di atas 2^53.
    """
    return bytes(Web3.keccak(text=canonical_json(bundle)))


def verdict_bundle_dir(client: VaultClient) -> Path:
    """Direktori bundel bukti, DI SAMPING `memory.db` klien ini (atau `VERDICT_BUNDLE_DIR`).

    Dijangkarkan ke memori, bukan ke direktori kerja, dengan alasan yang sama seperti
    `memory_db_path()`: yang menentukan artefak mana yang berlaku adalah konfigurasi.
    """
    if client.db_path is None:
        raise SafeModeStop(
            "klien vault dibangun tanpa path memori — bundel bukti tidak punya tempat, "
            "jadi tidak ada transaksi yang boleh dikirim"
        )
    raw = config_value(VERDICT_BUNDLE_DIR_ENV, "")
    if raw:
        arah = Path(raw).expanduser()
        return arah if arah.is_absolute() else (agent_root() / arah).resolve()
    return client.db_path.parent / VERDICT_BUNDLE_DIRNAME


def verdict_bundle_path(directory: Path, job_id: int, reason_hash: bytes) -> Path:
    """Path BER-ALAMAT-ISI satu bundel: `<jobId>-0x<reasonHash>.json`.

    `int()`/`hex()` membuat kedua bagian nama tidak bisa membawa pemisah path, jadi nilai
    dari chain maupun dari baris perintah tidak pernah keluar dari `directory`.
    """
    return directory / f"{int(job_id)}-0x{bytes(reason_hash).hex()}{VERDICT_BUNDLE_SUFFIX}"


def store_verdict_bundle(directory: Path, job_id: int, bundle: Mapping[str, object]) -> Path:
    """Menyimpan JSON KANONIK bundel — persis byte yang di-keccak jadi `reasonHash`.

    Ditulis SEBELUM `postVerdict` dikirim: bundel yang lahir sesudah transaksinya mendarat
    tidak pernah ada untuk verdict yang gagal di tengah jalan, dan justru run berikutnya
    yang membutuhkannya (spec §5 langkah 5 memajukan memori, jadi root hari ini berbeda).
    Menyimpan TEKS-nya, bukan objeknya, supaya perbandingan berikutnya adalah keccak atas
    byte yang sama — bukan hasil serialisasi ulang yang kebetulan mirip.

    SEKALI-TULIS, dan itu bukan kehati-hatian melainkan syarat hidup `reasonHash` (temuan
    TINGGI-A7): nama file diturunkan dari keccak isinya, jadi bundel yang berbeda TIDAK
    PERNAH menempati slot yang sama, dan run berikutnya — termasuk run yang dimulai selagi
    node RPC masih tertinggal dan mengira belum ada verdict — tidak bisa menghapus preimage
    verdict yang sudah diumumkan. `open("x")` dipakai supaya tabrakan nama menjadi galat
    yang terlihat, bukan penimpaan diam-diam; isi yang sama persis diperlakukan idempoten.
    """
    directory.mkdir(parents=True, exist_ok=True)
    text = canonical_json(dict(bundle))
    reason_hash = bytes(Web3.keccak(text=text))
    path = verdict_bundle_path(directory, job_id, reason_hash)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != text:
            raise VerdictMismatch(
                BUNDLE_COLLISION_TEMPLATE.format(path=path, job_id=int(job_id))
            ) from None
    return path


def stored_verdict_bundle(directory: Path, job_id: int, reason_hash: bytes) -> tuple[Path, str | None]:
    """Teks bundel tersimpan untuk `reasonHash` job ini. Tidak ada = `None`, bukan galat.

    Pembacaan TIDAK menebak: `reasonHash` datang dari `verdicts(jobId)` on-chain dan
    namanya menentukan satu file, jadi tidak ada pemindaian direktori yang bisa
    "menemukan" bundel milik job atau verdict lain.
    """
    path = verdict_bundle_path(directory, job_id, reason_hash)
    try:
        return path, path.read_text(encoding="utf-8")
    except OSError:
        return path, None


def bundle_job_ids(body: Mapping[str, object]) -> set[int]:
    """jobId yang DIKLAIM isi bundel — dari `gate.job` dan/atau `evaluation.job`.

    Kosong berarti bundel tidak menyebut job mana pun; itu ditolak, bukan dimaafkan.
    Nilai non-integer juga membuat hasilnya kosong: bundel yang jobnya tidak terbaca sama
    saja dengan bundel yang tidak menyebut job.
    """
    ids: set[int] = set()
    for section in ("gate", "evaluation"):
        part = body.get(section)
        if not isinstance(part, Mapping) or "job" not in part:
            continue
        nomor = part["job"]
        if not isinstance(nomor, int) or isinstance(nomor, bool):
            return set()
        ids.add(int(nomor))
    return ids


def bundle_reproduces_onchain(text: str, job_id: int, existing: VerdictState) -> bool:
    """Bundel tersimpan itu preimage `reasonHash` on-chain untuk JOB INI, verdict INI.

    EMPAT syarat, dan semuanya wajib. Tiga yang pertama dibuktikan dengan keccak dan
    dengan isi bundel, bukan dengan kepercayaan pada file lokal:

      1. keccak(teks) == `reasonHash` on-chain — menyodorkan bundel palsu untuk
         `reasonHash` asing menuntut preimage keccak256;
      2. `memory_root` di dalamnya == `memoryRoot` on-chain — bundel yang menjangkarkan
         verdict pada keadaan memori LAIN bukan bukti verdict ini;
      3. `job` DI DALAM bundel == jobId yang sedang difinalisasi (temuan SEDANG-A9).
         Syarat 1 dan 2 saja TIDAK mengikat job: reviewer menaruh bundel SAH milik job 42
         sebagai bukti job 43 (dengan `verdicts(43).reasonHash = keccak(bundel_42)`) dan
         job 43 IKUT difinalisasi sambil mencetak "DIREPRODUKSI". Isinya memang sudah
         job-bound sejak semula (`gate.job`, `evaluation.job`) — yang kurang justru
         pembacaannya di sini;
      4. `verdict` di dalamnya == `kind` on-chain — bukti mengikat ARAH verdict, bukan
         hanya keadaan yang melahirkannya (v3).
    """
    if bytes(Web3.keccak(text=text)) != bytes(existing.reason_hash):
        return False
    try:
        # `decanonical_value` mengembalikan `{"$u": "43"}` menjadi `43` — bentuk integer
        # kanonik encoding ini (memory_policy). Membaca `json.loads` apa adanya berarti
        # membandingkan penanda dengan angka dan tidak pernah cocok.
        body = decanonical_value(json.loads(text))
    except (ValueError, MemoryIntegrityError):
        return False
    if not isinstance(body, dict):
        return False
    if body.get("memory_root") != "0x" + bytes(existing.memory_root).hex():
        return False
    if bundle_job_ids(body) != {int(job_id)}:
        return False
    return body.get("verdict") == int(existing.kind)


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
    # Root DIREKAM di sini, pada pembacaan gerbang yang SAMA yang memberi `mode` dan
    # menjadi dasar `gate_job` di bawah — bukan dihitung ulang saat mengirim. Kegagalan
    # menurunkan root bukan alasan untuk membatalkan rencana (mode aman punya jalurnya
    # sendiri), tetapi rencana tanpa root TIDAK boleh menghasilkan transaksi: `run_live`
    # menolak `memory_root=None`.
    try:
        root_rencana: bytes | None = client.derived_memory_root()
    except MemoryRootMismatch as exc:
        log.warning("root memori tidak bisa diturunkan saat menyusun rencana: %s", exc)
        root_rencana = None
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
    return JobPlan(
        job=job,
        mode=gate.decision,
        gate=decision,
        evaluation=evaluation,
        deliverable=onchain,
        memory_root=root_rencana,
    )


def record_outcome(client: VaultClient, plan: JobPlan) -> ProviderProfile | None:
    """Menulis hasil job ke memori (spec §5 langkah 5) — SESUDAH `postVerdict`, SEBELUM
    `finalize`. Mengembalikan profil provider SESUDAH tulisan itu, atau `None` bila tidak
    ada yang bisa ditulis (job belum `Submitted`, jadi belum ada hasil cek).

    TIGA tulisan, bukan satu, dan urutannya persis bunyi spec §5 langkah 5 — *"pola gagal
    deterministik → `suspicion` (atau promosi); update `provider`"*:

      1. `record_suspicion` untuk SETIAP pola gagal deterministik job ini (`Evaluation
         .incidents()`). Karantina hanya menyimpan bukti; ia TIDAK PERNAH dibaca jalur
         keputusan (spec §3 aturan 1, ADR-002).
      2. `promote_suspicions`, yang mempromosikan HANYA karantina yang sudah punya bukti
         dari >= 2 job BERBEDA dan seluruhnya dari cek deterministik (spec §3 aturan 2)
         → `reference:pattern:{id}` + `provider.confirmed_patterns`.
      3. `record_job_outcome`, yang memperbarui statistik + `incident_jobs` + `risk_level`.

    Tanpa (1) dan (2), `reference:pattern` dan `confirmed_patterns` tidak pernah lahir dari
    pipa: `risk` tetap naik dari `incident_jobs`, tetapi pola yang dipelajari — bagian yang
    membuat memori ini bisa dibaca manusia dan diaudit — tidak ada di mana pun.

    `client_address` datang dari `getJob`, bukan dari log: `client` TIDAK indexed di
    `JobFunded` (api-facts §A). Tanpa argumen itu ADR-021 keputusan 2 mati diam-diam dan
    provider bisa mendanai jobnya sendiri untuk mengangkat capnya sendiri.

    Yang MEMUTUSKAN hanya hasil cek deterministik agen (`failed_checks` selalu subset
    `DETERMINISTIC_CHECK_IDS`, `Incident.evidence.check_id` divalidasi ulang di
    `record_suspicion`) — nol angka/keputusan di memori lahir dari teks pihak (spec §3
    aturan 3).

    TEKS PIHAK TETAP MASUK MEMORI, dan itu harus disebut apa adanya. `Evidence.proof`
    membawa KUTIPAN deliverable (mis. jendela 60 karakter di sekitar temuan cek `format`),
    dan `promote_suspicions` menyalinnya ke `reference:pattern:{id}.examples` — tier yang
    BOLEH dibaca jalur keputusan (`DECISION_REFERENCE_PREFIXES`) dan yang ikut ter-hash ke
    `memory_root` yang diumumkan on-chain. Yang menahannya: kutipan itu DATA, bukan
    instruksi (alasan lengkap di `Evidence.__post_init__`), disanitasi di SATU tempat
    (`checks.base.excerpt`: non-printable → spasi, whitespace diciutkan, potong di 160;
    batas keras `MAX_PROOF_LEN` 512 divalidasi ulang di konstruktor), dan nol keputusan
    hari ini membaca isinya. Siapa pun yang menambahkan `view.pattern(...)` ke sebuah
    keputusan sedang mengonsumsi teks yang dikendalikan pihak lain — perlakukan begitu, dan
    jangan melemahkan sanitasinya.
    Seluruhnya idempoten per `job_id`: bukti berulang dari job yang sama tidak menggerakkan
    ambang promosi (dedup `(job_id, check_id)`), dan karantina yang sudah `promoted` tidak
    pernah dipromosikan dua kali.
    """
    if plan.evaluation is None or client.db_path is None:
        return None
    provider = plan.job.provider
    memori = MemoryClient.local(str(client.db_path))
    try:
        for incident in plan.evaluation.incidents():
            body = record_suspicion(memori, provider, incident.pattern_id, incident.evidence)
            log.info(
                "karantina ditulis: provider=%s pola=%s count=%d (bukti dari cek %s)",
                provider,
                incident.pattern_id,
                int(body["count"]),
                incident.evidence.check_id,
            )
        promoted = promote_suspicions(memori, provider)
        if promoted:
            log.info(
                "POLA DIPROMOSIKAN (>= 2 job berbeda, semua bukti deterministik): "
                "provider=%s pola=%s → reference:pattern + confirmed_patterns",
                provider,
                promoted,
            )
        profile = record_job_outcome(
            memori,
            provider,
            plan.job.job_id,
            int(plan.job.budget),
            plan.evaluation.passed,
            failed_checks=plan.evaluation.failed_checks,
            client_address=plan.job.client_address,
        )
    finally:
        close_memory_client(memori)
    log.info(
        "memori diperbarui: provider=%s jobs=%d pass=%d reject=%d risk=%d insiden=%s pola=%s",
        profile.address,
        profile.stats_jobs,
        profile.stats_pass,
        profile.stats_reject,
        profile.risk_level,
        list(profile.incident_jobs),
        list(profile.confirmed_patterns),
    )
    return profile


def store_cap_in_memory(client: VaultClient, provider_address: str, cap: CapPlan) -> None:
    """Menuliskan cap yang BENAR-BENAR berlaku on-chain ke profil provider.

    Dipanggil di KEDUA cabang `sync_provider_cap` — sesudah tx yang mendarat, dan juga saat
    vault sudah memegang nilainya. Cabang kedua dulu melewatinya, sehingga `cap_usdc` tetap
    `None` di body yang masuk preimage `memory_root` (temuan RENDAH-1).
    """
    if client.db_path is None:
        return
    memori = MemoryClient.local(str(client.db_path))
    try:
        store_provider_cap(memori, provider_address, cap)
    finally:
        close_memory_client(memori)


def sync_provider_cap(
    client: VaultClient, mode: ModeDecision, profile: ProviderProfile | None
) -> str | None:
    """spec §7 langkah 2 / §3 aturan 4 — cap turunan memori DIKIRIM ke vault.

    Dipanggil SESUDAH `record_outcome` supaya capnya lahir dari memori yang sudah memuat
    job ini (promosi job B mengangkat `risk` ke 2 di tulisan yang sama), dan SEBELUM
    `finalize` supaya urutan on-chain-nya bisa dibaca sebagai satu rangkaian.

    Tiga keadaan yang TIDAK mengirim apa pun, semuanya disengaja:
      - tidak ada profil (job belum `Submitted` → tidak ada outcome baru);
      - `cap_usdc is None` (risk 0 = TANPA cap). `cap_to_onchain` menerjemahkannya menjadi
        0, dan 0 di kontrak berarti TANPA BATAS (ADR-001) — mengirimnya justru akan
        MENIMPA cap yang sudah ada. `set_provider_cap` menolaknya lagi di batas kirim;
        di sini ia bahkan tidak dibangun;
      - nilai on-chain sudah sama dengan cap hari ini (rerun/idempotensi) — gas dan nonce
        tidak dibakar untuk menulis nilai yang sama.

    `providerCap()` on-chain DIPAKAI SEBAGAI LANTAI, bukan sekadar pembanding kesetaraan
    (temuan TINGGI-1). Cap yang lebih longgar dari yang sedang ditegakkan vault DIKLEM ke
    nilai on-chain: monoton-tidak-naik milik `derive_cap` berjangkar pada `previous` di
    `memory.db`, dan file itu bisa dimundurkan ke snapshot lama, sedangkan nilai on-chain
    tidak bisa. `set_provider_cap` menolaknya lagi di batas kirim (`allow_raise`).

    Cap yang benar-benar BERLAKU on-chain DISIMPAN ke profil (`store_provider_cap`) supaya
    `derive_cap` berikutnya punya `previous` untuk aturan monoton-tidak-naik, dan supaya
    body provider yang masuk preimage `memory_root` tidak mengaku "tanpa cap" sementara
    vault menegakkan angka. Untuk cap yang baru dikirim, penyimpanan dilakukan SESUDAH
    receipt berstatus 1: memori tidak boleh mengklaim cap yang tidak pernah ada di chain.
    """
    if profile is None:
        return None
    cap: CapPlan = derive_cap(profile, mode)
    if cap.cap_usdc is None:
        log.info(
            "cap provider=%s: TANPA CAP (risk=%d, basis=%s) — nol setProviderCap, karena "
            "nilai 0 di kontrak berarti TANPA BATAS (ADR-001)",
            profile.address,
            profile.risk_level,
            cap.basis,
        )
        return None
    # Nilai <= 0 ditolak SEBELUM apa pun dibandingkan. Kalau tidak, cap 0 yang lahir dari
    # perhitungan yang rusak akan "cocok" dengan `providerCap` yang masih 0 dan dilewati
    # DIAM-DIAM sebagai "sudah sinkron" — yaitu TANPA BATAS (ADR-001) yang tidak pernah
    # diucapkan. `set_provider_cap` menolaknya lagi di batas kirim; ini lapis pertamanya.
    if int(cap.cap_usdc) <= 0:
        raise UnlimitedCapRefused(
            UNLIMITED_CAP_TEMPLATE.format(
                provider=profile.address, cap=int(cap.cap_usdc), db=client.db_path
            )
        )
    # LANTAI MONOTON ON-CHAIN (temuan TINGGI-1). `derive_cap` hanya bisa menjanjikan
    # monoton-tidak-naik terhadap `previous` yang tersimpan di `memory.db`, dan file itu
    # bisa ditulis pihak lain (kunci `flock` KOOPERATIF) atau dikembalikan ke snapshot
    # lama. `providerCap()` adalah satu-satunya nilai yang tidak bisa dipalsukan dari sisi
    # file, jadi ia yang mengikat: cap yang lebih longgar DIKLEM ke nilai on-chain, bukan
    # dikirim. Nilai 0 on-chain bukan lantai — ia TANPA BATAS (ADR-001).
    onchain = client.provider_cap(profile.address)
    if onchain > 0 and int(cap.cap_usdc) > onchain:
        log.warning(
            "cap provider=%s DIKLEM ke lantai on-chain: memori menghitung %d (basis=%s) "
            "sementara vault menegakkan %d — nilai yang MELONGGARKAN tidak dikirim",
            profile.address,
            int(cap.cap_usdc),
            cap.basis,
            onchain,
        )
        cap = replace(cap, cap_usdc=onchain, basis=f"onchain-floor({cap.basis})")
    if onchain == int(cap.cap_usdc):
        log.info(
            "cap provider=%s sudah %d di vault — tidak dikirim ulang",
            profile.address,
            onchain,
        )
        # Tetap DITULIS ke memori (temuan RENDAH-1). Body provider ikut preimage
        # `memory_root`: tanpa tulisan ini auditor yang merekonstruksi memori pada root
        # yang diumumkan melihat "tanpa cap" sementara vault menegakkan nilai nyata, dan
        # `derive_cap` berikutnya kehilangan `previous`-nya.
        store_cap_in_memory(client, profile.address, cap)
        return None
    log.info(
        "cap provider=%s: %d → %d (risk=%d, basis=%s, milestone=%s, sampel=%d)",
        profile.address,
        onchain,
        int(cap.cap_usdc),
        profile.risk_level,
        cap.basis,
        cap.require_milestone,
        cap.sample_size,
    )
    tx_hash = client.set_provider_cap(profile.address, cap_to_onchain(cap))
    receipt = client.wait_receipt(tx_hash)
    log.info(
        "TX setProviderCap = 0x%s (status=%d, blok=%d)",
        tx_hash,
        receipt.status,
        receipt.blockNumber,
    )
    if receipt.status != 1:
        raise RuntimeError(f"setProviderCap gagal on-chain: 0x{tx_hash}")
    store_cap_in_memory(client, profile.address, cap)
    return tx_hash


def required_verdict_kind(plan: JobPlan) -> int | None:
    """Verdict yang DIPAKSA oleh bukti agen sendiri, atau `None` bila bukti tidak memaksa.

    DUA sumber, keduanya milik agen dan tidak satu pun berasal dari baris perintah:

      1. spec §5 langkah 2 — *"jika budget > cap → `postVerdict(REJECT)`"*. Syarat
         `plan.evaluation is None` dulu ada di sini dan ITULAH lubangnya (temuan TINGGI-A):
         provider yang `submit()` lebih dulu — di `sim/` itu urutan NORMAL — membuat
         `Evaluation` terisi, penjaganya dilewati, dan job over-cap diumumkan `complete`.
         Gating cap tidak pernah berhenti berlaku hanya karena deliverable sudah ada.
      2. spec §5 langkah 3-4 — skor lahir dari cek deterministik. `Evaluation.passed ==
         False` berarti cek AGEN SENDIRI gagal, dan bundel yang di-hash ke `reasonHash`
         menyatakan `passed=false`. Mengumumkan `complete` di atasnya berarti verdict
         publik yang MEMBANTAH buktinya sendiri, sekaligus membayar provider (temuan
         TINGGI-B). Tidak bisa ditawar `--kind`.

    Arahnya SATU: bukti hanya bisa MENGETATKAN verdict menjadi REJECT. Ia tidak pernah
    memaksa `complete` — memaksa pembayaran adalah kelas kesalahan yang justru ditutup di
    sini, dan operator yang meminta `reject` atas job yang lolos cek tidak membahayakan
    siapa pun kecuali dirinya di jendela challenge.
    """
    if not plan.gate.accept:
        return KIND_REJECT
    if plan.evaluation is not None and not plan.evaluation.passed:
        return KIND_REJECT
    return None


def verdict_kind(plan: JobPlan, requested: int) -> int:
    """Verdict yang benar-benar diumumkan: `required_verdict_kind` lebih dulu, lalu pilihan
    operator. Baris perintah tidak pernah bisa melonggarkan hasil cek."""
    required = required_verdict_kind(plan)
    if required is None or requested == required:
        return requested
    # Penanda dibedakan supaya log menyebut SEBAB yang memaksa, bukan sekadar hasilnya:
    # "GERBANG MENOLAK" untuk pelanggaran cap (spec §5 langkah 2) dan "CEK DETERMINISTIK
    # GAGAL" untuk hasil cek sendiri (langkah 3-4). Keduanya bisa berlaku bersamaan.
    log.info(
        "%s jobId=%d — gerbang=%s (%s), cek gagal=%s; verdict dipaksa REJECT, bukan %s yang diminta",
        "GERBANG MENOLAK" if not plan.gate.accept else "CEK DETERMINISTIK GAGAL",
        plan.job.job_id,
        "lolos" if plan.gate.accept else "DITOLAK",
        plan.gate.reason,
        list(plan.evaluation.failed_checks) if plan.evaluation is not None else [],
        "complete" if requested == KIND_COMPLETE else str(requested),
    )
    return required


def require_readable_client_address(client: VaultClient, job: JobView) -> None:
    """`getJob(jobId).client` WAJIB berbentuk alamat sebelum job ini boleh menghasilkan tx.

    Bentuknya divalidasi dengan `memory_policy.normalize_address` — definisi alamat yang
    SATU, bukan salinan regex kedua yang bisa menyimpang dari sisi memori.

    Ini penjaga LAPIS PERTAMA; lapis keduanya `record_job_outcome` sendiri, yang menolak
    `client_address` rusak dengan `MemoryIntegrityError`. Dua lapis karena keduanya
    menjawab pertanyaan berbeda: yang di sini menahan TRANSAKSI (nol tx, job tidak
    menggantung separuh jalan), yang di memori menahan TULISAN (nol angka yang direkam
    dengan filter ADR-021 yang mati) — dan pemanggil memori tidak selalu lewat `run_job`.

    DUA HAL sekaligus, dan keduanya perlu:
      - `client.refuse()` memasang KUNCI sekali-jalan, sama seperti dua jalur berhenti
        lain di `run_job` (evaluator asing, deliverable tak terverifikasi). Sejak itu
        `_send()` menolak SETIAP transaksi, jadi jalur baru yang memanggil penjaga ini dan
        lupa memeriksa nilai baliknya tetap berhenti. Tanpa kunci itu, sabuk keduanya
        hilang: melepasnya membuat `finalize` bisa TERKIRIM.
      - `SafeModeStop` yang dilempar sesudahnya membedakan keadaan ini dari "job ini bukan
        milik kita": yang terakhir hasil normal yang berakhir exit 0, sedangkan pembacaan
        chain yang GAGAL harus terlihat operator (`EXIT_REFUSED`).
    Akibatnya barisnya muncul dua kali di log (sekali dari `refuse`, sekali dari handler
    `main()`); itu harga yang jauh lebih murah daripada satu jalur tanpa kunci.
    """
    try:
        normalize_address(job.client_address)
    except ValueError as exc:
        pesan = BROKEN_CLIENT_TEMPLATE.format(job_id=job.job_id, client=job.client_address)
        client.refuse(pesan)
        raise SafeModeStop(pesan) from exc


def run_job(
    client: VaultClient,
    job_id: int,
    kind: int,
    *,
    deliverable_dir: str | os.PathLike[str] | None = None,
    lookback_blocks: int = LOG_LOOKBACK_BLOCKS,
) -> int:
    """Jalur `--job-id`: `getJob` → saring evaluator → keputusan memori → pipa verdict.

    TIGA jalur berhenti dengan NOL transaksi, dan ketiganya memasang kunci
    `client.refuse()` supaya tidak ada jalur lain yang bisa mengirim tx sesudahnya:
      - `evaluator != VAULT` (ADR-022 keputusan 2) — berhenti bersih, exit 0;
      - `DeliverableUnverifiedError` (ADR-019 keputusan 2, utang task 2.3-min) — exit 0;
      - `getJob(jobId).client` yang tidak terbaca (task 2.4a AC (j)) — ini BUKAN hasil
        normal melainkan pembacaan chain yang gagal, jadi ia melempar `SafeModeStop` dan
        run-nya berakhir `EXIT_REFUSED`, bukan 0.
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
    require_readable_client_address(client, job)
    try:
        plan = plan_job(
            client, job, deliverable_dir=deliverable_dir, lookback_blocks=lookback_blocks
        )
    except DeliverableUnverifiedError as exc:
        client.refuse(str(exc) if str(exc).startswith(REFUSAL_LINE) else f"{REFUSAL_LINE}: {exc}")
        return 0
    log.info("%s", plan.line)
    return run_live(client, job_id, verdict_kind(plan, kind), plan=plan)


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


def require_onchain_verdict_agrees(
    client: VaultClient,
    job_id: int,
    existing: VerdictState,
    kind: int,
    reason_hash: bytes,
    memory_root: bytes,
) -> None:
    """Verdict yang SUDAH diumumkan WAJIB sama dengan yang dihitung run ini (SEDANG-2).

    Cabang "verdict sudah ada" dulu memfinalisasi apa pun yang ditemukannya, dan dua
    serangan menembusnya: (i) verdict `complete` yang terlanjur diumumkan tetap dieksekusi
    walau gerbang SEKARANG menolak — run bahkan melaporkan exit 0 `PIPA HIDUP SELESAI`;
    (ii) `reasonHash`/`memoryRoot` asing diterima tanpa protes sementara log mencetak
    versi baru hasil hitung sendiri, sehingga jejak audit menunjuk bundel yang BUKAN yang
    terikat on-chain.

    `kind` dibandingkan KERAS: ia yang menentukan siapa dibayar, dan tidak ada keadaan sah
    di mana verdict on-chain berbeda arah dari bukti hari ini.

    `reasonHash`/`memoryRoot` punya SATU perbedaan yang sah, dan ia bukan kelonggaran
    melainkan urutan spec §5: memori ditulis SESUDAH `postVerdict` (langkah 5), jadi run
    berikutnya atas job yang sama menghitung root yang lebih baru. Perbedaan itu hanya
    diterima bila bundel yang diumumkan MASIH BISA DITUNJUKKAN, dan "ditunjukkan" berarti
    keempat syarat `bundle_reproduces_onchain`: keccak teks tersimpan == `reasonHash`
    on-chain, `memory_root` di dalamnya == `memoryRoot` on-chain, `job` di dalamnya ==
    jobId INI, dan `verdict` di dalamnya == `kind` on-chain.

    Yang ditegakkan karena itu: bundel milik job/verdict LAIN tidak bisa menyelamatkan job
    ini walaupun seseorang berhasil menaruhnya di toko bukti (temuan SEDANG-A9 — dulu
    hanya dua syarat pertama yang diperiksa dan bundel SAH milik job 42 memfinalisasi job
    43). Yang TIDAK ditegakkan, dan sengaja: bundelnya tidak wajib sama dengan hitungan
    run hari ini — persamaan mutlak akan menggantung setiap retry `finalize` sampai
    `expiredAt` justru karena langkah 5 memang sudah memajukan memori.
    """
    if int(existing.kind) != int(kind):
        raise VerdictMismatch(
            ONCHAIN_KIND_DRIFT_TEMPLATE.format(
                job_id=job_id,
                onchain=int(existing.kind),
                onchain_name=verdict_kind_name(int(existing.kind)),
                fresh=int(kind),
                fresh_name=verdict_kind_name(int(kind)),
            )
        )
    if bytes(existing.reason_hash) == bytes(reason_hash) and bytes(existing.memory_root) == bytes(
        memory_root
    ):
        return
    # Dicari LANGSUNG lewat `reasonHash` on-chain: nama file bundel memuat hash itu, jadi
    # pembacaan ini tidak menebak dan tidak memindai (temuan TINGGI-A7).
    path, text = stored_verdict_bundle(
        verdict_bundle_dir(client), job_id, bytes(existing.reason_hash)
    )
    if text is not None and bundle_reproduces_onchain(text, job_id, existing):
        log.warning(
            "%s",
            ONCHAIN_BUNDLE_REPRODUCED_TEMPLATE.format(
                job_id=job_id,
                path=path,
                hash="0x" + bytes(existing.reason_hash).hex(),
                root="0x" + bytes(existing.memory_root).hex(),
                fresh_root="0x" + bytes(memory_root).hex(),
            ),
        )
        return
    raise VerdictMismatch(
        ONCHAIN_EVIDENCE_DRIFT_TEMPLATE.format(
            job_id=job_id,
            onchain_hash="0x" + bytes(existing.reason_hash).hex(),
            onchain_root="0x" + bytes(existing.memory_root).hex(),
            fresh_hash="0x" + bytes(reason_hash).hex(),
            fresh_root="0x" + bytes(memory_root).hex(),
            store=path.parent,
        )
    )


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

    `plan` WAJIB ada, dan buktinya boleh datang dari DUA sumber (`verdict_evidence`):
    hasil cek deterministik bila job sudah `Submitted`, atau `GateDecision` bila job masih
    `Funded` dan capnya dilanggar. Yang tetap dilarang adalah verdict TANPA bukti apa pun
    — itu yang dicabut 2.4b.

    `record_outcome` dipanggil di KEDUA cabang (verdict baru maupun verdict yang sudah ada
    di vault). Ia idempoten per `job_id`; melewatinya di cabang "sudah ada" berarti hasil
    job hilang dari memori SELAMANYA setiap kali run diulang.
    """
    kind_name = verdict_kind_name(kind)
    log.info("LIVE jobId ACP NYATA=%d kind=%d (%s)", job_id, kind, kind_name)
    if plan is None:
        raise MemoryRootMismatch(
            f"run_live jobId={job_id} tanpa rencana job — tidak ada bukti dan tidak ada "
            "keadaan memori yang bisa diumumkan; nol postVerdict/finalize/setProviderCap"
        )
    # Rencana WAJIB milik job INI. Tanpa penjaga satu baris ini `postVerdict(777, …)`
    # terkirim membawa bundel job 43 (temuan RENDAH review putaran-2).
    if int(plan.job.job_id) != int(job_id):
        raise VerdictMismatch(
            PLAN_JOB_MISMATCH_TEMPLATE.format(job_id=job_id, planned=plan.job.job_id)
        )
    # Gerbang dibaca ULANG lebih dulu supaya root yang dicetak/diumumkan adalah root yang
    # SAMA yang akan diperiksa `_send()`. `_send()` tetap membacanya lagi — itu yang mengikat.
    gate = client.refresh_memory_gate()
    # Mode saat RENCANA disusun WAJIB masih berlaku saat verdict diumumkan (temuan SEDANG-1).
    # `plan.mode` ikut ter-hash ke `reasonHash`; bila gerbang sudah berubah, bundel dan root
    # menggambarkan dua keadaan memori yang berbeda dan verdict itu tidak bisa diaudit.
    if gate.decision.mode != plan.mode.mode:
        raise MemoryRootMismatch(
            MODE_DRIFT_TEMPLATE.format(
                job_id=job_id,
                planned=plan.mode.mode,
                current=gate.decision.mode,
                db=client.db_path,
            )
        )
    memory_root = client.derived_memory_root()
    # Rencana terikat pada ROOT yang dibacanya, bukan hanya pada NAMA modenya (SEDANG-1).
    # Penulis `memory.db` yang mendarat sesudah `plan_job` membiarkan mode tetap `normal`
    # sementara root sudah berpindah; tanpa perbandingan ini root DB BARU diumumkan
    # menempel pada `gate`/`cap`/`incident_jobs` dari DB LAMA, dan jangkar bukti 2.4b
    # tidak berlaku bagi auditor yang merekonstruksi memori pada root itu.
    if plan.memory_root is None:
        raise VerdictMismatch(PLAN_WITHOUT_ROOT_TEMPLATE.format(job_id=job_id))
    if bytes(plan.memory_root) != bytes(memory_root):
        raise VerdictMismatch(
            ROOT_DRIFT_TEMPLATE.format(
                job_id=job_id,
                planned="0x" + bytes(plan.memory_root).hex(),
                current="0x" + bytes(memory_root).hex(),
                db=client.db_path,
            )
        )
    # `kind` ikut ke dalam bundel (v3): `reasonHash` mengikat ARAH verdict, bukan hanya
    # keadaan yang melahirkannya. Penjaga di bawah tetap yang memutuskan arah mana yang sah.
    bundle = verdict_evidence(plan, memory_root, kind)
    if evidence_kind(bundle) in EVIDENCE_KINDS_REQUIRING_REJECT and kind != KIND_REJECT:
        raise MemoryRootMismatch(
            GATE_REJECTION_KIND_TEMPLATE.format(job_id=job_id, kind=kind, kind_name=kind_name)
        )
    # Bukti cek deterministik yang GAGAL tidak boleh menemani verdict `complete` (TINGGI-B).
    # Lapis kedua di samping `verdict_kind()`: jalur yang memanggil `run_live` langsung —
    # termasuk otomasi 2.5 — tetap berhenti, alasan yang sama seperti mode aman ditegakkan
    # di `_send()` dan bukan di pemanggil.
    if kind != KIND_REJECT and plan.evaluation is not None and not plan.evaluation.passed:
        raise VerdictMismatch(
            FAILED_CHECKS_KIND_TEMPLATE.format(
                job_id=job_id,
                kind=kind,
                kind_name=kind_name,
                failed=list(plan.evaluation.failed_checks),
            )
        )
    reason_hash = verdict_reason_hash(bundle)
    log.info("memory_root TURUNAN memory.db di %s = 0x%s", client.db_path, memory_root.hex())
    log.info(
        "reason_hash (TURUNAN bukti job, kind bukti=%s)=0x%s",
        evidence_kind(bundle),
        reason_hash.hex(),
    )

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
        # Verdict on-chain WAJIB sama dengan yang dihitung run ini (SEDANG-2). Tanpa ini
        # cabang ini memfinalisasi apa pun yang kebetulan sudah ada — termasuk `complete`
        # atas job yang gerbangnya SEKARANG menolak.
        require_onchain_verdict_agrees(client, job_id, existing, kind, reason_hash, memory_root)
        # VerdictAlreadyPosted: lanjut ke finalize, jangan gagal total (jalur diminta 1.3d).
        # Nilai ON-CHAIN dicetak apa adanya: merekalah yang mengikat verdict ini. Tanpa baris
        # ini log hanya memuat `reasonHash`/`memoryRoot` hasil hitung run SEKARANG, dan jejak
        # audit menunjuk bundel yang BUKAN yang terikat on-chain (temuan SEDANG-2).
        log.info(
            "verdict jobId=%d SUDAH ADA (kind=%d (%s), readyAt=%d, reasonHash=0x%s, "
            "memoryRoot=0x%s — nilai ON-CHAIN inilah yang mengikat) — melewati postVerdict, "
            "lanjut finalize",
            job_id,
            existing.kind,
            verdict_kind_name(int(existing.kind)),
            existing.ready_at,
            bytes(existing.reason_hash).hex(),
            bytes(existing.memory_root).hex(),
        )
        ready_at = existing.ready_at
        post_hash = "(sudah ada sebelumnya)"
        # spec §5 langkah 5 TETAP berlaku di cabang ini (temuan TINGGI-2). Rerun sesudah
        # `postVerdict` mendarat — `EXIT_STOPPED_MIDWAY`, timeout receipt, atau `--job-id`
        # yang dijalankan ulang tangan — dulu melewati `record_outcome` SELAMANYA, sehingga
        # insiden job A tidak pernah lahir, `promote_suspicions` tidak pernah mencapai
        # count >= 2, `risk` tetap 0, `derive_cap` mengembalikan NO_CAP, dan
        # `cap_to_onchain` = 0 = TANPA BATAS (ADR-001): job C tidak pernah ditolak.
        # `record_job_outcome` idempoten per `job_id` (dedup di sisi memori), jadi memanggil
        # di KEDUA cabang aman dan tidak pernah menghitung satu job dua kali.
        sync_provider_cap(client, plan.mode, record_outcome(client, plan))
    else:
        # Bundel disimpan SEBELUM transaksinya dikirim (TASKS 2.5 AC (c)): begitu
        # `postVerdict` mendarat, `reasonHash` on-chain harus selalu punya preimage yang
        # bisa ditunjukkan — termasuk kepada run berikutnya, yang memorinya sudah maju.
        # Cabang ini juga dimasuki run yang node RPC-nya masih TERTINGGAL (`verdicts(jobId)`
        # mengembalikan 0 walau verdict sudah ada), jadi ia MENAMBAH bundel, tidak pernah
        # mengganti: nama file ber-alamat-isi yang membuatnya begitu (temuan TINGGI-A7).
        simpanan = store_verdict_bundle(verdict_bundle_dir(client), job_id, bundle)
        log.info("bundel bukti (preimage reasonHash) disimpan: %s", simpanan)
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
        # `setProviderCap` menyusul di transaksi yang sama-sama berada di antara
        # `postVerdict` dan `finalize` (spec §7 langkah 2): capnya lahir dari memori yang
        # BARU SAJA memuat job ini, jadi ia tidak bisa dihitung lebih awal.
        sync_provider_cap(client, plan.mode, record_outcome(client, plan))
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


def report_stopped_midway(sent: list[str], cause: str) -> int:
    """BERHENTI DI TENGAH PIPA: sebagian tx sudah mendarat, sisanya tidak akan pernah.

    Dipakai oleh SEMUA jalur galat `main()`, bukan hanya `SafeModeStop` (temuan SEDANG-2).
    Jendela antara `postVerdict` dan `finalize` kini memuat TIGA tx (`setProviderCap` di
    tengahnya), dan kegagalan di sana — receipt berstatus 0, galat/timeout RPC, penulisan
    memori yang kalah CAS — dulu jatuh ke `except Exception` generik: exit 1 TANPA satu
    baris pun yang mengatakan job menggantung sampai `expiredAt`, dan tanpa daftar tx yang
    sudah mendarat. Dampaknya terbatas (`finalize` permissionless, rerun pulih bersih);
    yang hilang adalah SINYAL untuk operator, dan justru itu gunanya kode keluar ini.
    """
    log.error(
        "%s: %d transaksi sudah mendarat sebelum %s (%s) — job MENGGANTUNG sampai "
        "expiredAt, dan run ini TIDAK selesai",
        EXIT_STOPPED_MIDWAY_MESSAGE,
        len(sent),
        cause,
        ", ".join("0x" + h for h in sent),
    )
    return EXIT_STOPPED_MIDWAY


def landed_transactions(dibangun: Mapping[str, VaultClient]) -> list[str]:
    client = dibangun.get("client")
    return list(client.sent_transactions) if client is not None else []


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
        default=None,
        help="verdict untuk --job-id — WAJIB, tidak ada default (cek deterministik dan "
        "gerbang cap tetap bisa MEMAKSA reject di atasnya)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    if args.guard is None and args.job_id is None:
        parser.print_usage(sys.stdout)
        return 2
    # Tidak ada verdict default (temuan TINGGI-B). Baris perintah terpendek dulu berarti
    # `complete` — yaitu MEMBAYAR provider — dan itu keputusan yang harus diketik, bukan
    # diwarisi dari default. Pilihan operator tetap tunduk pada `required_verdict_kind`.
    if args.job_id is not None and args.kind is None:
        log.error("%s", KIND_REQUIRED_MESSAGE)
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
                terkirim = landed_transactions(dibangun)
                if terkirim:
                    return report_stopped_midway(terkirim, "job dianulir pihak ketiga")
                return 1
        parser.print_usage(sys.stdout)
        return 2
    except (SafeModeStop, DeliverableUnverifiedError, MemoryIntegrityError) as exc:
        # Jaring kedua: gerbang di atas sudah menahan, jadi ini hanya terjadi bila sebuah
        # jalur baru mencoba mengirim tx tanpa lewat sana. `DeliverableUnverifiedError`
        # ikut di sini karena ADR-019 keputusan 2 menuntut perlakuan SEKELAS mode aman —
        # termasuk pembedaan "berhenti bersih" dari "berhenti di tengah pipa" di bawah.
        # `MemoryIntegrityError` ikut karena alasan yang sama dan karena ia TIDAK bisa
        # menjadi turunan `SafeModeStop`: ia hidup di `memory_policy`, yang tidak boleh
        # mengimpor modul ini. Jadi ia didaftarkan di sini, satu-satunya tempat yang
        # membuat kalimat "ia sekelas mode aman" benar. Isinya memang kelas yang sama:
        # memori yang tidak bisa dijadikan preimage jujur, dan bukti `getJob` yang tidak
        # bisa dipercaya — dua-duanya "kita tidak boleh menulis/mengirim apa pun", bukan
        # "ada bug Python".
        # `log.error`, bukan `log.info`: yang sampai ke sini adalah penolakan SESUDAH
        # gerbang start lolos — mode aman yang muncul di tengah jalan, root asing, bukti
        # yang tidak cocok. Semuanya keadaan yang harus terlihat di log, bukan catatan.
        # Disensor seperti handler generik: nol pesan hari ini membawa kunci, dan penjaga
        # yang hanya berlaku di sebagian jalur bukan penjaga.
        log.error("%s", redact(str(exc), private_key))
        terkirim = landed_transactions(dibangun)
        if terkirim:
            # BERHENTI DI TENGAH PIPA. Ini BUKAN "berhenti bersih": sebagian tx sudah
            # mendarat (mis. postVerdict) sementara sisanya (finalize) tidak akan pernah,
            # jadi job menggantung sampai `expiredAt`. Exit 0 di sini membuat otomasi 2.5
            # melaporkan sukses palsu — karena itu kode keluarnya BERBEDA.
            return report_stopped_midway(terkirim, "gerbang menahan sisanya")
        # Nol tx, tetapi tetap BUKAN sukses: gerbang start sudah lolos, jadi sesuatu
        # menolak di tengah jalan. Exit 0 di sini adalah laporan sukses palsu.
        log.error(
            "%s: nol transaksi terkirim, dan run ini TIDAK menghasilkan verdict",
            EXIT_REFUSED_MESSAGE,
        )
        return EXIT_REFUSED
    except JobVoidedError as exc:
        # Penjaga: tidak ada tx yang dikirim, keluar 0 (bukan kegagalan).
        log.info("%s", voided_message(exc.job_id, exc.status))
        return 0
    except Exception as exc:  # noqa: BLE001 — pesan disensor sebelum dicetak
        log.error("GAGAL: %s: %s", type(exc).__name__, redact(str(exc), private_key))
        terkirim = landed_transactions(dibangun)
        if terkirim:
            # Galat teknis SESUDAH sebuah tx mendarat adalah kelas keadaan yang sama
            # dengan penolakan di tengah pipa: sisanya tidak akan pernah dikirim run ini.
            return report_stopped_midway(terkirim, f"{type(exc).__name__} menghentikan pipa")
        return 1


if __name__ == "__main__":
    # sys.tracebacklimit tidak diubah: main() menangkap semua exception dan menyensor pesannya,
    # jadi tidak ada traceback yang bisa membawa kunci privat ke stdout/stderr.
    raise SystemExit(main())
