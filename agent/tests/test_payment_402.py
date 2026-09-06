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
import os
import pathlib
import socket
import threading
import time

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
    def __init__(self, app: px.RegisterApp, **kwargs) -> None:
        self.httpd = px.serve(app, "127.0.0.1", 0, **kwargs)
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

    def factory(app: px.RegisterApp, **kwargs) -> Server:
        server = Server(app, **kwargs)
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


# ======================================================================
# (1) SATU tx TIDAK BOLEH membayar dua job, TERMASUK lintas proses
#
# Bentuk kegagalan yang ditutup di sini persis yang terjadi saat `make demo` dan
# `python -m agent.payment_402` hidup bersamaan dengan `PAYMENT_LEDGER_PATH` yang sama:
# dua `PaymentLedger` atas SATU berkas, masing-masing memakai himpunan hash di memorinya
# sendiri, sehingga hash yang sama membayar dua job. Dua objek `PaymentLedger` adalah model
# yang setia untuk itu — `flock` melekat pada open file description, jadi dua `open()`
# terpisah saling mengunci meski berada di dalam satu proses.
# ======================================================================


def test_two_ledgers_over_one_file_cannot_both_claim_one_hash(tmp_path):
    path = tmp_path / "payments-402.jsonl"
    first = px.PaymentLedger(path)
    second = px.PaymentLedger(path)  # "proses kedua": membaca berkas yang sama saat start

    assert first.claim(TX_OK, 100) is True
    assert second.claim(TX_OK, 200) is False

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [r["tx"] for r in records] == [TX_OK]
    assert [r["job_id"] for r in records] == [100]


def test_two_servers_sharing_one_ledger_file_take_the_payment_only_once(tmp_path):
    """Reproduksi laporan: 200 untuk job 100 DAN 200 untuk job 200 dari satu hash."""
    path = tmp_path / "payments-402.jsonl"
    demo = make_app(receipts={TX_OK: good_receipt()}, ledger=px.PaymentLedger(path))
    standalone = make_app(receipts={TX_OK: good_receipt()}, ledger=px.PaymentLedger(path))

    first = demo.handle_register(auth(TX_OK), json.dumps({"job_id": 100}).encode())
    second = standalone.handle_register(auth(TX_OK), json.dumps({"job_id": 200}).encode())

    assert first[0] == 200
    assert second[0] == 402
    assert second[2]["reason"] == px.REASON_REPLAY

    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1


def test_concurrent_claims_from_two_ledger_objects_yield_exactly_one_winner(tmp_path):
    """Bukan sekadar muat-ulang: klaim yang benar-benar bersamaan pun hanya boleh satu menang."""
    path = tmp_path / "payments-402.jsonl"
    ledgers = [px.PaymentLedger(path), px.PaymentLedger(path)]
    results: list[bool] = []
    guard = threading.Lock()
    start = threading.Barrier(8)

    def worker(index: int) -> None:
        start.wait()
        won = ledgers[index % 2].claim(TX_OK, index)
        with guard:
            results.append(won)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert results.count(True) == 1
    assert results.count(False) == 7
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1


def test_a_claim_in_flight_blocks_the_other_process_until_it_lands(tmp_path):
    """Muat-ulang saja TIDAK cukup, dan tes 8-thread di atas terlalu jarang menabrak
    jendelanya untuk membuktikan itu. Di sini jendelanya dilebarkan sengaja: buku pertama
    memuat ulang dengan lambat SAMBIL memegang kunci berkas. Tanpa `flock`, buku kedua
    membaca berkas yang masih kosong dan ikut menang — satu tx membayar dua job.
    """
    path = tmp_path / "payments-402.jsonl"
    slow = px.PaymentLedger(path)
    fast = px.PaymentLedger(path)

    real_load = px.PaymentLedger._load

    def slow_load(target):
        # Membaca DULU lalu tertidur: jendelanya ada di antara "membaca" dan "menulis", persis
        # tempat proses kedua menyusup bila tidak ada kunci berkas.
        loaded = real_load(target)
        time.sleep(0.5)
        return loaded

    slow._load = slow_load  # atribut instans menutupi staticmethod-nya
    outcome: dict[str, bool] = {}

    thread = threading.Thread(target=lambda: outcome.__setitem__("slow", slow.claim(TX_OK, 100)))
    thread.start()
    time.sleep(0.2)  # `slow` sudah memegang kunci berkas dan sedang memuat ulang
    outcome["fast"] = fast.claim(TX_OK, 200)
    thread.join(timeout=10)

    assert list(outcome.values()).count(True) == 1, outcome
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1


