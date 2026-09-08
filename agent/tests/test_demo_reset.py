"""Endpoint hapus memori untuk panel juri — `agent/agent/demo_reset.py`.

Empat properti yang WAJIB terbukti, karena ini satu-satunya kode di repo yang menghapus
berkas atas perintah HTTP:

  (a) tanpa `DEMO_MODE`, endpointnya TIDAK ADA — 404, bukan 403 (403 mengakui keberadaannya);
  (b) path traversal DITOLAK, dan berkas di luar direktori demo tetap utuh sesudahnya;
  (c) KETIGA berkas (`memory.db`, `-wal`, `-shm`) benar-benar tersapu — menyisakan WAL berarti
      isinya bisa dipulihkan dan klaim "memori dihapus" jadi bohong;
  (d) memanggilnya dua kali tidak meledak (idempoten).

Seluruh berkas ini bekerja di `tmp_path`; tidak ada tes yang menyentuh `agent/data/`.
Servernya dibind ke `127.0.0.1:0`.
"""

from __future__ import annotations

import http.client
import json
import pathlib
import threading

import pytest

from agent import demo_reset as dr
from agent import vault_client as vc

# ----------------------------------------------------------------------
# Perkakas
# ----------------------------------------------------------------------


def make_root(tmp_path: pathlib.Path, *, with_db: bool = True) -> pathlib.Path:
    root = tmp_path / "demo"
    root.mkdir()
    if with_db:
        for suffix in dr.DB_SUFFIXES:
            (root / f"memory.db{suffix}").write_text(f"isi{suffix}", encoding="utf-8")
    return root


class Server:
    def __init__(self, route_table: dict[str, dr.DemoResetApp]) -> None:
        self.httpd = dr.serve(route_table, "127.0.0.1", 0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def request(self, method: str, path: str, body: bytes | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            raw = response.read()
            return response.status, raw
        finally:
            conn.close()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def serve_routes():
    servers: list[Server] = []

    def factory(route_table) -> Server:
        server = Server(route_table)
        servers.append(server)
        return server

    yield factory
    for server in servers:
        server.close()


@pytest.fixture
def no_env_file(monkeypatch):
    """`.env` repo TIDAK ikut menentukan hasil tes ini."""
    monkeypatch.setattr(vc, "_env_file_values", dict)


# ======================================================================
# (a) DEMO_MODE mati → endpoint TIDAK terdaftar
# ======================================================================


def test_withoutDemoMode_theRouteTableIsEmpty(monkeypatch, no_env_file):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert dr.demo_mode_enabled() is False
    assert dr.build_routes() == {}


def test_withDemoModeOff_theRouteTableIsEmpty(monkeypatch, no_env_file):
    for value in ("0", "false", "no", ""):
        monkeypatch.setenv("DEMO_MODE", value)
        assert dr.build_routes() == {}


def test_withDemoModeOn_theRouteIsRegistered(monkeypatch, no_env_file):
    monkeypatch.setenv("DEMO_MODE", "1")
    table = dr.build_routes()
    assert dr.RESET_PATH in table
    assert table[dr.RESET_PATH].root == dr.demo_data_root()


def test_withoutDemoMode_theEndpointAnswers404_not403(monkeypatch, no_env_file, serve_routes):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    server = serve_routes(dr.build_routes())
    status, raw = server.request("POST", dr.RESET_PATH, b"{}")
    assert status == 404
    assert status != 403
    assert json.loads(raw) == {"ok": False, "reason": dr.REASON_NOT_FOUND}


def test_withoutDemoMode_otherMethodsAlsoAnswer404(monkeypatch, no_env_file, serve_routes):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    server = serve_routes(dr.build_routes())
    for method in ("GET", "PUT", "DELETE"):
        status, _ = server.request(method, dr.RESET_PATH)
        assert status == 404


def test_routesHelper_ignoresTheAppWhenDemoModeIsOff(tmp_path):
    app = dr.DemoResetApp(make_root(tmp_path))
    assert dr.routes(app, demo_mode=False) == {}
    assert dr.routes(app, demo_mode=True) == {dr.RESET_PATH: app}


# ======================================================================
# (b) Path traversal DITOLAK — dan berkas di luar direktori demo selamat
# ======================================================================


TRAVERSALS = [
    "../memory.db",
    "..",
    "../../etc/passwd",
    "/etc/passwd",
    "sub/memory.db",
    "..\\memory.db",
    "memory.db\x00.txt",
    ".hidden",
    "memory .db",
    "",
]


@pytest.mark.parametrize("db_name", TRAVERSALS)
def test_traversalNamesAreRejectedBeforeAnyFileIsTouched(tmp_path, db_name):
    root = make_root(tmp_path)
    outsider = tmp_path / "memory.db"
    outsider.write_text("JANGAN SENTUH", encoding="utf-8")

    app = dr.DemoResetApp(root)
    with pytest.raises(dr.ResetRejected) as err:
        app.reset(db_name)
    assert err.value.reason in {dr.REASON_INVALID_DB, dr.REASON_OUTSIDE}

    assert outsider.read_text(encoding="utf-8") == "JANGAN SENTUH"
    for suffix in dr.DB_SUFFIXES:
        assert (root / f"memory.db{suffix}").exists()


@pytest.mark.parametrize("db_name", TRAVERSALS)
def test_traversalOverHttpIs400_andTheOutsiderSurvives(tmp_path, serve_routes, db_name):
    root = make_root(tmp_path)
    outsider = tmp_path / "memory.db"
    outsider.write_text("JANGAN SENTUH", encoding="utf-8")

    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})
    body = json.dumps({"db": db_name}).encode("utf-8")
    status, raw = server.request("POST", dr.RESET_PATH, body)
    assert status == 400
    assert json.loads(raw)["reason"] in {dr.REASON_INVALID_DB, dr.REASON_OUTSIDE}
    assert outsider.read_text(encoding="utf-8") == "JANGAN SENTUH"


