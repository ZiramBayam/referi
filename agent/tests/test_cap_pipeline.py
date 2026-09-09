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


# ======================================================================
# (4) TINGGI-1 — `providerCap()` on-chain adalah LANTAI, bukan sekadar
#     pembanding kesetaraan
# ======================================================================
#
# `derive_cap` mengklaim monoton-tidak-naik, tetapi jangkarnya (`previous`) hidup di
# `memory.db` — file lokal yang model ancaman proyek ini SUDAH akui bisa ditulis pihak
# lain (kunci `flock` bersifat KOOPERATIF). Sejak `setProviderCap` punya pemanggil
# produksi, memori yang dimundurkan bisa MELONGGARKAN penegakan on-chain, yaitu
# satu-satunya mekanisme yang didemokan spec §7 langkah 2. Nilai on-chain sudah dibaca;
# ia harus MENGIKAT, bukan hanya dibandingkan sama/tidak.


def restore(snapshot: dict[str, bytes], db: pathlib.Path) -> None:
    for suffix in vc.MEMORY_DB_SUFFIXES:
        path = db.with_name(db.name + suffix)
        isi = snapshot.get(suffix)
        if isi is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(isi)


def snapshot_of(db: pathlib.Path) -> dict[str, bytes]:
    keluar = {}
    for suffix in vc.MEMORY_DB_SUFFIXES:
        path = db.with_name(db.name + suffix)
        if path.is_file():
            keluar[suffix] = path.read_bytes()
    return keluar


def test_a_restored_memory_snapshot_cannot_raise_the_cap_the_vault_enforces(db, artifacts, bundles):
    """Serangan yang dijalankan reviewer: `memory.db` dimundurkan ke snapshot sebelum job B.

    Memori lokal lalu menurunkan cap 1.000.000 (risk 1) sementara vault menegakkan 250.000.
    Tanpa lantai on-chain, satu job berikutnya MENAIKKAN cap 4x lewat `setProviderCap`.
    """
    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
    sebelum_b = snapshot_of(db)
    run_submitted_job(db, artifacts, JOB_B, DELIVERABLE_B, provider_cap_onchain=1_000_000)
    assert view(db).provider(PROVIDER).cap_usdc == 250_000

    restore(sebelum_b, db)
    assert mp.derive_cap(view(db).provider(PROVIDER)).cap_usdc == 1_000_000, (
        "prasyarat serangan: memori yang dimundurkan memang menghitung cap yang LEBIH LONGGAR"
    )

    client = run_submitted_job(
        db, artifacts, JOB_C, DELIVERABLE_OK, provider_cap_onchain=250_000
    )

    naik = [args for args in cap_args(client) if int(args[1]) > 250_000]
    assert naik == [], f"cap on-chain DINAIKKAN oleh memori yang dimundurkan: {naik}"
    # Lantai on-chain juga MENJANGKARKAN ulang memori: `previous` berikutnya bukan 1.000.000.
    assert view(db).provider(PROVIDER).cap_usdc == 250_000


def test_a_tighter_cap_set_by_hand_is_never_raised_by_the_agent(db, artifacts, bundles):
    """Varian tanpa penyerang: arbiter/operator memasang cap lebih ketat langsung di vault."""
    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
    client = run_submitted_job(
        db, artifacts, JOB_B, DELIVERABLE_B, provider_cap_onchain=100_000
    )

    assert cap_args(client) == [], "cap 100.000 di vault DINAIKKAN diam-diam jadi 250.000"
    assert "setProviderCap" not in sent_names(client)
    assert view(db).provider(PROVIDER).cap_usdc == 100_000


def test_set_provider_cap_refuses_a_raise_at_the_send_boundary(db, artifacts, bundles):
    """Lapis kedua, sepola `allow_unlimited`: batas kirim menolak kenaikan diam-diam."""
    client = build_client(db=db, job_id=JOB_B, status=2)
    client.w3.eth.provider_caps[PROVIDER.lower()] = 250_000
    with pytest.raises(vc.CapRaiseRefused):
        client.set_provider_cap(PROVIDER, 1_000_000)
    assert client.w3.eth.built == []
    assert client.sent_transactions == []


def test_set_provider_cap_raises_only_through_the_explicit_conscious_path(db, artifacts, bundles):
    """Kenaikan tetap MUNGKIN — tetapi hanya bila pemanggil mengetiknya."""
    client = build_client(db=db, job_id=JOB_B, status=2)
    client.w3.eth.provider_caps[PROVIDER.lower()] = 250_000
    client.set_provider_cap(PROVIDER, 1_000_000, allow_raise=True)
    assert cap_args(client) == [(Web3.to_checksum_address(PROVIDER), 1_000_000)]


