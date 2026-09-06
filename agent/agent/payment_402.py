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
  (b) **Pembayaran di sini adalah kredensial bearer, dan itu bukan kiasan.** `nonce` di
      tantangan hanya korelasi/logging: transfer ERC-20 polos tidak membawa memo, jadi nonce
      TIDAK PERNAH disimpan dan TIDAK PERNAH dibandingkan saat klaim — konsekuensi ADR-010
      baris 115 ("kedaluwarsa nonce jadi kode kita sendiri") yang implementasinya NOL, ditulis
      di sini apa adanya alih-alih didiamkan. Yang diperiksa hanyalah ISI transfer, bukan siapa
      penuntutnya: `_matching_transfer` tidak pernah membaca `event["args"]["from"]`, jadi
      transfer yang dikirim ORANG LAIN tetap membayar bagi siapa pun yang mengutip hashnya.
      Siapa pun yang membaca mempool/explorer bisa **mendahului (front-running)** klien yang
      benar-benar membayar; klien itu lalu menerima `payment_already_used` dan ongkosnya hangus.
      Mengikat `from` tidak menutupnya (mengaku sebagai alamat lain itu gratis — butuh tanda
      tangan, dan itu di luar lingkup ADR-010); yang DIPASANG di sini hanya lantai blok opsional
      `PAYMENT_MIN_BLOCK`, supaya transfer purba ke `payTo` tidak berlaku sebagai kredensial
      selamanya. Default lantai itu 0 = mati, jadi tanpa konfigurasi sifat bearer tetap penuh.
      Yang benar-benar mencegah pemakaian ULANG adalah BUKU HASH TX (`PaymentLedger`) — di jalur
      x402 resmi pekerjaan itu milik fasilitator; di jalur kita tidak ada yang mengerjakannya
      kecuali kode ini.
  (c) Buku hash tx menjaga replay di dalam satu proses, **lintas proses**, dan lintas restart
      (file JSON Lines). Lintas proses ditegakkan `fcntl.flock(LOCK_EX)` atas `<buku>.lock` yang
      dipegang selama muat-ulang + cek + tulis, jadi dua server dengan `PAYMENT_LEDGER_PATH` yang
      sama tidak bisa lagi menerima satu hash dua kali; tiap baris di-`fsync` sebelum klaimnya
      diakui, jadi mati mendadak tidak meninggalkan baris terpotong yang membuat hash itu membayar
      lagi sesudah restart. Yang TETAP tidak dijaga, dan karena itu ditulis: buku yang **DIHAPUS**
      (atau dipindahkan/dikosongkan) saat server berjalan menghapus seluruh riwayat — sesudah
      restart, hash lama membayar lagi. Kuncinya juga KOOPERATIF: ia hanya menahan proses yang
      memakai modul ini, bukan editor, `rm`, atau penulis lain. Buku yang tidak bisa ditulis =
      **503**, bukan 200: gerbang menolak mengakui pembayaran yang tidak bisa ia catat.
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
  - **Setiap permintaan berbiaya bagi pemanggil sebelum ia berbiaya bagi kita**: `RateLimiter`
    per alamat klien berjalan SEBELUM receipt dibaca, sehingga permintaan tak berbayar tidak
    bisa mengubah gerbang ini menjadi amplifier `eth_getTransactionReceipt` atas kuota RPC kita.
  - **Tidak ada koneksi yang boleh memarkir thread selamanya**: `RegisterHandler.timeout`
    memasang batas waktu soket (klien yang menggantung di tengah badan diputus), dan jumlah
    koneksi hidup dibatasi `BoundedThreadingHTTPServer`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Iterator
from contextlib import contextmanager
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

try:  # pragma: no cover - Linux/macOS; cabang lain hanya ada supaya fail-closed
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

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
LEDGER_LOCK_SUFFIX = ".lock"

# Batas tunggu kunci buku. Operasinya lokal dan berorde milidetik; batas ini hanya mencegah
# permintaan menggantung bila proses lain macet sambil memegang kunci. Habis = 503, bukan 200.
LEDGER_LOCK_TIMEOUT_SECONDS = 5.0
LEDGER_LOCK_POLL_SECONDS = 0.01

# Batas waktu soket per koneksi. Tanpa ini `rfile.read(length)` memblokir SELAMANYA pada klien
# yang mengirim `Content-Length` besar lalu diam (slowloris), dan tiap koneksi seperti itu
# memarkir satu thread permanen.
REQUEST_TIMEOUT_SECONDS = 15.0

