"""Deterministic pre-funding policy for Escrow Firewall.

No provider score, external request, or LLM is used here.  The sole input that can
make terms stricter is a structured :class:`FailurePattern` recalled from Sibyl.
The resulting canonical JSON is the exact preimage of the commitment embedded in
the ACP job description before it is funded.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sibyl_memory_client import MemoryClient
from web3 import Web3

from agent.memory_policy import (
    DETERMINISTIC_CHECK_IDS,
    FailurePattern,
    canonical_json,
    load_failure_patterns,
)

TERMS_VERSION: Final = "escrow-firewall/terms/v1"
DESCRIPTION_COMMITMENT_PREFIX: Final = "\n\n[escrow-firewall-terms:"
DESCRIPTION_COMMITMENT_SUFFIX: Final = "]"
REVIEW_NONE: Final = "none"
REVIEW_CLIENT: Final = "client"
REVIEW_REQUIRED: Final = "required"
_REVIEW_LEVELS: Final = frozenset({REVIEW_NONE, REVIEW_CLIENT, REVIEW_REQUIRED})


def _clean(value: str, field: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} harus string tidak kosong")
    value = value.strip()
    if len(value) > maximum or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{field} tidak aman atau terlalu panjang")
    return value


@dataclass(frozen=True)
class TermsPolicy:
    """Terms yang dapat disetujui manusia dan dikomit sebelum escrow didanai."""

    task_category: str
    acceptance_criteria: tuple[str, ...]
    required_evidence: tuple[str, ...]
    milestone_required: bool
    review_level: str
    rationale: tuple[str, ...]
    applied_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_category", _clean(self.task_category, "task_category", 64))
        for name in ("acceptance_criteria", "required_evidence", "rationale", "applied_patterns"):
            values = tuple(sorted({_clean(item, name, 256) for item in getattr(self, name)}))
            if not values and name != "applied_patterns":
                raise ValueError(f"{name} tidak boleh kosong")
            object.__setattr__(self, name, values)
        if self.review_level not in _REVIEW_LEVELS:
            raise ValueError(f"review_level tidak sah: {self.review_level!r}")

    def to_body(self) -> dict[str, object]:
        return {
            "version": TERMS_VERSION,
            "task_category": self.task_category,
            "acceptance_criteria": list(self.acceptance_criteria),
            "required_evidence": list(self.required_evidence),
            "milestone_required": self.milestone_required,
            "review_level": self.review_level,
            "rationale": list(self.rationale),
            "applied_patterns": list(self.applied_patterns),
        }


@dataclass(frozen=True)
class PolicyProposal:
    """Policy hasil sintesis; rekomendasi tidak boleh diam-diam dianggap enforcement."""

    policy: TermsPolicy
    requires_client_approval: bool
    status: str

    def __post_init__(self) -> None:
        if self.status not in {"generic", "recommended", "requires-review"}:
            raise ValueError(f"status proposal tidak sah: {self.status!r}")
        if self.status == "requires-review" and not self.requires_client_approval:
            raise ValueError("proposal requires-review harus meminta persetujuan client")


def generic_policy(task_category: str) -> TermsPolicy:
    """Fallback eksplisit ketika tidak ada failure-pattern memory yang relevan."""
    return TermsPolicy(
        task_category=task_category,
        acceptance_criteria=("deliverable memenuhi brief yang disetujui client",),
        required_evidence=("deliverable-artifact",),
        milestone_required=False,
        review_level=REVIEW_CLIENT,
        rationale=("generic-terms-no-recalled-pattern",),
    )


def extract_failure_patterns(
    *, job_id: int, task_category: str, failed_checks: tuple[str, ...]
) -> tuple[FailurePattern, ...]:
    """Map evidence deterministic evaluator ke pola MVP; reject tanpa bukti menghasilkan nol pola."""
    if isinstance(job_id, bool) or int(job_id) < 0:
        raise ValueError("job_id harus integer tidak negatif")
    if any(check not in DETERMINISTIC_CHECK_IDS for check in failed_checks):
        raise ValueError("failed_checks harus berasal dari evaluator deterministik")
    # Cek format sudah membuktikan secara mekanis bahwa artifact/section yang diwajibkan
    # tidak ada. Cek lain belum punya pemetaan aman ke tiga pola MVP dan sengaja tidak
    # dipaksa menjadi sinyal palsu.
    if "format" not in failed_checks:
        return ()
    return (
        FailurePattern(
            pattern_id="firewall.incomplete-deliverable",
            task_category=task_category,
            trigger_signature="required-artifact-missing",
            failure_description="cek format deterministik menemukan artefak atau bagian wajib hilang",
            evidence_required=("artifact-inventory", "requirement-to-artifact-map"),
            recommended_countermeasure="require-artifact-inventory-before-milestone",
            observed_jobs=(int(job_id),),
        ),
    )


def synthesize_policy(task_category: str, patterns: tuple[FailurePattern, ...]) -> PolicyProposal:
    """Gabungkan safeguard secara monotonic: bukti ditambah, tidak pernah dikurangi."""
    if not patterns:
        return PolicyProposal(generic_policy(task_category), requires_client_approval=False, status="generic")
    if any(pattern.task_category not in {task_category, "general"} for pattern in patterns):
        raise ValueError("pattern tidak relevan untuk task_category")

    evidence = {"deliverable-artifact"}
    criteria = {"deliverable memenuhi brief yang disetujui client"}
    rationale: set[str] = set()
    applied: set[str] = set()
    low_confidence = False
    for pattern in patterns:
        evidence.update(pattern.evidence_required)
        criteria.add(pattern.recommended_countermeasure)
        rationale.add(f"recalled:{pattern.pattern_id}")
        applied.add(pattern.pattern_id)
        low_confidence = low_confidence or pattern.confidence_bps < 7_000

    review_level = REVIEW_REQUIRED if low_confidence else REVIEW_CLIENT
    policy = TermsPolicy(
        task_category=task_category,
        acceptance_criteria=tuple(criteria),
        required_evidence=tuple(evidence),
        milestone_required=True,
        review_level=review_level,
        rationale=tuple(rationale),
        applied_patterns=tuple(applied),
    )
    return PolicyProposal(
        policy,
        requires_client_approval=True,
        status="requires-review" if low_confidence else "recommended",
    )


def propose_policy_from_memory(
    client: MemoryClient, *, task_category: str, trigger_signature: str | None = None
) -> PolicyProposal:
    """Fresh-session entry point: Sibyl retrieval is an input required for terms synthesis."""
    patterns = load_failure_patterns(
        client, task_category=task_category, trigger_signature=trigger_signature
    )
    return synthesize_policy(task_category, patterns)


def canonical_terms(policy: TermsPolicy) -> str:
    return canonical_json(policy.to_body())


def terms_commitment(policy: TermsPolicy) -> bytes:
    return bytes(Web3.keccak(text=canonical_terms(policy)))


def committed_description(description: str, policy: TermsPolicy) -> str:
    """Bind immutable ACP `description` to the exact terms hash at createJob time."""
    description = _clean(description, "description", 4_096)
    return (
        description
        + DESCRIPTION_COMMITMENT_PREFIX
        + "0x"
        + terms_commitment(policy).hex()
        + DESCRIPTION_COMMITMENT_SUFFIX
    )


def extract_terms_commitment(description: str) -> bytes | None:
    """Return only a well-formed final commitment; duplicate/mutated suffixes fail closed."""
    if not isinstance(description, str) or description.count(DESCRIPTION_COMMITMENT_PREFIX) != 1:
        return None
    prefix, suffix = description.rsplit(DESCRIPTION_COMMITMENT_PREFIX, 1)
    if not prefix or not suffix.endswith(DESCRIPTION_COMMITMENT_SUFFIX):
        return None
    value = suffix[: -len(DESCRIPTION_COMMITMENT_SUFFIX)]
    if len(value) != 66 or not value.startswith("0x"):
        return None
    try:
        return bytes.fromhex(value[2:])
    except ValueError:
        return None


def description_matches_policy(description: str, policy: TermsPolicy) -> bool:
    return extract_terms_commitment(description) == terms_commitment(policy)


def _close(client: MemoryClient) -> None:
    close = getattr(getattr(client, "storage", None), "close", None)
    if callable(close):
        close()


def main(argv: list[str] | None = None) -> int:
    """Buat artefak terms immutable sebelum simulator mengirim `createJob`."""
    parser = argparse.ArgumentParser(prog="escrow_firewall")
    parser.add_argument("--memory-db", required=True)
    parser.add_argument("--task-category", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    client = MemoryClient.local(args.memory_db)
    try:
        proposal = propose_policy_from_memory(client, task_category=args.task_category)
    finally:
        _close(client)
    text = canonical_terms(proposal.policy)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(text + "\n")
    except FileExistsError:
        if output.read_text(encoding="utf-8") != text + "\n":
            raise RuntimeError("terms artifact sudah ada dengan isi berbeda; buat job baru") from None
    print("0x" + terms_commitment(proposal.policy).hex())
    return 0


if __name__ == "__main__":  # pragma: no cover - entrypoint manual
    raise SystemExit(main())
