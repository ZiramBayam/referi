"""Cek `chain` — angka/alamat yang DIKLAIM deliverable vs nilai SUNGGUHAN di kontrak.

Inilah cek yang menjatuhkan spec §7 langkah 1 ("Alpha rapi tapi angka supply salah"):
deliverable menyebut `Total supply: <n>`, kita membacanya dari token dan membandingkan.
Tidak ada toleransi, tidak ada pembulatan — angka yang tidak sama adalah gagal, dan
buktinya bisa diulang siapa pun dengan satu `cast call`.

Sumber fakta on-chain (`ChainFacts`) DISUNTIKKAN, bukan dibuat di dalam cek. Dua alasan:
tes berjalan tanpa jaringan, dan `Web3ChainFacts` bisa dipakai ulang oleh 2.4-min/2.5
tanpa membuat koneksi kedua.

Panggilan on-chain yang dipakai (docs/api-facts.md §A):
  - `paymentToken()(address)` di kontrak ACP — SATU-SATUNYA cara sah mengidentifikasi
    token escrow. `symbol()` DILARANG dipakai sebagai bukti identitas: dua token Base
    Sepolia sama-sama menjawab `"USDC"` dan sama-sama `decimals() == 6`.
  - `decimals()(uint8)` dan `totalSupply()(uint256)` di token escrow
    `0xECc22a8F6fD62388498fBa19813E214605a2BDb3`.

`totalSupply()` diverifikasi langsung ke Base Sepolia 2026-09-05:
`cast call 0xECc22a8F6fD62388498fBa19813E214605a2BDb3 "totalSupply()(uint256)"
--rpc-url https://sepolia.base.org` → `110000000004072000000`. Nilainya BERUBAH tiap kali
siapa pun memanggil `mint()` (token itu tanpa kontrol akses, ADR-017) — karena itu ia
dibaca saat evaluasi, TIDAK PERNAH dihardcode.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final, Protocol

from agent.checks.base import (
    CHECK_CHAIN,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNVERIFIED,
    CheckResult,
    Section,
    excerpt,
)

__all__ = [
    "CLAIM_LABELS",
    "FACT_DECIMALS",
    "FACT_PAYMENT_TOKEN",
    "FACT_TOTAL_SUPPLY",
    "PATTERN_CLAIM_MISMATCH",
    "PATTERN_CLAIM_UNPARSEABLE",
    "ChainFacts",
    "StaticChainFacts",
    "Web3ChainFacts",
    "check_claim",
]

FACT_TOTAL_SUPPLY: Final = "total_supply"
FACT_DECIMALS: Final = "decimals"
FACT_PAYMENT_TOKEN: Final = "payment_token"

# Id pola untuk `record_suspicion` (himpunan KONSTAN, sesuai `PATTERN_ID_RE`).
PATTERN_CLAIM_MISMATCH: Final = "chain.claim-mismatch"
PATTERN_CLAIM_UNPARSEABLE: Final = "chain.claim-unparseable"

# Label yang KITA kenali → fakta on-chain. Himpunan KONSTAN: teks deliverable memilih
# di antara kunci yang sudah ada, ia TIDAK PERNAH membuat kunci baru dan tidak pernah
# menjadi nama atribut/fungsi.
CLAIM_LABELS: Final[dict[str, str]] = {
    "total supply": FACT_TOTAL_SUPPLY,
    "totalsupply": FACT_TOTAL_SUPPLY,
    "suplai total": FACT_TOTAL_SUPPLY,
    "token decimals": FACT_DECIMALS,
    "decimals": FACT_DECIMALS,
    "desimal": FACT_DECIMALS,
    "payment token": FACT_PAYMENT_TOKEN,
    "token address": FACT_PAYMENT_TOKEN,
    "alamat token": FACT_PAYMENT_TOKEN,
}

# Baris klaim: `- Total supply: 110000000004072000000` / `Decimals = 6`.
_CLAIM_RE: Final = re.compile(
    r"^[ \t]*[-*>•]?[ \t]*\**[ \t]*(?P<label>[A-Za-z][A-Za-z ]{2,30}?)\**[ \t]*[:=][ \t]*"
    r"(?P<value>\S[^\r\n]*)$",
    re.MULTILINE,
)
# Pemisah ribuan yang DITERIMA lalu dibuang sebelum dibandingkan: koma, titik, garis
# bawah, spasi biasa, dan spasi tak-putus U+00A0 (ikut terbawa saat teks disalin dari web).
_THOUSANDS_SEPARATORS: Final = ",_.\u00a0 "
_NUMBER_RE: Final = re.compile(r"^(?P<digits>\d[\d,_.\u00a0 ]*)")
_ADDRESS_RE: Final = re.compile(r"0x[0-9a-fA-F]{40}")


class ChainFacts(Protocol):
    """Fakta on-chain yang boleh dipakai membandingkan klaim."""

    def total_supply(self) -> int: ...

    def decimals(self) -> int: ...

    def payment_token(self) -> str: ...


class StaticChainFacts:
    """Fakta tetap — untuk tes dan untuk menjalankan ulang evaluasi lama secara offline."""

    def __init__(self, total_supply: int, decimals: int, payment_token: str) -> None:
        self._total_supply = int(total_supply)
        self._decimals = int(decimals)
        self._payment_token = str(payment_token).lower()

    def total_supply(self) -> int:
        return self._total_supply

    def decimals(self) -> int:
        return self._decimals

    def payment_token(self) -> str:
        return self._payment_token


# ABI minimal. Hanya tiga fungsi view, semuanya ada di docs/api-facts.md §A
# (`totalSupply()` diverifikasi ke chain 2026-09-05, lihat docstring modul).
ERC20_MIN_ABI: Final[list[dict[str, Any]]] = [
    {
        "name": "totalSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]

ACP_MIN_ABI: Final[list[dict[str, Any]]] = [
    {
        "name": "paymentToken",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
]


class Web3ChainFacts:
    """Pembaca fakta on-chain lewat web3.py, dengan cache per instans.

    Cache-nya per-evaluasi, bukan global: nilai `totalSupply()` bisa berubah kapan saja
    (token escrow punya `mint()` tanpa kontrol akses), dan bukti yang kita tanda tangani
    harus menunjuk satu pembacaan yang jelas, bukan campuran beberapa blok.

    Identitas token TIDAK ditebak: alamatnya dibaca dari `paymentToken()` kontrak ACP.
    """

    def __init__(self, w3: Any, acp_address: str) -> None:
        self._w3 = w3
        self._acp_address = w3.to_checksum_address(acp_address)
        self._cache: dict[str, Any] = {}

    def _token(self) -> Any:
        if "token_contract" not in self._cache:
            acp = self._w3.eth.contract(address=self._acp_address, abi=ACP_MIN_ABI)
            address = self._w3.to_checksum_address(acp.functions.paymentToken().call())
            self._cache["payment_token"] = address.lower()
            self._cache["token_contract"] = self._w3.eth.contract(address=address, abi=ERC20_MIN_ABI)
        return self._cache["token_contract"]

    def payment_token(self) -> str:
        self._token()
        return str(self._cache["payment_token"])

    def total_supply(self) -> int:
        if "total_supply" not in self._cache:
            self._cache["total_supply"] = int(self._token().functions.totalSupply().call())
        return int(self._cache["total_supply"])

    def decimals(self) -> int:
        if "decimals" not in self._cache:
            self._cache["decimals"] = int(self._token().functions.decimals().call())
        return int(self._cache["decimals"])


def _parse_int(value: str) -> int | None:
    """Angka di awal nilai klaim, tanpa pemisah ribuan. `None` bila tidak berbentuk angka.

    Sengaja hanya membaca token angka PERTAMA dan mengabaikan prosa sesudahnya
    (`110000000004072000000 (1,1e20)`). Batasnya diakui: prosa itu tidak diperiksa.
    """
    match = _NUMBER_RE.match(value.strip())
    if match is None:
        return None
    digits = match.group("digits").translate({ord(c): None for c in _THOUSANDS_SEPARATORS})
    return int(digits) if digits.isdigit() else None


def _claims_in_scope(scope: Sequence[Section], fact: str) -> list[tuple[Section, str, str]]:
    """Semua klaim di cakupan yang labelnya memetakan ke `fact`."""
    found: list[tuple[Section, str, str]] = []
    for section in scope:
        for match in _CLAIM_RE.finditer(section.text):
            label = " ".join(match.group("label").split()).strip().lower()
            if CLAIM_LABELS.get(label) == fact:
                found.append((section, label, match.group("value").strip()))
    return found


def check_claim(
    scope: Sequence[Section],
    fact: str,
    facts: ChainFacts,
    criterion_id: str,
    depth: str,
) -> CheckResult:
    """Membandingkan SATU jenis klaim dengan nilai on-chain.

    Tiga keluaran, dan perbedaannya penting:
      - `fail`  : klaim ADA dan salah (atau ada tapi tidak berbentuk angka/alamat) →
                  masuk `failed_checks` dan menjadi bukti karantina;
      - `pass`  : klaim ada dan PERSIS sama dengan nilai on-chain;
      - `unverified` : klaim tidak ada DI CAKUPAN yang dibaca. Ini bukan "lolos". Pada
                  `sampling` ia berarti "kami tidak melihat bagian itu" — persis lubang
                  yang spec §7 langkah 4 tunjukkan hilang ketika memori dihapus.
    """
    claims = _claims_in_scope(scope, fact)
    if not claims:
        return CheckResult(
            check_id=CHECK_CHAIN,
            criterion_id=criterion_id,
            status=STATUS_UNVERIFIED,
            detail=f"tidak ada klaim {fact!r} pada {len(scope)} bagian yang dibaca (depth={depth})",
            depth=depth,
        )

    if fact == FACT_PAYMENT_TOKEN:
        expected_text = facts.payment_token().lower()
    elif fact == FACT_TOTAL_SUPPLY:
        expected_text = str(facts.total_supply())
    elif fact == FACT_DECIMALS:
        expected_text = str(facts.decimals())
    else:  # pragma: no cover — katalog kriteria hanya memakai tiga fakta di atas
        raise ValueError(f"fakta on-chain tidak dikenal: {fact!r}")

    for section, label, value in claims:
        if fact == FACT_PAYMENT_TOKEN:
            match = _ADDRESS_RE.search(value)
            actual_text = match.group(0).lower() if match else None
        else:
            parsed = _parse_int(value)
            actual_text = None if parsed is None else str(parsed)

        if actual_text is None:
            return CheckResult(
                check_id=CHECK_CHAIN,
                criterion_id=criterion_id,
                status=STATUS_FAIL,
                detail=f"klaim {label!r} tidak berbentuk nilai yang bisa dibandingkan",
                proof=excerpt(f"{label}: {value}"),
                pattern_id=PATTERN_CLAIM_UNPARSEABLE,
                section_index=section.index,
                depth=depth,
            )
        if actual_text != expected_text:
            return CheckResult(
                check_id=CHECK_CHAIN,
                criterion_id=criterion_id,
                status=STATUS_FAIL,
                detail=(
                    f"klaim {label!r} = {actual_text} pada bagian {section.index}, "
                    f"nilai on-chain = {expected_text}"
                ),
                proof=excerpt(f"{label}: {value} | onchain: {expected_text}"),
                pattern_id=PATTERN_CLAIM_MISMATCH,
                section_index=section.index,
                depth=depth,
            )

    return CheckResult(
        check_id=CHECK_CHAIN,
        criterion_id=criterion_id,
        status=STATUS_PASS,
        detail=f"{len(claims)} klaim {fact!r} cocok dengan nilai on-chain {expected_text}",
        depth=depth,
    )
