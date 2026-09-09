"""Fondasi failure-pattern memory untuk Escrow Firewall.

Tes ini sengaja hanya lokal/Sibyl: tidak ada RPC atau transaksi. Ia mengunci dua
klaim MVP yang paling penting sebelum policy synthesis ditambahkan:

1. pola adalah state terstruktur yang masuk `memory_root`, bukan catatan teks lepas;
2. pola dapat dipanggil ulang lintas provider dalam proses baru.
"""

from __future__ import annotations

import pytest
from sibyl_memory_client import MemoryClient

from agent import memory_policy as mp


def pattern() -> mp.FailurePattern:
    return mp.FailurePattern(
        pattern_id="firewall.missing-reproducible-evidence",
        task_category="smart-contract-audit",
        trigger_signature="claims-test-passed-without-artifact",
        failure_description="test tidak dapat dijalankan ulang dari deliverable",
        evidence_required=("commit-hash", "test-command", "test-output", "environment-version"),
        recommended_countermeasure="require-reproducible-evidence-before-milestone",
        confidence_bps=6_000,
        observed_jobs=(418,),
    )


def test_failure_pattern_is_hashed_and_recalled_across_provider(tmp_path):
    db = tmp_path / "memory.db"
    first = MemoryClient.local(str(db))
    root_before = mp.memory_root(first)
    saved = mp.save_failure_pattern(first, pattern())
    root_after = mp.memory_root(first)

    assert saved == pattern()
    assert root_after != root_before

    # Proses kedua membawa DB yang sama tetapi tidak menerima provider A sebagai input.
    second = MemoryClient.local(str(db))
    recalled = mp.load_failure_patterns(second, task_category="smart-contract-audit")

    assert recalled == (pattern(),)


def test_failure_pattern_records_countermeasure_outcome(tmp_path):
    client = MemoryClient.local(str(tmp_path / "memory.db"))
    mp.save_failure_pattern(client, pattern())

    updated = mp.record_countermeasure_outcome(
        client,
        "firewall.missing-reproducible-evidence",
        job_id=419,
        outcome=mp.COUNTERMEASURE_WORKED,
    )

    assert updated.observed_jobs == (418, 419)
    assert updated.successful_mitigations == 1
    assert updated.failed_mitigations == 0
    assert updated.inconclusive_mitigations == 0
    assert updated.confidence_bps > pattern().confidence_bps


def test_failure_pattern_rejects_non_firewall_namespace():
    with pytest.raises(ValueError, match="firewall\\."):
        mp.FailurePattern(
            pattern_id="format.placeholder-text",
            task_category="smart-contract-audit",
            trigger_signature="x",
            failure_description="x",
            evidence_required=("commit-hash",),
            recommended_countermeasure="x",
        )


def test_failure_pattern_rejects_untrusted_outcome_value(tmp_path):
    client = MemoryClient.local(str(tmp_path / "memory.db"))
    mp.save_failure_pattern(client, pattern())

    with pytest.raises(ValueError, match="outcome"):
        mp.record_countermeasure_outcome(
            client,
            "firewall.missing-reproducible-evidence",
            job_id=419,
            outcome="accept-anything",
        )


def test_mvp_templates_are_deterministic_and_cover_the_three_failure_modes():
    templates = mp.mvp_failure_pattern_templates()

    assert tuple(item.pattern_id for item in templates) == (
        "firewall.incomplete-deliverable",
        "firewall.missing-reproducible-evidence",
        "firewall.requirement-ambiguity",
    )
    assert all(item.status == "active" for item in templates)
    assert all(item.evidence_required for item in templates)


def test_retrieval_uses_category_and_trigger_signature(tmp_path):
    client = MemoryClient.local(str(tmp_path / "memory.db"))
    matching = pattern()
    irrelevant = mp.FailurePattern(
        pattern_id="firewall.requirement-ambiguity",
        task_category="smart-contract-audit",
        trigger_signature="missing-client-acceptance-criteria",
        failure_description="kriteria penerimaan tidak dapat ditentukan dari brief",
        evidence_required=("acceptance-criteria",),
        recommended_countermeasure="require-client-approval-before-funding",
    )
    mp.save_failure_pattern(client, matching)
    mp.save_failure_pattern(client, irrelevant)

    recalled = mp.load_failure_patterns(
        client,
        task_category="smart-contract-audit",
        trigger_signature="claims-test-passed-without-artifact",
    )

    assert recalled == (matching,)