def test_the_ledger_normalises_hash_case_at_its_own_boundary(tmp_path):
    """`PaymentLedger` adalah API publik: pemanggil baru yang tidak menormalkan hash
    tidak boleh bisa membayar dua kali, tanpa bergantung pada normalisasi di `verify()`.

    Diuji pada KEDUA bentuk buku — dengan berkas dan tanpa berkas — karena normalisasi
    keduanya lahir di tempat berbeda (`_load` vs `claim`); satu bentuk saja membuat pencabutan
    salah satunya lolos tanpa satu tes pun merah.
    """
    ledger = px.PaymentLedger(tmp_path / "payments-402.jsonl")
    assert ledger.claim("0x" + "AA" * 32, 1) is True
    assert ledger.claim("0x" + "aa" * 32, 2) is False
    assert ledger.is_used("0x" + "Aa" * 32) is True

    in_memory = px.PaymentLedger()
    assert in_memory.claim("0x" + "AA" * 32, 1) is True
    assert in_memory.claim("0x" + "aa" * 32, 2) is False
    assert in_memory.is_used("0x" + "Aa" * 32) is True


def test_every_ledger_record_is_flushed_to_disk(tmp_path, monkeypatch):
    """Tanpa `fsync`, baris terakhir bisa hilang saat mati mendadak → hash itu membayar LAGI."""
    synced: list[int] = []
    real_fsync = os.fsync

    def spy(fd: int) -> None:
        synced.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(px.os, "fsync", spy)
    ledger = px.PaymentLedger(tmp_path / "payments-402.jsonl")
    assert ledger.claim(TX_OK, 7) is True
    assert synced, "catatan buku ditulis tanpa fsync"


# ======================================================================
# (2) Buku yang tidak bisa ditulis: 503 yang sopan, tanpa membakar pembayaran
# ======================================================================


def sabotage_ledger_dir(directory: pathlib.Path) -> None:
    """Ganti direktori buku dengan BERKAS biasa: setiap tulisan/kunci di bawahnya jadi OSError.

    Dipilih ketimbang `chmod 0444` supaya tesnya tetap merah saat dijalankan sebagai root.
    """
    for child in directory.iterdir():
        child.unlink()
    directory.rmdir()
    directory.write_text("bukan direktori", encoding="utf-8")


def repair_ledger_dir(directory: pathlib.Path) -> None:
    directory.unlink()
    directory.mkdir()


def test_a_ledger_that_cannot_be_written_answers_503_and_does_not_burn_the_payment(tmp_path):
    book = tmp_path / "book"
    book.mkdir()
    app = make_app(receipts={TX_OK: good_receipt()}, ledger=px.PaymentLedger(book / "payments.jsonl"))

    sabotage_ledger_dir(book)
    status, headers, body = app.handle_register(auth(TX_OK), BODY)

    assert status == 503
    rendered = json.dumps(body) + json.dumps(headers)
    assert str(tmp_path) not in rendered and "book" not in rendered  # path buku TIDAK bocor
    assert app.verifier.ledger.is_used(TX_OK) is False  # pembayaran BELUM terbakar

    repair_ledger_dir(book)
    assert app.handle_register(auth(TX_OK), BODY)[0] == 200  # klien yang sudah membayar bisa mengulang


