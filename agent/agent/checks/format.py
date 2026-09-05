"""Cek `format` — kelengkapan struktur & sisa pekerjaan (spec §5 langkah 3, §7 langkah 1).

Ini cek yang menjawab AC 2.3 "setengah-jadi gagal di kelengkapan": deliverable yang
kehilangan bagian wajib atau masih memuat penanda pekerjaan (`TODO`, `TBD`, `lorem
ipsum`, `<isi di sini>`) DITOLAK tanpa satu pun panggilan jaringan.

Semua `check_id` di sini = `format` (himpunan konstan `DETERMINISTIC_CHECK_IDS`).

Kedalaman:
  - kelengkapan bagian membaca DAFTAR JUDUL, yang selalu terlihat di kedua kedalaman —
    bagian yang hilang seluruhnya adalah cacat KASAR dan tidak boleh bisa disembunyikan
    dengan cara menaruhnya jauh di belakang;
  - penanda pekerjaan hanya dicari di bagian yang berada DALAM CAKUPAN (`sections_in_scope`),
    jadi `TODO` di bagian ke-5 lolos saat `sampling` dan tertangkap saat `full`. Itulah
    cacat HALUS pada spec §7 langkah 4.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from agent.checks.base import (
    CHECK_FORMAT,
    STATUS_FAIL,
    STATUS_PASS,
    CheckResult,
    Document,
    Section,
    excerpt,
    normalize_heading,
)

__all__ = [
    "PATTERN_MISSING_SECTION",
    "PATTERN_PLACEHOLDER",
    "check_placeholders",
    "check_required_sections",
]

# Id pola untuk `record_suspicion` — himpunan KONSTAN, bentuknya mematuhi
# `memory_policy.PATTERN_ID_RE` (huruf kecil / angka / `._-`).
PATTERN_MISSING_SECTION: Final = "format.missing-section"
PATTERN_PLACEHOLDER: Final = "format.placeholder-text"

_PLACEHOLDER_RE: Final = re.compile(
    r"(?i)(?:\b(?:todo|tbd|fixme|wip|lorem ipsum|coming soon|placeholder|to be filled)\b"
    r"|<[a-z][a-z0-9 _-]{2,30}>)"
)


def check_required_sections(
    document: Document,
    required: Sequence[str],
    criterion_id: str,
    depth: str,
) -> CheckResult:
    """Semua judul wajib hadir? Judul dicocokkan setelah dinormalkan, bukan persis.

    Dicocokkan dengan awalan (`startswith`) supaya "Sources & references" memenuhi
    "sources", tetapi TIDAK sebaliknya: judul yang lebih pendek dari yang diminta tidak
    pernah dianggap memenuhi.
    """
    present = document.headings
    missing = [
        want
        for want in (normalize_heading(str(r)) for r in required)
        if not any(h.startswith(want) for h in present)
    ]
    if missing:
        return CheckResult(
            check_id=CHECK_FORMAT,
            criterion_id=criterion_id,
            status=STATUS_FAIL,
            detail=f"bagian wajib hilang: {missing}; judul yang ada: {list(present)}",
            proof=excerpt("judul yang ada: " + ", ".join(present) if present else "tanpa judul"),
            pattern_id=PATTERN_MISSING_SECTION,
            depth=depth,
        )
    return CheckResult(
        check_id=CHECK_FORMAT,
        criterion_id=criterion_id,
        status=STATUS_PASS,
        detail=f"seluruh {len(required)} bagian wajib hadir",
        depth=depth,
    )


def check_placeholders(
    scope: Sequence[Section],
    criterion_id: str,
    depth: str,
) -> CheckResult:
    """Penanda pekerjaan yang belum selesai di bagian yang tersampling/terbaca."""
    for section in scope:
        match = _PLACEHOLDER_RE.search(section.text)
        if match is None:
            continue
        return CheckResult(
            check_id=CHECK_FORMAT,
            criterion_id=criterion_id,
            status=STATUS_FAIL,
            detail=(
                f"penanda pekerjaan {match.group(0)!r} pada bagian "
                f"{section.index} ({section.slug or 'pembuka'})"
            ),
            proof=excerpt(_around(section.text, match.start())),
            pattern_id=PATTERN_PLACEHOLDER,
            section_index=section.index,
            depth=depth,
        )
    return CheckResult(
        check_id=CHECK_FORMAT,
        criterion_id=criterion_id,
        status=STATUS_PASS,
        detail=f"tanpa penanda pekerjaan pada {len(scope)} bagian yang dibaca",
        depth=depth,
    )


def _around(text: str, position: int, width: int = 60) -> str:
    start = max(0, position - width // 2)
    return text[start : start + width]
