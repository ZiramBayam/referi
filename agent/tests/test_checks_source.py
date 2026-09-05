"""Tes sumber teks deliverable — ADR-019 keputusan 1-2 (task 2.3-min).

Yang dibuktikan di sini:
  1. teks hanya diterima bila `keccak256(text)` PERSIS sama dengan nilai deliverable
     on-chain, dan hash itu dihitung dengan cara yang sama seperti SDK
     (`Web3.keccak(text=…)`, api-facts §B.1);
  2. SETIAP penyimpangan → REFUSE: melempar `DeliverableUnverifiedError` yang pesannya
     diawali `DELIVERABLE TIDAK TERVERIFIKASI`, dan tidak ada nilai balik yang bisa
     disalahartikan pemanggil sebagai "boleh nilai";
  3. penolakan itu juga TERCETAK (log ERROR), sehingga ada jejak seperti `MODE AMAN`.
"""

from __future__ import annotations

import json
import logging

import pytest
from web3 import Web3

from agent.checks import source as src

HONEST_TEXT = "# Summary\nlaporan ringkas\n\n## Sources\nhttps://sepolia.basescan.org/\n"


def write_artifact(directory, job_id: int, text: str, *, sha: str | None = None, **extra) -> None:
    """Menulis artefak seperti yang dilakukan `sim/` (ADR-019 keputusan 1)."""
    body = {
        "jobId": job_id,
        "text": text,
        "sha_keccak": sha if sha is not None else "0x" + Web3.keccak(text=text).hex(),
    }
    body.update(extra)
    (directory / f"{job_id}.json").write_text(json.dumps(body), encoding="utf-8")


def onchain_hash(text: str) -> str:
    return "0x" + Web3.keccak(text=text).hex()


def test_loadVerifiedDeliverable_returnsText_whenHashMatchesOnchain(tmp_path):
    write_artifact(tmp_path, 7, HONEST_TEXT)
    got = src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path)
    assert got.text == HONEST_TEXT
    assert got.hash_hex == onchain_hash(HONEST_TEXT)
    assert got.job_id == 7


def test_loadVerifiedDeliverable_acceptsBytes32_asBytes(tmp_path):
    write_artifact(tmp_path, 7, HONEST_TEXT)
    raw = bytes(Web3.keccak(text=HONEST_TEXT))
    assert src.load_verified_deliverable(7, raw, tmp_path).text == HONEST_TEXT


def test_loadVerifiedDeliverable_refuses_whenTextTampered(tmp_path, caplog):
    """Bukti REFUSE utama: satu spasi berubah → hash beda → menolak menilai."""
    write_artifact(tmp_path, 7, HONEST_TEXT + " ")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(src.DeliverableUnverifiedError) as exc:
            src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path)
    assert str(exc.value).startswith(src.REFUSAL_LINE)
    assert "!= deliverable on-chain" in str(exc.value)
    assert any(src.REFUSAL_LINE in r.getMessage() for r in caplog.records)


def test_loadVerifiedDeliverable_refuses_whenFileMissing(tmp_path):
    with pytest.raises(src.DeliverableUnverifiedError, match=src.REFUSAL_LINE):
        src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path)


def test_loadVerifiedDeliverable_refuses_whenDirectoryMissing(tmp_path):
    with pytest.raises(src.DeliverableUnverifiedError, match=src.REFUSAL_LINE):
        src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path / "tidak-ada")


def test_loadVerifiedDeliverable_refuses_whenArtifactBelongsToAnotherJob(tmp_path):
    """File job 8 tidak boleh menilai job 7 walau teksnya kebetulan cocok."""
    write_artifact(tmp_path, 7, HONEST_TEXT)
    body = json.loads((tmp_path / "7.json").read_text(encoding="utf-8"))
    body["jobId"] = 8
    (tmp_path / "7.json").write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(src.DeliverableUnverifiedError, match="bukan job 7"):
        src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path)


