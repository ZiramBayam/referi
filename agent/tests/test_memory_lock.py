"""Tes kunci single-instance atas `memory.db` — task 2.4a butir (1), AC (i).

Yang dibuktikan di sini, dan tidak lebih dari itu:
  1. kunci benar-benar DIPEGANG selama SELURUH baca-hitung (`load_snapshot` -> root) dan
     SELURUH tulis (`record_job_outcome`) — dibuktikan dari PROSES LAIN yang mencoba
     mengunci TEPAT di tengah operasi, bukan dengan membaca kode;
  2. gagal mendapat kunci = FAIL-CLOSED dan BERBATAS WAKTU (melempar, bukan menggantung);
  3. proses yang MATI (SIGKILL) tidak meninggalkan kunci hantu;
  4. lost update dua-proses yang dulu "tanpa satu pun error" kini BERHENTI dengan error,
     dan memori tidak berubah;
  5. klien yang path DB-nya tidak bisa ditentukan DITOLAK, bukan dijalankan tanpa kunci.

Semua skenario dua-proses memakai `subprocess` SUNGGUHAN: `flock` adalah properti kernel
per open file description, jadi thread di proses yang sama tidak akan pernah membuktikannya.
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys
import time

import pytest
from sibyl_memory_client import MemoryClient

from agent import memory_lock as ml
from agent import memory_policy as mp

PKG_ROOT = str(pathlib.Path(mp.__file__).resolve().parent.parent)

# Anak proses: ambil kunci, tulis penanda "sudah dipegang", lalu tidur sampai dibunuh.
HOLD_SRC = """
import pathlib, sys, time
from agent.memory_lock import memory_lock
db, ready = sys.argv[1], sys.argv[2]
with memory_lock(db, timeout_seconds=10):
    pathlib.Path(ready).write_text("ready", encoding="utf-8")
    time.sleep(120)
"""

# Anak proses: coba ambil kunci sebentar, cetak hasilnya apa adanya.
TRY_SRC = """
import sys
from agent.memory_lock import MemoryLockError, memory_lock
try:
    with memory_lock(sys.argv[1], timeout_seconds=float(sys.argv[2])):
        print("ACQUIRED")
except MemoryLockError as exc:
    print("LOCKED")
"""

# Anak proses: jalankan `record_job_outcome` PENUH (dengan kunci) di DB yang sama.
WRITE_SRC = """
import sys
from sibyl_memory_client import MemoryClient
from agent import memory_lock as ml
from agent import memory_policy as mp
ml.DEFAULT_TIMEOUT_SECONDS = float(sys.argv[3])
client = MemoryClient.local(sys.argv[1])
try:
    p = mp.record_job_outcome(
        client, sys.argv[2], job_id=int(sys.argv[4]), budget=1, passed=True,
        client_address="0x" + "cc" * 20,
    )
    print("WROTE", p.stats_jobs)
except ml.MemoryLockError:
    print("LOCKED")
