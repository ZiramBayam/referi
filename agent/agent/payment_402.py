"""Gerbang HTTP 402 buatan sendiri di depan `POST /jobs/register` (task 2.6, ADR-010).

INI BUKAN x402, DAN TIDAK KOMPATIBEL DENGANNYA. Nama modul sengaja TIDAK memakai
`x402_server.py` seperti tertulis di `docs/spec.md` §6 / TASKS 2.6: nama file adalah urusan
internal, tetapi proyek ini sudah tiga kali tergigit oleh nama/komentar yang mengklaim lebih
dari kenyataan, dan `grep -ri x402 agent/` yang menemukan sebuah file bernama `x402_server.py`
adalah cara paling murah untuk melahirkan klaim "kami mengimplementasikan x402" yang justru
DILARANG ADR-010 keputusan 4. Modul ini menggantikan nama itu; isinya sama persis dengan yang
diminta spec §6 baris 164. Angka `402` di nama modul adalah status HTTP yang benar-benar
dikirim (RFC 9110 §15.5.3), bukan merek protokol.

Alasan teknis ia tidak bisa menjadi x402, diverifikasi (bukan diingat) dan dicatat ADR-010:
skema `exact` EVM milik x402 berjalan di atas EIP-3009 `transferWithAuthorization`, sedangkan
token escrow ACP `0xECc22a8F6fD62388498fBa19813E214605a2BDb3` TIDAK punya fungsi itu — pada
bytecode terdeploy, selector `transferWithAuthorization` (`0xe3ee160e`) dan `DOMAIN_SEPARATOR`
(`0x3644e515`) NOL kemunculan, dengan kontrol positif `transfer` (`0xa9059cbb`) = 1. Klien x402
sungguhan mengirim otorisasi bertanda tangan di header `X-PAYMENT`; endpoint ini tidak
memahaminya dan tidak berpura-pura memahaminya. Karena itu nama skema di `WWW-Authenticate`
DILARANG `x402` atau turunannya (ADR-010 keputusan 3(iv)) — dijaga tes, bukan hanya komentar.

Bentuk kabelnya (ADR-010 keputusan 3):
  1. Tanpa pembayaran sah → **402** + `WWW-Authenticate: OnchainPayment realm=…, network=…,
     asset=…, payTo=…, amount=… (unit terkecil), nonce=…`, dan badan JSON yang mengulang
     parameter yang sama supaya terbaca manusia saat demo.
  2. Klien transfer token escrow ke `payTo` di chain, lalu MENGULANG permintaan dengan
     `Authorization: OnchainPayment tx="0x<64 hex>"`.
  3. Verifikasi **MEMBACA CHAIN**, bukan mempercayai header: `receipt.status == 1`, ada log
     `Transfer` yang dipancarkan **alamat token escrow**, `to == payTo`, `value >= amount`, dan
     hash tx BELUM PERNAH DIPAKAI.

Empat hal yang gampang salah dan karena itu ditulis eksplisit:

  (a) `ContractEvent.process_receipt` **TIDAK menyaring alamat kontrak** (web3 7.16.0, diukur:
      log `Transfer` dari `0x036CbD53…` tetap terdekode oleh kontrak `0xECc22a8F…`). Tanpa
      pembandingan `log["address"]` sendiri, siapa pun bisa men-deploy token sampah, mengirim
      "1.000.000" ke `payTo`, dan lolos. Pembandingannya ada di `_matching_transfer()` dan
      dikunci tes.
  (b) `nonce` di tantangan adalah **korelasi/logging saja**. Transfer ERC-20 polos tidak
      membawa memo, jadi tidak ada cara mengikat nonce ke pembayaran on-chain. Yang benar-benar
      mencegah replay adalah BUKU HASH TX (`PaymentLedger`) — di jalur x402 resmi pekerjaan itu
      milik fasilitator; di jalur kita tidak ada yang mengerjakannya kecuali kode ini.
  (c) Buku hash tx menjaga replay **di dalam satu proses dan lintas restart** (file JSON Lines).
      Ia TIDAK memakai kunci file, jadi DUA proses server yang berbagi file yang sama tidak
      saling menjaga. Jangan mengklaim lebih dari itu; jalankan satu proses.
  (d) Fee ini **bukan pengaman ekonomi**. Token escrow Base Sepolia punya `mint()` tanpa
      kontrol akses (docs/versions.md), jadi siapa pun bisa mencetak sendiri ongkosnya. Ia
      penghalang spam + peragaan alur "fee di muka" (spec §5 "Perbaikan insentif fee"), titik.

Batas yang dipegang modul ini:
  - **NOL transaksi.** Endpoint ini hanya MEMBACA chain (`eth_getTransactionReceipt`,
    `eth_chainId`). Tidak ada kunci privat yang dimuat di sini, tidak ada tx yang dibangun.
  - **NOL tulisan ke memori.** Badan permintaan adalah teks pihak ketiga yang tidak dipercaya;
    tidak ada satu pun jalur dari sini ke Sibyl (`set_entity`/`set_state`/`write_event`) — itu
    aturan yang sama yang membuat `checks/*` menjadi satu-satunya sumber tulisan memori.
  - Respons 200 hanya memantulkan `job_id` (integer yang sudah divalidasi) dan metadata
    pembayaran; TIDAK ada teks pihak ketiga yang dipantulkan kembali ke klien/UI.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.logs import DISCARD

from agent.vault_client import (
    DEFAULT_CHAIN_ID,
    DEFAULT_RPC_URL,
    agent_root,
    config_value,
)

log = logging.getLogger("payment_402")

# ----------------------------------------------------------------------
# Konstanta protokol lokal
# ----------------------------------------------------------------------

# Nama skema `WWW-Authenticate`. ADR-010 keputusan 3(iv): DILARANG `x402` atau turunannya,
# supaya klien x402 sungguhan tidak pernah menyangka endpoint ini bicara protokol mereka.
# Dijaga `test_scheme_name_is_not_x402_or_a_derivative`.
SCHEME = "OnchainPayment"

REGISTER_PATH = "/jobs/register"
DEFAULT_REALM = "evaluator-jobs-register"

# Jaringan & aset — docs/versions.md. `network` memakai bentuk CAIP-2 (`eip155:<chainId>`)
# karena itu penamaan jaringan yang lazim, bukan karena kompatibilitas x402.
DEFAULT_TOKEN_ADDRESS = "0xECc22a8F6fD62388498fBa19813E214605a2BDb3"
TOKEN_DECIMALS = 6

# Penerima fee = WALLET AGEN (EOA), BUKAN vault. Vault terdeploy TIDAK punya `sweepToken`
# (selector `0x258836fe` NOL kemunculan di bytecodenya, docs/versions.md), jadi token yang
# dikirim ke vault akan terkunci PERMANEN. Default yang salah di sini = uang client hilang.
DEFAULT_PAY_TO = "0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894"

# 1,000000 token (6 desimal) per pendaftaran job. Unit TERKECIL, seperti bunyi ADR-010.
DEFAULT_AMOUNT_UNITS = 1_000_000

DEFAULT_HOST = "127.0.0.1"  # sengaja loopback: server ini tidak punya autentikasi lain
DEFAULT_PORT = 8000  # cocok dengan NEXT_PUBLIC_AGENT_API di .env.example

DEFAULT_LEDGER_PATH = "./data/payments-402.jsonl"

# Fragmen ABI ERC-20 seperlunya. Bentuk `Transfer(address,address,uint256)` adalah standar
# ERC-20; topic0-nya `0xddf252ad…b3ef`.
ERC20_TRANSFER_ABI: list[dict[str, Any]] = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]

# Batas keras atas input pihak ketiga.
MAX_BODY_BYTES = 8 * 1024
MAX_AUTH_HEADER_CHARS = 512
MAX_REGISTRATIONS = 1000
MAX_JOB_ID = 2**64 - 1

# Kode alasan. Nilainya masuk ke badan JSON, jadi ia bagian dari kontrak HTTP modul ini.
REASON_OK = "ok"
REASON_DEMO = "demo_bypass"
REASON_MISSING = "payment_required"
REASON_SCHEME = "unsupported_scheme"
REASON_MALFORMED = "malformed_payment_header"
REASON_REPLAY = "payment_already_used"
REASON_RECEIPT = "receipt_not_found"
REASON_TX_FAILED = "transaction_failed"
REASON_NO_TRANSFER = "no_matching_transfer"
REASON_WRONG_CHAIN = "wrong_chain"
REASON_RPC = "rpc_unavailable"

_TX_HASH_RE = re.compile(r"\A0x[0-9a-fA-F]{64}\Z")
_AUTH_PARAM_RE = re.compile(r'([A-Za-z0-9_\-]+)\s*=\s*(?:"([^"\\\r\n]*)"|([^,\s"]+))')
# Nilai yang boleh masuk ke header respons. CR/LF mustahil lolos → tidak ada injeksi header.
_SAFE_HEADER_VALUE_RE = re.compile(r"\A[A-Za-z0-9:_.\-]+\Z")
_DEMO_TRUE = frozenset({"1", "true", "yes", "demo"})


class PaymentConfigError(RuntimeError):
    """Konfigurasi gerbang tidak sah (alamat/jumlah/realm). Fail-closed saat start."""


# ----------------------------------------------------------------------
# Syarat pembayaran
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentTerms:
    """Parameter tantangan 402. Semua nilai WAJIB aman untuk header (dijaga `validate()`)."""

    realm: str
    network: str
    asset: str
    pay_to: str
    amount: int
    decimals: int = TOKEN_DECIMALS

    def validate(self) -> PaymentTerms:
        for name, value in (("realm", self.realm), ("network", self.network)):
            if not _SAFE_HEADER_VALUE_RE.match(value):
                raise PaymentConfigError(f"{name} memuat karakter yang tidak boleh masuk header: {value!r}")
        if self.amount <= 0:
            raise PaymentConfigError(f"amount harus > 0 (unit terkecil), bukan {self.amount}")
        for name, value in (("asset", self.asset), ("payTo", self.pay_to)):
            if not _SAFE_HEADER_VALUE_RE.match(value):
                raise PaymentConfigError(f"{name} bukan alamat yang sah: {value!r}")
        return self

    def as_params(self, nonce: str) -> dict[str, str]:
        """Parameter tantangan — URUTAN INI dipakai header maupun badan JSON."""
        return {
            "realm": self.realm,
            "network": self.network,
            "asset": self.asset,
            "payTo": self.pay_to,
            "amount": str(self.amount),
            "nonce": nonce,
        }

    def challenge_header(self, nonce: str) -> str:
        params = self.as_params(nonce)
        for key, value in params.items():
            if not _SAFE_HEADER_VALUE_RE.match(value):
                raise PaymentConfigError(f"parameter tantangan {key} tidak aman untuk header: {value!r}")
        rendered = ", ".join(f'{key}="{value}"' for key, value in params.items())
        return f"{SCHEME} {rendered}"


def terms_from_config() -> PaymentTerms:
    """Syarat pembayaran dari env → `.env` repo → default (`vault_client.config_value`)."""
    chain_id = int(config_value("CHAIN_ID", str(DEFAULT_CHAIN_ID)))
    asset = Web3.to_checksum_address(config_value("USDC_ADDRESS", DEFAULT_TOKEN_ADDRESS))
    pay_to = Web3.to_checksum_address(config_value("PAYMENT_PAY_TO", DEFAULT_PAY_TO))
    amount = int(config_value("EVAL_FEE_UNITS", str(DEFAULT_AMOUNT_UNITS)))
    realm = config_value("PAYMENT_REALM", DEFAULT_REALM)
    return PaymentTerms(
        realm=realm,
        network=f"eip155:{chain_id}",
        asset=asset,
        pay_to=pay_to,
        amount=amount,
    ).validate()


def demo_mode_enabled() -> bool:
    return config_value("DEMO_MODE", "false").strip().lower() in _DEMO_TRUE


def ledger_path_from_config() -> Path:
    raw = Path(config_value("PAYMENT_LEDGER_PATH", DEFAULT_LEDGER_PATH)).expanduser()
    return raw if raw.is_absolute() else (agent_root() / raw).resolve()


# ----------------------------------------------------------------------
# Buku hash tx — SATU-SATUNYA penjaga replay
# ----------------------------------------------------------------------


class PaymentLedger:
    """Himpunan hash tx yang SUDAH dipakai, persisten sebagai JSON Lines.

    `claim()` adalah operasi cek-dan-tulis di bawah satu lock: dua permintaan bersamaan dengan
    hash yang sama TIDAK bisa dua-duanya menang. Batasnya jujur: lock ini milik satu proses.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._used: set[str] = set()
        if path is not None:
            self._used = self._load(path)

    @staticmethod
    def _load(path: Path) -> set[str]:
        used: set[str] = set()
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return used
        except OSError as exc:  # buku tidak terbaca → fail-closed di pemanggil
            raise PaymentConfigError(f"buku pembayaran tidak terbaca: {path} ({exc})") from exc
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Baris rusak DIABAIKAN untuk pembacaan, tetapi tidak boleh menghapus jejak:
                # file hanya ditambah (append), tidak pernah ditulis ulang.
                log.warning("baris buku pembayaran rusak diabaikan")
                continue
            tx = record.get("tx") if isinstance(record, dict) else None
            if isinstance(tx, str) and _TX_HASH_RE.match(tx):
                used.add(tx.lower())
        return used

    def is_used(self, tx_hash: str) -> bool:
        with self._lock:
            return tx_hash.lower() in self._used

    def claim(self, tx_hash: str, job_id: int) -> bool:
        """True bila hash ini BARU dan berhasil diklaim; False bila sudah pernah dipakai."""
        key = tx_hash.lower()
        with self._lock:
            if key in self._used:
                return False
            self._used.add(key)
            if self._path is not None:
                self._append(key, job_id)
            return True

    def _append(self, tx_hash: str, job_id: int) -> None:
        assert self._path is not None
        record = json.dumps({"tx": tx_hash, "job_id": job_id, "at": int(time.time())}, sort_keys=True)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(record + "\n")
            handle.flush()


