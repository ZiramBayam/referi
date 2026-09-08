"""Penjaga naskah dua varian destruktif `make demo` (task 3.3b).

`sim/` belum punya runner tes sendiri (README butir 18), sementara yang dijaga di sini
adalah KALIMAT dan URUTAN — dua hal yang bisa hilang tanpa satu pun tes lain memerah:

  - baris keluaran VARIAN B DIKUNCI oleh ADR-020 keputusan 8 + ADR-024 konsekuensi
    terakhir. "Ditolak dengan aman" adalah peringkasan yang dilarang: ia menghapus
    akibat (job menggantung) dan jalan keluarnya (pulih dari backup);
  - varian B WAJIB dipicu aturan (a) ADR-024 keputusan 2 (file HILANG), bukan aturan
    (b) yang sudah DICABUT;
  - penghapusan memori WAJIB menyapu KETIGA file (`memory.db`, `-wal`, `-shm`);
  - URUTAN: tidak boleh ada alat yang menyentuh path DB varian B sebelum agen membaca
    gerbangnya. `MemoryClient.local(path)` MEMBUAT filenya, jadi satu pembacaan lebih
    dulu mengubah `missing` menjadi `ada (kosong)` dan varian B gugur DIAM-DIAM: gerbang
    mencetak `safe`, file lahir, gerbang berikutnya `normal`, transaksi terbangun.
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEMO_TS = REPO_ROOT / "sim" / "src" / "demo.ts"

# Apa adanya, sampai tanda baca. Placeholder nonce sengaja dibiarkan sebagai ekspresi
# template supaya tes ini menjaga KALIMATNYA, bukan angkanya.
LOCKED_VARIANT_B_LINE = (
    "`VARIAN B: MODE AMAN, 0 tx baru, nonce ${varianB.nonceBefore} -> ${varianB.nonceAfter}, ` +\n"
    '      "job menggantung sampai expiredAt, pulih dengan memory.db dari backup"'
)


def demo_source() -> str:
    return DEMO_TS.read_text(encoding="utf-8")


def test_variantB_line_isPrintedVerbatim_notSummarized():
    source = demo_source()
    assert LOCKED_VARIANT_B_LINE in source
    # Peringkasan yang DILARANG ADR-020 keputusan 8.
    assert "ditolak dengan aman" not in source.lower()


def test_bothVariantsArePrinted_withDifferentTransactionCounts():
    source = demo_source()
    assert "VARIAN A:" in source
    assert "VARIAN B:" in source
    # Varian A menghitung tx dari nonce agen di rantai lokal; varian B dari nonce Sepolia.
    assert "nonceLocalAfter - nonceLocalBefore" in source
    assert "varianB.nonceAfter - varianB.nonceBefore" in source


def test_variantB_isTriggeredByTheMissingFileRule_notTheRevokedOne():
    source = demo_source()
    assert "memori lokal hilang .* → memori dihapus" in source
    assert "gerbang memori: mode=safe" in source


def test_memoryWipeCoversAllThreeFiles():
    source = demo_source()
    assert 'const MEMORY_DB_SUFFIXES = ["", "-wal", "-shm"] as const;' in source
    # Tiga penghapusan: job D, job E, dan varian B — semuanya lewat daftar yang sama.
    assert len(re.findall(r"for \(const suffix of MEMORY_DB_SUFFIXES\) rmSync", source)) == 3


def test_variantB_readsTheGateBeforeAnythingTouchesTheDbPath():
    """Urutan di dalam `runVariantB`: hapus → buktikan hilang → agen. Tidak ada yang lain."""
    source = demo_source()
    body = source.split("async function runVariantB()", 1)[1].split("\ntype StepRow", 1)[0]
    # Satu-satunya sentuhan ke path DB sebelum agen adalah rmSync + existsSync, dan
    # keduanya TIDAK membuat file.
    assert body.index("rmSync") < body.index("existsSync") < body.index("agent.vault_client")
    for pembuat_file in ("memory_export", "MemoryClient", "memory_root_check"):
        assert pembuat_file not in body


def test_variantB_usesTheFrozenVault_andASeparateWorkdir():
    source = demo_source()
    assert '"0x5c6EE4586ACABcb6326069c229E58091B21ef384" as Address' in source
    assert 'const VARIANT_B_DB = join(VARIANT_B_ROOT, "memory.db");' in source
    # `.env` TIDAK boleh diwarisi untuk lokasi memori/artefak.
    assert "SIBYL_DB_PATH: VARIANT_B_DB," in source