def test_lowering_the_cap_is_always_allowed(db, artifacts, bundles):
    """Kontrol dua arah: lantai on-chain TIDAK boleh membekukan cap yang MENGETAT."""
    client = build_client(db=db, job_id=JOB_B, status=2)
    client.w3.eth.provider_caps[PROVIDER.lower()] = 1_000_000
    client.set_provider_cap(PROVIDER, 250_000)
    assert cap_args(client) == [(Web3.to_checksum_address(PROVIDER), 250_000)]


def test_the_first_cap_may_be_set_while_the_vault_still_says_unlimited(db, artifacts, bundles):
    """Kontrol: on-chain 0 = TANPA BATAS (ADR-001), jadi nilai apa pun di atasnya MENGETAT."""
    client = run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A, provider_cap_onchain=0)
    assert cap_args(client) == [(Web3.to_checksum_address(PROVIDER), 1_000_000)]


# ======================================================================
# (5) RENDAH-1 — cabang "sudah sinkron" tetap menuliskan cap ke memori
# ======================================================================


def test_cap_is_stored_in_memory_even_when_the_vault_already_holds_it(db, artifacts, bundles):
    """Tanpa ini, `provider.cap_usdc` tetap `None` di body yang masuk preimage `memory_root`:
    auditor yang merekonstruksi memori pada root yang DIUMUMKAN melihat "tanpa cap"
    sementara vault menegakkan 250.000."""
    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
    client = run_submitted_job(db, artifacts, JOB_B, DELIVERABLE_B, provider_cap_onchain=250_000)

    assert cap_args(client) == [], "nilai sama tidak boleh dikirim ulang (gas + nonce)"
    assert view(db).provider(PROVIDER).cap_usdc == 250_000


# ======================================================================
# (6) SEDANG-2 — gagal SESUDAH postVerdict wajib melapor BERHENTI DI TENGAH
# ======================================================================


def test_a_failure_after_postverdict_reports_stopped_midway_with_its_tx_list(
    db, artifacts, bundles, monkeypatch, caplog
):
    """`setProviderCap` disisipkan tepat di jendela antara `postVerdict` dan `finalize`.
    Kegagalannya (receipt status 0, galat RPC, penulisan memori yang kalah CAS) dulu jatuh
    ke `except Exception` generik → exit 1 TANPA satu pun baris yang mengatakan job
    MENGGANTUNG sampai `expiredAt` dan tanpa daftar tx yang sudah mendarat."""
    import logging

    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)

    digest = write_artifact(artifacts, JOB_B, DELIVERABLE_B)
    client = build_client(db=db, job_id=JOB_B, status=2, deliverable=digest)
    client.w3.eth.provider_caps[PROVIDER.lower()] = 1_000_000

    asli = client.wait_receipt
    panggilan = {"n": 0}

    def receipt_kedua_gagal(tx_hash):
        panggilan["n"] += 1
        return asli(tx_hash) if panggilan["n"] == 1 else FakeReceipt(status=0)

    monkeypatch.setattr(client, "wait_receipt", receipt_kedua_gagal)
    monkeypatch.setenv(vc.DELIVERABLE_DIR_ENV, str(artifacts))
    monkeypatch.setattr(vc, "build_client", lambda private_key=None: client)
    monkeypatch.setattr(vc, "load_private_key", lambda: "0x" + "11" * 32)
    monkeypatch.setattr(vc.Account, "from_key", staticmethod(lambda key: SigningAccount()))

    with caplog.at_level(logging.INFO, logger="vault_client"):
        kode = vc.main(["--job-id", str(JOB_B), "--kind", "reject"])

    assert sent_names(client) == ["postVerdict", "setProviderCap"]
    assert "finalize" not in sent_names(client)
    assert kode == vc.EXIT_STOPPED_MIDWAY
    assert vc.EXIT_STOPPED_MIDWAY_MESSAGE in caplog.text
    assert "HANGS until expiredAt" in caplog.text
    for tx_hash in client.sent_transactions:
        assert "0x" + tx_hash in caplog.text


