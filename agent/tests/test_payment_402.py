"""Gerbang 402 buatan sendiri di depan `POST /jobs/register` — task 2.6, ADR-010.

Seluruh berkas ini OFFLINE: RPC dipalsukan (`FakeEth`) dan servernya dibind ke
`127.0.0.1:0`. Tidak ada satu pun transaksi yang dikirim — RPC palsu MELEDAK bila ada yang
mencoba (`send_raw_transaction`), sehingga "endpoint ini hanya membaca chain" adalah properti
yang diuji, bukan yang diklaim.

Yang dibuktikan di sini, urut menurut AC 2.6 + ADR-010:
  - tanpa header pembayaran → 402 lengkap dengan skema dan parameternya;
  - pembayaran sah (dibaca dari receipt) → 200; dummy di DEMO_MODE → 200 yang MENANDAI diri;
  - REPLAY: satu hash tx dipakai dua kali → 402, termasuk sesudah proses baru membaca ulang
    bukunya dari disk. Di jalur x402 resmi ini tugas fasilitator; di jalur kita tidak ada yang
    mengerjakannya kecuali kode kita, jadi tesnya wajib;
  - dekode log `Transfer` memakai web3 SUNGGUHAN (bukan mock) atas receipt buatan tangan,
    supaya penolakan token sampah benar-benar teruji: `process_receipt` 7.16.0 mendekode log
    `Transfer` dari kontrak MANA PUN.
"""

from __future__ import annotations

import http.client
import json
import pathlib
import threading

import pytest
from eth_utils import keccak
from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import TransactionNotFound

from agent import payment_402 as px

TOKEN = Web3.to_checksum_address("0xECc22a8F6fD62388498fBa19813E214605a2BDb3")
OTHER_TOKEN = Web3.to_checksum_address("0x036CbD53842c5426634e7929541eC2318f3dCF7e")
PAY_TO = Web3.to_checksum_address("0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894")
STRANGER = Web3.to_checksum_address("0x" + "cc" * 20)
PAYER = Web3.to_checksum_address("0x" + "11" * 20)
AMOUNT = 1_000_000
CHAIN_ID = 84532

TX_OK = "0x" + "aa" * 32
TX_SECOND = "0x" + "bb" * 32
TRANSFER_TOPIC = HexBytes(keccak(text="Transfer(address,address,uint256)"))


# ----------------------------------------------------------------------
# RPC palsu — hanya membaca; setiap jalur transaksi meledak
# ----------------------------------------------------------------------


def transfer_log(*, token: str, to: str, value: int, sender: str = PAYER) -> dict:
    def topic_address(address: str) -> HexBytes:
        return HexBytes("0x" + "00" * 12 + address[2:].lower())

    return {
        "address": Web3.to_checksum_address(token),
        "topics": [TRANSFER_TOPIC, topic_address(sender), topic_address(to)],
        "data": HexBytes(value.to_bytes(32, "big")),
        "blockHash": HexBytes("0x" + "22" * 32),
        "blockNumber": 46_400_000,
        "logIndex": 0,
        "transactionHash": HexBytes("0x" + "33" * 32),
        "transactionIndex": 0,
        "removed": False,
    }


def receipt(*, status: int = 1, logs: list[dict] | None = None) -> dict:
    return {"status": status, "logs": logs if logs is not None else []}


def good_receipt() -> dict:
    return receipt(logs=[transfer_log(token=TOKEN, to=PAY_TO, value=AMOUNT)])


