"""Cek DETERMINISTIK atas teks deliverable (spec §5 langkah 3, task 2.3-min).

Satu paket, empat aturan yang berlaku untuk SELURUH isinya:

1. Semua `check_id` berasal dari `memory_policy.DETERMINISTIC_CHECK_IDS`
   (`chain`, `links`, `format`, `sandbox`) — `record_job_outcome` menolak yang lain.
   `sandbox` BELUM ada implementasinya; jangan diklaim hidup.
2. Teks deliverable adalah DATA (spec §3 aturan 3): dibaca, dibandingkan, dikutip —
   tidak pernah dieksekusi, tidak pernah menjadi nama/kunci/perintah.
3. Tidak ada LLM di jalur ini (pemotongan PM 5 Sep): nol `anthropic`, nol kunci API,
   nol panggilan jaringan kecuali `Web3ChainFacts` yang eksplisit disuntikkan.
4. Sumber teks HANYA `demo/deliverables/<jobId>.json` yang hash-nya sudah diverifikasi
   ulang terhadap nilai on-chain (ADR-019 keputusan 1-2); lihat `checks/source.py`.
"""

from agent.checks.base import (
    CHECK_CHAIN,
    CHECK_FORMAT,
    CHECK_LINKS,
    CHECK_SANDBOX,
    SAMPLING_SECTION_LIMIT,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNVERIFIED,
    CheckResult,
    Document,
    Section,
    excerpt,
    parse_document,
    sections_in_scope,
)
from agent.checks.chain import (
    FACT_DECIMALS,
    FACT_PAYMENT_TOKEN,
    FACT_TOTAL_SUPPLY,
    ChainFacts,
    StaticChainFacts,
    Web3ChainFacts,
    check_claim,
)
from agent.checks.format import check_placeholders, check_required_sections
from agent.checks.links import check_links
from agent.checks.source import (
    REFUSAL_LINE,
    DeliverableUnverifiedError,
    VerifiedDeliverable,
    load_verified_deliverable,
)

__all__ = [
    "CHECK_CHAIN",
    "CHECK_FORMAT",
    "CHECK_LINKS",
    "CHECK_SANDBOX",
    "FACT_DECIMALS",
    "FACT_PAYMENT_TOKEN",
    "FACT_TOTAL_SUPPLY",
    "REFUSAL_LINE",
    "SAMPLING_SECTION_LIMIT",
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_UNVERIFIED",
    "ChainFacts",
    "CheckResult",
    "DeliverableUnverifiedError",
    "Document",
    "Section",
    "StaticChainFacts",
    "VerifiedDeliverable",
    "Web3ChainFacts",
    "check_claim",
    "check_links",
    "check_placeholders",
    "check_required_sections",
    "excerpt",
    "load_verified_deliverable",
    "parse_document",
    "sections_in_scope",
]
