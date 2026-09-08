"""Endpoint LOKAL "hapus memori" untuk panel juri — hidup HANYA saat `DEMO_MODE`.

Kenapa ada: `web/panel` punya kontrol "hapus memori" yang sampai hari ini hanya MENAMPILKAN
prosedur (tiga `rm`), karena database duduk di `agent/`, di luar batas folder frontend. Juri
harus bisa menekannya sungguhan, jadi penghapusnya tinggal di sini — di paket yang memang
memiliki `agent/data/`.

Yang dihapus: KETIGA berkas SQLite, `memory.db`, `memory.db-wal`, `memory.db-shm`. Menghapus
`memory.db` saja bukan penghapusan: WAL yang tertinggal bisa memulihkan isinya, dan demo yang
mengklaim "memori dihapus" sambil menyisakan WAL adalah hijau palsu — persis yang dilawan
proyek ini (naskah `sim/src/demo.ts` menyapu ketiganya untuk alasan yang sama).

EMPAT BATAS, semuanya ditegakkan kode, bukan diimbau komentar:

  1. **Tidak terdaftar tanpa `DEMO_MODE`.** `routes()` mengembalikan tabel KOSONG bila
     `DEMO_MODE` mati, jadi tanpa env itu path-nya menjawab 404 seperti path karangan mana
     pun — bukan 403. 403 mengakui bahwa endpointnya ADA dan hanya sedang ditolak; itu
     memberi tahu pemindai bahwa ada tombol penghapus berkas di sini, dan menyisakan satu
     `if` sebagai satu-satunya pemisah antara permintaan dan `unlink`. Yang tidak terdaftar
     tidak bisa dilupakan penjagaannya.
  2. **Hanya di bawah `agent/data/demo/`.** Akar diturunkan dari `agent_root()`, TIDAK PERNAH
     dari permintaan. Permintaan paling banyak boleh memilih NAMA basis data (`db`), dan nama
     itu wajib lolos `DB_NAME_RE` (nol `/`, nol `\\`, nol `..`, nol NUL) DAN hasil gabungnya
     wajib berinduk tepat pada akar demo. Dua lapis untuk satu properti, karena endpoint yang
     tugasnya MENGHAPUS berkas adalah tempat paling mahal untuk salah sekali. Penghapusannya
     sendiri TIDAK memakai path string melainkan fd direktori akar (`_open_root_fd`), supaya
     penukaran komponen leluhur sesudah pemeriksaan tidak bisa memindahkan sasaran.
  3. **Nol pengikutan symlink.** Berkas yang ternyata symlink TIDAK dihapus dan dilaporkan di
     `refused`. `unlink` atas symlink memang hanya melepas tautannya, tetapi menolaknya membuat
     jawaban endpoint ini jujur: tidak ada keadaan di mana ia melaporkan "terhapus" untuk
     sesuatu yang isinya masih utuh di tempat lain.
  4. **Loopback saja.** `serve()` MENOLAK host non-loopback.
  5. **Bukan dari browser.** Loopback saja TERNYATA BUKAN pertahanan: browser juri juga ada
     di loopback, dan satu tab jahat dengan `<form method=POST action="http://127.0.0.1:8010
     /demo/memory/reset">` sudah cukup untuk menghapus memori demo — form mengirim
     `text/plain`, yang termasuk daftar aman CORS, jadi tidak ada preflight yang menahannya
     dan penyerang tidak perlu bisa membaca jawabannya. Karena itu POST kini wajib: tanpa
     header `Origin`, tanpa `Sec-Fetch-Site` lintas-asal, `Content-Type: application/json`
     PERSIS (ini yang memaksa preflight), dan `Host` yang menyebut loopback + port server
     ini (menutup DNS rebinding). Pemanggil sah — proksi Next di sisi server — memenuhi
     semuanya tanpa perubahan: ia bukan browser.

Yang TIDAK dihapus, sengaja: `memory.db.lock`. Ia bukan isi memori melainkan pemegang
`flock` mutual-exclusion (`agent/memory_lock.py`); menghapusnya saat proses lain memegang
kuncinya justru menghasilkan dua proses yang sama-sama merasa memegang kunci. Membiarkan
berkas nol-byte itu tidak memulihkan satu bit pun memori.

Jawabannya melaporkan APA YANG BENAR-BENAR TERJADI per berkas (`deleted` / `missing` /
`refused`), sehingga UI bisa menampilkan "tidak ada yang terhapus" ketika memang sudah kosong.
Memanggilnya dua kali sah dan tidak meledak: panggilan kedua mengembalikan `deleted: []`.

NOL dependensi baru: `http.server` + `json` + `pathlib` dari stdlib, dan `config_value`/
`agent_root` dari `agent.vault_client`.
"""