def test_loadVerifiedDeliverable_refuses_whenOnchainValueIsZero(tmp_path):
    """bytes32 nol = belum submit. `kosong == kosong` tidak boleh pernah cocok."""
    write_artifact(tmp_path, 7, HONEST_TEXT)
    with pytest.raises(src.DeliverableUnverifiedError, match="bytes32 nol"):
        src.load_verified_deliverable(7, "0x" + "00" * 32, tmp_path)


def test_loadVerifiedDeliverable_refuses_whenShaFieldContradictsText(tmp_path):
    """`sha_keccak` yang berbeda = artefak tidak konsisten, walau on-chain cocok."""
    write_artifact(tmp_path, 7, HONEST_TEXT, sha="0x" + "11" * 32)
    with pytest.raises(src.DeliverableUnverifiedError, match="sha_keccak"):
        src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path)


def test_loadVerifiedDeliverable_refuses_whenExtraFieldsPresent(tmp_path):
    write_artifact(tmp_path, 7, HONEST_TEXT, verdict="complete")
    with pytest.raises(src.DeliverableUnverifiedError, match="di luar ADR-019"):
        src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path)


def test_loadVerifiedDeliverable_refuses_whenNotJson(tmp_path):
    (tmp_path / "7.json").write_text("bukan json", encoding="utf-8")
    with pytest.raises(src.DeliverableUnverifiedError, match="bukan JSON"):
        src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path)


def test_loadVerifiedDeliverable_refuses_whenTextIsNotString(tmp_path):
    (tmp_path / "7.json").write_text(json.dumps({"jobId": 7, "text": 12}), encoding="utf-8")
    with pytest.raises(src.DeliverableUnverifiedError, match="bukan string"):
        src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path)


def test_loadVerifiedDeliverable_refuses_whenFileTooLarge(tmp_path, monkeypatch):
    write_artifact(tmp_path, 7, HONEST_TEXT)
    monkeypatch.setattr(src, "MAX_DELIVERABLE_BYTES", 10)
    with pytest.raises(src.DeliverableUnverifiedError, match="batas"):
        src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), tmp_path)


def test_loadVerifiedDeliverable_refuses_whenArtifactIsSymlink(tmp_path):
    real = tmp_path / "nyata"
    real.mkdir()
    write_artifact(real, 7, HONEST_TEXT)
    box = tmp_path / "box"
    box.mkdir()
    (box / "7.json").symlink_to(real / "7.json")
    with pytest.raises(src.DeliverableUnverifiedError, match="symlink"):
        src.load_verified_deliverable(7, onchain_hash(HONEST_TEXT), box)


@pytest.mark.parametrize("job_id", ["7", "../7", 7.0, True, -1])
def test_loadVerifiedDeliverable_refuses_whenJobIdIsNotPlainInt(tmp_path, job_id):
    """Nama file DIBANGUN dari int; string pihak lain tidak pernah menjadi path."""
    write_artifact(tmp_path, 7, HONEST_TEXT)
    with pytest.raises(src.DeliverableUnverifiedError, match=src.REFUSAL_LINE):
        src.load_verified_deliverable(job_id, onchain_hash(HONEST_TEXT), tmp_path)


def test_deliverableDir_readsEnv_thenFallsBackToDefault(monkeypatch, tmp_path):
    monkeypatch.delenv(src.DELIVERABLE_DIR_ENV, raising=False)
    assert str(src.deliverable_dir()) == src.DEFAULT_DELIVERABLE_DIR
    monkeypatch.setenv(src.DELIVERABLE_DIR_ENV, str(tmp_path))
    assert src.deliverable_dir() == tmp_path
    assert src.deliverable_dir(tmp_path / "lain") == tmp_path / "lain"


def test_keccakText_matchesSdkVector():
    """Vektor dari docs/api-facts.md §B.1: `keccak256(toHex(s))` SDK == `Web3.keccak(text=s)`."""
    assert (
        "0x" + src.keccak_text("ipfs://bafkreiabc123").hex()
        == "0xc08fd6cd378f3bf0b1474acb8c35171dbde09e82d09074a574fcb6c9db20d3bd"
    )
