"""Kunci single-instance atas `memory.db` — task 2.4a butir (1).

MENGAPA MODUL INI ADA, dengan kalimat yang tidak diperhalus:
KOREKSI 2026-09-06 (docs/api-facts.md §C.2): alasan yang tertulis di sini sebelumnya —
"`sibyl-memory-client` 0.7.0 TIDAK punya transaksi (§C)" — SALAH DUA KALI. §C tidak pernah
menulis itu, dan `Storage.transaction()` MEMANG ADA, atomik (`BEGIN IMMEDIATE` / ROLLBACK
saat melempar / COMMIT saat bersih), dan terjangkau lewat properti `MemoryClient.storage`.
Modul ini tetap berdiri, tetapi karena TIGA celah yang transaksi itu TIDAK bisa tutup:

  1. BACA-UBAH-TULIS lewat API publik tidak bisa dijadikan satu transaksi. Setiap metode
     TULIS SDK (`set_entity`, `set_reference`, `delete_entity`, ...) membuka transaksinya
     SENDIRI di sambungan per-thread yang sama, jadi bersarang di dalam
     `storage.transaction()` melempar `cannot start a transaction within a transaction` DAN
     tulisannya hilang. `_save_provider_cas` — baca versi lalu tulis — karena itu tetap
     punya jendela cek-lalu-tulis yang hanya bisa ditutup DARI LUAR.
  2. RANGKAIANNYA MELEWATI BATAS SQLite. Kunci ini membentang dari `load_snapshot` sampai
     perhitungan `memory_root`, penulisan file ekspor, dan pengiriman tx. Transaksi SQLite
     tidak bisa membentang panggilan RPC; ditahan selama itu ia justru MEMBUNUH proses agen
     lain (`busy_timeout` 5 detik lalu `database is locked`, tulisan proses itu hilang).
  3. MODE GAGALNYA BEDA. Kunci menolak instans kedua SEBELUM ia bekerja (`MemoryLockError`,
     fail-closed). Transaksi menjatuhkannya DI TENGAH JALAN, sesudah ia mungkin sudah
     melakukan kerja di luar DB.

Untuk rangkaian BACA MURNI — `load_snapshot()` = 1x `list_entities` + 2x `search` +
N x `get_reference` — transaksi sebenarnya SUDAH cukup: pembacaan SDK boleh bersarang di
dalamnya dan menghasilkan satu titik waktu, dibuktikan lintas proses di §C.2. Kunci ini
menutup kelas itu JUGA, dengan mekanisme yang sama yang menutup dua kelas di atas. Yang
tetap benar tanpa penutup apa pun: tulisan yang mendarat di tengah rangkaian menghasilkan
snapshot yang memuat provider versi lama, kehilangan provider yang ditulis belakangan,
tetapi ikut menjangkar reference barunya — root untuk keadaan yang TIDAK PERNAH ADA. Dan itu
TIDAK terlihat dari file ekspor, karena file dan root lahir dari snapshot yang sama:
keduanya cocok, keduanya salah.

Penutup yang dipilih adalah SATU INSTANS pada satu `memory.db`, dan itulah yang ditegakkan
di sini — bukan diimbau di docstring.

BENTUKNYA (dan alasan tiap pilihan):
  - `flock(LOCK_EX|LOCK_NB)` atas lockfile `<db>.lock` di samping DB. `fcntl` ada di
    pustaka standar → tanpa dependensi baru.
  - TIDAK PERNAH menunggu selamanya: percobaan diulang sampai `timeout_seconds`, lalu
    MELEMPAR `MemoryLockError`. Gagal mendapat kunci = FAIL-CLOSED; pemanggil di jalur
    chain memperlakukannya sebagai mode aman (tidak ada tx), bukan sebagai antrean.
  - TIDAK MENINGGALKAN KUNCI HANTU: `flock` melekat pada open file description, jadi kernel
    melepasnya saat proses mati — termasuk `SIGKILL`. Berkasnya sendiri boleh tertinggal;
    isinya hanya PID untuk diagnosis dan TIDAK PERNAH dipakai sebagai keputusan penguncian.
  - REENTRAN di dalam satu proses: `record_job_outcome` -> `_save_provider_cas` ->
    `save_provider` semuanya meminta kunci yang sama. `flock` atas dua open file description
    di proses yang sama akan saling BLOKIR, jadi reentransi dihitung sendiri di sini, dan
    mutual-exclusion antar-thread dijaga `threading.RLock` (satu per path).

YANG TIDAK DIKLAIM: ini kunci KOOPERATIF. Ia menahan proses agen lain yang memakai modul
ini; ia tidak menahan `sqlite3` mentah, editor, atau `rm`. Penulis `memory.db` yang jahat
tetap menjadi ancaman yang sudah diakui di docstring `memory_policy` — penawarnya jangkar
root + mode aman, bukan kunci ini.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

try:  # pragma: no cover - Linux/macOS; cabang lain hanya ada untuk fail-closed
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

LOCK_SUFFIX: Final = ".lock"

# Batas tunggu default. Cukup panjang untuk melewati satu operasi memori normal (semuanya
# lokal dan berorde milidetik), cukup pendek untuk BERHENTI alih-alih menggantung: agen yang
# menunggu selamanya pada job berjendela waktu adalah kegagalan yang tidak terlihat.
DEFAULT_TIMEOUT_SECONDS: Final = 10.0
POLL_INTERVAL_SECONDS: Final = 0.02


class MemoryLockError(RuntimeError):
    """Kunci `memory.db` tidak bisa didapat/ditentukan. SELALU fail-closed."""


@dataclass
class _Holder:
    """Keadaan kunci untuk SATU path di dalam proses ini."""

    rlock: threading.RLock = field(default_factory=threading.RLock)
    fd: int | None = None
    depth: int = 0


_registry_lock = threading.Lock()
_holders: dict[str, _Holder] = {}


def lock_path_for(db_path: str | os.PathLike[str]) -> Path:
    """Lockfile untuk sebuah DB: `<db>.lock`, di direktori yang sama."""
    db = Path(db_path).expanduser()
    return db.with_name(db.name + LOCK_SUFFIX)


def _key(db_path: str | os.PathLike[str]) -> str:
    """Kunci registri = path lockfile yang sudah dinormalkan (symlink ikut diselesaikan).

    Normalisasi ini penting: `./data/memory.db` dan `/abs/data/memory.db` adalah DB yang
    SAMA, dan dua proses yang menyebutnya berbeda tetap harus saling mengunci. `flock`
    sendiri sudah bekerja per-inode, jadi normalisasi ini hanya menyamakan penghitung
    reentransi DI DALAM proses ini dengan kenyataan kernel.
    """
    return os.path.realpath(lock_path_for(db_path))


def _holder_for(key: str) -> _Holder:
    with _registry_lock:
        holder = _holders.get(key)
        if holder is None:
            holder = _Holder()
            _holders[key] = holder
        return holder


def is_locked_here(db_path: str | os.PathLike[str]) -> bool:
    """True bila PROSES INI sedang memegang kunci DB tersebut (untuk tes/diagnostik)."""
    with _registry_lock:
        holder = _holders.get(_key(db_path))
    return holder is not None and holder.depth > 0


def _describe_other_holder(path: Path) -> str:
    """PID pemegang kunci, apa adanya beserta peringatan bahwa isinya bisa basi."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    return f" (isi lockfile: {text!r}, bisa basi)" if text else ""


