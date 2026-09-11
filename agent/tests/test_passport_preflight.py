"""Preflight situs memakai jalur keputusan yang sama dengan CLI.

Tes ini ada karena situs pernah punya implementasi ulang aturan dalam JavaScript, dan
dua implementasi dari aturan yang sama akan menyimpang tanpa ada yang memerah. Yang
dikunci di sini bukan bentuk JSON-nya, melainkan bahwa keputusannya datang dari
`evaluate_rebalance_for_passport` dan dari memori Sibyl yang benar-benar dibaca.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent.passport_preflight import evaluate

AGENT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture()
def memory_db(tmp_path, monkeypatch):
    db = tmp_path / "web-memory.db"
    monkeypatch.setenv("REFERI_WEB_MEMORY_DB", str(db))
    return db


def test_stale_oracle_is_blocked_by_recalled_memory(memory_db):
    out = evaluate({"amount": 100_000, "memoryAvailable": True, "oracleFresh": False})

    assert out["decision"] == "block"
    assert out["passport"] is None
    assert out["hypothesisId"] == "stale-oracle-rebalance/v1"
    failed = [o for o in out["obligations"] if o["result"] != "satisfied"]
    assert [o["id"] for o in failed] == ["oracle-freshness"]


def test_fresh_oracle_issues_a_passport_bound_to_the_deployed_verifier(memory_db):
    out = evaluate({"amount": 100_000, "memoryAvailable": True, "oracleFresh": True})

    assert out["decision"] == "passport-issued"
    assert all(o["result"] == "satisfied" for o in out["obligations"])
    # Passport terikat ke kontrak yang BENAR-BENAR ada di Base Sepolia, bukan nama karangan.
    deployment = json.loads(
        (AGENT_DIR.parent / "deployments" / "passport-84532.json").read_text(encoding="utf-8")
    )
    assert out["deployment"]["verifier"] == deployment["contracts"]["PassportVerifier"]
    assert out["passport"]["target"].lower() == deployment["contracts"]["MockTreasury"].lower()
    assert out["passport"]["expiresAt"] - out["passport"]["issuedAt"] == 60
    # Belum ditandatangani, dan situs mengatakannya: proses yang melayani HTTP tidak
    # boleh memegang kunci.
    assert out["signed"] is False


def test_missing_memory_requires_human_review_instead_of_guessing(memory_db):
    out = evaluate({"amount": 100_000, "memoryAvailable": False, "oracleFresh": True})

    assert out["decision"] == "human-review-required"
    assert out["passport"] is None
    assert out["memoryRoot"] is None


def test_reserve_floor_blocks_even_with_fresh_oracle(memory_db):
    out = evaluate({"amount": 900_000, "memoryAvailable": True, "oracleFresh": True})

    assert out["decision"] == "block"
    assert out["passport"] is None
    assert any(o["id"] == "post-state-invariant" and o["result"] != "satisfied"
               for o in out["obligations"])


def test_memory_root_is_read_from_sibyl_not_invented(memory_db):
    first = evaluate({"amount": 100_000, "memoryAvailable": True, "oracleFresh": True})
    second = evaluate({"amount": 250_000, "memoryAvailable": True, "oracleFresh": True})

    # Root ikut MEMORI, bukan ikut aksi: dua aksi berbeda di atas memori yang sama
    # harus melaporkan root yang sama, dan root itu harus berupa hash 32-byte.
    assert first["memoryRoot"] == second["memoryRoot"]
    assert first["memoryRoot"].startswith("0x") and len(first["memoryRoot"]) == 66
    assert memory_db.exists()


def test_cli_entrypoint_speaks_json_over_stdin(memory_db):
    """Rute situs memanggilnya sebagai subprocess, jadi kontrak stdin/stdout ikut dikunci."""
    completed = subprocess.run(
        [sys.executable, "-m", "agent.passport_preflight"],
        cwd=AGENT_DIR,
        input=json.dumps({"amount": 100_000, "memoryAvailable": True, "oracleFresh": False}),
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["engine"] == "agent"
    assert payload["decision"] == "block"


def test_broken_input_reports_an_error_instead_of_crashing_silently(memory_db):
    completed = subprocess.run(
        [sys.executable, "-m", "agent.passport_preflight"],
        cwd=AGENT_DIR,
        input=json.dumps({"memoryAvailable": True}),
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    # Situs HARUS bisa membedakan "agen menolak" dari "agen rusak".
    assert "error" in payload


def test_executor_defaults_to_deployer_and_can_be_overridden(memory_db):
    out = evaluate({"amount": 100_000, "memoryAvailable": True, "oracleFresh": True})
    assert out["executor"] == out["passport"]["executor"]

    beta = "0xc3c6bf20dde1a547a35f6479d54b08e1548daeff"
    out = evaluate({"amount": 100_000, "oracleFresh": True, "executor": beta})
    assert out["passport"]["executor"] == beta
    actor = next(o for o in out["obligations"] if o["id"] == "actor-standing")
    assert actor["result"] == "satisfied"
