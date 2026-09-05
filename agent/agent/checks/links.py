"""Cek `links` — tautan sumber yang bisa dipertanggungjawabkan (spec §5 langkah 3).

Yang DIPERIKSA di 2.3-min, tanpa satu pun paket baru dan tanpa jaringan secara default:
  1. bagian sumber yang wajib memuat tautan benar-benar memuat tautan;
  2. skema tautan ada di daftar KONSTAN (`https`, `ipfs`) — `http://`, `file://`,
     `javascript:`, `data:` ditolak;
  3. host tidak menunjuk ke dalam mesin/jaringan kita sendiri (localhost, 127/8, 10/8,
     172.16/12, 192.168/16, 169.254/16, `::1`, `.local`, `.internal`) — deliverable
     TIDAK BOLEH mengarahkan pembaca (atau alat lain) ke jaringan internal evaluator;
  4. tidak ada userinfo `user:pass@host` dan tidak ada karakter non-ASCII di host
     (homograf/punycode yang menyamar).

Yang TIDAK diperiksa, dan tidak boleh diklaim diperiksa: KEHIDUPAN tautan. Probe HTTP =
jalur gagal baru + latensi di anggaran 901 detik (ADR-014) + evaluator yang bisa disuruh
mengetuk alamat pilihan pihak lain (SSRF). Karena itu liveness hanya jalan bila pemanggil
MENYUNTIKKAN `probe`; tanpa itu hasilnya dilaporkan apa adanya sebagai struktur saja.

Cakupan mengikuti kedalaman: tautan busuk di bagian belakang lolos saat `sampling` dan
tertangkap saat `full` (spec §7 langkah 4).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Final

from agent.checks.base import (
    CHECK_LINKS,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNVERIFIED,
    CheckResult,
    Section,
    excerpt,
)

__all__ = [
    "ALLOWED_SCHEMES",
    "PATTERN_LINK_DEAD",
    "PATTERN_LINK_UNSAFE",
    "PATTERN_NO_SOURCE_LINK",
    "check_links",
]

PATTERN_LINK_UNSAFE: Final = "links.unsafe-url"
PATTERN_NO_SOURCE_LINK: Final = "links.missing-source"
PATTERN_LINK_DEAD: Final = "links.dead-url"

ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"https", "ipfs"})

# Semua yang berbentuk `skema://…`, apa pun skemanya — termasuk skema terlarang, supaya
# ia bisa DILAPORKAN, bukan diam-diam tidak terlihat.
_URL_RE: Final = re.compile(r"(?i)\b([a-z][a-z0-9+.-]{1,15}):(//)?([^\s<>\"'\)\]\}]+)")

_PRIVATE_HOST_RE: Final = re.compile(
    r"(?i)^(?:localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|169\.254\.\d+\.\d+|0\.0\.0\.0|\[?::1\]?"
    r"|.*\.local|.*\.internal|.*\.localdomain)$"
)

# Skema yang WAJIB memakai `//` (URL berbasis host). `ipfs://<cid>` juga memakainya di
# artefak kita, jadi `//` diwajibkan untuk keduanya dan `mailto:`/`javascript:` jatuh ke
# cabang "skema tidak diizinkan" — bukan ke cabang "host kosong" yang membingungkan.
_LinkProbe = Callable[[str], bool]


def _authority_of(rest: str) -> str:
    """Bagian `[userinfo@]host[:port]` sebuah URL, apa adanya."""
    return rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]


def _host_of(authority: str) -> str:
    """Host saja: TANPA userinfo dan TANPA port.

    Port dibuang eksplisit — kalau tidak, seluruh daftar host internal bisa dilewati
    hanya dengan menambahkan `:8545`. Yang dibuang HANYA port yang benar-benar angka,
    supaya `user:pass@host` tidak berubah bentuk sebelum sempat ditolak. IPv6 literal
    (`[::1]:8545`) ditangani terpisah karena `:` di dalamnya bukan pemisah port.
    """
    host = authority.rsplit("@", 1)[-1]
    if host.startswith("["):
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    head, sep, tail = host.rpartition(":")
    return head if sep and tail.isdigit() else host


def _unsafe_reason(scheme: str, slashes: str, rest: str) -> str | None:
    """Alasan sebuah tautan ditolak, atau `None` bila bentuknya sah."""
    scheme = scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        return f"skema {scheme!r} di luar {sorted(ALLOWED_SCHEMES)}"
    if not slashes:
        return f"skema {scheme!r} tanpa `//`"
    authority = _authority_of(rest)
    if not authority:
        return "host kosong"
    if "@" in authority:
        return "memuat userinfo `user:pass@host`"
    host = _host_of(authority)
    if not host:
        return "host kosong"
    if any(ord(ch) > 127 for ch in host):
        return "host memuat karakter non-ASCII (homograf)"
    if scheme == "https" and _PRIVATE_HOST_RE.match(host):
        return f"host {host!r} menunjuk jaringan internal/loopback"
    if scheme == "ipfs" and not re.fullmatch(r"[A-Za-z0-9]{16,}", host):
        return f"CID ipfs {host!r} tidak berbentuk"
    return None


def check_links(
    scope: Sequence[Section],
    criterion_id: str,
    depth: str,
    required_link_sections: Sequence[str] = (),
    probe: _LinkProbe | None = None,
) -> CheckResult:
    """Satu hasil untuk seluruh tautan di cakupan. Temuan PERTAMA yang gagal yang dilaporkan."""
    required = {str(s).lower() for s in required_link_sections}
    seen: list[str] = []
    sections_with_links: set[str] = set()

    for section in scope:
        for match in _URL_RE.finditer(section.text):
            scheme, slashes, rest = match.group(1), match.group(2) or "", match.group(3)
            url = f"{scheme}:{slashes}{rest}"
            seen.append(url)
            sections_with_links.add(section.slug)
            reason = _unsafe_reason(scheme, slashes, rest)
            if reason is not None:
                return CheckResult(
                    check_id=CHECK_LINKS,
                    criterion_id=criterion_id,
                    status=STATUS_FAIL,
                    detail=f"tautan ditolak pada bagian {section.index}: {reason}",
                    proof=excerpt(f"{url} | {reason}"),
                    pattern_id=PATTERN_LINK_UNSAFE,
                    section_index=section.index,
                    depth=depth,
                )
            if probe is not None and not probe(url):
                return CheckResult(
                    check_id=CHECK_LINKS,
                    criterion_id=criterion_id,
                    status=STATUS_FAIL,
                    detail=f"tautan tidak hidup pada bagian {section.index}",
                    proof=excerpt(url),
                    pattern_id=PATTERN_LINK_DEAD,
                    section_index=section.index,
                    depth=depth,
                )

    missing = sorted(
        want
        for want in required
        if any(s.slug.startswith(want) for s in scope)
        and not any(s.startswith(want) for s in sections_with_links)
    )
    if missing:
        return CheckResult(
            check_id=CHECK_LINKS,
            criterion_id=criterion_id,
            status=STATUS_FAIL,
            detail=f"bagian sumber {missing} tidak memuat satu pun tautan",
            proof=excerpt(f"bagian tanpa tautan: {', '.join(missing)}"),
            pattern_id=PATTERN_NO_SOURCE_LINK,
            depth=depth,
        )

    if not seen:
        return CheckResult(
            check_id=CHECK_LINKS,
            criterion_id=criterion_id,
            status=STATUS_UNVERIFIED,
            detail=f"tidak ada tautan pada {len(scope)} bagian yang dibaca (depth={depth})",
            depth=depth,
        )
    liveness = "struktur + liveness" if probe is not None else "struktur saja (tanpa probe)"
    return CheckResult(
        check_id=CHECK_LINKS,
        criterion_id=criterion_id,
        status=STATUS_PASS,
        detail=f"{len(seen)} tautan lolos {liveness}",
        depth=depth,
    )