@contextmanager
def memory_lock(
    db_path: str | os.PathLike[str], *, timeout_seconds: float | None = None
) -> Iterator[Path]:
    """Memegang kunci eksklusif atas `db_path` selama blok `with`.

    Dipakai membungkus SELURUH operasi baca-hitung (`load_snapshot` -> root) dan SELURUH
    operasi tulis, bukan sepotong-sepotong: yang dilindungi adalah rangkaiannya, bukan tiap
    panggilan SDK-nya.

    `timeout_seconds=None` membaca `DEFAULT_TIMEOUT_SECONDS` SAAT DIPANGGIL (bukan saat
    modul diimpor), supaya batas tunggu bisa dikecilkan di tes tanpa menyalin nilai default
    ke setiap pemanggil.
    """
    timeout_seconds = DEFAULT_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    if fcntl is None:  # pragma: no cover - hanya di platform tanpa fcntl
        raise MemoryLockError(
            "fcntl tidak tersedia di platform ini — kunci single-instance memory.db tidak bisa "
            "ditegakkan, dan berjalan tanpa kunci DILARANG (task 2.4a)"
        )

    key = _key(db_path)
    holder = _holder_for(key)
    lock_file = Path(key)
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))

    # Lapisan 1 — antar-THREAD di proses ini. `flock` tidak memisahkan thread (satu proses),
    # jadi tanpa ini dua thread bisa masuk bersamaan meski `flock` "terpegang".
    if not holder.rlock.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise MemoryLockError(
            f"kunci memory.db {lock_file} dipegang thread lain di proses ini lebih dari "
            f"{timeout_seconds:g} detik — berhenti (fail-closed), tidak menunggu selamanya"
        )

    opened_here = False
    try:
        # Lapisan 2 — antar-PROSES. Hanya pemegang terluar yang membuka fd + flock.
        if holder.depth == 0:
            try:
                fd = os.open(key, os.O_CREAT | os.O_RDWR, 0o600)
            except OSError as exc:
                raise MemoryLockError(f"tidak bisa membuka lockfile {lock_file}: {exc}") from exc
            try:
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise MemoryLockError(
                                f"memory.db {Path(db_path)} sedang dipakai proses lain: kunci "
                                f"{lock_file} tidak didapat dalam {timeout_seconds:g} detik"
                                f"{_describe_other_holder(lock_file)} — BERHENTI (fail-closed). "
                                "Hanya SATU instans agen yang boleh memegang satu memory.db "
                                "(alasan mekanisnya di api-facts §C.2 — BUKAN ketiadaan "
                                "transaksi di SDK)"
                            ) from None
                        time.sleep(POLL_INTERVAL_SECONDS)
                os.ftruncate(fd, 0)
                os.write(fd, f"{os.getpid()}\n".encode())
            except BaseException:
                os.close(fd)
                raise
            holder.fd = fd
            opened_here = True
        holder.depth += 1
    except BaseException:
        holder.rlock.release()
        raise

    try:
        yield lock_file
    finally:
        holder.depth -= 1
        if opened_here:
            fd = holder.fd
            holder.fd = None
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
        holder.rlock.release()