# Plafon koneksi hidup. `ThreadingHTTPServer` polos membuat satu thread per koneksi tanpa batas.
MAX_CONCURRENT_CONNECTIONS = 64

# Rate limit per alamat klien. Nilainya longgar untuk demo satu klien, tetapi cukup untuk
# memutus amplifikasi RPC oleh pemanggil tak berbayar. 0 = mati.
DEFAULT_RATE_LIMIT_REQUESTS = 30
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60.0

# Lantai blok opsional untuk transfer yang boleh dipakai membayar (lihat (b) di docstring).
# 0 = mati; tanpa ini transfer ke `payTo` KAPAN PUN di masa lalu berlaku sebagai kredensial.
DEFAULT_MIN_BLOCK = 0

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
REASON_TOO_OLD = "transfer_too_old"
REASON_LEDGER = "ledger_unavailable"
REASON_RATE_LIMITED = "rate_limited"
REASON_INTERNAL = "internal_error"

_TX_HASH_RE = re.compile(r"\A0x[0-9a-fA-F]{64}\Z")
_AUTH_PARAM_RE = re.compile(r'([A-Za-z0-9_\-]+)\s*=\s*(?:"([^"\\\r\n]*)"|([^,\s"]+))')
# Nilai yang boleh masuk ke header respons. CR/LF mustahil lolos → tidak ada injeksi header.
_SAFE_HEADER_VALUE_RE = re.compile(r"\A[A-Za-z0-9:_.\-]+\Z")
_DEMO_TRUE = frozenset({"1", "true", "yes", "demo"})


class PaymentConfigError(RuntimeError):
    """Konfigurasi gerbang tidak sah (alamat/jumlah/realm). Fail-closed saat start."""


