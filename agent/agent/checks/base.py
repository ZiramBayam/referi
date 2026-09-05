"""Dasar bersama modul `agent/checks/*` — task 2.3-min (cek DETERMINISTIK saja).

Lingkup task ini dipotong PM 5 Sep: TIDAK ADA rubric LLM, TIDAK ADA `anthropic`, TIDAK ADA
kunci API. Yang ada hanya cek yang bisa dijalankan ulang siapa pun atas artefak yang sama
dan menghasilkan jawaban yang sama.

Dua invarian yang ditegakkan DI SINI, bukan di pemanggil:

1. Teks deliverable adalah DATA, TIDAK PERNAH instruksi (spec §3 aturan 3, ADR-019
   keputusan 3). Modul ini hanya MEMBACA teks dengan regex dan membandingkan hasilnya
   dengan fakta on-chain/konstanta. Tidak ada `eval`, tidak ada `format`/`%` yang memakai
   teks pihak sebagai template, tidak ada teks pihak yang menjadi nama fungsi, kunci
   memori, path, atau perintah.
2. Apa pun yang bisa mencapai memori (`proof`) lewat DI SINI dulu (`excerpt`): dipotong,
   dibersihkan dari karakter kontrol/format (termasuk override bidi U+202E yang bisa
   membalik tampilan di `web/`), dan dibatasi `MAX_PROOF_LEN` — batas yang SAMA dengan
   yang divalidasi `memory_policy.Evidence`.

Kedalaman cek (`DEPTH_SAMPLING` / `DEPTH_FULL`) datang dari `memory_policy.check_depth()`;
di sini ia diterjemahkan menjadi CAKUPAN BACA yang konkret. Itulah satu-satunya perbedaan
mekanis antara cacat KASAR dan cacat HALUS di spec §7 langkah 1 vs langkah 4: sampling
membaca judul SELURUH bagian tetapi hanya isi `SAMPLING_SECTION_LIMIT` bagian pertama;
full membaca semuanya.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from agent.memory_policy import (
    DEPTH_FULL,
    DEPTH_SAMPLING,
    DETERMINISTIC_CHECK_IDS,
    MAX_PROOF_LEN,
    PATTERN_ID_RE,
)

__all__ = [
    "CHECK_CHAIN",
    "CHECK_FORMAT",
    "CHECK_LINKS",
    "CHECK_SANDBOX",
    "SAMPLING_SECTION_LIMIT",
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_UNVERIFIED",
    "CheckResult",
    "Document",
    "Section",
    "excerpt",
    "normalize_heading",
    "parse_document",
    "sections_in_scope",
]

# `check_id` yang sah = himpunan KONSTAN `memory_policy.DETERMINISTIC_CHECK_IDS`.
# `record_job_outcome` menolak apa pun di luarnya, jadi konstanta di bawah bukan sinonim
# baru melainkan nama yang mengikat ke himpunan itu (dijaga `_assert_check_ids`).
CHECK_CHAIN: Final = "chain"
CHECK_FORMAT: Final = "format"
CHECK_LINKS: Final = "links"
CHECK_SANDBOX: Final = "sandbox"  # BELUM ada implementasinya di 2.3-min; jangan diklaim hidup.

STATUS_PASS: Final = "pass"
STATUS_FAIL: Final = "fail"
# "tidak diperiksa pada kedalaman ini". BUKAN sinonim lolos: ia tidak pernah masuk
# `failed_checks`, dan juga tidak pernah dilaporkan sebagai bukti bahwa sesuatu benar.
STATUS_UNVERIFIED: Final = "unverified"

VALID_STATUSES: Final[frozenset[str]] = frozenset({STATUS_PASS, STATUS_FAIL, STATUS_UNVERIFIED})

# Berapa bagian pertama yang ISINYA dibaca saat kedalaman `sampling`. Angka ini adalah
# KALIBRASI yang hilang ketika memori dihapus (spec §7 langkah 4): provider tanpa riwayat
# insiden hanya disampling, jadi cacat di bagian belakang lolos; provider ber-insiden
# dinaikkan ke `full` oleh `memory_policy.check_depth()` dan cacat yang sama tertangkap.
SAMPLING_SECTION_LIMIT: Final = 2

# Panjang maksimum satu kutipan bukti. Lebih ketat dari `MAX_PROOF_LEN` (512) supaya satu
# temuan tidak memakan seluruh anggaran `proof`.
MAX_EXCERPT_LEN: Final = 160

_HEADING_RE: Final = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")


def _assert_check_ids() -> None:
    """Nama cek di modul ini WAJIB subset himpunan konstan `memory_policy`.

    Dijalankan saat impor: `check_id` yang tidak dikenal `record_job_outcome` akan
    menggagalkan pencatatan insiden DI TENGAH jalur 2.5, jauh dari sini.
    """
    names = {CHECK_CHAIN, CHECK_FORMAT, CHECK_LINKS, CHECK_SANDBOX}
    unknown = names - set(DETERMINISTIC_CHECK_IDS)
    if unknown:
        raise RuntimeError(f"check_id di luar DETERMINISTIC_CHECK_IDS: {sorted(unknown)}")


_assert_check_ids()


def excerpt(text: str, limit: int = MAX_EXCERPT_LEN) -> str:
    """Kutipan teks pihak yang AMAN untuk disimpan di memori dan dirender.

    - karakter non-printable (kontrol C0/C1 DAN kategori format seperti U+200B/U+202E)
      diganti spasi — `str.isprintable()` sudah `False` untuk keduanya;
    - deretan whitespace diciutkan jadi satu spasi supaya newline tidak memalsukan baris
      log/laporan baru;
    - dipotong pada `limit` dengan penanda `…` (karakter cetak, jadi tetap lolos validasi
      `Evidence.proof`).

    Sanitasi ada di SATU tempat ini supaya "teks pihak yang menyamar jadi struktur kita"
    tidak punya jalur kedua.
    """
    if not isinstance(text, str):
        raise TypeError(f"excerpt hanya menerima string, dapat {type(text).__name__}")
    limit = max(1, min(int(limit), MAX_PROOF_LEN))
    cleaned = "".join(ch if ch.isprintable() else " " for ch in text)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1].rstrip() + "…"
    return cleaned


def normalize_heading(heading: str) -> str:
    """Judul → huruf kecil, tanpa tanda baca tepi, whitespace tunggal.

    Dipakai HANYA untuk mencocokkan judul dengan katalog KONSTAN; tidak pernah menjadi
    kunci memori, nama file, atau bagian perintah.
    """
    cleaned = "".join(ch if ch.isprintable() else " " for ch in heading)
    cleaned = " ".join(cleaned.split()).strip().lower()
    return cleaned.strip("#*_`:.,;!?-–— ")


@dataclass(frozen=True)
class Section:
    """Satu bagian deliverable. `index` 0 = pembuka (teks sebelum judul pertama)."""

    index: int
    heading: str
    body: str
    line: int

    @property
    def slug(self) -> str:
        return normalize_heading(self.heading)

    @property
    def text(self) -> str:
        return f"{self.heading}\n{self.body}" if self.heading else self.body


@dataclass(frozen=True)
class Document:
    """Deliverable yang sudah diurai jadi bagian. `text` disimpan APA ADANYA (byte-exact)."""

    text: str
    sections: tuple[Section, ...]

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.slug for s in self.sections if s.heading)


def parse_document(text: str) -> Document:
    """Membelah deliverable pada judul gaya markdown (`#`..`######`).

    Deliverable TANPA judul sama sekali tetap menghasilkan satu bagian (index 0), sehingga
    tidak ada jalur "dokumen aneh → nol bagian → nol cek → lolos diam-diam".
    """
    if not isinstance(text, str):
        raise TypeError(f"deliverable harus string, dapat {type(text).__name__}")
    sections: list[Section] = []
    heading = ""
    start_line = 1
    buffer: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = _HEADING_RE.match(line)
        if match is None:
            buffer.append(line)
            continue
        if heading or "".join(buffer).strip():
            sections.append(Section(len(sections), heading, "\n".join(buffer), start_line))
        heading = match.group(2)
        start_line = lineno
        buffer = []
    if heading or "".join(buffer).strip() or not sections:
        sections.append(Section(len(sections), heading, "\n".join(buffer), start_line))
    return Document(text=text, sections=tuple(sections))


def sections_in_scope(document: Document, depth: str) -> tuple[Section, ...]:
    """Terjemahan `check_depth()` menjadi cakupan baca yang konkret.

    `full` = seluruh bagian. `sampling` = `SAMPLING_SECTION_LIMIT` bagian pertama.
    Kedalaman yang TIDAK dikenal melempar, bukan diam-diam jatuh ke sampling: menebak ke
    arah yang lebih longgar adalah persis kesalahan yang spec §3 aturan 5 larang.
    """
    if depth == DEPTH_FULL:
        return document.sections
    if depth == DEPTH_SAMPLING:
        return document.sections[:SAMPLING_SECTION_LIMIT]
    raise ValueError(f"kedalaman cek tidak dikenal: {depth!r}")


@dataclass(frozen=True)
class CheckResult:
    """Hasil SATU cek deterministik atas SATU kriteria.

    `pattern_id` hanya diisi untuk temuan yang GAGAL, dan bentuknya dibatasi
    `PATTERN_ID_RE` — cermin `memory_policy.validate_pattern_id`, karena nilai ini
    berakhir sebagai komponen nama entity karantina `f"{addr}:{pattern}"`.
    """

    check_id: str
    criterion_id: str
    status: str
    detail: str
    proof: str = ""
    pattern_id: str | None = None
    section_index: int | None = None
    depth: str = DEPTH_FULL

    def __post_init__(self) -> None:
        if self.check_id not in DETERMINISTIC_CHECK_IDS:
            raise ValueError(
                f"check_id {self.check_id!r} bukan cek deterministik "
                f"{sorted(DETERMINISTIC_CHECK_IDS)} — record_job_outcome akan menolaknya"
            )
        if self.status not in VALID_STATUSES:
            raise ValueError(f"status hasil cek tidak sah: {self.status!r}")
        if not isinstance(self.criterion_id, str) or not self.criterion_id:
            raise ValueError("criterion_id wajib diisi")
        if len(self.proof) > MAX_PROOF_LEN:
            raise ValueError(f"proof melebihi {MAX_PROOF_LEN} karakter")
        if any(not ch.isprintable() for ch in self.proof):
            raise ValueError("proof memuat karakter non-printable — lewatkan `excerpt()` dulu")
        if self.pattern_id is not None and not PATTERN_ID_RE.match(self.pattern_id):
            raise ValueError(f"pattern_id tidak sah: {self.pattern_id!r}")
        if self.status == STATUS_FAIL and self.pattern_id is None:
            raise ValueError("temuan gagal WAJIB punya pattern_id (dipakai record_suspicion)")

    @property
    def failed(self) -> bool:
        return self.status == STATUS_FAIL

    def to_body(self) -> dict[str, object]:
        """Bentuk JSON-able untuk bundel bukti (`reasonHash`, task 2.5) dan log."""
        return {
            "check": self.check_id,
            "criterion": self.criterion_id,
            "status": self.status,
            "detail": self.detail,
            "proof": self.proof,
            "pattern": self.pattern_id or "",
            "section": -1 if self.section_index is None else int(self.section_index),
            "depth": self.depth,
        }