def db_path_of(client: Any) -> Path:
    """Path `memory.db` di balik sebuah `MemoryClient`.

    Diverifikasi 2026-09-05 pada `sibyl-memory-client==0.7.0` (`inspect`):
    `MemoryClient.storage` adalah `property` -> `sibyl_memory_client.storage.Storage`, dan
    `Storage.db_path` bertipe `pathlib.Path`. `storage` ada di daftar metode publik §C.

    Bila path TIDAK bisa ditentukan, fungsi ini MELEMPAR. Itu disengaja: "tidak tahu file
    mana yang harus dikunci" tidak boleh berarti "jalan tanpa kunci".
    """
    storage = getattr(client, "storage", None)
    if storage is None:
        raise MemoryLockError(
            f"klien memori {type(client).__name__} tidak mengekspos `.storage` — path memory.db "
            "tidak bisa ditentukan, jadi kunci single-instance tidak bisa dipegang (fail-closed)"
        )
    path = getattr(storage, "db_path", None)
    if path is None:
        raise MemoryLockError(
            f"storage {type(storage).__name__} tidak punya `.db_path` — path memory.db tidak "
            "bisa ditentukan, jadi kunci single-instance tidak bisa dipegang (fail-closed)"
        )
    return Path(path)


@contextmanager
def locked_client(client: Any, *, timeout_seconds: float | None = None) -> Iterator[Path]:
    """`memory_lock` atas DB milik sebuah `MemoryClient`."""
    with memory_lock(db_path_of(client), timeout_seconds=timeout_seconds) as path:
        yield path
