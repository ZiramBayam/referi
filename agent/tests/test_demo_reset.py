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

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ):
        """Permintaan default meniru proksi Next: JSON, tanpa `Origin`, tanpa `Sec-Fetch-*`."""
        sent = {"Content-Type": "application/json"}
        if headers is not None:
            sent = {k: v for k, v in headers.items() if v is not None}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=sent)
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
    assert root == vc.agent_root() / "data" / "demo"
    assert root.name == "demo" and root.parent.name == "data"


def test_demoDataRootIsNotResolved_soASymlinkedRootStaysVisible():
    """`.resolve()` di sini akan MENGIKUTI `data/demo -> ...` dan menyembunyikan tautannya."""
    assert ".." not in str(dr.demo_data_root())


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


# ======================================================================
# (e) CSRF — satu tab jahat TIDAK boleh cukup untuk menghapus memori
#
# Serangan yang dibuktikan reviewer, bukan diduga: juri membuka halaman apa pun sementara
# `python -m agent.demo_reset` berjalan; halaman itu memuat
#   <form method="POST" action="http://127.0.0.1:8010/demo/memory/reset">
# atau `fetch(url, {mode: "no-cors"})`. `Content-Type: text/plain` termasuk daftar aman
# CORS, jadi browser MENGIRIMNYA tanpa preflight; penyerang tidak perlu bisa membaca
# jawabannya karena penghapusan sudah terjadi. Versi pertama modul ini menjawab 200.
#
# "Loopback saja" bukan pertahanan terhadap browser: browser juga ada di loopback.
# ======================================================================


def assert_nothing_deleted(root: pathlib.Path) -> None:
    for suffix in dr.DB_SUFFIXES:
        assert (root / f"memory.db{suffix}").exists(), f"memory.db{suffix} ikut terhapus"


def test_theExactCsrfAttackFromTheReview_isRefused(tmp_path, serve_routes):
    """Form lintas-asal: `Origin` asing + `Content-Type: text/plain` → ditolak, nol hapus."""
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request(
        "POST",
        dr.RESET_PATH,
        b"{}",
        headers={
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://halaman-jahat.example",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "no-cors",
        },
    )

    assert status == 403
    assert json.loads(raw)["reason"] == dr.REASON_CROSS_ORIGIN
    assert_nothing_deleted(root)


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/plain;charset=UTF-8",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/json-patch+json",
        "",
        None,
    ],
)
def test_corsSafelistedContentTypesAreRefused(tmp_path, serve_routes, content_type):
    """Justru tipe yang BISA dikirim `<form>` tanpa preflight-lah yang harus mati di sini."""
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request(
        "POST", dr.RESET_PATH, b"{}", headers={"Content-Type": content_type}
    )

    assert status == 415
    assert json.loads(raw)["reason"] == dr.REASON_CONTENT_TYPE
    assert_nothing_deleted(root)


@pytest.mark.parametrize(
    "origin", ["https://jahat.example", "http://localhost:3000", "null", "http://127.0.0.1:8010"]
)
def test_anyOriginHeaderAtAllIsRefused(tmp_path, serve_routes, origin):
    """Tidak ada allowlist asal: pemanggil sah tidak pernah mengirim header ini."""
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request(
        "POST",
        dr.RESET_PATH,
        b"{}",
        headers={"Content-Type": "application/json", "Origin": origin},
    )

    assert status == 403
    assert json.loads(raw)["reason"] == dr.REASON_CROSS_ORIGIN
    assert_nothing_deleted(root)


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_secFetchSiteFromAnotherOriginIsRefused(tmp_path, serve_routes, site):
    """Port BUKAN bagian dari "site": :3000 → :8010 mengirim `same-site`, juga harus mati."""
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request(
        "POST",
        dr.RESET_PATH,
        b"{}",
        headers={"Content-Type": "application/json", "Sec-Fetch-Site": site},
    )

    assert status == 403
    assert json.loads(raw)["reason"] == dr.REASON_CROSS_ORIGIN
    assert_nothing_deleted(root)