def test_a_broken_ledger_does_not_drop_the_connection(serve_app, tmp_path):
    book = tmp_path / "book"
    book.mkdir()
    app = make_app(receipts={TX_OK: good_receipt()}, ledger=px.PaymentLedger(book / "payments.jsonl"))
    server = serve_app(app)
    sabotage_ledger_dir(book)

    status, _, raw = server.request("POST", px.REGISTER_PATH, BODY, {"Authorization": auth(TX_OK)})

    assert status == 503
    assert json.loads(raw)["error"] == px.REASON_LEDGER
    assert str(tmp_path) not in raw.decode()


def test_an_unexpected_failure_answers_500_without_leaking_anything(serve_app):
    app = make_app(demo_mode=True)

    def explode(authorization, body_bytes):
        raise RuntimeError(f"rahasia di {pathlib.Path(px.__file__)}")

    app.handle_register = explode
    server = serve_app(app)

    status, _, raw = server.request("POST", px.REGISTER_PATH, BODY, {"Authorization": auth(TX_OK)})

    assert status == 500
    assert json.loads(raw) == {"error": "internal_error"}


# ======================================================================
# (3) Slowloris: koneksi yang menggantung tidak boleh memarkir thread selamanya
# ======================================================================


def raw_post(port: int, *, content_length: int, sent: bytes, headers: str = "") -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    request = (
        f"POST {px.REGISTER_PATH} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        f"Content-Length: {content_length}\r\n{headers}\r\n"
    ).encode()
    sock.sendall(request + sent)
    return sock


def test_a_stalled_body_does_not_park_a_thread_forever(serve_app):
    server = serve_app(make_app(), timeout=0.5)
    sock = raw_post(server.port, content_length=8000, sent=b"{")
    try:
        started = time.monotonic()
        sock.settimeout(6)
        data = sock.recv(4096)  # server MENUTUP (atau menjawab) sendiri; tanpa timeout ini menggantung
        elapsed = time.monotonic() - started
    finally:
        sock.close()
    assert elapsed < 5, "koneksi menggantung: thread terparkir"
    assert b"HTTP/1.1 200" not in data


def test_the_handler_has_a_socket_timeout_by_default():
    assert px.RegisterHandler.timeout is not None
    assert 0 < px.RegisterHandler.timeout <= 60


def test_the_server_caps_the_number_of_live_connections(serve_app):
    app = make_app(demo_mode=True)
    entered = threading.Event()
    release = threading.Event()
    original = app.handle_register

    def blocking(authorization, body_bytes):
        entered.set()
        release.wait(10)
        return original(authorization, body_bytes)

    app.handle_register = blocking
    server = serve_app(app, max_connections=1, timeout=10)
    first = raw_post(
        server.port,
        content_length=len(BODY),
        sent=BODY,
        headers=f'Authorization: {px.SCHEME} demo="true"\r\n',
    )
    try:
        assert entered.wait(5), "permintaan pertama tidak pernah sampai ke handler"
        second = socket.create_connection(("127.0.0.1", server.port), timeout=5)
        try:
            second.settimeout(5)
            assert second.recv(1024) == b""  # ditolak plafon: ditutup tanpa dilayani
        finally:
            second.close()
    finally:
        release.set()
        first.close()


# ======================================================================
# (4) Rate limit: permintaan tak berbayar tidak boleh mengamplifikasi RPC kita
# ======================================================================


