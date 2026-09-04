"""Tes fungsi MURNI pemetaan status terminal job ACP (TASKS 1.3b).

Sumber angka: docs/api-facts.md — "Status enum: Open=0, Funded=1, Submitted=2, Completed=3,
Rejected=4, Expired=5". Tidak ada jaringan, tidak ada kunci, tidak ada memori.
"""

import pytest

from agent.vault_client import (
    JOB_STATUS_NAMES,
    TERMINAL_JOB_STATUSES,
    is_terminal_status,
    parse_env_file,
    redact,
    status_name,
    voided_message,
)


@pytest.mark.parametrize(
    ("status", "name"),
    [(0, "Open"), (1, "Funded"), (2, "Submitted"), (3, "Completed"), (4, "Rejected"), (5, "Expired")],
)
def test_status_name_matches_acp_enum(status, name):
    assert status_name(status) == name
    assert JOB_STATUS_NAMES[status] == name


def test_status_enum_has_exactly_six_members():
    assert sorted(JOB_STATUS_NAMES) == [0, 1, 2, 3, 4, 5]


@pytest.mark.parametrize("status", [0, 1, 2])
def test_non_terminal_statuses_allow_verdict(status):
    assert is_terminal_status(status) is False


@pytest.mark.parametrize("status", [3, 4, 5])
def test_terminal_statuses_void_verdict(status):
    assert is_terminal_status(status) is True


def test_terminal_set_is_exactly_completed_rejected_expired():
    assert TERMINAL_JOB_STATUSES == frozenset({3, 4, 5})


def test_unknown_status_is_not_terminal_and_reported_verbatim():
    assert status_name(9) == "Unknown(9)"
    assert is_terminal_status(9) is False


def test_voided_message_is_verbatim():
    assert voided_message(407, 3) == "VERDICT DIANULIR PIHAK KETIGA jobId=407 status=3"


def test_parse_env_file_handles_comments_and_quotes():
    values = parse_env_file(
        "\n".join(
            [
                "# komentar",
                "RPC_URL=https://sepolia.base.org",
                'VAULT_ADDRESS="0x5c6EE4586ACABcb6326069c229E58091B21ef384"   # deployed',
                "export CHAIN_ID=84532",
                "EMPTY=",
                "ONLY_COMMENT=# diisi setelah deploy",
                "tanpa-sama-dengan",
            ]
        )
    )
    assert values["RPC_URL"] == "https://sepolia.base.org"
    assert values["VAULT_ADDRESS"] == "0x5c6EE4586ACABcb6326069c229E58091B21ef384"
    assert values["CHAIN_ID"] == "84532"
    assert values["EMPTY"] == ""
    assert values["ONLY_COMMENT"] == ""
    assert "tanpa-sama-dengan" not in values


def test_redact_removes_key_from_messages():
    key = "0x" + "ab" * 32
    assert key not in redact(f"boom {key} end", key)
    assert "ab" * 32 not in redact(f"boom {'AB' * 32} end", key)