def test_noCorsFetchModeIsRefused(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request(
        "POST",
        dr.RESET_PATH,
        b"{}",
        headers={"Content-Type": "application/json", "Sec-Fetch-Mode": "no-cors"},
    )

    assert status == 403
    assert json.loads(raw)["reason"] == dr.REASON_CROSS_ORIGIN
    assert_nothing_deleted(root)


@pytest.mark.parametrize(
    "host",
    ["jahat.example", "jahat.example:8010", "192.168.1.10:8010", "[fe80::1]:8010", ""],
)
def test_nonLoopbackHostHeaderIsRefused(tmp_path, serve_routes, host):
    """DNS rebinding: nama penyerang yang menunjuk 127.0.0.1 tetap membawa Host miliknya."""
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request(
        "POST", dr.RESET_PATH, b"{}", headers={"Content-Type": "application/json", "Host": host}
    )

    assert status == 403
    assert json.loads(raw)["reason"] == dr.REASON_BAD_HOST
    assert_nothing_deleted(root)


def test_loopbackHostWithTheWrongPortIsRefused(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request(
        "POST",
        dr.RESET_PATH,
        b"{}",
        headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{server.port + 1}"},
    )

    assert status == 403
    assert json.loads(raw)["reason"] == dr.REASON_BAD_HOST
    assert_nothing_deleted(root)


@pytest.mark.parametrize("template", ["127.0.0.1:{port}", "localhost:{port}", "[::1]:{port}"])
def test_theThreeLoopbackHostFormsAreAccepted(tmp_path, serve_routes, template):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request(
        "POST",
        dr.RESET_PATH,
        b"{}",
        headers={
            "Content-Type": "application/json",
            "Host": template.format(port=server.port),
        },
    )

    assert status == 200
    assert json.loads(raw)["deleted"] == ["memory.db", "memory.db-wal", "memory.db-shm"]


def test_theNextProxyShapedRequestStillWorks(tmp_path, serve_routes):
    """Pemanggil SAH: Node di sisi server, `content-type: application/json`, nol Origin."""
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    status, raw = server.request(
        "POST",
        dr.RESET_PATH,
        b"{}",
        headers={"content-type": "application/json", "accept": "*/*"},
    )

    assert status == 200
    assert json.loads(raw)["ok"] is True
    assert list(root.iterdir()) == []


def test_jsonWithCharsetParameterIsAccepted(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})
    status, _ = server.request(
        "POST", dr.RESET_PATH, b"{}", headers={"Content-Type": "application/json; charset=utf-8"}
    )
    assert status == 200


def test_sameOriginBrowserHeadersAreAccepted(tmp_path, serve_routes):
    """`Sec-Fetch-Site: same-origin` tanpa Origin (mis. dev tool lokal) tetap boleh."""
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})
    status, _ = server.request(
        "POST",
        dr.RESET_PATH,
        b"{}",
        headers={
            "Content-Type": "application/json",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
        },
    )
    assert status == 200


def test_theCsrfGateRunsBeforeTheRouteExistenceCheckIsLeaked(tmp_path, serve_routes):
    """Rute tak dikenal tetap 404 meski permintaannya lintas-asal — nol kebocoran."""
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(make_root(tmp_path))})
    status, _ = server.request(
        "POST",
        "/demo/memory/wipe",
        b"{}",
        headers={"Content-Type": "text/plain", "Origin": "https://jahat.example"},
    )
    assert status == 404


# ======================================================================
# (f) Gerbang DEMO_MODE: env HADIR-tapi-kosong = MATI
# ======================================================================


def test_emptyEnvVarBeatsTheDotEnvFile(monkeypatch):
    """`DEMO_MODE= python -m agent.demo_reset` MEMATIKAN, tidak menyalakan.

    Cacat yang ditemukan reviewer: `config_value` menganggap string kosong sebagai "tidak
    diset" lalu jatuh ke `.env` — dan `.env.example` proyek mengirim `DEMO_MODE=true`.
    Operator yang mengetiknya untuk mematikan justru menyalakan penghapus berkas.
    """
    monkeypatch.setattr(vc, "_env_file_values", lambda: {"DEMO_MODE": "true"})
    monkeypatch.setenv("DEMO_MODE", "")
    assert dr.demo_mode_enabled() is False
    assert dr.build_routes() == {}


@pytest.mark.parametrize("value", ["", "   ", "0", "false", "no", "off", "2", "disabled"])
def test_offValuesKeepTheEndpointUnborn(monkeypatch, value):
    monkeypatch.setattr(vc, "_env_file_values", lambda: {"DEMO_MODE": "true"})
    monkeypatch.setenv("DEMO_MODE", value)
    assert dr.demo_mode_enabled() is False
    assert dr.build_routes() == {}


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "demo"])
def test_onValuesArmTheEndpoint(monkeypatch, no_env_file, value):
    monkeypatch.setenv("DEMO_MODE", value)
    assert dr.demo_mode_enabled() is True


def test_theDotEnvFileIsOnlyConsultedWhenTheEnvVarIsAbsent(monkeypatch):
    monkeypatch.setattr(vc, "_env_file_values", lambda: {"DEMO_MODE": "true"})
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert dr.demo_mode_enabled() is True


def test_thePaymentGateAgreesWithTheResetGate(monkeypatch):
    """Dua gerbang DEMO_MODE, satu aturan — tidak boleh ada yang tetap bersenjata."""
    from agent import payment_402

    monkeypatch.setattr(vc, "_env_file_values", lambda: {"DEMO_MODE": "true"})
    monkeypatch.setenv("DEMO_MODE", "")
    assert payment_402.demo_mode_enabled() is dr.demo_mode_enabled() is False


# ======================================================================
# (g) Akar demo yang di-symlink tidak boleh mengalihkan penghapus
# ======================================================================