class FakeEth:
    """`eth.contract` DIDELEGASIKAN ke web3 sungguhan: dekode lognya nyata, RPC-nya palsu."""

    def __init__(self, receipts: dict[str, dict], chain_id: int = CHAIN_ID) -> None:
        self._receipts = {k.lower(): v for k, v in receipts.items()}
        self._real = Web3()
        self.chain_id = chain_id
        self.receipt_reads: list[str] = []

    def contract(self, address=None, **kwargs):
        return self._real.eth.contract(address=address, **kwargs)

    def get_transaction_receipt(self, transaction_hash):
        key = str(transaction_hash).lower()
        self.receipt_reads.append(key)
        try:
            return self._receipts[key]
        except KeyError:
            raise TransactionNotFound(f"tidak ada receipt untuk {key}") from None

    def send_raw_transaction(self, *args, **kwargs):  # pragma: no cover — harus tak terpanggil
        raise AssertionError("gerbang 402 DILARANG mengirim transaksi")

    def get_transaction_count(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("gerbang 402 DILARANG membaca nonce penandatangan")


class FakeWeb3:
    def __init__(self, receipts: dict[str, dict] | None = None, chain_id: int = CHAIN_ID) -> None:
        self.eth = FakeEth(receipts or {}, chain_id=chain_id)


def make_terms(**overrides) -> px.PaymentTerms:
    values = {
        "realm": "evaluator-jobs-register",
        "network": f"eip155:{CHAIN_ID}",
        "asset": TOKEN,
        "pay_to": PAY_TO,
        "amount": AMOUNT,
    }
    values.update(overrides)
    return px.PaymentTerms(**values)


def make_app(
    *,
    receipts: dict[str, dict] | None = None,
    demo_mode: bool = False,
    ledger: px.PaymentLedger | None = None,
    chain_id: int = CHAIN_ID,
    w3: FakeWeb3 | None = None,
) -> px.RegisterApp:
    w3 = w3 or FakeWeb3(receipts, chain_id=chain_id)
    verifier = px.PaymentVerifier(
        w3,
        make_terms(),
        CHAIN_ID,
        ledger or px.PaymentLedger(),
        demo_mode=demo_mode,
    )
    return px.RegisterApp(verifier, demo_mode=demo_mode)


def auth(tx: str) -> str:
    return f'{px.SCHEME} tx="{tx}"'


BODY = json.dumps({"job_id": 421}).encode()


# ----------------------------------------------------------------------
# Klien HTTP nyata di atas soket loopback
# ----------------------------------------------------------------------


class Server:
    def __init__(self, app: px.RegisterApp) -> None:
        self.httpd = px.serve(app, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    def request(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            raw = response.read()
            return response.status, dict(response.getheaders()), raw
        finally:
            conn.close()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def serve_app():
    servers: list[Server] = []

    def factory(app: px.RegisterApp) -> Server:
        server = Server(app)
        servers.append(server)
        return server

    yield factory
    for server in servers:
        server.close()


# ======================================================================
# AC 1 — tanpa header pembayaran → 402 dengan skemanya
# ======================================================================


def test_post_without_payment_header_returns_402_with_scheme(serve_app):
    server = serve_app(make_app())
    status, headers, raw = server.request(
        "POST", px.REGISTER_PATH, BODY, {"Content-Type": "application/json"}
    )

    assert status == 402
    challenge = headers["WWW-Authenticate"]
    assert challenge.startswith(px.SCHEME + " ")
    for key, value in (
        ("realm", "evaluator-jobs-register"),
        ("network", f"eip155:{CHAIN_ID}"),
        ("asset", TOKEN),
        ("payTo", PAY_TO),
        ("amount", str(AMOUNT)),
    ):
        assert f'{key}="{value}"' in challenge
    assert 'nonce="' in challenge

    body = json.loads(raw)
    # ADR-010 keputusan 3(i): badan JSON MENGULANG parameter yang sama.
    assert body["scheme"] == px.SCHEME
    assert body["network"] == f"eip155:{CHAIN_ID}"
    assert body["asset"] == TOKEN
    assert body["payTo"] == PAY_TO
    assert body["amount"] == str(AMOUNT)
    assert body["realm"] == "evaluator-jobs-register"
    assert len(body["nonce"]) == 32
    assert body["reason"] == px.REASON_MISSING


def test_each_challenge_carries_a_fresh_nonce(serve_app):
    server = serve_app(make_app())
    nonces = set()
    for _ in range(3):
        _, headers, _ = server.request("POST", px.REGISTER_PATH, BODY)
        nonces.add(headers["WWW-Authenticate"].split('nonce="')[1].split('"')[0])
    assert len(nonces) == 3


def test_scheme_name_is_not_x402_or_a_derivative():
    """ADR-010 keputusan 3(iv) — dijaga tes supaya tidak bisa kembali lewat rename diam-diam."""
    assert "x402" not in px.SCHEME.lower()
    assert px.SCHEME.lower() not in {"402", "payment402", "http402"}
    challenge = make_terms().challenge_header("00" * 16)
    assert "x402" not in challenge.lower()


def test_the_402_body_says_out_loud_that_this_is_not_x402(serve_app):
    server = serve_app(make_app())
    _, _, raw = server.request("POST", px.REGISTER_PATH, BODY)
    assert "BUKAN x402" in json.loads(raw)["protocol"]


# ======================================================================
# AC 2 — pembayaran sah (dibaca dari chain) → 200
# ======================================================================


def test_valid_onchain_payment_returns_200(serve_app):
    app = make_app(receipts={TX_OK: good_receipt()})
    server = serve_app(app)
    status, headers, raw = server.request("POST", px.REGISTER_PATH, BODY, {"Authorization": auth(TX_OK)})

    assert status == 200
    body = json.loads(raw)
    assert body["status"] == "registered"
    assert body["job_id"] == 421
    assert body["mode"] == "live"
    assert body["payment"]["tx"] == TX_OK
    assert body["payment"]["verified_onchain"] is True
    assert "X-Payment-Mode" not in headers
    # Verifikasi benar-benar MEMBACA chain, bukan mempercayai header.
    assert app.verifier.w3.eth.receipt_reads == [TX_OK]


def test_payment_over_the_asking_price_is_accepted():
    app = make_app(receipts={TX_OK: receipt(logs=[transfer_log(token=TOKEN, to=PAY_TO, value=AMOUNT * 3)])})
    status, _, body = app.handle_register(auth(TX_OK), BODY)
    assert status == 200
    assert body["payment"]["value"] == str(AMOUNT * 3)


# ======================================================================
# AC 2b — DEMO_MODE: header dummy → 200 yang MENANDAI dirinya mode demo
# ======================================================================


def test_demo_header_is_accepted_and_the_200_marks_itself(serve_app):
    server = serve_app(make_app(demo_mode=True))
    status, headers, raw = server.request(
        "POST", px.REGISTER_PATH, BODY, {"Authorization": f'{px.SCHEME} demo="true"'}
    )

    assert status == 200
    body = json.loads(raw)
    assert body["mode"] == "demo"
    assert body["demo"] is True
    assert "DEMO_MODE" in body["warning"]
    assert body["payment"]["verified_onchain"] is False
    assert headers["X-Payment-Mode"] == "demo"


def test_demo_header_is_rejected_when_demo_mode_is_off(serve_app):
    server = serve_app(make_app(demo_mode=False))
    status, _, raw = server.request(
        "POST", px.REGISTER_PATH, BODY, {"Authorization": f'{px.SCHEME} demo="true"'}
    )
    assert status == 402
    assert json.loads(raw)["reason"] == px.REASON_MALFORMED


def test_demo_mode_does_not_rescue_a_bogus_tx_claim():
    """Mode demo membuka jalur TANPA klaim tx. Klaim tx yang cacat tetap dibaca ke chain."""
    app = make_app(demo_mode=True)
    status, _, body = app.handle_register(f'{px.SCHEME} tx="0xdeadbeef" demo="true"', BODY)
    assert status == 402
    assert body["reason"] == px.REASON_MALFORMED

    app2 = make_app(demo_mode=True)
    status2, _, body2 = app2.handle_register(f'{px.SCHEME} tx="{TX_OK}" demo="true"', BODY)
    assert status2 == 402
    assert body2["reason"] == px.REASON_RECEIPT


# ======================================================================
# REPLAY — penjaga milik kita sendiri (ADR-010 konsekuensi terakhir)
# ======================================================================


def test_the_same_tx_hash_cannot_pay_twice(serve_app):
    server = serve_app(make_app(receipts={TX_OK: good_receipt()}))

    first, _, _ = server.request("POST", px.REGISTER_PATH, BODY, {"Authorization": auth(TX_OK)})
    second, headers, raw = server.request("POST", px.REGISTER_PATH, BODY, {"Authorization": auth(TX_OK)})

    assert first == 200
    assert second == 402
    assert json.loads(raw)["reason"] == px.REASON_REPLAY
    assert headers["WWW-Authenticate"].startswith(px.SCHEME + " ")


def test_replay_is_still_blocked_after_a_restart(tmp_path):
    """Buku hash tx dibaca ulang dari disk: restart bukan cara membayar dua kali."""
    path = tmp_path / "payments-402.jsonl"
    first = make_app(receipts={TX_OK: good_receipt()}, ledger=px.PaymentLedger(path))
    assert first.handle_register(auth(TX_OK), BODY)[0] == 200

    reborn = make_app(receipts={TX_OK: good_receipt()}, ledger=px.PaymentLedger(path))
    status, _, body = reborn.handle_register(auth(TX_OK), BODY)
    assert status == 402
    assert body["reason"] == px.REASON_REPLAY

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [r["tx"] for r in records] == [TX_OK]


def test_case_variation_of_the_hash_is_the_same_payment():
    app = make_app(receipts={TX_OK: good_receipt()})
    assert app.handle_register(auth(TX_OK), BODY)[0] == 200
    status, _, body = app.handle_register(auth("0x" + "AA" * 32), BODY)
    assert status == 402
    assert body["reason"] == px.REASON_REPLAY


def test_a_second_distinct_payment_is_still_accepted():
    app = make_app(receipts={TX_OK: good_receipt(), TX_SECOND: good_receipt()})
    assert app.handle_register(auth(TX_OK), BODY)[0] == 200
    assert app.handle_register(auth(TX_SECOND), BODY)[0] == 200


def test_a_rejected_request_does_not_burn_a_valid_payment():
    """Badan cacat → 400, dan hash tx TIDAK diklaim; klien boleh mengulang dengan tx yang sama."""
    app = make_app(receipts={TX_OK: good_receipt()})
    status, _, body = app.handle_register(auth(TX_OK), b"{bukan json")
    assert status == 400
    assert body["error"] == "invalid_json"
    assert app.verifier.ledger.is_used(TX_OK) is False
    assert app.handle_register(auth(TX_OK), BODY)[0] == 200


def test_concurrent_requests_with_one_hash_yield_exactly_one_200():
    app = make_app(receipts={TX_OK: good_receipt()})
    results: list[int] = []
    lock = threading.Lock()
    start = threading.Barrier(8)

    def worker() -> None:
        start.wait()
        status, _, _ = app.handle_register(auth(TX_OK), BODY)
        with lock:
            results.append(status)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert results.count(200) == 1
    assert results.count(402) == 7


# ======================================================================
# Verifikasi = membaca chain. Setiap syarat ADR-010 3(iii) punya penolakannya sendiri.
# ======================================================================


@pytest.mark.parametrize(
    ("name", "tx_receipt", "expected"),
    [
        (
            "receipt gagal (status 0)",
            receipt(status=0, logs=[transfer_log(token=TOKEN, to=PAY_TO, value=AMOUNT)]),
            px.REASON_TX_FAILED,
        ),
        (
            "tanpa log Transfer",
            receipt(logs=[]),
            px.REASON_NO_TRANSFER,
        ),
        (
            "penerima orang lain",
            receipt(logs=[transfer_log(token=TOKEN, to=STRANGER, value=AMOUNT)]),
            px.REASON_NO_TRANSFER,
        ),
        (
            "nilai kurang satu unit",
            receipt(logs=[transfer_log(token=TOKEN, to=PAY_TO, value=AMOUNT - 1)]),
            px.REASON_NO_TRANSFER,
        ),
        (
            "token lain, jumlah besar",
            receipt(logs=[transfer_log(token=OTHER_TOKEN, to=PAY_TO, value=AMOUNT * 99)]),
            px.REASON_NO_TRANSFER,
        ),
    ],
)
def test_chain_read_rejects(name, tx_receipt, expected):
    app = make_app(receipts={TX_OK: tx_receipt})
    status, _, body = app.handle_register(auth(TX_OK), BODY)
    assert status == 402, name
    assert body["reason"] == expected, name


def test_a_junk_token_cannot_pay_the_bill_even_though_web3_decodes_its_log():
    """`process_receipt` 7.16.0 TIDAK menyaring alamat kontrak — pembandingannya milik kita.

    Diukur, bukan diingat: log `Transfer` dari `0x036CbD53…` tetap terdekode oleh kontrak
    `0xECc22a8F…`. Tes ini menjadi merah kalau `_matching_transfer` berhenti membandingkan
    `log["address"]`.
    """
    app = make_app()
    decoded = list(
        app.verifier._token.events.Transfer().process_receipt(
            receipt(logs=[transfer_log(token=OTHER_TOKEN, to=PAY_TO, value=AMOUNT * 99)]),
            errors=px.DISCARD,
        )
    )
    assert len(decoded) == 1  # web3 mendekodenya…
    assert app.verifier._matching_transfer(  # …dan gerbang tetap menolaknya
        receipt(logs=[transfer_log(token=OTHER_TOKEN, to=PAY_TO, value=AMOUNT * 99)])
    ) is None


def test_unknown_tx_hash_is_refused():
    app = make_app(receipts={})
    status, _, body = app.handle_register(auth(TX_OK), BODY)
    assert status == 402
    assert body["reason"] == px.REASON_RECEIPT


def test_rpc_failure_fails_closed():
    class ExplodingEth(FakeEth):
        def get_transaction_receipt(self, transaction_hash):
            raise TimeoutError("RPC mati")

    w3 = FakeWeb3()
    w3.eth = ExplodingEth({})
    app = make_app(w3=w3)
    status, _, body = app.handle_register(auth(TX_OK), BODY)
    assert status == 402
    assert body["reason"] == px.REASON_RPC


def test_wrong_chain_fails_closed():
    app = make_app(receipts={TX_OK: good_receipt()}, chain_id=1)
    status, _, body = app.handle_register(auth(TX_OK), BODY)
    assert status == 402
    assert body["reason"] == px.REASON_WRONG_CHAIN
    # Receipt tidak pernah dibaca: chain yang salah ditolak lebih dulu.
    assert app.verifier.w3.eth.receipt_reads == []


def test_the_gate_never_signs_or_sends_anything():
    """RPC palsu meledak pada `send_raw_transaction`/`get_transaction_count`; tidak ada yang meledak."""
    app = make_app(receipts={TX_OK: good_receipt()})
    assert app.handle_register(auth(TX_OK), BODY)[0] == 200
    assert app.handle_register(None, BODY)[0] == 402


# ======================================================================
# Header pembayaran adalah input pihak ketiga
# ======================================================================


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Bearer sesuatu",
        "x402 tx=\"" + TX_OK + "\"",
        px.SCHEME,
        f"{px.SCHEME} tx=",
        f'{px.SCHEME} tx="0x123"',
        f'{px.SCHEME} tx="{TX_OK}z"',
        f'{px.SCHEME} tx="{"0x" + "zz" * 32}"',
        f'{px.SCHEME} tx="{TX_OK}" ' + "x" * px.MAX_AUTH_HEADER_CHARS,
    ],
)
def test_malformed_authorization_headers_get_402(header):
    app = make_app(receipts={TX_OK: good_receipt()})
    status, _, _ = app.handle_register(header, BODY)
    assert status == 402


def test_scheme_matching_is_case_insensitive():
    app = make_app(receipts={TX_OK: good_receipt()})
    status, _, _ = app.handle_register(f'{px.SCHEME.upper()} tx="{TX_OK}"', BODY)
    assert status == 200


def test_unquoted_parameter_value_is_accepted():
    app = make_app(receipts={TX_OK: good_receipt()})
    assert app.handle_register(f"{px.SCHEME} tx={TX_OK}", BODY)[0] == 200


def test_header_injection_via_config_is_impossible():
    with pytest.raises(px.PaymentConfigError):
        make_terms(realm="evil\r\nSet-Cookie: a=b").validate()
    with pytest.raises(px.PaymentConfigError):
        make_terms(pay_to='0x00" , realm="x').validate()
    with pytest.raises(px.PaymentConfigError):
        make_terms(amount=0).validate()


def test_challenge_response_never_echoes_client_text(serve_app):
    server = serve_app(make_app())
    payload = json.dumps({"job_id": 1, "note": "<script>MARKER</script>"}).encode()
    _, _, raw = server.request(
        "POST", px.REGISTER_PATH, payload, {"Authorization": f'{px.SCHEME} tx="MARKER"'}
    )
    assert b"MARKER" not in raw


def test_success_response_never_echoes_client_text():
    app = make_app(receipts={TX_OK: good_receipt()})
    payload = json.dumps({"job_id": 7, "note": "<script>MARKER</script>", "criteria": "MARKER"}).encode()
    status, _, body = app.handle_register(auth(TX_OK), payload)
    assert status == 200
    assert "MARKER" not in json.dumps(body)
    assert body["job_id"] == 7


# ======================================================================
# Badan permintaan
# ======================================================================


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"", "invalid_json"),
        (b"[]", "invalid_json"),
        (b'"421"', "invalid_json"),
        (b"\xff\xfe", "invalid_json"),
        (b"{}", "invalid_job_id"),
        (json.dumps({"job_id": "421"}).encode(), "invalid_job_id"),
        (json.dumps({"job_id": True}).encode(), "invalid_job_id"),
        (json.dumps({"job_id": -1}).encode(), "invalid_job_id"),
        (json.dumps({"job_id": 2**64}).encode(), "invalid_job_id"),
    ],
)
def test_bad_bodies_get_400_after_payment(payload, expected):
    app = make_app(receipts={TX_OK: good_receipt()})
    status, _, body = app.handle_register(auth(TX_OK), payload)
    assert status == 400
    assert body["error"] == expected