def test_nonStringDbNameIsRejected(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})
    status, raw = server.request("POST", dr.RESET_PATH, json.dumps({"db": 7}).encode())
    assert status == 400
    assert json.loads(raw)["reason"] == dr.REASON_INVALID_DB
    assert (root / "memory.db").exists()


def test_symlinkIsRefused_andItsTargetSurvives(tmp_path):
    root = make_root(tmp_path, with_db=False)
    victim = tmp_path / "korban.db"
    victim.write_text("data korban", encoding="utf-8")
    (root / "memory.db").symlink_to(victim)
    (root / "memory.db-wal").write_text("wal", encoding="utf-8")

    body = dr.DemoResetApp(root).reset()

    assert body["refused"] == ["memory.db"]
    assert body["deleted"] == ["memory.db-wal"]
    assert victim.read_text(encoding="utf-8") == "data korban"
    assert (root / "memory.db").is_symlink()


def test_theRootIsDerivedFromTheAgentPackage_notFromTheRequest():
    root = dr.demo_data_root()
    assert root.is_absolute()
    assert root == (vc.agent_root() / "data" / "demo").resolve()
    assert root.name == "demo" and root.parent.name == "data"


# ======================================================================
# (c) Ketiga berkas benar-benar tersapu
# ======================================================================


def test_allThreeSqliteFilesAreDeleted(tmp_path):
    root = make_root(tmp_path)
    keep = root / "verdicts.json"
    keep.write_text("bukan target", encoding="utf-8")

    body = dr.DemoResetApp(root).reset()

    assert body["ok"] is True
    assert body["deleted"] == ["memory.db", "memory.db-wal", "memory.db-shm"]
    assert body["missing"] == []
    assert body["refused"] == []
    for suffix in dr.DB_SUFFIXES:
        assert not (root / f"memory.db{suffix}").exists()
    assert keep.read_text(encoding="utf-8") == "bukan target"


def test_theWalFileIsNeverLeftBehind(tmp_path):
    """Menyisakan `-wal` = isi memori masih bisa dipulihkan = klaim penghapusan bohong."""
    root = make_root(tmp_path)
    dr.DemoResetApp(root).reset()
    assert sorted(p.name for p in root.iterdir()) == []


