"""Penjaga RUNTIME `client_address` — dipasang untuk SELURUH suite.

Kenapa ada, padahal sudah ada pemindai AST
(`test_job_pipeline.py::test_every_production_call_of_record_job_outcome_passes_client_address`):
pemindai AST membaca BENTUK, dan bentuk bisa dihindari tanpa satu pun karakter yang salah.
`getattr(mp, "record_job_outcome")(...)`, `functools.partial(...)`, `vars(mp)[...]`, tabel
dispatch `{"w": record_job_outcome}["w"](...)`, `map(record_job_outcome, ...)` — semuanya
memanggil fungsi yang sama tanpa pernah menampilkan sebuah `ast.Call` yang bisa dibaca
pemindai statis mana pun. Penjaga di berkas ini tidak melihat bentuk sama sekali: ia
melihat PANGGILAN yang benar-benar terjadi, jadi kelas bypass itu tidak ada untuknya.

Dua penjaga ini melengkapi, bukan menggantikan:
  - AST menangkap kode yang TIDAK PERNAH DIJALANKAN suite (jalur langka, cabang error);
  - runtime menangkap kode yang dijalankan LEWAT BENTUK APA PUN, termasuk yang dibangun
    saat itu juga dari string.

Yang DIJAGA: setiap panggilan `record_job_outcome` yang frame pemanggilnya berada di dalam
paket `agent/agent/` (= jalur produksi) wajib MENGIKAT parameter `client_address`, entah
sebagai keyword atau posisional. Yang TIDAK diklaim, dan sengaja:
  - panggilan dari berkas tes (mereka menguji fungsinya, bukan memakainya);
  - panggilan dari proses anak yang tidak memuat conftest ini (`test_memory_lock.py`);
  - kode produksi yang tidak pernah dieksekusi suite — itu bagian pemindai AST.

Galatnya turunan `BaseException`, bukan `Exception`: `vault_client.main()` menangkap
`Exception` secara generik, dan penjaga yang bisa ditelan `except Exception` di jalur yang
sedang ia jaga adalah penjaga yang berbunyi seperti jaminan padahal bukan.
"""

from __future__ import annotations

import functools
import inspect
import pathlib

import pytest

from agent import memory_policy as mp
from agent import vault_client as vc

# Direktori paket produksi. `resolve()` sekali di sini supaya perbandingan per panggilan
# tidak menyentuh filesystem.
PACKAGE_DIR = pathlib.Path(mp.__file__).resolve().parent

GUARDED_NAME = "record_job_outcome"
GUARDED_PARAM = "client_address"

# Modul yang memegang referensi SENDIRI ke fungsi itu. `vault_client` mengimpor namanya
# (`from agent.memory_policy import record_job_outcome`), jadi menambal `memory_policy`
# saja akan meninggalkan jalur produksi yang sesungguhnya tanpa penjaga.
GUARDED_MODULES = (mp, vc)


class ClientAddressGuardViolation(BaseException):
    """Jalur produksi memanggil `record_job_outcome` tanpa mengikat `client_address`."""


def caller_is_production(filename: str) -> bool:
    """Frame pemanggil berada di dalam paket `agent/agent/`?

    Nama berkas diambil apa adanya dari `f_code.co_filename` — ia tidak harus benar-benar
    ada di disk. Justru itu yang membuat penjaga ini bisa DIUJI: tes mengeksekusi bentuk
    bypass dengan `compile(..., filename=<di dalam paket>, ...)`.
    """
    try:
        return pathlib.Path(filename).resolve().is_relative_to(PACKAGE_DIR)
    except (OSError, ValueError):  # nama berkas sintetis (`<string>`, `<stdin>`)
        return False


def _binds_client_address(signature: inspect.Signature, args: tuple, kwargs: dict) -> bool:
    """`client_address` benar-benar TERIKAT oleh panggilan ini (keyword ATAU posisional)?

    `bind_partial` dipakai, bukan `bind`: yang ditanya bukan "apakah panggilannya sah"
    (itu urusan Python) melainkan "apakah argumen ini diucapkan". Default parameter TIDAK
    dihitung sebagai terikat — dan memang itu intinya: `None` yang datang dari default
    adalah kelalaian, `None` yang diketik adalah pernyataan "tidak diketahui".
    """
    try:
        bound = signature.bind_partial(*args, **kwargs)
    except TypeError:
        # Panggilan yang tidak cocok signature akan gagal sendiri sedetik lagi; penjaga ini
        # bukan pemeriksa tipe, jadi ia meneruskannya.
        return True
    return GUARDED_PARAM in bound.arguments


def guard_client_address(fn):
    """Membungkus `fn` supaya setiap panggilan DARI dalam paket produksi wajib mengetik
    `client_address`. Idempoten: membungkus dua kali tidak menambah lapisan."""
    if getattr(fn, "__client_address_guard__", False):
        return fn
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        # `inspect.currentframe().f_back`, bukan `inspect.stack()[1]`: keduanya menunjuk
        # frame yang SAMA, tetapi `inspect.stack()` membangun FrameInfo untuk SELURUH
        # tumpukan (termasuk membaca sumber dari disk) pada setiap panggilan.
        frame = inspect.currentframe()
        pemanggil = frame.f_back if frame is not None else None
        nama_berkas = pemanggil.f_code.co_filename if pemanggil is not None else ""
        if caller_is_production(nama_berkas) and not _binds_client_address(signature, args, kwargs):
            raise ClientAddressGuardViolation(
                f"{nama_berkas}:{pemanggil.f_lineno} memanggil {GUARDED_NAME} TANPA "
                f"{GUARDED_PARAM} — filter ADR-021 keputusan 2 (client == provider -> budget "
                "dibuang) MATI DIAM-DIAM di panggilan itu: tidak ada galat, tidak ada log, "
                "hanya cap yang tidak pernah turun. Teruskan `getJob(jobId).client` ke sana."
            )
        return fn(*args, **kwargs)

    wrapper.__client_address_guard__ = True
    return wrapper


@pytest.fixture(scope="session", autouse=True)
def _client_address_runtime_guard():
    """Memasang penjaga ke SETIAP modul yang memegang referensi, untuk seluruh sesi."""
    asli = {modul: getattr(modul, GUARDED_NAME) for modul in GUARDED_MODULES}
    for modul, fn in asli.items():
        setattr(modul, GUARDED_NAME, guard_client_address(fn))
    try:
        yield
    finally:
        for modul, fn in asli.items():
            setattr(modul, GUARDED_NAME, fn)
