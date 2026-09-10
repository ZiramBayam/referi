"""Perintah bukti Virtuals: yang diuji adalah PEMBACAAN dan PEMBENTUKAN barisnya.

Panggilan RPC-nya sendiri tidak diuji: ia butuh jaringan, dan tes yang butuh jaringan
akan merah karena wifi juri, bukan karena kode kita. Yang dikunci di sini adalah bahwa
ketidakcocokan antara berkas dan chain DILAPORKAN, bukan disamarkan.
"""

from __future__ import annotations

from agent.virtuals_evidence import format_rows

JOBS = [
    {
        "jobId": "421",
        "provider": "0xc3c6Bf20ddE1a547a35f6479D54B08E1548dAeff",
        "providerLabel": "Beta",
        "acpStatus": 3,
        "verdictKind": 1,
        "verdictTxHash": "0x02356b07…8a1467",
    },
    {
        "jobId": "422",
        "provider": "0x20212E4D95A75E6716575ED26e884cdeFf66b321",
        "providerLabel": "Alpha",
        "acpStatus": 4,
        "verdictKind": 2,
        "verdictTxHash": "0xe95910d2…295830",
    },
]


def test_matching_job_reports_confirmed():
    onchain = {
        421: {"exists": True, "provider": "0xc3c6bf20dde1a547a35f6479d54b08e1548daeff"},
        422: {"exists": True, "provider": "0x20212e4d95a75e6716575ed26e884cdeff66b321"},
    }
    rows = format_rows(JOBS, onchain)
    joined = "\n".join(rows)

    assert "job=421 onchain=yes provider_match=yes" in joined
    assert "job=422 onchain=yes provider_match=yes" in joined
    assert "jobs_confirmed_onchain=2/2" in joined


def test_provider_mismatch_is_reported_not_hidden():
    onchain = {
        421: {"exists": True, "provider": "0x0000000000000000000000000000000000000001"},
        422: {"exists": True, "provider": "0x20212e4d95a75e6716575ed26e884cdeff66b321"},
    }
    rows = format_rows(JOBS, onchain)
    joined = "\n".join(rows)

    assert "job=421 onchain=yes provider_match=NO" in joined
    assert "jobs_confirmed_onchain=1/2" in joined


def test_missing_job_is_reported():
    onchain = {
        421: {"exists": False, "provider": None},
        422: {"exists": True, "provider": "0x20212e4d95a75e6716575ed26e884cdeff66b321"},
    }
    rows = format_rows(JOBS, onchain)
    joined = "\n".join(rows)

    assert "job=421 onchain=NO" in joined
    assert "jobs_confirmed_onchain=1/2" in joined
