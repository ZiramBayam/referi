"""Sumber teks deliverable + verifikasi ulang hash-nya — ADR-019 keputusan 1-2 (MENGIKAT).

Kenapa ada file lokal sama sekali: `session.submit()` SDK memanggil `api.postDeliverable`
ke API off-chain Virtuals, dan API itu MENOLAK wallet simulator kita
(`POST https://api.acp.virtuals.io/auth/agent` → 404 `Agent not found with wallet address …`,
terbukti 4 Sep; docs/api-facts.md §B.1 + ADR-019 konteks (a)). Jadi on-chain HANYA ada
`keccak256` deliverable, bukan teksnya.

Aturan ADR-019 keputusan 1-2, apa adanya:
  - `sim/` menulis `demo/deliverables/<jobId>.json` = `{"jobId","text","sha_keccak"}`, dan
    yang dikirim on-chain adalah `keccak256` dari byte UTF-8 field `text` yang PERSIS sama
    (SDK: `keccak256(toHex(deliverable))`, api-facts §B.1);
  - `agent/` membaca teks HANYA dari direktori itu (`DELIVERABLE_DIR`, default
    `demo/deliverables`) dan WAJIB memverifikasi ulang `keccak256(text)` == nilai
    deliverable ON-CHAIN sebelum menilai;
  - tidak cocok / file hilang → **REFUSE**: nol `postVerdict`, nol `finalize`, cetak
    `DELIVERABLE TIDAK TERVERIFIKASI`. Perlakuannya sekelas mode aman (task 2.4a).

Karena itu fungsi di sini MELEMPAR (`DeliverableUnverifiedError`), bukan mengembalikan
objek "kosong": pemanggil yang lupa memeriksa nilai balik tetap berhenti. Itu bentuk
fail-closed yang sama dengan `SafeModeStop` di `vault_client`.

File lokal ini TIDAK dipercaya sedikit pun: otoritasnya ada di hash on-chain. Yang
dilakukan file lokal hanyalah MENGUSULKAN preimage; kalau preimage itu tidak menghasilkan
hash yang sama, ia dibuang. Juri bisa mengulang langkah yang sama dengan
`cast keccak "$(jq -r .text demo/deliverables/<id>.json)"`.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from web3 import Web3

log = logging.getLogger("checks.source")

__all__ = [
    "DEFAULT_DELIVERABLE_DIR",
    "DELIVERABLE_DIR_ENV",
    "MAX_DELIVERABLE_BYTES",
    "REFUSAL_LINE",
    "DeliverableUnverifiedError",
    "VerifiedDeliverable",
    "deliverable_dir",
    "keccak_text",
    "load_verified_deliverable",
]

DELIVERABLE_DIR_ENV: Final = "DELIVERABLE_DIR"
DEFAULT_DELIVERABLE_DIR: Final = "demo/deliverables"

# Baris yang WAJIB tercetak saat menolak (ADR-019 keputusan 2). Sama seperti `MODE AMAN:`,
# ia adalah BUKTI, jadi bentuknya tidak boleh diringkas/diterjemahkan pemanggil.
REFUSAL_LINE: Final = "DELIVERABLE TIDAK TERVERIFIKASI"

# Batas ukuran file. Deliverable demo berukuran kilobyte; 256 KiB memberi ruang lebar
# tanpa mengizinkan file lokal 2 GB menghabiskan memori agen sebelum satu hash pun dihitung.
MAX_DELIVERABLE_BYTES: Final = 256 * 1024

# Field yang dikenal di artefak (ADR-019 keputusan 1). Field asing DITOLAK, bukan
# diabaikan: satu-satunya bentuk sah artefak ini ditetapkan ADR, dan file yang bentuknya
# lain lebih mungkin salah/dipalsukan daripada "versi baru yang ramah".
_ARTIFACT_FIELDS: Final[frozenset[str]] = frozenset({"jobId", "text", "sha_keccak"})


class DeliverableUnverifiedError(RuntimeError):
    """Teks deliverable tidak bisa dibuktikan sebagai preimage hash on-chain.

    BUKAN kegagalan teknis yang boleh di-retry menjadi "ya sudah, nilai saja": agen
    memang menolak menilai. Pesannya diawali `DELIVERABLE TIDAK TERVERIFIKASI` apa adanya.
    """


def deliverable_dir(override: str | os.PathLike[str] | None = None) -> Path:
    """Direktori artefak: argumen → env `DELIVERABLE_DIR` → `demo/deliverables`.

    Path relatif diselesaikan terhadap CWD (sama seperti `SIBYL_DB_PATH` di
    `vault_client`), supaya demo yang dijalankan dari root repo menemukan `demo/`.

    HANYA environment sungguhan yang dibaca di sini, BUKAN file `.env` root. Pemanggil
    yang ingin pola `vault_client.config_value` (env → .env → default) WAJIB meneruskan
    hasilnya lewat `override`; modul cek sengaja tidak mengimpor `vault_client` supaya
    tidak ada impor melingkar ketika `vault_client` memakai `criteria.evaluate_job`.
    """
    if override is not None:
        return Path(override).expanduser()
    value = os.environ.get(DELIVERABLE_DIR_ENV, "").strip()
    return Path(value or DEFAULT_DELIVERABLE_DIR).expanduser()


def keccak_text(text: str) -> bytes:
    """`keccak256` byte UTF-8 sebuah string — identik dengan `keccak256(toHex(s))` SDK.

    Kesamaannya dibuktikan byte-per-byte di docs/api-facts.md §B.1
    (`"ipfs://bafkreiabc123"` → `c08fd6cd…d3bd` di kedua sisi).
    """
    return bytes(Web3.keccak(text=text))


def _parse_onchain(value: bytes | bytearray | str) -> bytes:
    """Nilai `deliverable` on-chain (bytes32) → 32 byte, apa pun bentuk masukannya.

    bytes32 NOL ditolak: itu artinya job belum di-`submit` (atau slotnya kosong), dan
    "kosong == kosong" tidak boleh pernah dianggap cocok.
    """
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, str):
        text = value.strip()
        text = text[2:] if text.lower().startswith("0x") else text
        try:
            raw = bytes.fromhex(text)
        except ValueError as exc:
            raise DeliverableUnverifiedError(
                f"{REFUSAL_LINE}: nilai deliverable on-chain bukan hex 32 byte"
            ) from exc
    else:
        raise DeliverableUnverifiedError(
            f"{REFUSAL_LINE}: nilai deliverable on-chain bertipe {type(value).__name__}"
        )
    if len(raw) != 32:
        raise DeliverableUnverifiedError(
            f"{REFUSAL_LINE}: nilai deliverable on-chain {len(raw)} byte, bukan 32"
        )
    if raw == bytes(32):
        raise DeliverableUnverifiedError(
            f"{REFUSAL_LINE}: deliverable on-chain masih bytes32 nol (job belum submit)"
        )
    return raw


def _artifact_path(job_id: int, directory: Path) -> Path:
    """`<dir>/<jobId>.json` dengan nama file yang DIBANGUN dari int, bukan dari teks.

    `job_id` diketatkan jadi int non-negatif supaya tidak ada jalur di mana string dari
    pihak lain (`"../../etc/passwd"`, `"1; rm -rf"`) menjadi nama file. Hasilnya juga
    diperiksa: ia WAJIB anak langsung direktori itu dan BUKAN symlink — file yang isinya
    memang salah akan tertangkap hash, tetapi symlink ke `/dev/zero` menghabiskan proses
    sebelum sempat di-hash.
    """
    if isinstance(job_id, bool) or not isinstance(job_id, int):
        raise DeliverableUnverifiedError(
            f"{REFUSAL_LINE}: job_id harus int, dapat {type(job_id).__name__}"
        )
    if job_id < 0:
        raise DeliverableUnverifiedError(f"{REFUSAL_LINE}: job_id negatif ({job_id})")
    path = directory / f"{job_id}.json"
    if path.is_symlink():
        raise DeliverableUnverifiedError(f"{REFUSAL_LINE}: {path} adalah symlink")
    if path.parent.resolve() != directory.resolve():
        raise DeliverableUnverifiedError(f"{REFUSAL_LINE}: {path} di luar {directory}")
    return path


@dataclass(frozen=True)
class VerifiedDeliverable:
    """Teks deliverable yang SUDAH terbukti sebagai preimage hash on-chain."""

    job_id: int
    text: str
    onchain_hash: bytes
    path: Path

    @property
    def hash_hex(self) -> str:
        # web3 7.x: `HexBytes.hex()` TANPA prefix `0x` (api-facts §B.1) → tambahkan sendiri.
        return "0x" + self.onchain_hash.hex()


def load_verified_deliverable(
    job_id: int,
    onchain_deliverable: bytes | bytearray | str,
    directory: str | os.PathLike[str] | None = None,
) -> VerifiedDeliverable:
    """Membaca `<DELIVERABLE_DIR>/<jobId>.json` lalu MEMBUKTIKAN teksnya (ADR-019 kep. 2).

    Melempar `DeliverableUnverifiedError` — dan mencatat baris `DELIVERABLE TIDAK
    TERVERIFIKASI` — pada SETIAP kondisi berikut, tanpa jalur pemulihan:
      file/direktori tidak ada, bukan file biasa, terlalu besar, bukan JSON, bukan objek,
      field asing, `jobId` tidak cocok, `text` bukan string, teks tidak bisa di-encode
      UTF-8, `sha_keccak` tercantum tapi berbeda, dan — yang utama —
      `keccak256(text) != deliverable on-chain`.
    """
    expected = _parse_onchain(onchain_deliverable)
    base = deliverable_dir(directory)
    path = _artifact_path(job_id, base)

    def refuse(reason: str) -> DeliverableUnverifiedError:
        message = f"{REFUSAL_LINE}: job {job_id}: {reason}"
        # Dicatat DI SINI supaya tidak ada jalur penolakan yang senyap, sekalipun
        # pemanggil menelan exception-nya.
        log.error("%s", message)
        return DeliverableUnverifiedError(message)

    if not path.is_file():
        raise refuse(f"berkas {path} tidak ada")
    size = path.stat().st_size
    if size > MAX_DELIVERABLE_BYTES:
        raise refuse(f"berkas {path} {size} byte > batas {MAX_DELIVERABLE_BYTES}")

    raw = path.read_bytes()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise refuse(f"{path} bukan JSON UTF-8 yang sah ({type(exc).__name__})") from exc
    if not isinstance(obj, dict):
        raise refuse(f"{path} bukan objek JSON")
    unknown = set(obj) - _ARTIFACT_FIELDS
    if unknown:
        raise refuse(f"{path} memuat field di luar ADR-019: {sorted(unknown)}")

    claimed_id = obj.get("jobId")
    if isinstance(claimed_id, bool) or not isinstance(claimed_id, (int, str)):
        raise refuse(f"{path}: jobId bertipe {type(claimed_id).__name__}")
    try:
        if int(claimed_id) != job_id:
            raise refuse(f"{path}: jobId {claimed_id!r} bukan job {job_id}")
    except ValueError as exc:
        raise refuse(f"{path}: jobId {claimed_id!r} bukan bilangan") from exc

    text = obj.get("text")
    if not isinstance(text, str):
        raise refuse(f"{path}: field text bertipe {type(text).__name__}, bukan string")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:  # surrogate yatim — Python melempar, Node menambal
        raise refuse(f"{path}: text tidak bisa di-encode UTF-8") from exc

    actual = keccak_text(text)
    if actual != expected:
        raise refuse(
            f"keccak256(text) = 0x{actual.hex()} != deliverable on-chain 0x{expected.hex()}"
        )

    claimed_hash = obj.get("sha_keccak")
    if claimed_hash is not None:
        if not isinstance(claimed_hash, str):
            raise refuse(f"{path}: sha_keccak bertipe {type(claimed_hash).__name__}")
        normalized = claimed_hash.strip().lower()
        normalized = normalized[2:] if normalized.startswith("0x") else normalized
        if normalized != actual.hex():
            raise refuse(f"{path}: sha_keccak {claimed_hash!r} != 0x{actual.hex()}")

    log.info(
        "deliverable terverifikasi: job=%s hash=0x%s sumber=%s (%d byte teks)",
        job_id,
        actual.hex(),
        path,
        len(text.encode("utf-8")),
    )
    return VerifiedDeliverable(job_id=job_id, text=text, onchain_hash=actual, path=path)