def test_overHttp_theThreeFilesAreSweptAndReported(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request("POST", dr.RESET_PATH, b"")
    body = json.loads(raw)

    assert status == 200
    assert body["ok"] is True
    assert body["db"] == "memory.db"
    assert body["deleted"] == ["memory.db", "memory.db-wal", "memory.db-shm"]
    assert body["root"] == str(root.resolve())
    assert list(root.iterdir()) == []


def test_partialStateIsReportedHonestly(tmp_path):
    """Hanya `-wal` yang ada → jawabannya menyebut satu terhapus dan dua hilang."""
    root = make_root(tmp_path, with_db=False)
    (root / "memory.db-wal").write_text("wal", encoding="utf-8")

    body = dr.DemoResetApp(root).reset()

    assert body["deleted"] == ["memory.db-wal"]
    assert body["missing"] == ["memory.db", "memory.db-shm"]


# ======================================================================
# (d) Dua kali panggil tidak meledak
# ======================================================================


def test_callingTwiceIsIdempotent(tmp_path):
    root = make_root(tmp_path)
    app = dr.DemoResetApp(root)

    first = app.reset()
    second = app.reset()

    assert first["deleted"] == ["memory.db", "memory.db-wal", "memory.db-shm"]
    assert second["ok"] is True
    assert second["deleted"] == []
    assert second["missing"] == ["memory.db", "memory.db-wal", "memory.db-shm"]


def test_overHttp_theSecondCallSays200WithNothingDeleted(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    server.request("POST", dr.RESET_PATH, b"{}")
    status, raw = server.request("POST", dr.RESET_PATH, b"{}")
    body = json.loads(raw)

    assert status == 200
    assert body["deleted"] == []
    assert len(body["missing"]) == 3


def test_resetOnAnEmptyDirectoryDoesNotRaise(tmp_path):
    root = make_root(tmp_path, with_db=False)
    body = dr.DemoResetApp(root).reset()
    assert body["ok"] is True
    assert body["deleted"] == []


# ======================================================================
# Permukaan HTTP lain
# ======================================================================


def test_wrongMethodOnARegisteredRouteIs405(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})
    status, raw = server.request("GET", dr.RESET_PATH)
    assert status == 405
    assert json.loads(raw)["reason"] == dr.REASON_METHOD
    assert (root / "memory.db").exists()


def test_unknownPathIs404(tmp_path, serve_routes):
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(make_root(tmp_path))})
    status, _ = server.request("POST", "/demo/memory/wipe", b"{}")
    assert status == 404


def test_malformedJsonIs400(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})
    status, raw = server.request("POST", dr.RESET_PATH, b"{bukan json")
    assert status == 400
    assert json.loads(raw)["reason"] == dr.REASON_MALFORMED
    assert (root / "memory.db").exists()


def test_oversizedBodyIsRejectedWithoutDeleting(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})
    payload = json.dumps({"db": "memory.db", "pad": "x" * (dr.MAX_BODY_BYTES + 10)}).encode()
    status, raw = server.request("POST", dr.RESET_PATH, payload)
    assert status == 413
    assert json.loads(raw)["reason"] == dr.REASON_BODY_TOO_LARGE
    assert (root / "memory.db").exists()


def test_queryStringDoesNotBypassTheRouteTable(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})
    status, _ = server.request("POST", f"{dr.RESET_PATH}?db=../x", b"{}")
    assert status == 200
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10"])
def test_serveRefusesNonLoopbackHosts(tmp_path, host):
    with pytest.raises(ValueError, match="loopback"):
        dr.serve({dr.RESET_PATH: dr.DemoResetApp(make_root(tmp_path))}, host, 0)


def test_serveBindsLoopbackOnly(tmp_path, serve_routes):
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(make_root(tmp_path))})
    assert server.httpd.server_address[0] == "127.0.0.1"


def test_mainRefusesToRunWithoutDemoMode(monkeypatch, no_env_file):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert dr.main([]) == 1