def test_oversized_body_is_refused_before_being_parsed(serve_app):
    server = serve_app(make_app(receipts={TX_OK: good_receipt()}))
    payload = b"{" + b"a" * (px.MAX_BODY_BYTES + 10) + b"}"
    status, _, raw = server.request("POST", px.REGISTER_PATH, payload, {"Authorization": auth(TX_OK)})
    assert status == 413
    assert json.loads(raw)["error"] == "body_too_large"


def test_payment_is_checked_before_the_body(serve_app):
    """Pemanggil yang belum membayar mendapat 402, bukan bocoran perilaku parser."""
    server = serve_app(make_app())
    status, _, raw = server.request("POST", px.REGISTER_PATH, b"{bukan json}")
    assert status == 402
    assert json.loads(raw)["reason"] == px.REASON_MISSING


# ======================================================================
# Permukaan HTTP
# ======================================================================


def test_other_paths_are_404(serve_app):
    server = serve_app(make_app())
    for path in ("/", "/jobs", "/jobs/register/x", "/admin"):
        status, _, _ = server.request("POST", path, BODY)
        assert status == 404, path


def test_get_on_the_register_path_is_405(serve_app):
    server = serve_app(make_app())
    status, headers, _ = server.request("GET", px.REGISTER_PATH)
    assert status == 405
    assert headers["Allow"] == "POST"