# ----------------------------------------------------------------------
# Verifikasi pembayaran — MEMBACA CHAIN
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentResult:
    ok: bool
    reason: str
    tx_hash: str | None = None
    value: int | None = None
    demo: bool = False


def parse_authorization(header: str | None) -> tuple[str, dict[str, str]] | None:
    """`Authorization: <Scheme> k="v", k2=v2` → `(scheme, params)`; `None` bila tidak terbaca.

    Input pihak ketiga: panjangnya dibatasi dan hanya parameter berbentuk `kunci=nilai` yang
    diambil. Nilai TIDAK pernah dipantulkan ke header respons.
    """
    if not header:
        return None
    header = header.strip()
    if len(header) > MAX_AUTH_HEADER_CHARS:
        return None
    parts = header.split(None, 1)
    scheme = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    params: dict[str, str] = {}
    for match in _AUTH_PARAM_RE.finditer(rest):
        key = match.group(1).lower()
        value = match.group(2) if match.group(2) is not None else match.group(3)
        params.setdefault(key, value or "")
    return scheme, params


class PaymentVerifier:
    """Memverifikasi klaim pembayaran dengan MEMBACA receipt di chain.

    `w3` cukup harus punya `eth.contract`, `eth.get_transaction_receipt`, dan `eth.chain_id`;
    tes memakai RPC palsu sehingga seluruh berkas tes ini offline. Verifier ini TIDAK PERNAH
    membangun atau mengirim transaksi dan tidak pernah memuat kunci privat.
    """

    def __init__(
        self,
        w3: Any,
        terms: PaymentTerms,
        chain_id: int,
        ledger: PaymentLedger,
        *,
        demo_mode: bool = False,
    ) -> None:
        self.w3 = w3
        self.terms = terms.validate()
        self.chain_id = chain_id
        self.ledger = ledger
        self.demo_mode = demo_mode
        self._token = w3.eth.contract(address=Web3.to_checksum_address(terms.asset), abi=ERC20_TRANSFER_ABI)
        self._chain_id_verified = False

    # -- langkah-langkah ------------------------------------------------

    def _check_chain(self) -> str | None:
        """`None` bila chain cocok; kode alasan bila tidak. Dibaca sekali lalu di-cache."""
        if self._chain_id_verified:
            return None
        try:
            onchain = int(self.w3.eth.chain_id)
        except Exception as exc:  # noqa: BLE001 — RPC apa pun yang gagal = fail-closed
            log.warning("chainId tidak terbaca: %s", type(exc).__name__)
            return REASON_RPC
        if onchain != self.chain_id:
            log.error(
                "chainId RPC %d != CHAIN_ID %d — gerbang menolak semua pembayaran",
                onchain,
                self.chain_id,
            )
            return REASON_WRONG_CHAIN
        self._chain_id_verified = True
        return None

    def _matching_transfer(self, receipt: Any) -> int | None:
        """Nilai transfer PERTAMA yang memenuhi syarat, atau `None`.

        Tiga syaratnya diperiksa SENDIRI, terutama alamat pemancar log: `process_receipt`
        web3 7.16.0 mendekode log `Transfer` dari kontrak MANA PUN (diukur), jadi tanpa
        pembandingan ini token sampah bisa membayar tagihan kita.
        """
        try:
            events = self._token.events.Transfer().process_receipt(receipt, errors=DISCARD)
        except Exception as exc:  # noqa: BLE001 — receipt aneh tidak boleh menjatuhkan server
            log.warning("log receipt tidak terdekode: %s", type(exc).__name__)
            return None
        for event in events:
            try:
                emitter = Web3.to_checksum_address(event["address"])
                recipient = Web3.to_checksum_address(event["args"]["to"])
                value = int(event["args"]["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if emitter != self.terms.asset:
                continue  # token lain — termasuk token sampah yang sengaja di-deploy
            if recipient != self.terms.pay_to:
                continue
            if value < self.terms.amount:
                continue
            return value
        return None

    # -- muka publik ----------------------------------------------------

    def verify(self, authorization: str | None) -> PaymentResult:
        parsed = parse_authorization(authorization)
        if parsed is None:
            return PaymentResult(False, REASON_MISSING)
        scheme, params = parsed
        if scheme.lower() != SCHEME.lower():
            return PaymentResult(False, REASON_SCHEME)

        raw_tx = params.get("tx", "").strip()
        if not raw_tx:
            # Jalur DEMO: hanya sah bila DEMO_MODE hidup DAN klien tidak mengklaim tx apa pun.
            # Klaim tx yang cacat TIDAK boleh diselamatkan oleh mode demo.
            if self.demo_mode and params.get("demo", "").strip().lower() in _DEMO_TRUE:
                log.warning("DEMO_MODE: header pembayaran dummy diterima — TIDAK ada verifikasi on-chain")
                return PaymentResult(True, REASON_DEMO, demo=True)
            return PaymentResult(False, REASON_MALFORMED)

        if not _TX_HASH_RE.match(raw_tx):
            return PaymentResult(False, REASON_MALFORMED)
        tx_hash = raw_tx.lower()

        if self.ledger.is_used(tx_hash):
            log.warning("pembayaran ditolak: hash tx sudah pernah dipakai")
            return PaymentResult(False, REASON_REPLAY, tx_hash=tx_hash)

        chain_problem = self._check_chain()
        if chain_problem is not None:
            return PaymentResult(False, chain_problem, tx_hash=tx_hash)

        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return PaymentResult(False, REASON_RECEIPT, tx_hash=tx_hash)
        except Exception as exc:  # noqa: BLE001 — RPC gagal = tolak, bukan luluskan
            log.warning("receipt tidak terbaca: %s", type(exc).__name__)
            return PaymentResult(False, REASON_RPC, tx_hash=tx_hash)
        if receipt is None:
            return PaymentResult(False, REASON_RECEIPT, tx_hash=tx_hash)

        try:
            status = int(receipt["status"])
        except (KeyError, TypeError, ValueError):
            return PaymentResult(False, REASON_RECEIPT, tx_hash=tx_hash)
        if status != 1:
            return PaymentResult(False, REASON_TX_FAILED, tx_hash=tx_hash)

        value = self._matching_transfer(receipt)
        if value is None:
            return PaymentResult(False, REASON_NO_TRANSFER, tx_hash=tx_hash)
        return PaymentResult(True, REASON_OK, tx_hash=tx_hash, value=value)


# ----------------------------------------------------------------------
# Aplikasi HTTP
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Registration:
    job_id: int
    tx_hash: str | None
    demo: bool
    at: int


class RegisterApp:
    """Logika endpoint, terpisah dari `http.server` supaya bisa diuji tanpa soket."""

    def __init__(self, verifier: PaymentVerifier, *, demo_mode: bool = False) -> None:
        self.verifier = verifier
        self.demo_mode = demo_mode
        self._lock = threading.Lock()
        self.registrations: list[Registration] = []

    # -- respons --------------------------------------------------------

    def challenge(self, reason: str) -> tuple[int, dict[str, str], dict[str, Any]]:
        nonce = secrets.token_hex(16)
        terms = self.verifier.terms
        params = terms.as_params(nonce)
        headers = {"WWW-Authenticate": terms.challenge_header(nonce)}
        body: dict[str, Any] = {
            "error": "payment_required",
            "reason": reason,
            "scheme": SCHEME,
            **params,
            "amount_decimals": terms.decimals,
            "protocol": "402 buatan sendiri (ADR-010) — BUKAN x402",
            "how": (
                f'transfer >= {terms.amount} unit token {terms.asset} ke {terms.pay_to} di '
                f'{terms.network}, lalu ulangi permintaan dengan header '
                f'Authorization: {SCHEME} tx="0x<hash 64 hex>"'
            ),
        }
        if self.demo_mode:
            body["demo_hint"] = (
                f'DEMO_MODE aktif: Authorization: {SCHEME} demo="true" diterima tanpa pembayaran'
            )
        return HTTPStatus.PAYMENT_REQUIRED, headers, body

    # -- jalur permintaan ------------------------------------------------

    def handle_register(
        self, authorization: str | None, body_bytes: bytes
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        """PEMBAYARAN DULU, badan permintaan belakangan.

        Urutannya disengaja: penantang 402 tidak boleh membocorkan perilaku parser badan
        kepada pemanggil yang belum membayar. Hash tx baru DIKLAIM saat permintaan benar-benar
        berhasil, sehingga badan yang cacat tidak membakar pembayaran yang sah.
        """
        result = self.verifier.verify(authorization)
        if not result.ok:
            return self.challenge(result.reason)

        parsed = _parse_body(body_bytes)
        if isinstance(parsed, str):
            return HTTPStatus.BAD_REQUEST, {}, {"error": parsed}
        job_id = parsed

        if result.tx_hash is not None:
            if not self.verifier.ledger.claim(result.tx_hash, job_id):
                # Balapan: hash yang sama menang di permintaan lain sesudah `verify()`.
                return self.challenge(REASON_REPLAY)

        with self._lock:
            if len(self.registrations) >= MAX_REGISTRATIONS:
                self.registrations.pop(0)
            self.registrations.append(
                Registration(job_id=job_id, tx_hash=result.tx_hash, demo=result.demo, at=int(time.time()))
            )

        terms = self.verifier.terms
        payment: dict[str, Any] = {
            "asset": terms.asset,
            "payTo": terms.pay_to,
            "amount": str(terms.amount),
            "network": terms.network,
            "verified_onchain": not result.demo,
        }
        if result.tx_hash is not None:
            payment["tx"] = result.tx_hash
        if result.value is not None:
            payment["value"] = str(result.value)

        body: dict[str, Any] = {
            "status": "registered",
            "job_id": job_id,
            "mode": "demo" if result.demo else "live",
            "payment": payment,
        }
        headers = {}
        if result.demo:
            # ADR-010 keputusan 3(v): respons 200 mode demo WAJIB menandai dirinya sendiri.
            headers["X-Payment-Mode"] = "demo"
            body["demo"] = True
            body["warning"] = "DEMO_MODE: pembayaran TIDAK diverifikasi on-chain"
        log.info(
            "jobs/register jobId=%d mode=%s tx=%s",
            job_id,
            body["mode"],
            result.tx_hash or "-",
        )
        return HTTPStatus.OK, headers, body


def _parse_body(body_bytes: bytes) -> int | str:
    """`job_id` yang sudah divalidasi, atau kode galat sebagai `str`.

    Seluruh isi badan adalah teks pihak ketiga: apa pun selain `job_id` DIABAIKAN dan tidak
    pernah dipantulkan, disimpan ke memori, atau dimasukkan ke log.
    """
    if len(body_bytes) > MAX_BODY_BYTES:
        return "body_too_large"
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "invalid_json"
    if not isinstance(payload, dict):
        return "invalid_json"
    raw = payload.get("job_id")
    if isinstance(raw, bool) or not isinstance(raw, int):
        return "invalid_job_id"
    if raw < 0 or raw > MAX_JOB_ID:
        return "invalid_job_id"
    return raw


# ----------------------------------------------------------------------
# Jembatan http.server
# ----------------------------------------------------------------------


class RegisterHandler(BaseHTTPRequestHandler):
    """Handler stdlib. `app` dipasang lewat subclass yang dibuat `make_handler()`."""

    app: RegisterApp
    protocol_version = "HTTP/1.1"
    server_version = "evaluator-402"
    sys_version = ""  # jangan bocorkan versi Python ke klien

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — tanda tangan stdlib
        log.info("http %s", format % args)

    def _respond(self, status: int, headers: dict[str, str], body: dict[str, Any]) -> None:
        payload = json.dumps(body, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> bytes | None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return b""
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            return None
        if length < 0 or length > MAX_BODY_BYTES:
            return None
        return self.rfile.read(length)

    def do_POST(self) -> None:  # noqa: N802 — tanda tangan stdlib
        # Badan dibaca (atau ditolak) SEBELUM routing: koneksi keep-alive yang masih menyimpan
        # sisa badan akan membaca sisa itu sebagai baris permintaan berikutnya.
        body = self._read_body()
        if body is None:
            # Badan terlalu besar TIDAK dikuras — satu-satunya penutup yang benar adalah
            # menutup koneksinya, bukan menebak di mana permintaan berikutnya mulai.
            self.close_connection = True
            self._respond(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"Connection": "close"},
                {"error": "body_too_large"},
            )
            self.close_connection = True
            return
        if self.path.split("?", 1)[0] != REGISTER_PATH:
            self._respond(HTTPStatus.NOT_FOUND, {}, {"error": "not_found"})
            return
        status, headers, payload = self.app.handle_register(self.headers.get("Authorization"), body)
        self._respond(status, headers, payload)

    def do_GET(self) -> None:  # noqa: N802 — tanda tangan stdlib
        if self._read_body() is None:
            self.close_connection = True
            self._respond(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"Connection": "close"},
                {"error": "body_too_large"},
            )
            self.close_connection = True
            return
        if self.path.split("?", 1)[0] != REGISTER_PATH:
            self._respond(HTTPStatus.NOT_FOUND, {}, {"error": "not_found"})
            return
        self._respond(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"Allow": "POST"},
            {"error": "method_not_allowed", "allow": "POST"},
        )

    do_PUT = do_GET
    do_DELETE = do_GET


def make_handler(app: RegisterApp) -> type[RegisterHandler]:
    return type("BoundRegisterHandler", (RegisterHandler,), {"app": app})


def build_app(w3: Any | None = None) -> RegisterApp:
    """Aplikasi dari konfigurasi env/`.env`. `w3=None` → `Web3(HTTPProvider(RPC_URL))`.

    TIDAK ADA kunci privat yang dimuat: gerbang ini hanya membaca chain.
    """
    terms = terms_from_config()
    chain_id = int(config_value("CHAIN_ID", str(DEFAULT_CHAIN_ID)))
    demo = demo_mode_enabled()
    if w3 is None:
        w3 = Web3(Web3.HTTPProvider(config_value("RPC_URL", DEFAULT_RPC_URL)))
    ledger = PaymentLedger(ledger_path_from_config())
    verifier = PaymentVerifier(w3, terms, chain_id, ledger, demo_mode=demo)
    return RegisterApp(verifier, demo_mode=demo)


def serve(app: RegisterApp, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Server yang SUDAH terikat, belum melayani. Pemanggil memutuskan cara menjalankannya."""
    return ThreadingHTTPServer((host, port), make_handler(app))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gerbang 402 buatan sendiri untuk POST /jobs/register (ADR-010 — BUKAN x402)"
    )
    parser.add_argument("--host", default=config_value("PAYMENT_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(config_value("PAYMENT_PORT", str(DEFAULT_PORT))))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app = build_app()
    terms = app.verifier.terms
    log.info(
        "402 gate: %s%s skema=%s network=%s asset=%s payTo=%s amount=%d demo=%s",
        f"http://{args.host}:{args.port}",
        REGISTER_PATH,
        SCHEME,
        terms.network,
        terms.asset,
        terms.pay_to,
        terms.amount,
        app.demo_mode,
    )
    httpd = serve(app, args.host, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover — dijalankan lewat `python -m`
    raise SystemExit(main())
