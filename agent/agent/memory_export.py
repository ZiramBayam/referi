"""Ekspor memori yang bisa diaudit siapa pun — task 2.1b (spec §3 baris 123-124).

Spec §3 menutup bagian memori dengan satu kalimat klaim:
*"Siapa pun bisa merekonstruksi root dari file memori yang dipublikasikan/diaudit."*
Modul ini adalah pembuktian kalimat itu, dan tidak lebih dari itu: ia menulis SATU file JSON
kanonik berisi seluruh himpunan yang dijangkar `memory_root` (ADR-020 keputusan 7 — semua
entity `provider`, semua `reference:pattern:*`, semua `reference:rubric:*`, termasuk pattern
YATIM), lalu menghitung ulang root DARI FILE ITU. Tanpa IPFS, tanpa UI, tanpa publikasi.

Empat batas yang menentukan bentuk modul ini (semuanya dari review 2.1r, bukan preferensi):

1. SATU PEMBACAAN DB — dan hanya SEJAUH ITU. Yang dijamin modul ini: file ekspor dan root
   diserialkan/dihash dari objek `MemorySnapshot` yang SAMA, jadi tidak ada pembacaan DB kedua
   yang bisa menyelipkan keadaan lain di antara keduanya.
   YANG BELUM TERTUTUP, dan jangan dibaca lebih besar dari ini: balapan DI DALAM
   `load_snapshot` sendiri. Ia melakukan 1x `list_entities` + 2x `search` + N x `get_reference`
   dan Sibyl 0.7.0 TIDAK punya transaksi (api-facts §C), sehingga tulisan yang mendarat di
   tengah rangkaian itu — persis yang dilakukan `promote_suspicions` DARI PROSES YANG SAMA —
   menghasilkan snapshot yang memuat provider versi lama, kehilangan provider yang ditulis
   belakangan, tetapi ikut menjangkar reference barunya. Root untuk keadaan yang tidak pernah
   ada, dan file ekspornya cocok dengan root itu sehingga TIDAK terlihat dari file. Penutupnya
   (kunci single-instance atas `memory.db`) adalah task 2.4a keputusan (i); modul ini tidak
   bisa dan tidak berpura-pura menutupnya.

2. SATU IMPLEMENTASI ROOT. Root dihitung lewat `memory_policy.memory_root_for_onchain()` —
   GERBANG yang sama yang dipakai `vault_client`/`postVerdict` (task 2.4b). Bukan sekadar
   "fungsi yang sama": bila suatu saat encoding dibuka kembali, gerbang itu MELEMPAR, dan
   alat ekspor ikut berhenti alih-alih menerbitkan angka yang tidak boleh dijanjikan
   siapa pun. Modul ini tidak punya salinan encoding apa pun.

3. VALIDASI YANG SAMA DI KEDUA ARAH. Membaca kembali file ekspor lewat
   `MemorySnapshot.from_export_obj`, yang sejak 2.1b memvalidasi nama provider dan awalan kunci
   lewat `from_mapping` — alat audit tidak boleh menerima file yang agen sendiri tolak.

4. KUNCI TANPA ESCAPE DI SUMBER. Lihat `assert_no_escaped_object_keys` di bawah.

Modul ini MURNI baca: ia tidak pernah menulis ke memori, tidak menyentuh jaringan/chain/LLM,
dan tidak pernah membaca entity `suspicion` (ADR-002) — satu-satunya pintu bacanya
`memory_policy.load_snapshot`, yang berjalan di atas `DecisionMemoryView`.

Pakai:
    uv run python -m agent.memory_export --db ./data/memory.db --out /tmp/mem.json
    uv run python -m agent.memory_export --check /tmp/mem.json      # hanya hitung ulang
    node agent/tools/memory_root_check.mjs /tmp/mem.json            # hitung ulang di luar Python
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sibyl_memory_client import MemoryClient

from agent.memory_policy import (
    MEMORY_ROOT_ENCODING_VERSION,
    MemoryIntegrityError,
    MemoryPolicyError,
    MemorySnapshot,
    load_snapshot,
    memory_root_for_onchain,
)

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 2


class MemoryExportError(MemoryPolicyError):
    """Ekspor/audit gagal dengan alasan yang bisa dibaca manusia (bukan traceback)."""


# ----------------------------------------------------------------------
# Kunci objek TIDAK BOLEH ber-escape DI SUMBER JSON
# ----------------------------------------------------------------------
# `BODY_KEY_RE` di `memory_policy` sudah melarang kunci yang BUTUH escape sesudah didekode.
# Yang tersisa — dan yang dibuktikan nyata di review 2.1r — adalah kunci yang DITULIS dengan
# escape padahal hasil dekodenya legal, mis. `{"kB": …}` yang mendekode jadi `kB`.
# Sebabnya konkret: V8 mengintern nama properti ber-backslash LINTAS panggilan `JSON.parse`
# dalam satu isolate, sehingga dokumen yang diparse belakangan bisa membaca nama properti
# hasil intern milik dokumen sebelumnya. `agent/tools/memory_root_check.mjs` tidak terpapar
# (satu parse per proses), tetapi `web/` adalah isolate berumur panjang yang mem-`JSON.parse`
# banyak ekspor — persis prasyarat pemicunya (dicatat juga di TASKS.md 2.4b).
# Karena itu dua kewajiban, dan keduanya ada di sini:
#   - EKSPORTIR menjamin: keluarannya diperiksa sebelum ditulis, bukan sekadar "seharusnya
#     tidak mungkin karena `BODY_KEY_RE`";
#   - ALAT AUDIT menolak file yang melanggarnya DI SUMBER, bukan hanya menolak dekode ilegal.
# Pemeriksaannya di atas TEKS, sebelum `json.loads`, karena sesudah dekode buktinya hilang.

_WHITESPACE = " \t\r\n"


def _iter_json_strings(text: str) -> Iterator[tuple[int, str, bool]]:
    """(offset, potongan sumber apa adanya termasuk kutip, apakah ia NAMA properti).

    Di JSON yang sah, string yang diikuti `:` selalu nama properti dan tidak pernah nilai —
    jadi pemindaian ini tidak perlu tahu struktur dokumen sama sekali.
    """
    i, n = 0, len(text)
    while i < n:
        if text[i] != '"':
            i += 1
            continue
        start = i
        i += 1
        while i < n:
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == '"':
                break
            i += 1
        if i >= n:
            raise MemoryExportError("file ekspor bukan JSON yang sah (string tidak ditutup)")
        raw = text[start : i + 1]
        i += 1
        j = i
        while j < n and text[j] in _WHITESPACE:
            j += 1
        yield start, raw, j < n and text[j] == ":"


def escaped_object_keys(text: str) -> list[str]:
    """Nama properti di SUMBER yang memuat escape atau byte non-ASCII/kontrol."""
    bad: list[str] = []
    for _, raw, is_key in _iter_json_strings(text):
        if not is_key:
            continue
        if "\\" in raw or any(ch < "\x20" or ch > "\x7e" for ch in raw):
            bad.append(raw)
    return bad


def assert_no_escaped_object_keys(text: str) -> None:
    bad = escaped_object_keys(text)
    if bad:
        raise MemoryIntegrityError(
            f"nama properti {bad[0]} butuh escape di SUMBER JSON; encoding ini melarangnya "
            "(nama properti ber-backslash bisa didekode berbeda oleh JSON.parse yang "
            "mengintern nama lintas dokumen)"
        )


# ----------------------------------------------------------------------
# Serialisasi & pembacaan ulang
# ----------------------------------------------------------------------


def export_text(snapshot: MemorySnapshot) -> str:
    """Teks file ekspor untuk SATU snapshot — deterministik byte per byte.

    `sort_keys` + `ensure_ascii` + pemisah tanpa spasi: hasilnya bebas locale dan bisa
    dibandingkan dengan `diff`/`sha256sum` antar mesin. Nilainya sudah bebas bilangan JSON
    (`to_canonical_obj` mengubah setiap integer jadi `{"$u":"<desimal>"}`), sehingga uint256
    di atas 2^53 selamat melewati `JSON.parse`.
    """
    text = json.dumps(
        snapshot.to_canonical_obj(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert_no_escaped_object_keys(text)  # kewajiban EKSPORTIR, bukan asumsi
    return text + "\n"


def snapshot_from_text(text: str) -> MemorySnapshot:
    """Kebalikan `export_text` — jalur ALAT AUDIT.

    Urutannya penting: sumber diperiksa DULU (kunci ber-escape), baru didekode; sesudah
    `json.loads` tidak ada lagi cara membedakan `"kB"` dari `"k\\u0042"`.
    """
    assert_no_escaped_object_keys(text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MemoryExportError(f"file ekspor bukan JSON yang sah: {exc}") from exc
    if not isinstance(obj, dict):
        raise MemoryExportError("file ekspor harus objek JSON di level teratas")
    return MemorySnapshot.from_export_obj(obj)


def root_hex(snapshot: MemorySnapshot) -> str:
    """`0x` + keccak preimage — SATU pintu root (`memory_root_for_onchain`, ADR-020 kep. 6)."""
    return "0x" + memory_root_for_onchain(snapshot).hex()


def root_from_text(text: str) -> str:
    """Root yang dihitung ULANG dari isi file — jalur yang ditiru `memory_root_check.mjs`."""
    return root_hex(snapshot_from_text(text))


def root_from_file(path: str | Path) -> str:
    file = Path(path)
    if not file.is_file():
        raise MemoryExportError(f"file ekspor tidak ditemukan: {file}")
    try:
        text = file.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # `memory_root_check.mjs` menolak byte UTF-8 ilegal juga (Node akan diam-diam
        # menggantinya dengan U+FFFD kalau tidak dijaga). Dua alat, satu jawaban.
        raise MemoryExportError(f"file ekspor bukan UTF-8 yang sah: {exc}") from exc
    return root_from_text(text)


# ----------------------------------------------------------------------
# Ekspor dari DB
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ExportResult:
    """Hasil satu ekspor. `root` berasal dari `snapshot` yang SAMA dengan isi `text`."""

    snapshot: MemorySnapshot
    text: str
    root: str
    out_path: Path | None
    db_path: Path

    @property
    def counts(self) -> dict[str, int]:
        return {
            "providers": len(self.snapshot.providers),
            "patterns": len(self.snapshot.patterns),
            "rubrics": len(self.snapshot.rubrics),
        }


def open_memory(db_path: str | Path) -> MemoryClient:
    """`MemoryClient.local` (api-facts §C) dengan satu penjaga: DB harus SUDAH ADA.

    `MemoryClient.local` membuat DB baru dari nol bila filenya tidak ada. Di alat ekspor itu
    berbahaya secara diam-diam: salah ketik path menghasilkan file ekspor KOSONG yang tetap
    punya root sah — dan root memori kosong adalah persis yang muncul ketika memori dihapus.
    Alat audit yang menjawab "ini rootnya" untuk pertanyaan yang salah lebih buruk daripada
    alat audit yang berhenti.
    """
    db = Path(db_path)
    if db.is_dir():
        raise MemoryExportError(f"--db menunjuk direktori, bukan file DB: {db}")
    if not db.is_file():
        raise MemoryExportError(
            f"DB memori tidak ditemukan: {db} — jalankan agen dulu, atau tunjuk file yang ada "
            "dengan --db (alat ini sengaja TIDAK membuat DB baru)"
        )
    return MemoryClient.local(str(db))


def export_snapshot(snapshot: MemorySnapshot, out_path: str | Path | None, db_path: Path) -> ExportResult:
    """Menserialkan SATU objek snapshot dan menghitung rootnya dari objek yang SAMA."""
    text = export_text(snapshot)
    root = root_hex(snapshot)

    # Pemeriksaan silang di dalam proses: file yang baru dibuat harus memberi root yang sama
    # lewat jalur PEMBACA (parse + `from_export_obj`), bukan lewat jalur penulis.
    ulang = root_from_text(text)
    if ulang != root:
        raise MemoryIntegrityError(
            f"root dari snapshot ({root}) != root yang dihitung ulang dari file ({ulang})"
        )

    out = None
    if out_path is not None:
        out = Path(out_path)
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    log.info(
        "ekspor memori selesai",
        extra={"root": root, "out": str(out) if out else None, "db": str(db_path)},
    )
    return ExportResult(snapshot=snapshot, text=text, root=root, out_path=out, db_path=db_path)


def export_memory(db_path: str | Path, out_path: str | Path | None = None) -> ExportResult:
    """Ekspor lengkap: SATU `load_snapshot`, lalu file + root dari objek itu saja.

    Tidak ada pembacaan DB kedua di fungsi ini — itu batas 1 di docstring modul.
    """
    db = Path(db_path)
    client = open_memory(db)
    snapshot = load_snapshot(client)  # <- SATU-SATUNYA pembacaan DB
    return export_snapshot(snapshot, out_path, db)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agent.memory_export",
        description=(
            "Ekspor memori evaluator ke JSON kanonik dan hitung ulang memory_root dari file itu."
        ),
    )
    parser.add_argument("--db", help="path file memory.db (harus sudah ada)")
    parser.add_argument("--out", help="path file JSON hasil ekspor")
    parser.add_argument(
        "--check",
        metavar="FILE",
        help="hanya hitung ulang root dari file ekspor yang sudah ada (tanpa menyentuh DB)",
    )
    return parser


def main(argv: list[str] | None = None, *, stdout: Any = None) -> int:
    args = _build_parser().parse_args(argv)
    out = stdout or sys.stdout
    try:
        if args.check:
            if args.db or args.out:
                raise MemoryExportError("--check tidak dapat digabung dengan --db/--out")
            root = root_from_file(args.check)
            out.write(f"file       : {Path(args.check)}\n")
            out.write(f"encoding   : {MEMORY_ROOT_ENCODING_VERSION}\n")
            out.write(f"memory_root: {root}\n")
            return EXIT_OK
        if not args.db:
            raise MemoryExportError("--db wajib diisi (atau pakai --check FILE)")
        result = export_memory(args.db, args.out)
        counts = result.counts
        out.write(f"db         : {result.db_path}\n")
        out.write(f"out        : {result.out_path if result.out_path else '(tidak ditulis)'}\n")
        out.write(f"encoding   : {MEMORY_ROOT_ENCODING_VERSION}\n")
        out.write(
            "entri      : {providers} provider, {patterns} pattern, {rubrics} rubric\n".format(
                **counts
            )
        )
        out.write(f"memory_root: {result.root}\n")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001 - CLI: satu bentuk kegagalan, bukan traceback
        # Sengaja seluas ini. Auditor yang melihat "Python melempar traceback sementara Node
        # mencetak root" akan menyimpulkan Node yang benar; satu-satunya pesan yang boleh
        # keluar dari alat ini adalah `GAGAL: …` + exit 2, apa pun sebab teknisnya.
        log.debug("ekspor gagal", exc_info=True)
        sys.stderr.write(f"GAGAL: {type(exc).__name__}: {exc}\n")
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover - dijalankan lewat CLI
    raise SystemExit(main())