class PaymentLedgerError(RuntimeError):
    """Buku pembayaran tidak bisa dikunci/dibaca/ditulis SAAT BERJALAN.

    Selalu fail-closed di pemanggil: pembayaran yang tidak bisa dicatat TIDAK diakui (503),
    dan hashnya TIDAK ditandai terpakai supaya klien yang sudah membayar bisa mengulang.
    Pesannya memuat path buku, jadi ia hanya boleh masuk LOG — tidak pernah badan respons.
    """


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

    `claim()` adalah operasi MUAT-ULANG → cek → tulis di bawah DUA kunci sekaligus:
    `threading.Lock` untuk thread di proses ini, dan `fcntl.flock(LOCK_EX)` atas `<buku>.lock`
    untuk proses lain yang menunjuk berkas yang sama. Dua permintaan bersamaan dengan hash yang
    sama TIDAK bisa dua-duanya menang, termasuk bila datang dari dua server berbeda dengan
    `PAYMENT_LEDGER_PATH` yang sama (`make demo` + `python -m agent.payment_402` bersamaan).

    Muat-ulang di dalam kunci itu WAJIB, bukan hiasan: himpunan di memori lahir saat objek
    dibuat, jadi tanpa membacanya lagi, proses kedua tidak akan pernah melihat baris yang
    ditulis proses pertama sesudah start. `flock` sendiri hanya menyerialkan, ia tidak
    memberitahu apa yang berubah.

    `fcntl` ada di pustaka standar → ADR-010 (nol dependensi baru) aman. Mekanisme yang sama
    sudah dipakai `agent/memory_lock.py`; batas kejujurannya juga sama: kunci ini KOOPERATIF.
    """

    def __init__(self, path: Path | None = None, *, lock_timeout_seconds: float | None = None) -> None:
        self._path = path
        self._lock_path = (
            path.with_name(path.name + LEDGER_LOCK_SUFFIX) if path is not None else None
        )
        self._lock_timeout = (
            LEDGER_LOCK_TIMEOUT_SECONDS if lock_timeout_seconds is None else float(lock_timeout_seconds)
        )
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

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Kunci eksklusif lintas proses atas buku. MELEMPAR `PaymentLedgerError` bila gagal.

        Tidak pernah menunggu selamanya: gagal dapat kunci = 503 di pemanggil, bukan antrean
        tak berbatas yang memarkir thread.
        """
        assert self._lock_path is not None
        if fcntl is None:  # pragma: no cover - hanya di platform tanpa fcntl
            raise PaymentLedgerError(
                "fcntl tidak tersedia: buku pembayaran tidak bisa dikunci lintas proses, dan "
                "menulis tanpa kunci DILARANG (satu tx bisa membayar dua job)"
            )
        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            raise PaymentLedgerError(
                f"kunci buku pembayaran tidak bisa dibuka: {self._lock_path} ({exc})"
            ) from exc
        deadline = time.monotonic() + max(0.0, self._lock_timeout)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise PaymentLedgerError(
                            f"kunci buku pembayaran {self._lock_path} dipegang proses lain lebih "
                            f"dari {self._lock_timeout:g} detik"
                        ) from None
                    time.sleep(LEDGER_LOCK_POLL_SECONDS)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def claim(self, tx_hash: str, job_id: int) -> bool:
        """True bila hash ini BARU dan berhasil diklaim; False bila sudah pernah dipakai.

        MELEMPAR `PaymentLedgerError` bila buku tidak bisa dikunci/dibaca/ditulis. Dalam kasus
        itu hash TIDAK ditandai terpakai — pembayaran yang gagal dicatat tidak boleh terbakar.
        """
        key = tx_hash.lower()
        with self._lock:
            if self._path is None:
                if key in self._used:
                    return False
                self._used.add(key)
                return True
            with self._file_lock():
                try:
                    self._used = self._load(self._path)
                except PaymentConfigError as exc:
                    raise PaymentLedgerError(str(exc)) from exc
                if key in self._used:
                    return False
                self._append(key, job_id)  # gagal → melempar SEBELUM hash ditandai terpakai
                self._used.add(key)
                return True

    def _append(self, tx_hash: str, job_id: int) -> None:
        """Satu baris, `O_APPEND` + `fsync`, di bawah kunci berkas milik `claim()`.

        `O_APPEND` membuat setiap baris utuh meski ada penulis lain; `fsync` membuat klaim
        yang sudah diakui tidak bisa hilang saat mati mendadak (baris terpotong = hash itu
        membayar LAGI sesudah restart).
        """
        assert self._path is not None
        record = json.dumps({"tx": tx_hash, "job_id": job_id, "at": int(time.time())}, sort_keys=True)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, (record + "\n").encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise PaymentLedgerError(f"buku pembayaran tidak bisa ditulis: {self._path} ({exc})") from exc


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
        min_block: int = DEFAULT_MIN_BLOCK,
    ) -> None:
        self.w3 = w3
        self.terms = terms.validate()
        self.chain_id = chain_id
        self.ledger = ledger
        self.demo_mode = demo_mode
        self.min_block = max(0, int(min_block))
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

        # Lantai blok opsional: tanpa ini transfer ke `payTo` KAPAN PUN di masa lalu berlaku
        # sebagai kredensial (docstring (b)). Receipt tanpa `blockNumber` DITOLAK saat lantai
        # dipasang — "tidak bisa dibuktikan cukup baru" tidak boleh berarti "lolos".
        if self.min_block > 0:
            try:
                block_number = int(receipt["blockNumber"])
            except (KeyError, TypeError, ValueError):
                return PaymentResult(False, REASON_RECEIPT, tx_hash=tx_hash)
            if block_number < self.min_block:
                log.warning("pembayaran ditolak: transfer di blok %d di bawah lantai", block_number)
                return PaymentResult(False, REASON_TOO_OLD, tx_hash=tx_hash)

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
            try:
                claimed = self.verifier.ledger.claim(result.tx_hash, job_id)
            except PaymentLedgerError as exc:
                # Buku tidak bisa dikunci/ditulis. Arah amannya: JANGAN mengakui pembayaran yang
                # tidak bisa dicatat (kalau diakui, hash yang sama bisa dipakai lagi nanti).
                # Hashnya juga TIDAK terbakar, jadi klien yang sudah membayar bisa mengulang.
                # Pesan galat memuat path buku → hanya masuk log, tidak pernah badan respons.
                log.error("buku pembayaran tidak bisa dicatat: %s", exc)
                return (
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"Retry-After": "5"},
                    {
                        "error": REASON_LEDGER,
                        "detail": "buku pembayaran tidak bisa dicatat; pembayaran BELUM dipakai",
                        "retry_with_same_tx": True,
                    },
                )
            if not claimed:
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
# Rate limit — pustaka standar, per alamat klien
# ----------------------------------------------------------------------