def test_aSymlinkedRootIsRefusedAtConstruction(tmp_path):
    """`data/demo -> data/chain-abc` akan memindahkan penghapus ke memori yang dipakai."""
    real = tmp_path / "chain-abc"
    real.mkdir()
    (real / "memory.db").write_text("memori sungguhan", encoding="utf-8")
    link = tmp_path / "demo"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(dr.ResetRejected) as err:
        dr.DemoResetApp(link)

    assert err.value.reason == dr.REASON_ROOT_SYMLINK
    assert (real / "memory.db").read_text(encoding="utf-8") == "memori sungguhan"


def test_aSymlinkedRootLeavesTheRouteTableEmpty(tmp_path, monkeypatch, no_env_file):
    real = tmp_path / "chain-abc"
    real.mkdir()
    link = tmp_path / "demo"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setattr(dr, "demo_data_root", lambda: link)

    assert dr.build_routes() == {}


def test_aRootSwappedForASymlinkAfterStartupIsRefused(tmp_path, serve_routes):
    """Tautan dipasang SESUDAH konstruksi — pemeriksaan diulang tiap `reset()`."""
    root = make_root(tmp_path)
    app = dr.DemoResetApp(root)
    server = serve_routes({dr.RESET_PATH: app})

    victim = tmp_path / "chain-abc"
    victim.mkdir()
    (victim / "memory.db").write_text("memori sungguhan", encoding="utf-8")
    for child in root.iterdir():
        child.unlink()
    root.rmdir()
    root.symlink_to(victim, target_is_directory=True)

    status, raw = server.request("POST", dr.RESET_PATH, b"{}")

    assert status == 500
    assert json.loads(raw)["reason"] == dr.REASON_ROOT_SYMLINK
    assert (victim / "memory.db").read_text(encoding="utf-8") == "memori sungguhan"


# ======================================================================
# (h) Kebersihan jawaban & kejujuran laporan
# ======================================================================


def test_theSuccessBodyDoesNotLeakAnAbsolutePath(tmp_path, serve_routes):
    root = make_root(tmp_path)
    server = serve_routes({dr.RESET_PATH: dr.DemoResetApp(root)})

    _, raw = server.request("POST", dr.RESET_PATH, b"{}")
    body = json.loads(raw)

    assert body["root"] == "demo"
    assert not body["root"].startswith("/")
    assert str(tmp_path) not in raw.decode("utf-8")


def test_theRootLabelIsRelativeToTheAgentPackage():
    app = dr.DemoResetApp(dr.demo_data_root())
    assert dr._root_label(app.root) == str(pathlib.Path("data") / "demo")


def test_aDirectoryNamedLikeTheDbIsRefused_notDeleted(tmp_path):
    """Direktori tidak boleh dilaporkan `deleted` — dan tidak boleh disentuh."""
    root = make_root(tmp_path, with_db=False)
    (root / "memory.db").mkdir()
    (root / "memory.db" / "isi").write_text("x", encoding="utf-8")

    body = dr.DemoResetApp(root).reset()

    assert body["refused"] == ["memory.db"]
    assert (root / "memory.db" / "isi").exists()


def test_theLockFileIsDeliberatelyLeftBehind(tmp_path):
    """`memory.db.lock` BUKAN isi memori; menghapusnya merusak mutual exclusion flock."""
    root = make_root(tmp_path)
    lock = root / "memory.db.lock"
    lock.write_text("", encoding="utf-8")

    body = dr.DemoResetApp(root).reset()

    assert body["deleted"] == ["memory.db", "memory.db-wal", "memory.db-shm"]
    assert lock.exists()


# ======================================================================
# (i) `config_flag` — helper gerbang, terpisah dari `config_value`
# ======================================================================


def test_configFlagAndConfigValueDisagreeOnPurpose(monkeypatch):
    """`config_value` sengaja TIDAK diubah: ia dipakai 30+ tempat untuk NILAI, bukan gerbang.

    Untuk nilai, "kosong = tidak diset" masuk akal (string kosong bukan URL/alamat).
    Untuk gerbang, aturan itu berbahaya. Karena itu ada dua fungsi, dan tes ini mengunci
    perbedaannya supaya tidak ada yang "merapikan"-nya jadi satu.
    """
    monkeypatch.setattr(vc, "_env_file_values", lambda: {"DEMO_MODE": "true"})
    monkeypatch.setenv("DEMO_MODE", "")

    assert vc.config_value("DEMO_MODE", "false") == "true"
    assert vc.config_flag("DEMO_MODE") is False


def test_configFlagFallsBackToTheDotEnvFileOnlyWhenUnset(monkeypatch):
    monkeypatch.setattr(vc, "_env_file_values", lambda: {"X_GATE": "1"})
    monkeypatch.delenv("X_GATE", raising=False)
    assert vc.config_flag("X_GATE") is True
    monkeypatch.setenv("X_GATE", "0")
    assert vc.config_flag("X_GATE") is False


def test_configFlagIsFalseWhenNothingIsConfigured(monkeypatch):
    monkeypatch.setattr(vc, "_env_file_values", dict)
    monkeypatch.delenv("X_GATE", raising=False)
    assert vc.config_flag("X_GATE") is False
