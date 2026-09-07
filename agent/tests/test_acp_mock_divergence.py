"""Penjaga divergensi SENGAJA antara mock ACP dan ACP nyata.

Mock `contracts/test/mocks/AgenticCommerce.sol` sengaja TIDAK mengimplementasikan
`jobCounter()` (ACP nyata punya, `docs/api-facts.md` §A). Alasannya ada di NatSpec mock:
semantiknya BEDA dari `nextJobId` milik mock (id TERAKHIR vs id BERIKUTNYA), dan
`nextJobId - 1` hanyalah tebakan kami — bukan fakta terverifikasi — yang lagi pula
underflow saat belum ada job.

Konsekuensinya nyata: kode produksi yang memanggil `jobCounter()` HIJAU melawan Base
Sepolia tapi REVERT melawan Anvil (mock tidak punya fallback), yaitu tepat di `make demo`.
Penjaga di bawah membuat kegagalan itu muncul saat `make test`, bukan saat demo:
begitu ada pemanggil `jobCounter` di `agent/agent/` atau `sim/src/`, tes ini MERAH dan
menuntut keputusan sadar (tambah fungsi ke mock lewat api-verifier, atau jangan panggil).
"""

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

FORBIDDEN_SYMBOL = "job" + "Counter"  # dipecah supaya berkas tes ini tidak menjaring dirinya

# Yang dijaring adalah PEMANGGILAN, bukan penyebutan. `jobCounter(` menangkap panggilan
# langsung dan fragmen ABI ("function jobCounter() view returns (uint256)"); `.jobCounter`
# menangkap bentuk web3.py/ethers yang menyerahkan fungsi tanpa langsung memanggilnya
# (`contract.functions.jobCounter`). Prosa yang menyebut nama getter ini di komentar
# sengaja DIBIARKAN — hari ini `sim/src/scenario.ts:27` melakukannya untuk menjelaskan
# kenapa jobId tidak idempoten, dan memerahkannya hanya akan mengajari orang menghapus
# komentar yang benar.
CALL_SITE = re.compile(r"\.\s*" + FORBIDDEN_SYMBOL + r"\b|\b" + FORBIDDEN_SYMBOL + r"\s*\(")

# Pohon kode yang dieksekusi melawan Anvil lewat `make demo`.
SCANNED_TREES = (
    (REPO_ROOT / "agent" / "agent", ("*.py",)),
    (REPO_ROOT / "sim" / "src", ("*.ts", "*.mts", "*.mjs", "*.js")),
)

MOCK_PATH = REPO_ROOT / "contracts" / "test" / "mocks" / "AgenticCommerce.sol"


def _scan(root: pathlib.Path, patterns: tuple[str, ...]) -> list[str]:
    """Kembalikan `path:baris` tiap kemunculan simbol terlarang di bawah `root`."""
    hits: list[str] = []
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if CALL_SITE.search(line):
                    shown = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
                    hits.append(f"{shown}:{lineno}: {line.strip()}")
    return hits


@pytest.mark.parametrize("root,patterns", SCANNED_TREES, ids=lambda v: str(v)[-24:])
def test_scanned_tree_is_not_empty(root: pathlib.Path, patterns: tuple[str, ...]) -> None:
    """Penjaga atas penjaga: pohon yang dipindai HARUS ada dan berisi berkas.

    Tanpa ini, memindahkan/mengganti nama `sim/src` membuat pemindainya hijau abadi
    atas nol berkas — hijau palsu yang persis mematikan gunanya.
    """
    assert root.is_dir(), f"{root} tidak ada — pemindai memindai kekosongan"
    found = [p for pattern in patterns for p in root.rglob(pattern)]
    assert found, f"{root} tidak berisi berkas {patterns} — pemindai memindai kekosongan"


@pytest.mark.parametrize(
    "source",
    [
        "value = contract.functions." + FORBIDDEN_SYMBOL + "().call()",
        "fn = contract.functions." + FORBIDDEN_SYMBOL,
        'ABI = ["function ' + FORBIDDEN_SYMBOL + '() view returns (uint256)"]',
        "const n = await acp." + FORBIDDEN_SYMBOL + "();",
    ],
)
def test_scanner_finds_a_caller_when_there_is_one(tmp_path: pathlib.Path, source: str) -> None:
    """Kontrol positif: pemindainya benar-benar menggigit tiap bentuk pemanggilan."""
    (tmp_path / "caller.py").write_text(source + "\n", encoding="utf-8")
    assert _scan(tmp_path, ("*.py",)) != []


def test_scanner_lets_prose_mentions_through(tmp_path: pathlib.Path) -> None:
    """Kontrol negatif: menyebut nama getter di komentar BUKAN pemanggilan."""
    (tmp_path / "prose.py").write_text(
        "# `" + FORBIDDEN_SYMBOL + "` ACP menaik dan tidak bisa diputar balik\n",
        encoding="utf-8",
    )
    assert _scan(tmp_path, ("*.py",)) == []


def test_no_production_caller_of_the_missing_acp_getter() -> None:
    hits = [line for root, patterns in SCANNED_TREES for line in _scan(root, patterns)]
    assert hits == [], (
        f"`{FORBIDDEN_SYMBOL}()` TIDAK ADA di mock ACP "
        "(contracts/test/mocks/AgenticCommerce.sol) dan panggilan ini akan REVERT di "
        "Anvil, termasuk saat `make demo`. Divergensinya SENGAJA: semantik `jobCounter` "
        "(id terakhir) != `nextJobId` (id berikutnya), dan `nextJobId - 1` adalah tebakan "
        "yang underflow saat nol job. Kalau getter ini memang dibutuhkan: minta "
        "@agent-api-verifier mencatat semantiknya, lalu tambahkan ke mock — jangan "
        "menghapus tes ini.\nPemanggil:\n" + "\n".join(hits)
    )


def test_mock_documents_the_deliberate_divergence() -> None:
    """NatSpec mock WAJIB menyebut divergensi ini, supaya tidak ditemukan ulang."""
    text = MOCK_PATH.read_text(encoding="utf-8")
    assert FORBIDDEN_SYMBOL in text