def test_query_string_does_not_bypass_the_route(serve_app):
    server = serve_app(make_app())
    status, headers, _ = server.request("POST", px.REGISTER_PATH + "?free=1", BODY)
    assert status == 402
    assert "WWW-Authenticate" in headers


def test_the_server_does_not_leak_its_python_version(serve_app):
    server = serve_app(make_app())
    _, headers, _ = server.request("POST", px.REGISTER_PATH, BODY)
    assert "Python" not in headers.get("Server", "")


def test_registrations_are_capped():
    app = make_app(demo_mode=True)
    for _ in range(px.MAX_REGISTRATIONS + 5):
        assert app.handle_register(f'{px.SCHEME} demo="true"', BODY)[0] == 200
    assert len(app.registrations) == px.MAX_REGISTRATIONS


# ======================================================================
# Konfigurasi & batas modul
# ======================================================================


def test_terms_come_from_env_then_dotenv_then_default(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "84532")
    monkeypatch.setenv("USDC_ADDRESS", TOKEN)
    monkeypatch.setenv("PAYMENT_PAY_TO", PAY_TO)
    monkeypatch.setenv("EVAL_FEE_UNITS", "250000")
    terms = px.terms_from_config()
    assert terms.amount == 250_000
    assert terms.asset == TOKEN
    assert terms.pay_to == PAY_TO
    assert terms.network == "eip155:84532"