def test_unpaid_requests_cannot_amplify_rpc_reads(serve_app):
    w3 = FakeWeb3({})
    app = make_app(w3=w3)
    server = serve_app(app, limiter=px.RateLimiter(3, 60.0))

    codes = []
    for index in range(10):
        status, headers, raw = server.request(
            "POST",
            px.REGISTER_PATH,
            BODY,
            {"Authorization": auth("0x" + f"{index:064x}")},
        )
        codes.append(status)
        if status == 429:
            assert int(headers["Retry-After"]) >= 1
            assert json.loads(raw)["error"] == px.REASON_RATE_LIMITED

    assert codes[:3] == [402, 402, 402]
    assert set(codes[3:]) == {429}
    assert len(w3.eth.receipt_reads) == 3  # NOL amplifikasi sesudah plafon


def test_the_rate_limiter_forgets_after_its_window():
    now = [1000.0]
    limiter = px.RateLimiter(2, 10.0, clock=lambda: now[0])
    assert limiter.check("a") is None
    assert limiter.check("a") is None
    wait = limiter.check("a")
    assert wait is not None and 0 < wait <= 10
    now[0] += 10.1
    assert limiter.check("a") is None


def test_the_rate_limiter_counts_clients_separately_and_bounds_its_memory():
    limiter = px.RateLimiter(1, 60.0, max_keys=8)
    assert limiter.check("a") is None
    assert limiter.check("b") is None
    assert limiter.check("a") is not None
    for index in range(50):
        limiter.check(f"klien-{index}")
    assert limiter.tracked_keys() <= 8


# ======================================================================
# (5) PENGAKUAN: pembayaran adalah kredensial bearer, dan catatan buku bisa hilang
# ======================================================================


def test_a_transfer_paid_by_somebody_else_still_pays(serve_app):
    """Perilaku yang DIAKUI docstring, dikunci di sini supaya tidak diam-diam diklaim lain:
    `from` TIDAK diperiksa, jadi siapa pun yang mengutip hash transfer orang lain lolos."""
    app = make_app(
        receipts={TX_OK: receipt(logs=[transfer_log(token=TOKEN, to=PAY_TO, value=AMOUNT, sender=STRANGER)])}
    )
    assert app.handle_register(auth(TX_OK), BODY)[0] == 200


def test_a_transfer_older_than_the_configured_block_floor_is_refused():
    """Lantai blok opsional: transfer purba ke `payTo` tidak boleh berlaku selamanya."""
    w3 = FakeWeb3({TX_OK: good_receipt() | {"blockNumber": 46_400_000}})
    verifier = px.PaymentVerifier(
        w3, make_terms(), CHAIN_ID, px.PaymentLedger(), min_block=46_500_000
    )
    result = verifier.verify(auth(TX_OK))
    assert result.ok is False
    assert result.reason == px.REASON_TOO_OLD


def test_the_block_floor_accepts_a_transfer_at_or_above_it():
    w3 = FakeWeb3({TX_OK: good_receipt() | {"blockNumber": 46_500_000}})
    verifier = px.PaymentVerifier(
        w3, make_terms(), CHAIN_ID, px.PaymentLedger(), min_block=46_500_000
    )
    assert verifier.verify(auth(TX_OK)).ok is True


def test_a_receipt_without_a_block_number_is_refused_when_a_floor_is_set():
    w3 = FakeWeb3({TX_OK: good_receipt()})
    verifier = px.PaymentVerifier(w3, make_terms(), CHAIN_ID, px.PaymentLedger(), min_block=1)
    result = verifier.verify(auth(TX_OK))
    assert result.ok is False
    assert result.reason == px.REASON_RECEIPT


def test_the_block_floor_is_off_by_default():
    assert px.PaymentVerifier(FakeWeb3(), make_terms(), CHAIN_ID, px.PaymentLedger()).min_block == 0


def test_the_docstring_admits_the_payment_is_a_bearer_credential():
    doc = (px.__doc__ or "").lower()
    assert "bearer" in doc
    assert "nonce" in doc
    assert "front-running" in doc or "mendahului" in doc


def test_the_docstring_admits_ledger_records_can_be_lost():
    doc = (px.__doc__ or "").lower()
    assert "dihapus" in doc
    assert "fsync" in doc