def test_the_conscious_escape_hatches_have_zero_production_callers():
    """`allow_raise=True`/`allow_unlimited=True` adalah jalur SADAR: ia harus diketik, dan
    hari ini tidak seorang pun di jalur produksi mengetiknya. Tes ini yang membuat kalimat
    itu tetap benar besok.

    Pemindaiannya AST, bukan substring: pesan galat dan docstring MEMUAT kata itu apa
    adanya (dan memang harus), jadi pemindai substring akan merah pada teks yang benar.
    Yang ditandai: (a) argumen kata kunci itu dengan nilai apa pun selain `False` literal,
    dan (b) `**kwargs` pada panggilan `set_provider_cap`/`_send` — jalur yang bisa
    menyelundupkan keduanya tanpa mengetik namanya.
    """
    import ast

    def nama_fungsi(simpul: ast.Call) -> str:
        target = simpul.func
        if isinstance(target, ast.Attribute):
            return target.attr
        if isinstance(target, ast.Name):
            return target.id
        return ""

    paket = pathlib.Path(vc.__file__).parent
    pelanggar: list[str] = []
    for berkas in sorted(paket.rglob("*.py")):
        pohon = ast.parse(berkas.read_text(encoding="utf-8"), filename=str(berkas))
        for simpul in ast.walk(pohon):
            if not isinstance(simpul, ast.Call):
                continue
            for kata in simpul.keywords:
                if kata.arg in ("allow_raise", "allow_unlimited"):
                    literal_false = (
                        isinstance(kata.value, ast.Constant) and kata.value.value is False
                    )
                    # SATU pengecualian: pipa internal `set_provider_cap` → `_send` yang
                    # meneruskan parameter bernama SAMA. Ia tidak memilih apa pun.
                    diteruskan = (
                        nama_fungsi(simpul) == "_send"
                        and isinstance(kata.value, ast.Name)
                        and kata.value.id == kata.arg
                    )
                    if not (literal_false or diteruskan):
                        pelanggar.append(f"{berkas.relative_to(paket)}:{simpul.lineno}")
                elif kata.arg is None and nama_fungsi(simpul) in ("set_provider_cap", "_send"):
                    pelanggar.append(f"{berkas.relative_to(paket)}:{simpul.lineno} (**kwargs)")
    assert pelanggar == [], f"escape hatch cap dipakai di jalur produksi: {pelanggar}"


# ----------------------------------------------------------------------
# Task 3.0b — lantai on-chain di jalur KEPUTUSAN, bukan hanya jalur kirim
#
# Temuan 4 gerbang fase 2: `provider_cap()` hanya dibaca `_require_onchain_cap_floor`
# (batas KIRIM) dan `sync_provider_cap`. `gate_job` tidak pernah membacanya, sehingga
# memori yang dikosongkan membuat `derive_cap` mengembalikan None dan gerbang MENERIMA
# budget yang cap terbitan vault sendiri tolak. Lantai 2.4b menahan `setProviderCap` dari
# NAIK; ia tidak pernah menahan gerbang dari MENERIMA.
# ----------------------------------------------------------------------


def _mode_normal() -> mp.ModeDecision:
    return mp.ModeDecision(
        mode=mp.MODE_NORMAL,
        reason="uji 3.0b",
        depth=mp.DEPTH_SAMPLING,
        forced_risk=None,
        allow_finalize=True,
        allow_post_verdict=True,
        allow_set_provider_cap=True,
    )


def _gate(db: pathlib.Path, budget: int, onchain_cap: int | None) -> mp.GateDecision:
    memori = MemoryClient.local(str(db))
    try:
        mode = _mode_normal()
        return mp.gate_job(
            mp.DecisionMemoryView(memori), PROVIDER, budget, mode, onchain_cap=onchain_cap
        )
    finally:
        vc.close_memory_client(memori)


def test_an_emptied_memory_cannot_accept_what_the_vault_already_caps(db):
    """AC (a) — persis skenario juri: memori kosong + vault mengumumkan 250000."""
    tanpa_lantai = _gate(db, 2_000_000, None)
    assert tanpa_lantai.accept is True, "prasyarat: tanpa lantai, memori kosong memang menerima"
    assert tanpa_lantai.cap.cap_usdc is None

    dengan_lantai = _gate(db, 2_000_000, 250_000)
    assert dengan_lantai.accept is False
    assert dengan_lantai.onchain_cap == 250_000
    assert dengan_lantai.effective_cap == 250_000
    assert "DIUMUMKAN vault" in dengan_lantai.reason


def test_a_fresh_vault_publishes_zero_and_that_is_not_a_cap(db):
    """AC (b) — 0 = TIDAK DIPASANG (ADR-001), jadi AC (e) task 2.5 tidak berubah.

    Pada vault SEGAR capnya memang 0, dan job yang sama memang TIDAK ditolak tanpa memori:
    itulah jawaban demo untuk "hapus memori kalian", bukan bug.
    """
    assert _gate(db, 2_000_000, 0).accept is True
    assert _gate(db, 2_000_000, 0).onchain_cap is None
    assert _gate(db, 2_000_000, None).accept is True