from __future__ import annotations

import argparse
import errno
import json
import logging
import os
import re
import stat
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent.vault_client import agent_root, config_flag, config_value

log = logging.getLogger("demo_reset")

RESET_PATH = "/demo/memory/reset"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010

# Loopback saja. Daftar, bukan pemeriksaan "bukan 0.0.0.0": `::` dan alamat LAN mesin juga
# mengekspos penghapus berkas ke jaringan.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Akhiran SQLite yang WAJIB ikut tersapu. Sama persis dengan `MEMORY_DB_SUFFIXES` di
# `sim/src/demo.ts`; berbeda = penghapusan yang tidak setara antara demo dan panel.
DB_SUFFIXES = ("", "-wal", "-shm")

# Nama basis data yang boleh diminta. Sengaja sempit: huruf/angka di awal, lalu titik, garis
# bawah, dan tanda hubung. `..`, `/`, `\`, NUL, dan spasi mustahil lolos.
DB_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
DEFAULT_DB_NAME = "memory.db"

# Penghapusan berjalan RELATIF terhadap fd direktori akar (lihat `_open_root_fd`). Tanpa
# dukungan itu modul menolak menghapus apa pun: jalur path-string punya balapan penukaran
# leluhur yang sudah pernah terbukti menghapus berkas di luar akar demo.
_DIR_FD_SUPPORTED = os.open in os.supports_dir_fd and os.unlink in os.supports_dir_fd

MAX_BODY_BYTES = 4 * 1024
REQUEST_TIMEOUT_SECONDS = 15.0

# Satu-satunya `Content-Type` yang diterima. Ini BUKAN kerewelan format: `application/json`
# TIDAK termasuk daftar aman CORS (`text/plain`, `application/x-www-form-urlencoded`,
# `multipart/form-data`), jadi mewajibkannya memaksa browser melakukan preflight — dan
# preflight `OPTIONS` di sini dijawab 501 tanpa satu pun header `Access-Control-Allow-*`.
# Halaman jahat karena itu tidak pernah sampai ke `do_POST`.
JSON_CONTENT_TYPE = "application/json"

# Nilai `Sec-Fetch-Site` yang boleh lewat. Perhatikan: port BUKAN bagian dari "site", jadi
# halaman di http://localhost:3000 yang menembak :8010 mengirim `same-site`, bukan
# `cross-site` — menolak hanya `cross-site` akan meninggalkan lubangnya terbuka.
ALLOWED_FETCH_SITE = frozenset({"none", "same-origin"})

# Mode yang tidak mungkin datang dari pemanggil sah. `no-cors` adalah persis mode yang
# dipakai serangan "kirim saja, tak perlu bisa membaca jawabannya".
FORBIDDEN_FETCH_MODE = frozenset({"no-cors", "navigate", "websocket"})