class RateLimiter:
    """Jendela geser sederhana per kunci (alamat klien), in-process.

    Ada karena verifikasi pembayaran MEMBACA CHAIN sebelum pemanggil membayar apa pun: tanpa
    pembatas, 200 permintaan tak berbayar berisi hash acak = 200 `eth_getTransactionReceipt`
    atas kuota RPC KITA, dan komponen yang alasan hidupnya "penghalang spam" justru menjadi
    amplifier. Sengaja sederhana (stdlib, tanpa dependensi baru — ADR-010).

    Ingatannya DIBATASI `max_keys`: peta per-klien yang tumbuh bebas hanyalah kebocoran memori
    dengan nama lain. Kunci yang paling lama tidak tersentuh dibuang lebih dulu.

    `clock` bisa disuntik supaya kedaluwarsa jendela bisa diuji tanpa `sleep`.
    """

    def __init__(
        self,
        max_requests: int = DEFAULT_RATE_LIMIT_REQUESTS,
        window_seconds: float = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        *,
        max_keys: int = 1024,
        clock: Any = time.monotonic,
    ) -> None:
        self.max_requests = max(1, int(max_requests))
        self.window_seconds = max(0.001, float(window_seconds))
        self.max_keys = max(1, int(max_keys))
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def check(self, key: str) -> float | None:
        """`None` bila permintaan boleh lanjut (dan sudah dihitung); detik tunggu bila ditolak."""
        now = float(self._clock())
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
            self._hits.move_to_end(key)
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return max(0.0, hits[0] + self.window_seconds - now)
            hits.append(now)
            while len(self._hits) > self.max_keys:
                self._hits.popitem(last=False)
            return None

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._hits)


def limiter_from_config() -> RateLimiter | None:
    """`None` bila `PAYMENT_RATE_LIMIT` <= 0 (sengaja dimatikan)."""
    max_requests = int(config_value("PAYMENT_RATE_LIMIT", str(DEFAULT_RATE_LIMIT_REQUESTS)))
    window = float(config_value("PAYMENT_RATE_WINDOW_SECONDS", str(DEFAULT_RATE_LIMIT_WINDOW_SECONDS)))
    if max_requests <= 0:
        log.warning("PAYMENT_RATE_LIMIT <= 0: rate limit gerbang 402 DIMATIKAN")
        return None
    return RateLimiter(max_requests, window)


# ----------------------------------------------------------------------
# Jembatan http.server
# ----------------------------------------------------------------------


class RegisterHandler(BaseHTTPRequestHandler):
    """Handler stdlib. `app` dipasang lewat subclass yang dibuat `make_handler()`."""

    app: RegisterApp
    limiter: RateLimiter | None = None
    protocol_version = "HTTP/1.1"
    server_version = "evaluator-402"
    sys_version = ""  # jangan bocorkan versi Python ke klien

    # Batas waktu soket per koneksi. `socketserver.StreamRequestHandler.setup` memasangnya ke
    # soket, jadi `rfile.read(length)` TIDAK bisa lagi memblokir selamanya: klien yang mengirim
    # `Content-Length: 8000` lalu satu byte akan diputus, bukan memarkir satu thread permanen.
    timeout = REQUEST_TIMEOUT_SECONDS

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

    @contextmanager
    def _guard(self) -> Iterator[None]:
        """Satu-satunya penangan galat umum. Tanpa ini, galat apa pun di jalur permintaan
        menembus ke `socketserver`, yang MENUTUP koneksi tanpa respons dan mencetak traceback
        (berisi path absolut) ke stderr. Klien mendapat 500 JSON yang tidak menyebut apa pun."""
        try:
            yield
        except TimeoutError:
            raise  # slowloris: dibiarkan naik supaya stdlib menutup koneksinya
        except Exception as exc:  # noqa: BLE001 — permukaan jaringan: tidak boleh ada yang lolos
            log.error("permintaan gagal tak terduga: %s", type(exc).__name__)
            self.close_connection = True
            try:
                self._respond(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"Connection": "close"},
                    {"error": REASON_INTERNAL},
                )
            except OSError:  # koneksi sudah mati — tidak ada yang bisa dikirim
                pass

    def _client_key(self) -> str:
        address = getattr(self, "client_address", None)
        if isinstance(address, tuple) and address:
            return str(address[0])
        return "-"

    def _rate_limited(self) -> bool:
        """True (dan respons 429 sudah dikirim) bila pemanggil melewati plafon lajunya.

        Dicek SEBELUM badan dibaca dan sebelum pembayaran diverifikasi, karena verifikasi itulah
        yang memanggil RPC. Karena badan tidak dikuras, framing keep-alive tidak bisa dipercaya
        lagi → koneksi ditutup.
        """
        limiter = self.limiter
        if limiter is None:
            return False
        wait = limiter.check(self._client_key())
        if wait is None:
            return False
        retry_after = max(1, int(wait) + 1)
        self.close_connection = True
        self._respond(
            HTTPStatus.TOO_MANY_REQUESTS,
            {"Connection": "close", "Retry-After": str(retry_after)},
            {"error": REASON_RATE_LIMITED, "retry_after": retry_after},
        )
        self.close_connection = True
        return True

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
        with self._guard():
            self._post()

    def _post(self) -> None:
        if self._rate_limited():
            return
        # Badan dibaca (atau ditolak) SEBELUM routing: koneksi keep-alive yang masih menyimpan
        # sisa badan akan membaca sisa itu sebagai baris permintaan berikutnya. Ia dibatasi DUA
        # arah — ukuran (`MAX_BODY_BYTES`) dan waktu (`timeout`) — dan tetap TIDAK PERNAH
        # di-parse sebelum pembayaran diverifikasi (`RegisterApp.handle_register`).
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
        with self._guard():
            self._get()

    def _get(self) -> None:
        if self._rate_limited():
            return
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