def test_the_tighter_of_the_two_bounds_wins(db, artifacts, bundles):
    """AC (c) — cap memori 100000 lebih ketat dari on-chain 250000, dan itu yang berlaku."""
    run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
    run_submitted_job(db, artifacts, JOB_B, DELIVERABLE_B)
    profil = view(db).provider(PROVIDER)
    assert profil.risk_level == 2, "prasyarat: dua insiden terkonfirmasi"
    cap_memori = mp.derive_cap(profil, _mode_normal()).cap_usdc
    assert cap_memori is not None and cap_memori < 500_000, cap_memori

    # cap memori (250000) LEBIH KETAT dari lantai on-chain (500000) -> yang memori menang
    ketat = _gate(db, 400_000, 500_000)
    assert ketat.accept is False
    assert ketat.effective_cap == cap_memori, "yang lebih KETAT yang berlaku, bukan yang on-chain"
    assert "melebihi cap milestone" in ketat.reason


def test_a_negative_or_non_integer_floor_is_refused_not_ignored(db):
    with pytest.raises(TypeError):
        _gate(db, 1, "250000")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        _gate(db, 1, True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _gate(db, 1, -1)


def test_an_unreadable_onchain_cap_stops_the_run_instead_of_accepting(db, artifacts, bundles):
    """AC (d) — kerusakan lingkungan BUKAN izin (pelajaran task 2.4a).

    Kalau `providerCap()` tidak bisa dibaca, lantai on-chain tidak diketahui. Menerima
    dalam keadaan itu berarti memakai ketidaktahuan sebagai izin; jadi run berhenti dengan
    NOL transaksi, bukan lolos ke `postVerdict`.
    """
    digest = write_artifact(artifacts, JOB_A, DELIVERABLE_A)
    client = build_client(db=db, job_id=JOB_A, status=2, budget=1_000_000, deliverable=digest)

    def meledak(_provider: str) -> int:
        raise RuntimeError("RPC mati saat membaca providerCap")

    client.provider_cap = meledak  # type: ignore[method-assign]

    job = client.job(JOB_A)
    with pytest.raises(vc.SafeModeStop) as galat:
        vc.plan_job(client, job, deliverable_dir=artifacts)

    assert "providerCap" in str(galat.value)
    assert sent_names(client) == [], "nol transaksi saat lantai tidak bisa dibaca"
    assert client.w3.eth.nonce_reads == 0, "nonce tidak boleh dibaca sama sekali"


def test_plan_job_actually_hands_the_published_cap_to_the_gate(db, artifacts, bundles):
    """Kabelnya, bukan daunnya.

    Reviewer 3.0b membuktikan mutan AC (e) saya menguji bagian yang SALAH: mencabut lantai
    di DALAM `gate_job` memang merah, tetapi menghapus `onchain_cap=` di titik panggil
    `plan_job` membuat SELURUH suite tetap hijau sementara temuan 4 juri hidup lagi.
    Tes ini menutup kabel itu lewat pipa sungguhan.
    """
    digest = write_artifact(artifacts, JOB_A, DELIVERABLE_A)
    client = build_client(db=db, job_id=JOB_A, status=1, budget=2_000_000, deliverable=digest)
    client.w3.eth.provider_caps[PROVIDER.lower()] = 250_000  # vault mengumumkan cap

    plan = vc.plan_job(client, client.job(JOB_A), deliverable_dir=artifacts)

    assert plan.gate.accept is False, "cap terbitan vault harus mengikat gerbang lewat plan_job"
    assert plan.gate.onchain_cap == 250_000
    assert plan.gate.effective_cap == 250_000
    assert plan.gate.cap.cap_usdc is None, "memori memang kosong; yang menolak adalah lantai"


def test_an_unreadable_cap_also_locks_every_later_transaction(db, artifacts, bundles):
    """SEDANG-2 reviewer: jalur berhenti ini WAJIB memasang latch seperti tiga saudaranya."""
    digest = write_artifact(artifacts, JOB_A, DELIVERABLE_A)
    client = build_client(db=db, job_id=JOB_A, status=2, budget=1_000_000, deliverable=digest)
    client.provider_cap = lambda _p: (_ for _ in ()).throw(RuntimeError("RPC mati"))  # type: ignore[method-assign]

    with pytest.raises(vc.SafeModeStop):
        vc.plan_job(client, client.job(JOB_A), deliverable_dir=artifacts)

    assert client.refusal is not None, "latch harus terpasang"
    with pytest.raises(vc.SafeModeStop):
        client.finalize(JOB_A)
    assert sent_names(client) == [], "nol tx sesudah latch"


def test_the_bundle_carries_the_value_that_actually_decided_the_rejection(db, artifacts, bundles):
    """Mengikat perbaikan SEDANG-1 (bundel v4), bukan sekadar namanya.

    Reviewer 3.0b menunjukkan empat mutan LOLOS dengan suite penuh hijau: kedua field
    dihapus, di-hardcode `None` (bundel BERBOHONG), diisi cap MEMORI (provenance salah),
    dan versi dikembalikan ke v3. Karena itu yang di-assert di sini adalah ISI bundel dan
    REKOMPUTASI keputusannya, bukan keberadaan nama field.
    """
    digest = write_artifact(artifacts, JOB_A, DELIVERABLE_A)
    client = build_client(db=db, job_id=JOB_A, status=1, budget=2_000_000, deliverable=digest)
    client.w3.eth.provider_caps[PROVIDER.lower()] = 250_000

    plan = vc.plan_job(client, client.job(JOB_A), deliverable_dir=artifacts)
    bundel = vc.verdict_evidence(plan, bytes(32), vc.KIND_REJECT)
    gate = bundel["gate"]

    assert bundel["version"].endswith("/v4"), "isi berubah, jadi versinya WAJIB ikut"
    assert gate["cap"]["usdc"] is None, "memori kosong: yang menolak adalah lantai, bukan cap memori"
    assert gate["onchain_cap"] == 250_000, "lantai on-chain WAJIB ada di bukti"
    assert gate["effective_cap"] == 250_000
    assert gate["onchain_cap"] != gate["cap"]["usdc"], "provenance: lantai != cap memori"

    # Rekomputasi independen dari BUNDEL saja — inilah klaim docstring yang diuji.
    batas = [c for c in (gate["cap"]["usdc"], gate["onchain_cap"]) if c is not None]
    assert min(batas) == gate["effective_cap"]
    assert int(gate["budget"]) > min(batas), "auditor sampai ke accept=False dari bundel saja"
    assert gate["accept"] is False


def test_plan_job_hands_the_depth_the_memory_decided_to_the_checks(db, artifacts, bundles):
    """TB-1 juri 3.0a: KABEL memori→kedalaman, bukan daunnya.

    Juri memutus kabel `depth=decision.depth` (`vault_client.py:1970`) dengan menambal
    `evaluate_job` supaya SELALU `sampling` — dan 601 tes tetap HIJAU. Lapis kebijakan
    (`check_depth`) sudah terjaga, tetapi barisnya yang menyerahkan hasil itu ke cek TIDAK.
    Ini kelas yang sama dengan yang memblokir 3.0b ronde-1: penjaga ada, tidak ada yang
    memanggilnya. Tes ini menangkap `depth` yang BENAR-BENAR diterima `evaluate_job`.
    """
    dilihat: list[str] = []
    asli = vc.evaluate_job

    def rekam(job_id, onchain, **kw):
        dilihat.append(kw["depth"])
        return asli(job_id, onchain, **kw)

    # provider BERSIH (risk 0) -> sampling
    digest = write_artifact(artifacts, JOB_A, DELIVERABLE_A)
    bersih = build_client(db=db, job_id=JOB_A, status=2, budget=250_000, deliverable=digest)
    vc.evaluate_job = rekam  # type: ignore[assignment]
    try:
        vc.plan_job(bersih, bersih.job(JOB_A), deliverable_dir=artifacts)
        assert dilihat == [mp.DEPTH_SAMPLING], dilihat

        # provider yang SUDAH punya dua insiden terkonfirmasi -> full
        run_submitted_job(db, artifacts, JOB_A, DELIVERABLE_A)
        run_submitted_job(db, artifacts, JOB_B, DELIVERABLE_B)
        assert view(db).provider(PROVIDER).risk_level == 2, "prasyarat: risk 2"
        dilihat.clear()   # penyemai di atas juga lewat evaluate_job; hitung hanya yang berikut

        digest_c = write_artifact(artifacts, JOB_C, DELIVERABLE_A)
        kotor = build_client(db=db, job_id=JOB_C, status=2, budget=250_000, deliverable=digest_c)
        vc.plan_job(kotor, kotor.job(JOB_C), deliverable_dir=artifacts)
        assert dilihat == [mp.DEPTH_FULL], dilihat
    finally:
        vc.evaluate_job = asli  # type: ignore[assignment]
