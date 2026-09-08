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
     tugasnya MENGHAPUS berkas adalah tempat paling mahal untuk salah sekali.
  3. **Nol pengikutan symlink.** Berkas yang ternyata symlink TIDAK dihapus dan dilaporkan di
     `refused`. `unlink` atas symlink memang hanya melepas tautannya, tetapi menolaknya membuat
     jawaban endpoint ini jujur: tidak ada keadaan di mana ia melaporkan "terhapus" untuk
     sesuatu yang isinya masih utuh di tempat lain.
  4. **Loopback saja.** `serve()` MENOLAK host non-loopback. Endpoint ini tidak punya
     autentikasi apa pun, dan memang tidak seharusnya punya: ia perkakas demo di mesin juri.

Jawabannya melaporkan APA YANG BENAR-BENAR TERJADI per berkas (`deleted` / `missing` /
`refused`), sehingga UI bisa menampilkan "tidak ada yang terhapus" ketika memang sudah kosong.
Memanggilnya dua kali sah dan tidak meledak: panggilan kedua mengembalikan `deleted: []`.

NOL dependensi baru: `http.server` + `json` + `pathlib` dari stdlib, dan `config_value`/
`agent_root` dari `agent.vault_client`.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent.vault_client import agent_root, config_value

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

MAX_BODY_BYTES = 4 * 1024
REQUEST_TIMEOUT_SECONDS = 15.0

# Kode alasan — bagian dari kontrak HTTP modul ini.
REASON_OK = "ok"
REASON_NOT_FOUND = "not_found"
REASON_METHOD = "method_not_allowed"
REASON_BODY_TOO_LARGE = "body_too_large"
REASON_MALFORMED = "malformed_json"
REASON_INVALID_DB = "invalid_db_name"
REASON_OUTSIDE = "path_outside_demo_dir"
REASON_IO = "delete_failed"

_DEMO_TRUE = frozenset({"1", "true", "yes", "demo"})


class ResetRejected(ValueError):
    """Permintaan ditolak SEBELUM satu berkas pun disentuh. `reason` masuk badan respons."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def demo_mode_enabled() -> bool:
    return config_value("DEMO_MODE", "false").strip().lower() in _DEMO_TRUE


def demo_data_root() -> Path:
    """`<agent>/data/demo` — satu-satunya direktori yang boleh disentuh endpoint ini.

    Diturunkan dari `agent_root()` (jangkar `pyproject.toml`), BUKAN dari cwd dan BUKAN dari
    permintaan. Tidak ada env yang bisa memindahkannya: sebuah `DEMO_RESET_DIR` akan membuat
    "hanya di bawah data demo" bergantung pada konfigurasi, dan konfigurasi bisa salah.
    """
    return (agent_root() / "data" / "demo").resolve()


@dataclass(frozen=True)
class FileOutcome:
    """Nasib satu berkas. `state` ∈ {deleted, missing, refused}."""

    name: str
    state: str


class DemoResetApp:
    """Logika endpoint, tanpa HTTP. Diuji langsung maupun lewat soket."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

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
        targets = [(suffix, self.resolve_target(db_name, suffix)) for suffix in DB_SUFFIXES]
        outcomes: list[FileOutcome] = []
        for _suffix, path in targets:
            outcomes.append(FileOutcome(path.name, self._remove(path)))

        body: dict[str, Any] = {
            "ok": True,
            "reason": REASON_OK,
            "root": str(self.root),
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

    @staticmethod
    def _remove(path: Path) -> str:
        if path.is_symlink():
            # Menolak, bukan mengikuti: lihat batas 3 di docstring modul.
            return "refused"
        try:
            path.unlink()
        except FileNotFoundError:
            return "missing"
        except IsADirectoryError:
            return "refused"
        except OSError as err:
            # Path TIDAK dipantulkan ke klien; ia hanya masuk log.
            log.warning("demo reset: gagal menghapus %s (%s)", path, err.__class__.__name__)
            raise ResetRejected(REASON_IO) from None
        return "deleted"

    # -- jalur HTTP -----------------------------------------------------
    def handle_reset(self, body_bytes: bytes) -> tuple[int, dict[str, Any]]:
        db_name = _parse_body(body_bytes)
        try:
            return HTTPStatus.OK, self.reset(db_name)
        except ResetRejected as rejected:
            status = (
                HTTPStatus.INTERNAL_SERVER_ERROR
                if rejected.reason == REASON_IO
                else HTTPStatus.BAD_REQUEST
            )
            return status, {"ok": False, "reason": rejected.reason}


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
            self._respond(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": rejected.reason})
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
    return routes(DemoResetApp(demo_data_root()) if demo else None, demo_mode=demo)


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
