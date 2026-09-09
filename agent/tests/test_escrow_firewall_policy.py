from __future__ import annotations

import json

from sibyl_memory_client import MemoryClient

from agent.escrow_firewall import (
    REVIEW_REQUIRED,
    committed_description,
    description_matches_policy,
    extract_failure_patterns,
    generic_policy,
    main,
    propose_policy_from_memory,
    synthesize_policy,
    terms_commitment,
)
from agent.memory_policy import FailurePattern, save_failure_pattern


def reproducibility_pattern(confidence_bps: int = 8_000) -> FailurePattern:
    return FailurePattern(
        pattern_id="firewall.missing-reproducible-evidence",
        task_category="general",
        trigger_signature="claims-test-passed-without-artifact",
        failure_description="klaim tes tidak bisa direproduksi",
        evidence_required=("commit-hash", "test-command", "test-output"),
        recommended_countermeasure="require-reproducible-evidence-before-milestone",
        confidence_bps=confidence_bps,
    )


def test_memory_pattern_changes_generic_terms_before_funding():
    generic = generic_policy("smart-contract-audit")
    proposal = synthesize_policy("smart-contract-audit", (reproducibility_pattern(),))

    assert proposal.status == "recommended"
    assert proposal.requires_client_approval is True
    assert proposal.policy.milestone_required is True
    assert "commit-hash" in proposal.policy.required_evidence
    assert terms_commitment(generic) != terms_commitment(proposal.policy)


def test_low_confidence_pattern_requires_human_review():
    proposal = synthesize_policy("smart-contract-audit", (reproducibility_pattern(6_999),))

    assert proposal.status == "requires-review"
    assert proposal.policy.review_level == REVIEW_REQUIRED


def test_commitment_is_canonical_and_description_rejects_mutation():
    policy = synthesize_policy("smart-contract-audit", (reproducibility_pattern(),)).policy
    committed = committed_description("audit contract escrow", policy)

    assert description_matches_policy(committed, policy)
    assert not description_matches_policy(committed + " altered", policy)
    assert not description_matches_policy(committed, generic_policy("smart-contract-audit"))


def test_extractor_requires_deterministic_evidence_not_generic_reject():
    assert extract_failure_patterns(job_id=418, task_category="general", failed_checks=()) == ()
    extracted = extract_failure_patterns(
        job_id=418, task_category="general", failed_checks=("format",)
    )

    assert extracted[0].pattern_id == "firewall.incomplete-deliverable"


def test_cli_writes_immutable_canonical_terms_artifact(tmp_path, capsys):
    db = tmp_path / "memory.db"
    client = MemoryClient.local(str(db))
    save_failure_pattern(client, reproducibility_pattern())
    output = tmp_path / "terms.json"

    assert (
        main(
            ["--memory-db", str(db), "--task-category", "smart-contract-audit", "--output", str(output)]
        )
        == 0
    )
    commitment = capsys.readouterr().out.strip()
    artifact = json.loads(output.read_text(encoding="utf-8"))

    assert commitment.startswith("0x") and len(commitment) == 66
    assert artifact["version"] == "escrow-firewall/terms/v1"


def test_deleting_memory_removes_the_pre_funding_safeguard(tmp_path):
    db = tmp_path / "memory.db"
    remembered = MemoryClient.local(str(db))
    save_failure_pattern(remembered, reproducibility_pattern())
    remembered.storage.close()

    fresh_with_memory = MemoryClient.local(str(db))
    remembered_proposal = propose_policy_from_memory(
        fresh_with_memory, task_category="smart-contract-audit"
    )
    fresh_with_memory.storage.close()
    db.unlink()

    fresh_after_delete = MemoryClient.local(str(db))
    generic_proposal = propose_policy_from_memory(
        fresh_after_delete, task_category="smart-contract-audit"
    )

    assert "commit-hash" in remembered_proposal.policy.required_evidence
    assert generic_proposal.status == "generic"
    assert "commit-hash" not in generic_proposal.policy.required_evidence