# Kode alasan — bagian dari kontrak HTTP modul ini.
REASON_OK = "ok"
REASON_NOT_FOUND = "not_found"
REASON_METHOD = "method_not_allowed"
REASON_BODY_TOO_LARGE = "body_too_large"
REASON_MALFORMED = "malformed_json"
REASON_INVALID_DB = "invalid_db_name"
REASON_OUTSIDE = "path_outside_demo_dir"
REASON_IO = "delete_failed"
REASON_CROSS_ORIGIN = "cross_origin_request"
REASON_CONTENT_TYPE = "unsupported_media_type"
REASON_BAD_HOST = "bad_host"
REASON_ROOT_SYMLINK = "root_is_symlink"


def _status_for(reason: str) -> int:
    """Kode alasan → status HTTP. Satu tabel, supaya semua jalur galat sepakat."""
    return {
        REASON_CROSS_ORIGIN: HTTPStatus.FORBIDDEN,
        REASON_BAD_HOST: HTTPStatus.FORBIDDEN,
        REASON_CONTENT_TYPE: HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
        REASON_IO: HTTPStatus.INTERNAL_SERVER_ERROR,
        REASON_ROOT_SYMLINK: HTTPStatus.INTERNAL_SERVER_ERROR,
    }.get(reason, HTTPStatus.BAD_REQUEST)