"""


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = PKG_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run(src: str, *args: str, timeout: float = 60.0) -> str:
    done = subprocess.run(
        [sys.executable, "-c", src, *args],
        capture_output=True,
        text=True,
        env=_env(),
        timeout=timeout,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _try_lock_elsewhere(db: pathlib.Path, timeout: float = 0.2) -> str:
    """Hasil percobaan mengunci dari PROSES LAIN: 'ACQUIRED' atau 'LOCKED'."""
    return _run(TRY_SRC, str(db), str(timeout))


def _hold_lock(db: pathlib.Path, tmp_path: pathlib.Path) -> subprocess.Popen:
    ready = tmp_path / "ready.flag"
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLD_SRC, str(db), str(ready)],
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 30
    while not ready.exists():
        assert proc.poll() is None, proc.communicate()[1]
        assert time.monotonic() < deadline, "anak proses tidak pernah mendapat kunci"
        time.sleep(0.02)
    return proc


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "memory.db"
    MemoryClient.local(str(path))
    return path


@pytest.fixture
def client(db):
    return MemoryClient.local(str(db))


def addr(n: int) -> str:
    return f"0x{n:040x}"


# ----------------------------------------------------------------------
# Bentuk kunci
# ----------------------------------------------------------------------


def test_lockfile_sits_next_to_the_database(tmp_path):
    assert ml.lock_path_for(tmp_path / "memory.db") == tmp_path / "memory.db.lock"


def test_lock_is_reentrant_within_one_process(db):
    """`record_job_outcome` -> `_save_provider_cas` -> `save_provider` bersarang tiga."""
    with ml.memory_lock(db, timeout_seconds=1):
        with ml.memory_lock(db, timeout_seconds=1):
            with ml.memory_lock(db, timeout_seconds=1):
                assert ml.is_locked_here(db)
    assert not ml.is_locked_here(db)


def test_relative_and_absolute_paths_are_the_same_lock(db, monkeypatch):
    monkeypatch.chdir(db.parent)
    with ml.memory_lock(db.name, timeout_seconds=1):
        assert ml.is_locked_here(db)
        assert _try_lock_elsewhere(db) == "LOCKED"


# ----------------------------------------------------------------------
# Fail-closed + berbatas waktu
# ----------------------------------------------------------------------


def test_second_process_is_refused_and_does_not_wait_forever(db, tmp_path):
    proc = _hold_lock(db, tmp_path)
    try:
        mulai = time.monotonic()
        with pytest.raises(ml.MemoryLockError) as exc:
            with ml.memory_lock(db, timeout_seconds=0.3):
                pass
        elapsed = time.monotonic() - mulai
    finally:
        proc.kill()
        proc.wait(timeout=10)
    # Menunggu SESUAI batas, lalu BERHENTI — bukan menggantung, bukan langsung menyerah
    # sebelum batas (kalau langsung menyerah, operasi normal yang beruntun akan saling
    # menjatuhkan tanpa sebab).
    assert 0.3 <= elapsed < 15
    assert "dipakai proses lain" in str(exc.value)
    assert "fail-closed" in str(exc.value).lower()


def test_a_killed_process_leaves_no_ghost_lock(db, tmp_path):
    proc = _hold_lock(db, tmp_path)
    assert _try_lock_elsewhere(db) == "LOCKED"
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=10)
    # Berkasnya boleh tertinggal; yang tidak boleh tertinggal adalah KUNCInya.
    assert ml.lock_path_for(db).exists()
    with ml.memory_lock(db, timeout_seconds=5):
        assert ml.is_locked_here(db)
    assert _try_lock_elsewhere(db) == "ACQUIRED"


def test_lock_is_released_even_when_the_body_raises(db):
    with pytest.raises(ZeroDivisionError):
        with ml.memory_lock(db, timeout_seconds=1):
            raise ZeroDivisionError
    assert not ml.is_locked_here(db)
    assert _try_lock_elsewhere(db) == "ACQUIRED"


def test_client_without_a_discoverable_db_path_is_refused(client):
    """'Tidak tahu file mana yang dikunci' TIDAK BOLEH berarti 'jalan tanpa kunci'."""

    class TanpaStorage:
        """Klien palsu tanpa `.storage` — mis. test double atau pembungkus buatan sendiri."""

        def list_entities(self, *a, **k):  # pragma: no cover - tidak boleh sempat terpanggil
            raise AssertionError("memori dibaca tanpa kunci")

    with pytest.raises(ml.MemoryLockError):
        ml.db_path_of(TanpaStorage())
    with pytest.raises(ml.MemoryLockError):
        mp.load_snapshot(TanpaStorage())


# ----------------------------------------------------------------------
# Kunci DIPEGANG selama seluruh operasi — dibuktikan dari proses lain
# ----------------------------------------------------------------------


def test_lock_is_held_across_the_whole_read_and_root_computation(client, db, monkeypatch):
    """Balapan DI DALAM `load_snapshot` (1x list_entities + 2x search + N x get_reference).

    Probe dijalankan TEPAT di antara pembacaan pertama dan pembacaan reference — titik
    yang persis dipakai reviewer untuk menghasilkan root bagi keadaan yang tidak pernah ada.
    """
    mp.save_provider(client, mp.ProviderProfile(address=addr(0xA1)))
    mp.set_rubric(client, "defi", {"note": "x"})

    asli = mp._reference_keys
    probe: list[str] = []

    def _spy(reader, prefix):
        probe.append(_try_lock_elsewhere(db))
        return asli(reader, prefix)

    monkeypatch.setattr(mp, "_reference_keys", _spy)
    root = mp.memory_root_for_onchain(client)

    assert len(root) == 32
    assert probe and set(probe) == {"LOCKED"}, probe
    # Sesudah operasi selesai, kunci dilepas.
    assert _try_lock_elsewhere(db) == "ACQUIRED"


def test_lock_is_held_across_the_whole_write(client, db, monkeypatch):
    """`_save_provider_cas` non-atomik: probe dijalankan di ANTARA baca-versi dan tulis."""
    asli = mp.save_provider
    probe: list[str] = []

    def _spy(c, profile):
        probe.append(_try_lock_elsewhere(db))
        return asli(c, profile)

    monkeypatch.setattr(mp, "save_provider", _spy)
    mp.record_job_outcome(
        client, addr(0xB2), job_id=1, budget=5, passed=True, client_address=addr(0xC3)
    )

    assert probe and set(probe) == {"LOCKED"}, probe
    assert _try_lock_elsewhere(db) == "ACQUIRED"


def test_export_holds_the_lock_while_it_reads(client, db, tmp_path, monkeypatch):
    """Alat ekspor (2.1b) memakai `load_snapshot` yang sama, jadi ikut terkunci."""
    from agent import memory_export as me

    mp.save_provider(client, mp.ProviderProfile(address=addr(0xA4)))
    asli = mp._reference_keys
    probe: list[str] = []

    def _spy(reader, prefix):
        probe.append(_try_lock_elsewhere(db))
        return asli(reader, prefix)

    monkeypatch.setattr(mp, "_reference_keys", _spy)
    hasil = me.export_memory(db, tmp_path / "mem.json")

    assert hasil.root.startswith("0x")
    assert probe and set(probe) == {"LOCKED"}, probe


# ----------------------------------------------------------------------
# Lost update dua-proses: dulu senyap, sekarang BERHENTI
# ----------------------------------------------------------------------


def test_two_process_lost_update_now_fails_loudly_instead_of_silently(client, db, tmp_path):
    """AC (i): dulu dua proses saling menimpa TANPA satu pun error.

    Sekarang proses kedua berhenti dengan `MemoryLockError`, dan memori tidak berubah —
    yang berarti pemanggil di jalur chain (vault_client) masuk mode aman, bukan menulis
    provider dari snapshot yang sudah basi.
    """
    provider = addr(0xD4)
    mp.record_job_outcome(
        client, provider, job_id=1, budget=1, passed=True, client_address=addr(0xC3)
    )
    sebelum = mp.ProviderProfile.from_body(
        provider, client.get_entity(mp.CATEGORY_PROVIDER, provider)["body"]
    )

    proc = _hold_lock(db, tmp_path)
    try:
        keluaran = _run(WRITE_SRC, str(db), provider, "0.3", "2")
    finally:
        proc.kill()
        proc.wait(timeout=10)

    assert keluaran == "LOCKED", keluaran
    sesudah = mp.ProviderProfile.from_body(
        provider, client.get_entity(mp.CATEGORY_PROVIDER, provider)["body"]
    )
    assert sesudah == sebelum

    # Kontrol: tanpa pemegang kunci, proses kedua memang BISA menulis — jadi tes di atas
    # bukan hijau palsu karena subprocess-nya rusak.
    assert _run(WRITE_SRC, str(db), provider, "5", "2") == "WROTE 2"