def test_pay_to_default_is_the_agent_wallet_not_the_vault():
    """Vault terdeploy tidak punya `sweepToken`: token yang dikirim ke sana terkunci selamanya."""
    from agent.vault_client import DEFAULT_VAULT_ADDRESS

    assert px.DEFAULT_PAY_TO.lower() != DEFAULT_VAULT_ADDRESS.lower()
    assert px.DEFAULT_PAY_TO == "0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894"


def test_the_gate_has_no_path_into_memory():
    """Badan permintaan adalah teks pihak ketiga: tidak ada tulisan ke Sibyl dari modul ini."""
    import re

    source = pathlib.Path(px.__file__).read_text(encoding="utf-8")
    for forbidden in ("set_entity", "set_reference", "set_state", "write_event"):
        assert re.search(rf"\b{forbidden}\s*\(", source) is None, forbidden
    assert "MemoryClient" not in source


def test_no_module_in_the_agent_package_is_named_after_x402():
    package = pathlib.Path(px.__file__).parent
    assert [p.name for p in package.rglob("x402*")] == []


def test_the_module_docstring_denies_x402_compatibility():
    doc = px.__doc__ or ""
    assert "BUKAN x402" in doc
    assert "EIP-3009" in doc
    assert "transferWithAuthorization" in doc
