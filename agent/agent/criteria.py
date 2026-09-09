"""Kriteria evaluasi + orkestrasi cek DETERMINISTIK (task 2.3-min).

Ruang lingkup dipotong PM 5 Sep: **cek deterministik SAJA, TANPA rubric LLM.** Modul ini
karena itu TIDAK mengimpor `anthropic`, tidak membaca kunci API, dan tidak punya jalur
apa pun yang mengirim teks ke model. Kriteria yang tidak bisa diperiksa secara
deterministik tetap DICATAT (`kind="qualitative"`) dan dilaporkan sebagai TIDAK DINILAI —
bukan diam-diam dianggap lolos.

Alur (spec §5 langkah 1 & 3):
  1. `resolve_rubric_category(description)` memilih SATU kategori dari himpunan KONSTAN;
  2. katalog konstan memberi daftar `Criterion` untuk kategori itu;
  3. `evaluate_job()` memuat teks deliverable lewat `checks/source.py` — yang MELEMPAR
     bila `keccak256(text)` tidak sama dengan nilai on-chain (ADR-019 keputusan 2) —
     lalu menjalankan cek `format`/`chain`/`links` sesuai kedalaman dari
     `memory_policy.check_depth()`;
  4. hasilnya `Evaluation`: skor per-kriteria + `failed_checks` yang SIAP diberikan ke
     `record_job_outcome`, dan `incidents()` yang siap diberikan ke `record_suspicion`.

KASAR vs HALUS (spec §7 langkah 1 vs langkah 4) — perbedaannya MEKANIS, bukan penilaian:
kedalaman `sampling` hanya membaca isi `SAMPLING_SECTION_LIMIT` bagian pertama (judul
seluruh bagian tetap terlihat), sedangkan `full` membaca semuanya. Cacat kasar duduk di
depan / berupa bagian yang hilang → tertangkap di kedua kedalaman. Cacat halus duduk di
bagian belakang → hanya tertangkap saat memori sudah menaikkan provider ke `full`.

KATEGORI RUBRIC (AC tambahan butir 5, PM): PILIHAN KAMI = **himpunan KONSTAN**.
`RUBRIC_CATEGORIES` di bawah adalah satu-satunya sumber nilai `category`; tidak ada nilai
turunan deliverable/LLM yang bisa sampai ke `set_rubric`. `assert_rubric_category()`
menegakkannya dua lapis (keanggotaan himpunan DAN bentuk kunci, cermin
`memory_policy.validate_pattern_id`), sehingga kunci `rubric:*` yang rusak — yang akan
mematikan perhitungan `memory_root` secara PERMANEN — tidak bisa lahir dari sini.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from agent.checks.base import (
    CHECK_CHAIN,
    CHECK_FORMAT,
    CHECK_LINKS,
    STATUS_FAIL,
    STATUS_UNVERIFIED,
    CheckResult,
    Document,
    excerpt,
    parse_document,
    sections_in_scope,
)
from agent.checks.chain import (
    FACT_DECIMALS,
    FACT_PAYMENT_TOKEN,
    FACT_TOTAL_SUPPLY,
    ChainFacts,
    check_claim,
)
from agent.checks.format import check_placeholders, check_required_sections
from agent.checks.links import check_links
from agent.checks.source import (
    VerifiedDeliverable,
    load_verified_deliverable,
)
from agent.memory_policy import (
    DEPTH_FULL,
    DEPTH_SAMPLING,
    DETERMINISTIC_CHECK_IDS,
    PATTERN_ID_RE,
    Evidence,
)

log = logging.getLogger("criteria")

__all__ = [
    "CATEGORY_GENERAL",
    "CATEGORY_LINK_DIGEST",
    "CATEGORY_TOKEN_REPORT",
    "KIND_DETERMINISTIC",
    "KIND_QUALITATIVE",
    "RUBRIC_CATEGORIES",
    "VERDICT_COMPLETE",
    "VERDICT_REJECT",
    "Criterion",
    "Evaluation",
    "Incident",
    "RubricTemplate",
    "assert_rubric_category",
    "build_criteria",
    "evaluate_job",
    "resolve_rubric_category",
    "rubric_body",
]

KIND_DETERMINISTIC: Final = "deterministic"
KIND_QUALITATIVE: Final = "qualitative"

# `EvaluatorVault.postVerdict(kind)`: 1 = complete, 2 = reject (spec §4).
VERDICT_COMPLETE: Final = 1
VERDICT_REJECT: Final = 2

# ----------------------------------------------------------------------
# Kategori rubric — HIMPUNAN KONSTAN (AC tambahan butir 5)
# ----------------------------------------------------------------------

CATEGORY_TOKEN_REPORT: Final = "token-report"
CATEGORY_LINK_DIGEST: Final = "link-digest"
CATEGORY_GENERAL: Final = "general"

RUBRIC_CATEGORIES: Final[frozenset[str]] = frozenset(
    {CATEGORY_TOKEN_REPORT, CATEGORY_LINK_DIGEST, CATEGORY_GENERAL}
)

# Cermin `memory_policy.PATTERN_ID_RE`: kunci reference `rubric:{cat}` harus tunduk pada
# batas bentuk yang sama dengan `pattern:{id}`. Lapis kedua di belakang keanggotaan
# himpunan, supaya konstanta baru yang ceroboh (`"a:b"`, `"kucing 🐈"`) mati di tes impor,
# bukan di produksi saat `memory_root` sudah tidak bisa dihitung lagi.
RUBRIC_CATEGORY_RE: Final = PATTERN_ID_RE

QUALITATIVE_UNSCORED: Final = (
    "kriteria kualitatif TIDAK DINILAI di 2.3-min: rubric LLM dipotong (PM 5 Sep). "
    "Ia dicatat apa adanya, tidak pernah dianggap lolos."
)


def assert_rubric_category(category: str) -> str:
    """Satu-satunya pintu menuju `category` yang boleh mencapai `set_rubric`.

    Dua lapis, sengaja berlebih:
      1. keanggotaan `RUBRIC_CATEGORIES` — nilai turunan teks pihak MUSTAHIL lolos;
      2. bentuk kunci `PATTERN_ID_RE` — menjaga kalau suatu saat himpunan di atas
         ditambah tanpa berpikir. Kunci `rubric:*` yang rusak = `memory_root` tidak bisa
         dihitung = DoS PERMANEN sampai DB dibetulkan tangan.
    """
    if not isinstance(category, str):
        raise ValueError(f"category harus string, dapat {type(category).__name__}")
    if category not in RUBRIC_CATEGORIES:
        raise ValueError(
            f"category {category!r} di luar himpunan konstan {sorted(RUBRIC_CATEGORIES)}"
        )
    if not RUBRIC_CATEGORY_RE.match(category):
        raise ValueError(f"category {category!r} bukan kunci reference yang sah")
    return category


for _category in sorted(RUBRIC_CATEGORIES):  # dijalankan saat impor — lihat lapis 2 di atas
    assert_rubric_category(_category)
del _category


# ----------------------------------------------------------------------
# Kriteria & katalog
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Criterion:
    """Satu kriteria evaluasi (spec §5 langkah 1)."""

    id: str
    kind: str
    text: str
    check_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("id kriteria wajib diisi")
        if self.kind not in {KIND_DETERMINISTIC, KIND_QUALITATIVE}:
            raise ValueError(f"kind kriteria tidak sah: {self.kind!r}")
        if self.kind == KIND_DETERMINISTIC and self.check_id not in DETERMINISTIC_CHECK_IDS:
            raise ValueError(
                f"kriteria deterministik {self.id!r} menunjuk check_id {self.check_id!r} "
                f"di luar {sorted(DETERMINISTIC_CHECK_IDS)}"
            )
        if self.kind == KIND_QUALITATIVE and self.check_id is not None:
            raise ValueError("kriteria kualitatif tidak boleh mengaku punya cek deterministik")

    def to_body(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "check": self.check_id or "",
        }


CRITERION_SECTIONS: Final = "format.required-sections"
CRITERION_PLACEHOLDER: Final = "format.no-placeholder"
CRITERION_LINKS: Final = "links.safe-sources"
CRITERION_CHAIN_PREFIX: Final = "chain."


@dataclass(frozen=True)
class RubricTemplate:
    """Rubric KONSTAN per kategori. Tidak ada bagian dari ini yang berasal dari teks pihak."""

    category: str
    required_sections: tuple[str, ...]
    chain_facts: tuple[str, ...]
    link_sections: tuple[str, ...]

    def criteria(self) -> tuple[Criterion, ...]:
        items = [
            Criterion(
                id=CRITERION_SECTIONS,
                kind=KIND_DETERMINISTIC,
                check_id=CHECK_FORMAT,
                text=f"deliverable memuat seluruh bagian wajib: {list(self.required_sections)}",
            ),
            Criterion(
                id=CRITERION_PLACEHOLDER,
                kind=KIND_DETERMINISTIC,
                check_id=CHECK_FORMAT,
                text="tidak ada penanda pekerjaan yang belum selesai (TODO/TBD/placeholder)",
            ),
        ]
        items += [
            Criterion(
                id=f"{CRITERION_CHAIN_PREFIX}{fact}",
                kind=KIND_DETERMINISTIC,
                check_id=CHECK_CHAIN,
                text=f"angka/alamat yang diklaim untuk {fact!r} sama dengan nilai on-chain",
            )
            for fact in self.chain_facts
        ]
        items.append(
            Criterion(
                id=CRITERION_LINKS,
                kind=KIND_DETERMINISTIC,
                check_id=CHECK_LINKS,
                text=(
                    "tautan memakai skema yang diizinkan, bukan alamat internal, dan bagian "
                    f"sumber {list(self.link_sections)} benar-benar memuat tautan"
                ),
            )
        )
        return tuple(items)


CATALOG: Final[dict[str, RubricTemplate]] = {
    CATEGORY_TOKEN_REPORT: RubricTemplate(
        category=CATEGORY_TOKEN_REPORT,
        required_sections=("summary", "supply", "sources"),
        chain_facts=(FACT_TOTAL_SUPPLY, FACT_DECIMALS, FACT_PAYMENT_TOKEN),
        link_sections=("sources",),
    ),
    CATEGORY_LINK_DIGEST: RubricTemplate(
        category=CATEGORY_LINK_DIGEST,
        required_sections=("summary", "sources"),
        chain_facts=(),
        link_sections=("sources",),
    ),
    CATEGORY_GENERAL: RubricTemplate(
        category=CATEGORY_GENERAL,
        required_sections=("summary",),
        chain_facts=(),
        link_sections=(),
    ),
}

# Kata kunci → kategori. Yang dipilih hanya SALAH SATU KUNCI di atas; teks pihak tidak
# pernah menjadi nilai `category`, ia hanya MEMILIH di antara konstanta.
_CATEGORY_KEYWORDS: Final[tuple[tuple[str, str], ...]] = (
    ("token", CATEGORY_TOKEN_REPORT),
    ("supply", CATEGORY_TOKEN_REPORT),
    ("suplai", CATEGORY_TOKEN_REPORT),
    ("erc-20", CATEGORY_TOKEN_REPORT),
    ("erc20", CATEGORY_TOKEN_REPORT),
    ("link", CATEGORY_LINK_DIGEST),
    ("tautan", CATEGORY_LINK_DIGEST),
    ("digest", CATEGORY_LINK_DIGEST),
)

# Berapa banyak kriteria kualitatif yang dicatat dari deskripsi client. Dibatasi supaya
# deskripsi 1 MB tidak melahirkan ribuan kriteria di bundel bukti.
MAX_QUALITATIVE_CRITERIA: Final = 5


def resolve_rubric_category(description: str = "", requirement: str | None = None) -> str:
    """Memilih SATU kategori dari `RUBRIC_CATEGORIES` berdasarkan kata kunci.

    Kodomainnya adalah himpunan konstan itu, apa pun isi masukannya — termasuk masukan
    yang sengaja dibuat untuk merusak kunci reference (`"a:b"`, `"../../x"`, teks 1 MB).
    Nilai baliknya divalidasi ulang sebelum dikembalikan.
    """
    haystack = f"{description or ''}\n{requirement or ''}".lower()
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in haystack:
            return assert_rubric_category(category)
    return assert_rubric_category(CATEGORY_GENERAL)


def rubric_body(category: str) -> dict[str, Any]:
    """Body konstan yang boleh disimpan `memory_policy.set_rubric(client, category, body)`.

    Modul ini TIDAK memanggil `set_rubric` sendiri (menulis memori bukan lingkup 2.3-min),
    tetapi menyediakan satu-satunya bentuk yang sah, dengan `category` yang sudah lewat
    `assert_rubric_category`.
    """
    template = CATALOG[assert_rubric_category(category)]
    return {
        "category": template.category,
        "required_sections": list(template.required_sections),
        "chain_facts": list(template.chain_facts),
        "link_sections": list(template.link_sections),
        "criteria": [c.to_body() for c in template.criteria()],
    }


def _qualitative_criteria(description: str, requirement: str | None) -> tuple[Criterion, ...]:
    """Butir deskripsi client dicatat sebagai kriteria KUALITATIF — dan tidak dinilai.

    Teksnya disanitasi `excerpt()` karena ia ikut masuk bundel bukti dan `web/`.
    """
    lines: list[str] = []
    for raw in f"{description or ''}\n{requirement or ''}".splitlines():
        stripped = raw.strip().lstrip("-*•").strip()
        if len(stripped) >= 8:
            lines.append(stripped)
        if len(lines) >= MAX_QUALITATIVE_CRITERIA:
            break
    return tuple(
        Criterion(
            id=f"qualitative.{index}",
            kind=KIND_QUALITATIVE,
            text=excerpt(line),
        )
        for index, line in enumerate(lines)
    )


def build_criteria(
    description: str = "",
    requirement: str | None = None,
    category: str | None = None,
) -> tuple[Criterion, ...]:
    """Kriteria untuk satu job: deterministik dari katalog + kualitatif dari deskripsi."""
    resolved = (
        assert_rubric_category(category)
        if category is not None
        else resolve_rubric_category(description, requirement)
    )
    return CATALOG[resolved].criteria() + _qualitative_criteria(description, requirement)


# ----------------------------------------------------------------------
# Hasil evaluasi
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Incident:
    """Satu temuan gagal, siap diberikan ke `memory_policy.record_suspicion`."""

    pattern_id: str
    evidence: Evidence


@dataclass(frozen=True)
class Evaluation:
    """Hasil evaluasi satu job — bahan `postVerdict` + tulisan memori (spec §5 langkah 4-5)."""

    job_id: int
    category: str
    depth: str
    deliverable_hash: str
    criteria: tuple[Criterion, ...]
    results: tuple[CheckResult, ...]

    @property
    def failed_results(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status == STATUS_FAIL)

    @property
    def failed_checks(self) -> tuple[str, ...]:
        """`check_id` unik yang GAGAL — argumen `record_job_outcome(failed_checks=…)`.

        Selalu subset `DETERMINISTIC_CHECK_IDS`: `CheckResult` sudah menolak yang lain di
        konstruktornya, jadi tidak ada jalur di mana skor non-deterministik menaikkan risk.
        """
        return tuple(sorted({r.check_id for r in self.failed_results}))

    @property
    def unverified_criteria(self) -> tuple[str, ...]:
        """Kriteria yang TIDAK diperiksa pada kedalaman ini. Bukan lolos — belum dilihat."""
        return tuple(sorted(r.criterion_id for r in self.results if r.status == STATUS_UNVERIFIED))

    @property
    def unscored_criteria(self) -> tuple[str, ...]:
        """Kriteria kualitatif — tidak dinilai sama sekali (rubric LLM dipotong)."""
        return tuple(c.id for c in self.criteria if c.kind == KIND_QUALITATIVE)

    @property
    def passed(self) -> bool:
        return not self.failed_results

    @property
    def verdict_kind(self) -> int:
        return VERDICT_COMPLETE if self.passed else VERDICT_REJECT

    def incidents(self) -> tuple[Incident, ...]:
        """Bukti untuk karantina. HANYA dari cek deterministik yang gagal (spec §3 aturan 2)."""
        return tuple(
            Incident(
                pattern_id=str(result.pattern_id),
                evidence=Evidence(job_id=self.job_id, check_id=result.check_id, proof=result.proof),
            )
            for result in self.failed_results
        )

    def to_body(self) -> dict[str, Any]:
        """Bundel bukti JSON-able (bahan `reasonHash` di task 2.5)."""
        return {
            "job": int(self.job_id),
            "category": self.category,
            "depth": self.depth,
            "deliverable": self.deliverable_hash,
            "criteria": [c.to_body() for c in self.criteria],
            "checks": [r.to_body() for r in self.results],
            "failed_checks": list(self.failed_checks),
            "unverified": list(self.unverified_criteria),
            "unscored": list(self.unscored_criteria),
            "unscored_reason": QUALITATIVE_UNSCORED,
            "verdict": int(self.verdict_kind),
        }


def _run_checks(
    document: Document,
    template: RubricTemplate,
    depth: str,
    facts: ChainFacts | None,
    link_probe: Callable[[str], bool] | None,
) -> tuple[CheckResult, ...]:
    scope = sections_in_scope(document, depth)
    results = [
        check_required_sections(document, template.required_sections, CRITERION_SECTIONS, depth),
        check_placeholders(scope, CRITERION_PLACEHOLDER, depth),
    ]
    for fact in template.chain_facts:
        if facts is None:
            raise ValueError(
                f"kategori {template.category!r} menuntut fakta on-chain {fact!r}; "
                "berikan `facts=` (Web3ChainFacts / StaticChainFacts)"
            )
        results.append(check_claim(scope, fact, facts, f"{CRITERION_CHAIN_PREFIX}{fact}", depth))
    results.append(
        check_links(
            scope,
            CRITERION_LINKS,
            depth,
            required_link_sections=template.link_sections,
            probe=link_probe,
        )
    )
    return tuple(results)


def evaluate_job(
    job_id: int,
    onchain_deliverable: bytes | bytearray | str,
    *,
    depth: str = DEPTH_SAMPLING,
    facts: ChainFacts | None = None,
    description: str = "",
    requirement: str | None = None,
    category: str | None = None,
    deliverable_dir: str | os.PathLike[str] | None = None,
    link_probe: Callable[[str], bool] | None = None,
) -> Evaluation:
    """Evaluasi satu job dari artefak deliverable yang HASH-nya sudah dibuktikan.

    `depth` datang dari `memory_policy.check_depth(profile, mode)` — modul ini TIDAK
    membaca memori sendiri (dan karena itu tidak punya jalur ke entity `suspicion`,
    ADR-002); ia menerima kalibrasinya sebagai argumen.

    MELEMPAR `DeliverableUnverifiedError` bila teks tidak bisa dibuktikan sebagai preimage
    hash on-chain (ADR-019 keputusan 2). Itu bukan verdict "gagal" — itu penolakan menilai:
    tidak ada `Evaluation` yang dihasilkan, jadi tidak ada bahan `postVerdict`/`finalize`.
    """
    if depth not in {DEPTH_SAMPLING, DEPTH_FULL}:
        raise ValueError(f"kedalaman cek tidak dikenal: {depth!r}")
    verified: VerifiedDeliverable = load_verified_deliverable(
        job_id, onchain_deliverable, deliverable_dir
    )
    resolved = (
        assert_rubric_category(category)
        if category is not None
        else resolve_rubric_category(description, requirement)
    )
    template = CATALOG[resolved]
    document = parse_document(verified.text)
    results = _run_checks(document, template, depth, facts, link_probe)
    evaluation = Evaluation(
        job_id=job_id,
        category=resolved,
        depth=depth,
        deliverable_hash=verified.hash_hex,
        criteria=build_criteria(description, requirement, resolved),
        results=results,
    )
    log.info(
        "evaluation job=%s category=%s depth=%s -> %s (failed=%s, unverified=%s)",
        job_id,
        resolved,
        depth,
        "PASS" if evaluation.passed else "REJECTED",
        list(evaluation.failed_checks),
        list(evaluation.unverified_criteria),
    )
    return evaluation
