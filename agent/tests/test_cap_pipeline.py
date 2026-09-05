"""Rantai A/B/C task 2.5 — tulisan karantina/promosi DAN `setProviderCap` di jalur produksi.

Yang dibuktikan di sini, dan hanya ini:

  (1) spec §5 langkah 5 lengkap: sesudah `postVerdict`, agen menulis KETIGA hal — hasil job
      (`provider`), bukti pola gagal deterministik (`suspicion`), dan promosinya bila sudah
      memenuhi syarat. Sebelum task ini `record_outcome` hanya menulis yang pertama, jadi
      `reference:pattern` dan `provider.confirmed_patterns` TIDAK PERNAH lahir dari pipa —
      hanya dari tes yang menanamnya sendiri.

  (2) spec §7 langkah 2: begitu promosi mengangkat `risk` ke 2, cap turunan memori
      benar-benar DIKIRIM ke vault (`setProviderCap`). Tanpa langkah ini `providerCap()`
      on-chain tetap 0 = TANPA BATAS (ADR-001) dan gating job C tidak pernah bisa
      dibuktikan kepada siapa pun di luar proses agen.

  (3) Penjaga nilai 0 tetap yang terakhir bicara: `cap_usdc is None` → NOL transaksi.
      Cap yang sudah sama dengan nilai on-chain juga tidak dikirim ulang (gas + nonce).

RPC dipalsukan seluruhnya: offline, deterministik, tanpa kunci. Tidak satu pun tes di sini
mengirim transaksi ke jaringan mana pun.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from sibyl_memory_client import MemoryClient
from web3 import Web3

from agent import memory_policy as mp
from agent import vault_client as vc

VAULT_ADDRESS = "0x5c6EE4586ACABcb6326069c229E58091B21ef384"
ACP_ADDRESS = "0x0b93793923CD5De81850aF8604a233f3f24d461e"
CLIENT = "0x" + "cc" * 20
PROVIDER = "0x" + "ab" * 20
ZERO_ADDRESS = "0x" + "00" * 20
ZERO = bytes(32)
ROOT_ONCHAIN = bytes.fromhex("11" * 32)

JOB_A = 501
JOB_B = 502
JOB_C = 503

DESCRIPTION = "Tulis ringkasan singkat pekerjaan"
# Kedua deliverable gagal pada CEK yang sama (`format`) dan POLA yang sama
# (`format.placeholder-text`) — syarat spec §3 aturan 2 untuk promosi dari job BERBEDA.
DELIVERABLE_A = "# Summary\nRingkasan pekerjaan.\n\n- TODO: lengkapi angka supply\n"
DELIVERABLE_B = "# Summary\nRingkasan kedua.\n\n- TODO: bagian ini belum ditulis\n"
DELIVERABLE_OK = "# Summary\nRingkasan pekerjaan yang sudah selesai dan lengkap.\n"

PATTERN_TODO = "format.placeholder-text"


# ----------------------------------------------------------------------
# RPC palsu — cukup lengkap untuk MENJALANKAN run_job sampai finalize
# ----------------------------------------------------------------------


class FakeFunction:
    def __init__(self, contract: FakeContract, name: str, args: tuple) -> None:
        self.contract = contract
        self.fn_name = name
        self.args = args

    def call(self):
        self.contract.eth.reads.append((self.fn_name, self.args))
        return self.contract.returns_for(self.fn_name, self.args)

    def build_transaction(self, params):
        self.contract.eth.built.append((self.fn_name, self.args))
        return {"to": self.contract.address, "data": "0x", **params}


class FakeFunctions:
    def __init__(self, contract: FakeContract) -> None:
        self._contract = contract

    def __getattr__(self, name: str):
        def maker(*args):
            return FakeFunction(self._contract, name, args)

        return maker


class FakeEventType:
    def __init__(self, contract: FakeContract, name: str) -> None:
        self.contract = contract
        self.name = name

    def get_logs(self, argument_filters=None, from_block=None, to_block=None):
        keluar = []
        for event in self.contract.eth.logs.get(self.name, []):
            if argument_filters and any(
                event["args"].get(k) != v for k, v in argument_filters.items()
            ):
                continue
            if from_block is not None and int(event["blockNumber"]) < int(from_block):
                continue
            if to_block is not None and int(event["blockNumber"]) > int(to_block):
                continue
            keluar.append(event)
        return keluar

    def process_receipt(self, receipt, errors=None):
        return list(self.contract.eth.receipt_logs.get(self.name, []))


class FakeEvents:
    def __init__(self, contract: FakeContract) -> None:
        self._contract = contract

    def __getattr__(self, name: str):
        def maker():
            return FakeEventType(self._contract, name)

        return maker


class FakeContract:
    def __init__(self, eth: FakeEth, address: str) -> None:
        self.eth = eth
        self.address = address
        self.functions = FakeFunctions(self)
        self.events = FakeEvents(self)

    def returns_for(self, name: str, args: tuple):
        if name == "providerCap":
            return self.eth.provider_caps.get(str(args[0]).lower(), 0)
        return self.eth.returns[name]


class FakeReceipt:
    def __init__(self, status: int = 1, block: int = 46_400_100) -> None:
        self.status = status
        self.blockNumber = block


class FakeEth:
    def __init__(self, returns: dict, logs: dict, receipt_logs: dict) -> None:
        self.returns = returns
        self.logs = logs
        self.receipt_logs = receipt_logs
        self.provider_caps: dict[str, int] = {}
        self.reads: list[tuple] = []
        self.built: list[tuple] = []
        self.sent: list[bytes] = []
        self.nonce_reads = 0
        self.chain_id = 84532
        self.block_number = 46_400_000
        self.timestamp = 4_000_000_000  # selalu SESUDAH readyAt

    def contract(self, address=None, abi=None):
        return FakeContract(self, address or VAULT_ADDRESS)

    def get_transaction_count(self, address):
        self.nonce_reads += 1
        return 75

    def send_raw_transaction(self, raw):
        self.sent.append(raw)
        return b"\xaa" * 32

    def wait_for_transaction_receipt(self, tx_hash, timeout=None):
        return FakeReceipt()

    def get_block(self, which):
        return {"timestamp": self.timestamp}


class FakeWeb3:
    def __init__(self, returns: dict, logs: dict, receipt_logs: dict) -> None:
        self.eth = FakeEth(returns, logs, receipt_logs)

    @staticmethod
    def to_checksum_address(value):
        return Web3.to_checksum_address(value)


class SigningAccount:
    address = "0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894"

    def sign_transaction(self, tx):
        return type("Signed", (), {"raw_transaction": b"\xbb" * 32})()


def build_client(
    *,
    db: pathlib.Path,
    job_id: int,
    status: int = 2,
    budget: int = 1_000_000,
    deliverable: bytes | None = None,
) -> vc.VaultClient:
    returns = {
        "lastMemoryRoot": ROOT_ONCHAIN,
        "jobs": (CLIENT, status, PROVIDER, 0, VAULT_ADDRESS, ZERO_ADDRESS, budget, DESCRIPTION),
        "verdicts": (0, ZERO, ZERO, 0, False, ZERO_ADDRESS),
    }
    logs: dict[str, list] = {"JobSubmitted": []}
    if deliverable is not None:
        logs["JobSubmitted"].append(
            {
                "blockNumber": 46_399_500,
                "args": {"jobId": job_id, "provider": PROVIDER, "deliverable": deliverable},
            }
        )
    receipt_logs = {
        "VerdictPosted": [{"args": {"jobId": job_id, "kind": 2, "readyAt": 3_000_000_000}}],
        "Finalized": [{"args": {"jobId": job_id, "kind": 2, "reasonHash": ZERO}}],
        "FinalizeFailed": [],
    }
    w3 = FakeWeb3(returns, logs, receipt_logs)
    return vc.VaultClient(w3, VAULT_ADDRESS, ACP_ADDRESS, SigningAccount(), 84532, db_path=db)


@pytest.fixture
def db(tmp_path) -> pathlib.Path:
    path = tmp_path / "memory.db"
    MemoryClient.local(str(path))
    return path


@pytest.fixture
def artifacts(tmp_path) -> pathlib.Path:
    return tmp_path / "deliverables"


@pytest.fixture
def bundles(tmp_path, monkeypatch) -> pathlib.Path:
    directory = tmp_path / "verdicts"
    monkeypatch.setenv(vc.VERDICT_BUNDLE_DIR_ENV, str(directory))
    return directory


def write_artifact(directory: pathlib.Path, job_id: int, text: str) -> bytes:
    directory.mkdir(parents=True, exist_ok=True)
    digest = Web3.keccak(text=text)
    (directory / f"{job_id}.json").write_text(
        json.dumps({"jobId": job_id, "text": text, "sha_keccak": "0x" + digest.hex()}),
        encoding="utf-8",
    )
    return bytes(digest)


def run_submitted_job(
    db: pathlib.Path,
    artifacts: pathlib.Path,
    job_id: int,
    text: str,
    *,
    budget: int = 1_000_000,
    provider_cap_onchain: int = 0,
) -> vc.VaultClient:
    """Satu job `Submitted` melewati pipa SUNGGUHAN: run_job → postVerdict → memori → finalize."""
    digest = write_artifact(artifacts, job_id, text)
    client = build_client(db=db, job_id=job_id, status=2, budget=budget, deliverable=digest)
    client.w3.eth.provider_caps[PROVIDER.lower()] = provider_cap_onchain
    kode = vc.run_job(client, job_id, vc.KIND_REJECT, deliverable_dir=artifacts)
    assert kode == 0
    return client


def sent_names(client: vc.VaultClient) -> list[str]:
    return [name for name, _ in client.w3.eth.built]


def cap_args(client: vc.VaultClient) -> list[tuple]:
    return [args for name, args in client.w3.eth.built if name == "setProviderCap"]


def view(db: pathlib.Path) -> mp.DecisionMemoryView:
    return mp.DecisionMemoryView(MemoryClient.local(str(db)))


def suspicion_rows(db: pathlib.Path) -> list[dict]:
    memori = MemoryClient.local(str(db))
    return memori.list_entities(mp.CATEGORY_QUARANTINE, limit=100)


# ======================================================================
# (1) spec §5 langkah 5 — karantina lahir dari pipa, bukan dari tes
# ======================================================================


def test_job_a_writes_a_suspicion_with_count_one_and_no_promotion(db, artifacts, bundles):
    """Job A rantai 2.5: cek deterministik gagal → REJECT, `suspicion` count = 1."""
    client = run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)

    rows = suspicion_rows(db)
    assert len(rows) == 1, f"karantina tidak lahir dari pipa: {rows}"
    row = rows[0]
    assert row["name"] == mp.quarantine_name(PROVIDER, PATTERN_TODO)
    assert row["body"]["count"] == 1
    assert row["body"]["status"] == mp.QUARANTINE_STATUS_PENDING
    assert [e["job"] for e in row["body"]["evidence"]] == [JOB_A]

    profil = view(db).provider(PROVIDER)
    assert profil.risk_level == 1
    assert profil.incident_jobs == (JOB_A,)
    # Satu insiden BELUM promosi (spec §3 aturan 2 menuntut >= 2 job berbeda).
    assert profil.confirmed_patterns == ()
    assert view(db).pattern(PATTERN_TODO) is None
    assert "postVerdict" in sent_names(client)


def test_job_b_promotes_the_pattern_to_reference_and_provider(db, artifacts, bundles):
    """Job B: pola yang SAMA dari job BERBEDA → count 2 → promosi + risk 2."""
    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
    run_submitted_job(db, artifacts, JOB_B, DELIVERABLE_B, provider_cap_onchain=1_000_000)

    row = suspicion_rows(db)[0]
    assert row["body"]["count"] == 2
    assert row["body"]["status"] == mp.QUARANTINE_STATUS_PROMOTED

    profil = view(db).provider(PROVIDER)
    assert profil.risk_level == 2
    assert profil.incident_jobs == (JOB_A, JOB_B)
    assert profil.confirmed_patterns == (PATTERN_TODO,)

    pattern = view(db).pattern(PATTERN_TODO)
    assert pattern is not None
    assert pattern["pattern_id"] == PATTERN_TODO
    assert sorted(e["job"] for e in pattern["examples"]) == [JOB_A, JOB_B]


# ======================================================================
# (2) spec §7 langkah 2 — cap turunan memori BENAR-BENAR dikirim ke vault
# ======================================================================


def test_job_b_sends_setprovidercap_with_the_derived_cap(db, artifacts, bundles):
    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
    client = run_submitted_job(db, artifacts, JOB_B, DELIVERABLE_B, provider_cap_onchain=1_000_000)

    profil = view(db).provider(PROVIDER)
    cap = mp.derive_cap(profil)
    assert cap.cap_usdc == 250_000, "risk 2 → 25% baseline (spec §3 aturan 4)"

    assert cap_args(client) == [(Web3.to_checksum_address(PROVIDER), 250_000)]
    # Urutan spec §5 langkah 5→6: memori & cap di ANTARA postVerdict dan finalize.
    assert sent_names(client) == ["postVerdict", "setProviderCap", "finalize"]


def test_the_cap_that_was_sent_is_the_one_that_rejects_job_c(db, artifacts, bundles):
    """Rantai penuh: A → B → C. Job C masih `Funded` dan budgetnya di atas cap."""
    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
    run_submitted_job(db, artifacts, JOB_B, DELIVERABLE_B, provider_cap_onchain=1_000_000)

    client = build_client(db=db, job_id=JOB_C, status=1, budget=2_000_000)
    client.w3.eth.provider_caps[PROVIDER.lower()] = 250_000
    assert vc.run_job(client, JOB_C, vc.KIND_COMPLETE) == 0

    # Job C belum `Submitted` → tidak ada outcome, jadi tidak ada cap baru yang dikirim.
    assert sent_names(client) == ["postVerdict", "finalize"]
    plan = vc.plan_job(client, client.job(JOB_C))
    assert plan.gate.accept is False
    assert plan.gate.cap.cap_usdc == 250_000
    assert plan.gate.incident_jobs == (JOB_A, JOB_B)


# ======================================================================
# (3) penjaga: 0 = TANPA BATAS (ADR-001), dan tidak ada tx sia-sia
# ======================================================================


def test_a_passing_job_never_sends_a_cap(db, artifacts, bundles):
    """risk 0 → `cap_usdc is None` → `cap_to_onchain` = 0 = TANPA BATAS → NOL tx cap."""
    digest = write_artifact(artifacts, JOB_A, DELIVERABLE_OK)
    client = build_client(db=db, job_id=JOB_A, status=2, deliverable=digest)
    assert vc.run_job(client, JOB_A, vc.KIND_COMPLETE, deliverable_dir=artifacts) == 0

    assert view(db).provider(PROVIDER).risk_level == 0
    assert cap_args(client) == []
    assert "setProviderCap" not in sent_names(client)


def test_cap_is_not_resent_when_the_vault_already_holds_it(db, artifacts, bundles):
    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
    client = run_submitted_job(db, artifacts, JOB_B, DELIVERABLE_B, provider_cap_onchain=250_000)

    assert cap_args(client) == []
    assert sent_names(client) == ["postVerdict", "finalize"]


def test_sync_provider_cap_refuses_to_send_zero(db, artifacts, bundles, monkeypatch):
    """Mutan: `derive_cap` mengembalikan cap 0 → `UnlimitedCapRefused`, nol tx cap."""
    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
    profil = view(db).provider(PROVIDER)
    client = build_client(db=db, job_id=JOB_B, status=2)
    plan_mode = mp.decide_mode(
        ROOT_ONCHAIN, mp.LocalMemoryEvidence.ok(job_outcomes=1, root=ZERO, detail="tes")
    )

    monkeypatch.setattr(
        vc,
        "derive_cap",
        lambda profile, mode=None: mp.CapPlan(
            cap_usdc=0, require_milestone=True, basis="mutan", sample_size=0
        ),
    )
    with pytest.raises(vc.UnlimitedCapRefused):
        vc.sync_provider_cap(client, plan_mode, profil)
    assert client.w3.eth.built == []
    assert client.w3.eth.sent == []