def make_handler(
    app: RegisterApp,
    *,
    limiter: RateLimiter | None = None,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> type[RegisterHandler]:
    return type(
        "BoundRegisterHandler",
        (RegisterHandler,),
        {"app": app, "limiter": limiter, "timeout": float(timeout)},
    )


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """`ThreadingHTTPServer` dengan PLAFON koneksi hidup.

    Versi polosnya membuat satu thread per koneksi tanpa batas apa pun; batas waktu soket
    memang sudah membuat tiap thread berumur terbatas, tetapi tidak membatasi BERAPA BANYAK
    yang hidup sekaligus. Slot diambil sebelum thread dibuat dan dikembalikan saat thread
    selesai; koneksi yang melewati plafon ditutup TANPA dilayani (bukan diantrekan).
    """

    daemon_threads = True

    def __init__(
        self,
        *args: Any,
        max_connections: int = MAX_CONCURRENT_CONNECTIONS,
        **kwargs: Any,
    ) -> None:
        self._slots = threading.BoundedSemaphore(max(1, int(max_connections)))
        super().__init__(*args, **kwargs)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            log.warning("plafon koneksi tercapai — koneksi baru ditutup tanpa dilayani")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def build_app(w3: Any | None = None) -> RegisterApp:
    """Aplikasi dari konfigurasi env/`.env`. `w3=None` → `Web3(HTTPProvider(RPC_URL))`.

    TIDAK ADA kunci privat yang dimuat: gerbang ini hanya membaca chain.
    """
    terms = terms_from_config()
    chain_id = int(config_value("CHAIN_ID", str(DEFAULT_CHAIN_ID)))
    demo = demo_mode_enabled()
    min_block = int(config_value("PAYMENT_MIN_BLOCK", str(DEFAULT_MIN_BLOCK)))
    if w3 is None:
        w3 = Web3(Web3.HTTPProvider(config_value("RPC_URL", DEFAULT_RPC_URL)))
    ledger = PaymentLedger(ledger_path_from_config())
    verifier = PaymentVerifier(w3, terms, chain_id, ledger, demo_mode=demo, min_block=min_block)
    return RegisterApp(verifier, demo_mode=demo)


def serve(
    app: RegisterApp,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    limiter: RateLimiter | None = None,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
    max_connections: int = MAX_CONCURRENT_CONNECTIONS,
) -> ThreadingHTTPServer:
    """Server yang SUDAH terikat, belum melayani. Pemanggil memutuskan cara menjalankannya."""
    return BoundedThreadingHTTPServer(
        (host, port),
        make_handler(app, limiter=limiter, timeout=timeout),
        max_connections=max_connections,
    )


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
        "402 gate: %s%s skema=%s network=%s asset=%s payTo=%s amount=%d demo=%s minBlock=%d buku=%s",
        f"http://{args.host}:{args.port}",
        REGISTER_PATH,
        SCHEME,
        terms.network,
        terms.asset,
        terms.pay_to,
        terms.amount,
        app.demo_mode,
        app.verifier.min_block,
        ledger_path_from_config(),
    )
    httpd = serve(app, args.host, args.port, limiter=limiter_from_config())
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover — dijalankan lewat `python -m`
    raise SystemExit(main())