class ResetRejected(ValueError):
    """Permintaan ditolak SEBELUM satu berkas pun disentuh. `reason` masuk badan respons."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def demo_mode_enabled() -> bool:
    """Gerbang demo, dengan aturan `config_flag`: env HADIR menang walau kosong.

    Sengaja BUKAN `config_value("DEMO_MODE", "false")`. Yang itu memperlakukan string
    kosong sebagai "tidak diset" lalu membaca `.env` — dan `.env.example` proyek ini
    mengirim `DEMO_MODE=true`, jadi `DEMO_MODE= python -m agent.demo_reset`, yang ditulis
    operator untuk MEMATIKAN penghapus berkas, justru menyalakannya. Gerbang harus mati
    ke arah aman.
    """
    return config_flag("DEMO_MODE")


def demo_data_root() -> Path:
    """`<agent>/data/demo` — satu-satunya direktori yang boleh disentuh endpoint ini.

    Diturunkan dari `agent_root()` (jangkar `pyproject.toml`), BUKAN dari cwd dan BUKAN dari
    permintaan. Tidak ada env yang bisa memindahkannya: sebuah `DEMO_RESET_DIR` akan membuat
    "hanya di bawah data demo" bergantung pada konfigurasi, dan konfigurasi bisa salah.
    """
    # SENGAJA tanpa `.resolve()`: yang dikembalikan adalah path yang DIDEKLARASIKAN.
    # `.resolve()` di sini akan diam-diam mengikuti `data/demo -> ...` dan memindahkan
    # sasaran penghapus ke direktori lain; `DemoResetApp` yang memeriksa lalu meresolve.
    return agent_root() / "data" / "demo"


@dataclass(frozen=True)
class FileOutcome:
    """Nasib satu berkas. `state` ∈ {deleted, missing, refused}."""

    name: str
    state: str


class DemoResetApp:
    """Logika endpoint, tanpa HTTP. Diuji langsung maupun lewat soket."""

    def __init__(self, root: Path) -> None:
        self.declared_root = Path(root)
        self._assert_root_is_not_a_symlink()
        self.root = self.declared_root.resolve()

    def _assert_root_is_not_a_symlink(self) -> None:
        """Akar demo wajib direktori sungguhan, bukan tautan.

        `.resolve()` MENGIKUTI symlink pada komponen terakhir. Kalau `agent/data/demo`
        ternyata `-> data/chain-abc`, seluruh penghapus ini diam-diam pindah sasaran ke
        basis data lain — dan basis data itulah yang menghasilkan verdict. Prasyaratnya
        hanya hak tulis lokal, dan bisa datang dari niat baik (juri memindah direktori
        demo ke disk lain). Diperiksa dua kali: saat konstruksi DAN saat setiap `reset()`,
        karena tautan bisa dipasang di antara keduanya.
        """
        if self.declared_root.is_symlink():
            log.warning("demo reset: akar %s adalah symlink — ditolak", self.declared_root)
            raise ResetRejected(REASON_ROOT_SYMLINK)

    # -- validasi -------------------------------------------------------
    def resolve_target(self, db_name: str, suffix: str = "") -> Path:
        """Path absolut berkas yang boleh dihapus, atau `ResetRejected`.

        Lapis 1: nama wajib lolos `DB_NAME_RE`. Lapis 2: induk hasil gabung wajib PERSIS
        akar demo. Lapis 2 tetap dipasang meski lapis 1 sudah menutup `..` dan `/`, karena
        biaya salah sekali di sini adalah berkas orang lain yang hilang.
        """
        if not isinstance(db_name, str) or not DB_NAME_RE.match(db_name):
            raise ResetRejected(REASON_INVALID_DB)
        candidate = self.root / f"{db_name}{suffix}"
        parent = candidate.parent
        try:
            parent_resolved = parent.resolve()
        except OSError:  # pragma: no cover — induk selalu ada di jalur normal
            raise ResetRejected(REASON_OUTSIDE) from None
        if parent_resolved != self.root or candidate.name != f"{db_name}{suffix}":
            raise ResetRejected(REASON_OUTSIDE)
        return self.root / f"{db_name}{suffix}"

    # -- penghapusan ----------------------------------------------------
    def reset(self, db_name: str = DEFAULT_DB_NAME) -> dict[str, Any]:
        """Sapu `<db>`, `<db>-wal`, `<db>-shm`. Idempoten: yang tidak ada = `missing`."""
        if not _DIR_FD_SUPPORTED:  # pragma: no cover — POSIX punya keduanya
            log.error("demo reset: platform tanpa dukungan dir_fd — penghapusan ditolak")
            raise ResetRejected(REASON_IO)
        self._assert_root_is_not_a_symlink()
        if self.declared_root.resolve() != self.root:
            # Akar berpindah sejak konstruksi (mis. direktori ditukar). Jangan hapus apa pun.
            log.warning("demo reset: akar %s berubah sejak start — ditolak", self.declared_root)
            raise ResetRejected(REASON_ROOT_SYMLINK)
        names = [self.resolve_target(db_name, suffix).name for suffix in DB_SUFFIXES]
        dir_fd = self._open_root_fd()
        if dir_fd is None:
            # Direktori demonya sendiri tidak ada: tidak ada yang bisa hilang, dan jawaban
            # "semuanya missing" adalah laporan yang jujur untuk keadaan itu.
            outcomes = [FileOutcome(name, "missing") for name in names]
        else:
            try:
                outcomes = self._sweep(dir_fd, names)
            finally:
                os.close(dir_fd)

        body: dict[str, Any] = {
            "ok": True,
            "reason": REASON_OK,
            # Path RELATIF, bukan absolut: jawaban sukses ini melewati proksi Next ke
            # browser, dan `/home/<user>/...` adalah nama pengguna + tata letak disk juri
            # yang tidak dibutuhkan UI untuk apa pun. Jalur galat memang sudah bersih;
            # jalur sukses sekarang menyusul.
            "root": _root_label(self.root),
            "db": db_name,
            "deleted": [o.name for o in outcomes if o.state == "deleted"],
            "missing": [o.name for o in outcomes if o.state == "missing"],
            "refused": [o.name for o in outcomes if o.state == "refused"],
        }
        log.info(
            "demo reset: root=%s db=%s deleted=%d missing=%d refused=%d",
            self.root,
            db_name,
            len(body["deleted"]),
            len(body["missing"]),
            len(body["refused"]),
        )
        return body

    def _open_root_fd(self) -> int | None:
        """Pegang akar demo sebagai FILE DESCRIPTOR direktori, bukan sebagai string.

        Inilah yang menutup balapan yang dulu nyata: `self.root` adalah string yang dibekukan
        saat konstruksi, jadi setiap `os.open`/`unlink` atas string itu meresolve ULANG seluruh
        komponen leluhurnya. Menukar komponen `demo` menjadi symlink di antara penjaga
        `reset()` dan `unlink` karena itu dulu mengarahkan penghapusan ke direktori lain —
        terukur ~4,5% per panggilan di bawah balapan. Sesudah fd ini terbuka, kernel yang
        memegang direktorinya: penukaran nama apa pun sesudahnya tidak lagi memindahkan sasaran.

        `O_NOFOLLOW` menolak kasus di mana `demo` SUDAH jadi symlink saat dibuka; `O_DIRECTORY`
        menolak kasus di mana ia sudah jadi berkas biasa. `None` berarti direktorinya tidak ada
        (mis. `sim/src/demo.ts` sedang membangun ulang `agent/data/demo`), yang bukan galat.
        """
        try:
            return os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        except OSError as err:
            if err.errno in (errno.ELOOP, errno.EMLINK, errno.ENOTDIR):
                log.warning("demo reset: akar %s bukan direktori sungguhan — ditolak", self.root)
                raise ResetRejected(REASON_ROOT_SYMLINK) from None
            log.warning("demo reset: gagal membuka akar (%s)", err.__class__.__name__)
            raise ResetRejected(REASON_IO) from None

    def _sweep(self, dir_fd: int, names: list[str]) -> list[FileOutcome]:
        """Hapus tiap nama RELATIF terhadap `dir_fd`. Tidak ada path absolut yang dipakai lagi."""
        return [FileOutcome(name, self._remove(dir_fd, name)) for name in names]

    @staticmethod
    def _remove(dir_fd: int, name: str) -> str:
        """Hapus satu berkas dan laporkan nasibnya: deleted / missing / refused.

        Dua penjaga, keduanya di tingkat panggilan kernel:

          * `dir_fd` — `name` diresolve DI DALAM direktori yang sudah dipegang, jadi hanya
            komponen terakhir yang bisa ditukar lawan. Leluhur tidak ikut diresolve ulang.
          * `O_NOFOLLOW` — symlink ditolak dalam SATU panggilan, bukan lewat `is_symlink()`
            lalu `unlink()`. Yang kedua adalah dua panggilan atas nama yang sama: berkas biasa
            bisa berubah jadi tautan di antaranya, dan laporannya lalu berkata "deleted" untuk
            sesuatu yang isinya utuh di tempat lain.

        Sisa balapan yang jujur diakui, dan ini kali ini benar-benar terbatas: entri bernama
        `name` masih bisa ditukar antara `open` dan `unlink`. Dampaknya hanya pada kejujuran
        laporan — `unlink(dir_fd=...)` tidak pernah mengikuti symlink pada komponen terakhir
        dan namanya tidak bisa keluar dari direktori yang dipegang fd, jadi berkas yang hilang
        lewat jalur ini selalu entri di dalam akar demo itu sendiri.
        """
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
        except FileNotFoundError:
            return "missing"
        except OSError as err:
            if err.errno in (errno.ELOOP, errno.EMLINK):
                # Lihat batas 3 di docstring modul: menolak, bukan mengikuti.
                return "refused"
            log.warning("demo reset: gagal membuka %s (%s)", name, err.__class__.__name__)
            raise ResetRejected(REASON_IO) from None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return "refused"
        finally:
            os.close(fd)
        try:
            os.unlink(name, dir_fd=dir_fd)
        except FileNotFoundError:
            return "missing"
        except IsADirectoryError:
            return "refused"
        except OSError as err:
            # Nama TIDAK dipantulkan ke klien; ia hanya masuk log.
            log.warning("demo reset: gagal menghapus %s (%s)", name, err.__class__.__name__)
            raise ResetRejected(REASON_IO) from None
        return "deleted"

    # -- jalur HTTP -----------------------------------------------------
    def handle_reset(self, body_bytes: bytes) -> tuple[int, dict[str, Any]]:
        db_name = _parse_body(body_bytes)
        try:
            return HTTPStatus.OK, self.reset(db_name)
        except ResetRejected as rejected:
            return _status_for(rejected.reason), {"ok": False, "reason": rejected.reason}


def _root_label(root: Path) -> str:
    """Nama direktori untuk DITAMPILKAN — relatif terhadap paket agen, tidak pernah absolut."""
    try:
        return str(root.relative_to(agent_root()))
    except ValueError:
        return root.name


# ----------------------------------------------------------------------
# Gerbang lintas-asal (CSRF)
# ----------------------------------------------------------------------
#
# PELAJARAN YANG MEMATAHKAN ASUMSI VERSI PERTAMA MODUL INI: "loopback saja" BUKAN
# pertahanan terhadap browser, karena browser juga ada di loopback. Selama endpoint ini
# menerima POST apa pun, satu tab jahat yang kebetulan terbuka di mesin juri sudah cukup:
#
#     <form method="POST" action="http://127.0.0.1:8010/demo/memory/reset">
#
# Form itu mengirim `Content-Type: text/plain` (termasuk daftar aman CORS), jadi browser
# MENGIRIMNYA tanpa preflight. Penyerang tidak perlu bisa membaca jawabannya — memori demo
# sudah terhapus saat itu juga. Diuji, bukan diduga: permintaan mentah semacam itu dulu
# dijawab `200 {"deleted": [...]}`.
#
# Tiga syarat di bawah semuanya dipenuhi TANPA usaha oleh pemanggil sah (proksi Next di
# sisi server: ia bukan browser, ia tidak mengirim `Origin`/`Sec-Fetch-*`, dan ia memang
# sudah mengirim `content-type: application/json`), sementara ketiganya mustahil dipenuhi
# oleh halaman jahat: `Origin` dipasang browser sendiri dan tidak bisa dihapus JavaScript,
# dan `application/json` memaksa preflight yang tidak akan pernah dijawab dengan izin.


def _header_values(headers: Any, name: str) -> list[str]:
    """Semua salinan satu header, sudah dipangkas. Bekerja untuk `email.message` dan dict."""
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        return [(value or "").strip() for value in (get_all(name) or [])]
    return [(headers.get(name) or "").strip()]


def check_same_origin(headers: Any, expected_port: int | None) -> None:
    """Tolak permintaan yang datang dari konteks browser lintas-asal. Diam bila aman."""
    # SEMUA salinan header dibaca, bukan hanya yang pertama: `headers.get("Origin")`
    # mengembalikan salinan PERTAMA, jadi `Origin:` kosong yang disusul `Origin:
    # http://jahat.example` dulu lolos gerbang ini. Pemanggil sah tidak mengirim satu pun.
    for origin in _header_values(headers, "Origin"):
        if not origin:
            continue
        # TIDAK ada allowlist asal. Pemanggil sah tidak pernah mengirim header ini sama
        # sekali; membandingkan isinya hanya menambah tempat untuk salah.
        log.warning("demo reset: ditolak, permintaan membawa Origin=%r", origin[:120])
        raise ResetRejected(REASON_CROSS_ORIGIN)

    fetch_site = (headers.get("Sec-Fetch-Site") or "").strip().lower()
    if fetch_site and fetch_site not in ALLOWED_FETCH_SITE:
        log.warning("demo reset: ditolak, Sec-Fetch-Site=%r", fetch_site[:40])
        raise ResetRejected(REASON_CROSS_ORIGIN)

    fetch_mode = (headers.get("Sec-Fetch-Mode") or "").strip().lower()
    if fetch_mode in FORBIDDEN_FETCH_MODE:
        log.warning("demo reset: ditolak, Sec-Fetch-Mode=%r", fetch_mode[:40])
        raise ResetRejected(REASON_CROSS_ORIGIN)

    _check_host(headers.get("Host"), expected_port)


def _check_host(raw_host: str | None, expected_port: int | None) -> None:
    """`Host` wajib menyebut loopback DAN port server ini — tidak ada rebinding DNS.

    Tanpa ini, nama domain penyerang yang di-resolve ke 127.0.0.1 (DNS rebinding) membuat
    permintaannya same-origin di mata browser, dan seluruh pemeriksaan di atas lolos.
    """
    host = (raw_host or "").strip()
    if not host:
        raise ResetRejected(REASON_BAD_HOST)
    if host.startswith("["):  # IPv6 literal: [::1] atau [::1]:8010
        closing = host.find("]")
        if closing < 0:
            raise ResetRejected(REASON_BAD_HOST)
        name, rest = host[1:closing], host[closing + 1 :]
        port_part = rest[1:] if rest.startswith(":") else rest
    elif host.count(":") == 1:
        name, port_part = host.split(":", 1)
    else:
        name, port_part = host, ""
    if name.lower() not in LOOPBACK_HOSTS:
        log.warning("demo reset: ditolak, Host=%r bukan loopback", host[:120])
        raise ResetRejected(REASON_BAD_HOST)
    if expected_port is None:
        return
    if not port_part:
        # `agent/README.md` menjanjikan "port wajib port server"; menerima `Host: localhost`
        # tanpa port membuat janji itu bohong dan menyisakan satu bentuk Host yang lolos
        # tanpa menyebut port mana pun. Pemanggil sah selalu menyebutnya: port server ini
        # bukan 80/443, jadi setiap klien HTTP memasangnya sendiri.
        log.warning("demo reset: ditolak, Host=%r tanpa port", host[:120])
        raise ResetRejected(REASON_BAD_HOST)
    if port_part != str(expected_port):
        log.warning("demo reset: ditolak, port pada Host=%r bukan %d", host[:120], expected_port)
        raise ResetRejected(REASON_BAD_HOST)


def check_content_type(headers: Any) -> None:
    """`Content-Type: application/json` PERSIS (parameter seperti `charset` boleh).

    Inilah pemaksa preflight. `text/plain`, `application/x-www-form-urlencoded`, dan
    `multipart/form-data` — yakni segala yang bisa dikirim `<form>` tanpa preflight —
    ditolak di sini, begitu pula permintaan tanpa `Content-Type` sama sekali.
    """
    raw = (headers.get("Content-Type") or "").strip()
    base = raw.split(";", 1)[0].strip().lower()
    if base != JSON_CONTENT_TYPE:
        log.warning("demo reset: ditolak, Content-Type=%r", raw[:120])
        raise ResetRejected(REASON_CONTENT_TYPE)


def _parse_body(body_bytes: bytes) -> str:
    """Badan permintaan → nama basis data. Badan kosong = default `memory.db`."""
    if not body_bytes.strip():
        return DEFAULT_DB_NAME
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ResetRejected(REASON_MALFORMED) from None
    if not isinstance(payload, dict):
        raise ResetRejected(REASON_MALFORMED)
    db_name = payload.get("db", DEFAULT_DB_NAME)
    if db_name is None:
        return DEFAULT_DB_NAME
    if not isinstance(db_name, str):
        raise ResetRejected(REASON_INVALID_DB)
    return db_name


def routes(app: DemoResetApp | None, *, demo_mode: bool) -> dict[str, DemoResetApp]:
    """Tabel rute. KOSONG bila `DEMO_MODE` mati — endpointnya tidak lahir sama sekali."""
    if not demo_mode or app is None:
        return {}
    return {RESET_PATH: app}


class ResetHandler(BaseHTTPRequestHandler):
    server_version = "evaluator-demo-reset"
    sys_version = ""
    timeout = REQUEST_TIMEOUT_SECONDS
    route_table: dict[str, DemoResetApp] = {}

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — tanda tangan stdlib
        log.info("%s - %s", self.address_string(), format % args)

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _bound_port(self) -> int | None:
        try:
            return int(self.server.server_address[1])
        except (AttributeError, IndexError, TypeError, ValueError):  # pragma: no cover
            return None

    def _read_body(self) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length < 0 or length > MAX_BODY_BYTES:
            return None
        return self.rfile.read(length) if length else b""

    def do_POST(self) -> None:  # noqa: N802 — tanda tangan stdlib
        path = self.path.split("?", 1)[0]
        app = self.route_table.get(path)
        if app is None:
            self._respond(HTTPStatus.NOT_FOUND, {"ok": False, "reason": REASON_NOT_FOUND})
            return
        try:
            check_same_origin(self.headers, self._bound_port())
            check_content_type(self.headers)
        except ResetRejected as rejected:
            self._respond(_status_for(rejected.reason), {"ok": False, "reason": rejected.reason})
            return
        body = self._read_body()
        if body is None:
            self._respond(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"ok": False, "reason": REASON_BODY_TOO_LARGE},
            )
            return
        try:
            status, payload = app.handle_reset(body)
        except ResetRejected as rejected:
            self._respond(_status_for(rejected.reason), {"ok": False, "reason": rejected.reason})
            return
        except Exception:  # pragma: no cover — jaring terakhir; detail hanya ke log
            log.exception("demo reset: galat tak terduga")
            self._respond(
                HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "reason": REASON_IO}
            )
            return
        self._respond(status, payload)

    def _other(self) -> None:
        path = self.path.split("?", 1)[0]
        # Rute yang tidak terdaftar TETAP 404, apa pun metodenya: keberadaan endpoint ini
        # tidak boleh bocor lewat selisih 404/405.
        if path not in self.route_table:
            self._respond(HTTPStatus.NOT_FOUND, {"ok": False, "reason": REASON_NOT_FOUND})
            return
        self._respond(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "reason": REASON_METHOD})

    do_GET = _other
    do_PUT = _other
    do_DELETE = _other


def make_handler(route_table: dict[str, DemoResetApp]) -> type[ResetHandler]:
    return type("BoundResetHandler", (ResetHandler,), {"route_table": dict(route_table)})


def serve(
    route_table: dict[str, DemoResetApp],
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    """Server yang SUDAH terikat, belum melayani. Host non-loopback DITOLAK."""
    if host not in LOOPBACK_HOSTS:
        raise ValueError(
            f"host {host!r} bukan loopback — endpoint hapus memori tidak boleh terikat ke "
            "antarmuka yang bisa dijangkau jaringan"
        )
    return ThreadingHTTPServer((host, port), make_handler(route_table))


def build_routes() -> dict[str, DemoResetApp]:
    """Tabel rute dari konfigurasi. Tanpa `DEMO_MODE` → kosong."""
    demo = demo_mode_enabled()
    if not demo:
        return routes(None, demo_mode=False)
    try:
        app = DemoResetApp(demo_data_root())
    except ResetRejected as rejected:
        # Akar demo adalah symlink → JANGAN daftarkan apa pun. Gagal ke arah "tidak
        # menghapus", bukan ke arah "menghapus sesuatu yang lain".
        log.error("demo reset: akar demo ditolak (%s) — endpoint tidak didaftarkan", rejected.reason)
        return {}
    return routes(app, demo_mode=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Endpoint hapus memori untuk panel juri (HANYA saat DEMO_MODE=1)"
    )
    parser.add_argument("--host", default=config_value("DEMO_RESET_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port", type=int, default=int(config_value("DEMO_RESET_PORT", str(DEFAULT_PORT)))
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    table = build_routes()
    if not table:
        log.error(
            "DEMO_MODE mati — endpoint %s TIDAK didaftarkan dan server tidak dijalankan",
            RESET_PATH,
        )
        return 1
    log.info(
        "demo reset: http://%s:%d%s → %s", args.host, args.port, RESET_PATH, demo_data_root()
    )
    httpd = serve(table, args.host, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover — dijalankan lewat `python -m`
    raise SystemExit(main())
