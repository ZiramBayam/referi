"""Pipa verdict `run_live` DIJALANKAN SAMPAI SELESAI — temuan TINGGI-1/TINGGI-2 review 2.4b.

Yang dibuktikan di sini, dan hanya ini:

  TINGGI-1  Verdict REJECT saat job masih `Funded` (gating cap, spec §5 langkah 2) BISA
            diumumkan. Bentuk lama menuntut `Evaluation`, yang baru ada sesudah provider
            `submit()` — jadi penolakan `budget > cap` mustahil diumumkan dan gagalnya
            SENYAP (`MemoryRootMismatch` turunan `SafeModeStop` → exit 0, nol tx). Itu
            persis job C rantai 2.5.
  TINGGI-2  Rerun sesudah `postVerdict` mendarat TETAP menulis hasil job ke memori. Cabang
            "verdict SUDAH ADA" dulu melewati `record_outcome` selamanya: insiden job A
            hilang → promosi tidak pernah mencapai count >= 2 → risk 0 → `NO_CAP` →
            `cap_to_onchain` = 0 = TANPA BATAS (ADR-001) → job C tidak pernah ditolak.
  SEDANG-1  Mode yang dipakai saat rencana disusun terikat dengan mode saat tx dikirim.
  SEDANG-2  Penolakan yang BUKAN mode-aman-saat-start punya kode keluar sendiri (bukan 0).

RPC dipalsukan seluruhnya: offline, deterministik, tanpa kunci. Tidak satu pun tes di sini
mengirim transaksi ke jaringan mana pun.
"""

from __future__ import annotations

import json
import logging
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

JOB_A = 41  # insiden pertama (rantai 2.5)
JOB_B = 42  # insiden kedua  → promosi, risk 2, cap
JOB_C = 43  # job yang di-fund dengan budget di atas cap
PATTERN = "supply-salah"
DET_CHECK = "chain"

DESCRIPTION = "Tulis ringkasan singkat pekerjaan"
DELIVERABLE_OK = "# Summary\nRingkasan pekerjaan yang sudah selesai dan lengkap.\n"
DELIVERABLE_TODO = (
    "# Summary\nRingkasan pekerjaan yang belum selesai.\n\n- TODO: lengkapi bagian ini\n"
)


# ----------------------------------------------------------------------
# RPC palsu — cukup lengkap untuk MENJALANKAN run_live sampai akhir
# ----------------------------------------------------------------------


class FakeFunction:
    def __init__(self, contract: FakeContract, name: str, args: tuple, kwargs: dict) -> None:
        self.contract = contract
        self.fn_name = name
        self.args = args
        self.kwargs = kwargs

    def call(self):
        self.contract.eth.reads.append(self.fn_name)
        return self.contract.returns[self.fn_name]

    def build_transaction(self, params):
        self.contract.eth.built.append(self.fn_name)
        return {"to": self.contract.address, "data": "0x", **params}


class FakeFunctions:
    def __init__(self, contract: FakeContract) -> None:
        self._contract = contract

    def __getattr__(self, name: str):
        def maker(*args, **kwargs):
            return FakeFunction(self._contract, name, args, kwargs)

        return maker


class FakeEventType:
    def __init__(self, contract: FakeContract, name: str) -> None:
        self.contract = contract
        self.name = name

    def get_logs(self, argument_filters=None, from_block=None, to_block=None):
        keluar = []
        for event in self.contract.eth.logs.get(self.name, []):
            if argument_filters and any(event["args"].get(k) != v for k, v in argument_filters.items()):
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
    def __init__(self, eth: FakeEth, returns: dict, address: str) -> None:
        self.eth = eth
        self.returns = returns
        self.address = address
        self.functions = FakeFunctions(self)
        self.events = FakeEvents(self)


class FakeReceipt:
    def __init__(self, status: int = 1, block: int = 46_400_100) -> None:
        self.status = status
        self.blockNumber = block


class FakeEth:
    def __init__(self, returns: dict, logs: dict, receipt_logs: dict) -> None:
        self.returns = returns
        self.logs = logs
        self.receipt_logs = receipt_logs
        self.reads: list[str] = []
        self.built: list[str] = []
        self.sent: list[bytes] = []
        self.nonce_reads = 0
        self.chain_id = 84532
        self.block_number = 46_400_000
        self.timestamp = 4_000_000_000  # selalu SESUDAH readyAt: tidak ada tes yang menunggu

    def contract(self, address=None, abi=None):
        return FakeContract(self, self.returns, address or VAULT_ADDRESS)

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
    status: int = 1,
    budget: int = 2_000_000,
    deliverable: bytes | None = None,
    verdict: tuple | None = None,
    onchain_root: bytes = ROOT_ONCHAIN,
    ready_at: int = 3_000_000_000,
) -> vc.VaultClient:
    returns = {
        "lastMemoryRoot": onchain_root,
        "jobs": (CLIENT, status, PROVIDER, 0, VAULT_ADDRESS, ZERO_ADDRESS, budget, DESCRIPTION),
        "verdicts": verdict or (0, ZERO, ZERO, 0, False, ZERO_ADDRESS),
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
        "VerdictPosted": [{"args": {"jobId": job_id, "kind": 2, "readyAt": ready_at}}],
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


def write_artifact(directory: pathlib.Path, job_id: int, text: str) -> bytes:
    """Artefak ADR-019 keputusan 1 persis seperti `sim/`; mengembalikan hash on-chain-nya."""
    directory.mkdir(parents=True, exist_ok=True)
    digest = Web3.keccak(text=text)
    (directory / f"{job_id}.json").write_text(
        json.dumps({"jobId": job_id, "text": text, "sha_keccak": "0x" + digest.hex()}),
        encoding="utf-8",
    )
    return bytes(digest)


def seed_two_incidents(db: pathlib.Path) -> mp.ProviderProfile:
    """Rantai 2.5 job A + job B lewat JALUR SUNGGUHAN: outcome → karantina → promosi.

    Tidak ada profil yang ditulis tangan: risk 2 di sini benar-benar lahir dari dua job
    berbeda yang gagal cek DETERMINISTIK, persis syarat spec §3 aturan 2.
    """
    memori = MemoryClient.local(str(db))
    for job in (JOB_A, JOB_B):
        mp.record_job_outcome(
            memori, PROVIDER, job_id=job, budget=1_000_000, passed=False, failed_checks=[DET_CHECK]
        )
        mp.record_suspicion(memori, PROVIDER, PATTERN, mp.Evidence(job, DET_CHECK, proof="bukti"))
    mp.promote_suspicions(memori, PROVIDER)
    return mp.DecisionMemoryView(memori).provider(PROVIDER)


def assert_nothing_was_sent(client: vc.VaultClient) -> None:
    eth = client.w3.eth
    assert eth.sent == [], f"ada transaksi terkirim: {eth.sent}"
    assert eth.built == [], f"ada transaksi dibangun: {eth.built}"
    assert eth.nonce_reads == 0, "nonce dibaca — jalur tx sudah dimulai"
    assert client.sent_transactions == []


# ======================================================================
# TINGGI-1 — verdict penolakan GERBANG saat job masih `Funded`
# ======================================================================


def test_the_seeded_chain_really_produces_a_cap_that_rejects_job_c(db):
    """Prasyarat tes di bawah, dibuktikan sendiri: dua insiden → risk 2 → cap 250000."""
    profil = seed_two_incidents(db)
    assert profil.risk_level == 2
    assert profil.incident_jobs == (JOB_A, JOB_B)

    mode = mp.decide_mode(ROOT_ONCHAIN, mp.LocalMemoryEvidence.ok(job_outcomes=2, root=ZERO, detail="tes"))
    gate = mp.gate_job(mp.DecisionMemoryView(MemoryClient.local(str(db))), PROVIDER, 2_000_000, mode)
    assert gate.accept is False
    assert gate.cap.cap_usdc == 250_000
    assert gate.incident_jobs == (JOB_A, JOB_B)
    assert gate.risk_level == 2


def test_a_funded_job_over_cap_is_actually_announced_as_reject(db, caplog):
    """TINGGI-1: `budget > cap` saat `Funded` → `postVerdict(REJECT)` + `finalize`, BUKAN nol tx.

    Bentuk lama melempar `MemoryRootMismatch` ("tidak ada hasil evaluasi") sebelum satu pun
    transaksi dibangun, dan karena ia turunan `SafeModeStop` `main()` melaporkan exit 0.
    """
    seed_two_incidents(db)
    client = build_client(db=db, job_id=JOB_C, status=1, budget=2_000_000)

    with caplog.at_level(logging.INFO, logger="vault_client"):
        kode = vc.run_job(client, JOB_C, vc.KIND_COMPLETE)

    assert kode == 0
    assert client.w3.eth.built == ["postVerdict", "finalize"]
    assert len(client.sent_transactions) == 2
    # `--kind complete` TIDAK boleh menang atas gating (spec §5 langkah 2).
    assert "GERBANG MENOLAK" in caplog.text
    assert "gate=DITOLAK" in caplog.text


def test_the_gate_rejection_bundle_names_the_cap_and_both_incident_jobs(db):
    """TASKS 2.5 AC (c): bundel job C memuat kata `cap` + KEDUA jobId insiden."""
    seed_two_incidents(db)
    client = build_client(db=db, job_id=JOB_C, status=1, budget=2_000_000)
    plan = vc.plan_job(client, client.job(JOB_C))
    assert plan.evaluation is None and plan.gate.accept is False

    root = client.refresh_memory_gate().local.root
    bundel = vc.verdict_evidence(plan, root)

    assert bundel["kind"] == vc.EVIDENCE_KIND_GATE_REJECTION
    assert bundel["gate"]["cap"]["usdc"] == 250_000
    assert bundel["gate"]["cap"]["basis"]
    assert bundel["gate"]["incident_jobs"] == [JOB_A, JOB_B]
    assert bundel["gate"]["budget"] == 2_000_000
    assert bundel["memory_root"] == "0x" + root.hex()

    teks = mp.canonical_json(bundel)
    assert "cap" in teks
    assert str(JOB_A) in teks and str(JOB_B) in teks
    # reasonHash = keccak bundel kanonik — bisa dihitung ulang auditor mana pun.
    assert vc.verdict_reason_hash(bundel) == bytes(Web3.keccak(text=teks))


def test_the_reason_hash_that_reaches_postverdict_is_the_hash_of_that_bundle(db, monkeypatch):
    """Bundel yang disimpan/diaudit dan `reasonHash` di calldata WAJIB satu nilai."""
    seed_two_incidents(db)
    client = build_client(db=db, job_id=JOB_C, status=1, budget=2_000_000)
    terekam: dict = {}
    asli = vc.VaultClient.post_verdict

    def spy(self, job_id, kind, reason_hash, memory_root):
        terekam.update(
            {"job_id": job_id, "kind": kind, "reason_hash": reason_hash, "root": memory_root}
        )
        return asli(self, job_id, kind, reason_hash, memory_root)

    monkeypatch.setattr(vc.VaultClient, "post_verdict", spy)
    assert vc.run_job(client, JOB_C, vc.KIND_REJECT) == 0

    plan = vc.plan_job(client, client.job(JOB_C))
    root = client.refresh_memory_gate().local.root
    assert terekam["kind"] == vc.KIND_REJECT
    assert terekam["root"] == root
    assert terekam["reason_hash"] == vc.verdict_reason_hash(vc.verdict_evidence(plan, root))


def test_a_gate_rejection_bundle_can_never_ride_along_with_a_complete_verdict(db):
    """Bukti penolakan cap + verdict `complete` = verdict yang membantah buktinya sendiri."""
    seed_two_incidents(db)
    client = build_client(db=db, job_id=JOB_C, status=1, budget=2_000_000)
    plan = vc.plan_job(client, client.job(JOB_C))

    with pytest.raises(vc.MemoryRootMismatch) as exc:
        vc.run_live(client, JOB_C, vc.KIND_COMPLETE, plan=plan)
    assert "BUKTI PENOLAKAN GERBANG TIDAK COCOK" in str(exc.value)
    assert_nothing_was_sent(client)


def test_a_funded_job_within_cap_still_has_no_verdict_to_announce(db):
    """Kontrol: yang dibuka HANYA penolakan gerbang, bukan "verdict tanpa bukti"."""
    client = build_client(db=db, job_id=JOB_C, status=1, budget=1)
    plan = vc.plan_job(client, client.job(JOB_C))
    assert plan.evaluation is None and plan.gate.accept is True

    with pytest.raises(vc.MemoryRootMismatch):
        vc.verdict_evidence(plan, mp.empty_memory_root())
    with pytest.raises(vc.MemoryRootMismatch):
        vc.run_live(client, JOB_C, vc.KIND_REJECT, plan=plan)
    assert_nothing_was_sent(client)


def test_an_evaluation_bundle_is_still_the_evaluation_shape(db, artifacts):
    """Bentuk lama tidak boleh ikut berubah isinya: job Submitted tetap dinilai dari cek."""
    digest = write_artifact(artifacts, JOB_C, DELIVERABLE_OK)
    client = build_client(db=db, job_id=JOB_C, status=2, deliverable=digest)
    plan = vc.plan_job(client, client.job(JOB_C), deliverable_dir=artifacts)

    bundel = vc.verdict_evidence(plan, mp.empty_memory_root())
    assert bundel["kind"] == vc.EVIDENCE_KIND_EVALUATION
    assert "gate" not in bundel
    assert bundel["evaluation"]["job"] == JOB_C


# ======================================================================
# TINGGI-2 — cabang "verdict SUDAH ADA" tetap menulis memori
# ======================================================================


def build_submitted_client(db, artifacts, *, verdict=None, text: str = DELIVERABLE_TODO):
    digest = write_artifact(artifacts, JOB_B, text)
    return build_client(db=db, job_id=JOB_B, status=2, deliverable=digest, verdict=verdict)


def profil(db: pathlib.Path) -> mp.ProviderProfile:
    return mp.DecisionMemoryView(MemoryClient.local(str(db))).provider(PROVIDER)


def test_a_rerun_after_postverdict_still_records_the_job_outcome(db, artifacts, caplog):
    """TINGGI-2: verdict sudah ada on-chain → `finalize` saja, TETAPI memori tetap ditulis.

    Jalur masuknya adalah aksi demo yang sangat mungkin terjadi: `EXIT_STOPPED_MIDWAY`,
    timeout receipt, atau `--job-id` yang diulang tangan. Dulu hasil job hilang SELAMANYA
    di sini, dan rantai akibatnya berakhir di "job C tidak pernah ditolak".
    """
    sudah_ada = (vc.KIND_REJECT, ZERO, ZERO, 1_000, False, ZERO_ADDRESS)
    client = build_submitted_client(db, artifacts, verdict=sudah_ada)
    plan = vc.plan_job(client, client.job(JOB_B), deliverable_dir=artifacts)
    assert plan.evaluation is not None and plan.evaluation.passed is False

    assert profil(db).stats_jobs == 0
    with caplog.at_level(logging.INFO, logger="vault_client"):
        kode = vc.run_live(client, JOB_B, vc.KIND_REJECT, plan=plan)

    assert kode == 0
    assert client.w3.eth.built == ["finalize"], "postVerdict memang dilewati (verdict sudah ada)"
    sesudah = profil(db)
    assert sesudah.stats_jobs == 1
    assert sesudah.stats_reject == 1
    assert sesudah.recorded_jobs == (JOB_B,)
    assert sesudah.incident_jobs == (JOB_B,), "insiden WAJIB lahir juga di cabang ini"


def test_recording_in_both_branches_never_counts_a_job_twice(db, artifacts):
    """`record_job_outcome` idempoten per `job_id` — itulah yang membuat TINGGI-2 aman."""
    sudah_ada = (vc.KIND_REJECT, ZERO, ZERO, 1_000, False, ZERO_ADDRESS)
    for _ in range(3):
        client = build_submitted_client(db, artifacts, verdict=sudah_ada)
        plan = vc.plan_job(client, client.job(JOB_B), deliverable_dir=artifacts)
        assert vc.run_live(client, JOB_B, vc.KIND_REJECT, plan=plan) == 0

    sesudah = profil(db)
    assert sesudah.stats_jobs == 1
    assert sesudah.recorded_jobs == (JOB_B,)
    assert sesudah.incident_jobs == (JOB_B,)


def test_the_fresh_verdict_branch_records_between_postverdict_and_finalize(db, artifacts):
    """Kontrol untuk tes di atas: cabang normal tetap menulis, dan urutannya spec §5 5→6."""
    client = build_submitted_client(db, artifacts)
    plan = vc.plan_job(client, client.job(JOB_B), deliverable_dir=artifacts)
    urutan: list[str] = []
    asli_send = vc.VaultClient._send
    asli_record = vc.record_outcome

    def send(self, func, extra=None):
        urutan.append(getattr(func, "fn_name", "tx"))
        return asli_send(self, func, extra)

    def record(client_, plan_):
        urutan.append("record_outcome")
        return asli_record(client_, plan_)

    vc.VaultClient._send = send
    vc.record_outcome = record
    try:
        assert vc.run_live(client, JOB_B, vc.KIND_REJECT, plan=plan) == 0
    finally:
        vc.VaultClient._send = asli_send
        vc.record_outcome = asli_record

    assert urutan == ["postVerdict", "record_outcome", "finalize"]
    assert profil(db).recorded_jobs == (JOB_B,)


# ======================================================================
# SEDANG-1 — mode saat rencana == mode saat mengirim
# ======================================================================


def test_a_mode_that_changes_between_plan_and_send_stops_the_pipeline(db, artifacts, tmp_path):
    """Rencana lahir dalam mode NORMAL; memori lenyap; gerbang jadi NAIF → BERHENTI.

    Tanpa penjaga ini `postVerdict` TERKIRIM membawa root DB KOSONG sementara `reasonHash`
    mengikat bundel yang menyatakan `mode=normal`: auditor yang merekonstruksi memori
    pelahir verdict mendapat DB kosong. Prasyaratnya `lastMemoryRoot == 0` — tidak berlaku
    di vault beku, tetapi BERLAKU di Anvil / vault segar (TASKS 2.5 AC (e), 3.3b varian A).
    """
    client = build_submitted_client(db, artifacts)
    client.w3.eth.returns["lastMemoryRoot"] = ZERO  # vault segar
    plan = vc.plan_job(client, client.job(JOB_B), deliverable_dir=artifacts)
    assert plan.mode.mode == mp.MODE_NORMAL

    for suffix in vc.MEMORY_DB_SUFFIXES:  # memori lenyap DI ANTARA rencana dan tx
        db.with_name(db.name + suffix).unlink(missing_ok=True)
    assert client.refresh_memory_gate().decision.mode == mp.MODE_NAIVE

    with pytest.raises(vc.MemoryRootMismatch) as exc:
        vc.run_live(client, JOB_B, vc.KIND_REJECT, plan=plan)
    assert "MODE BERUBAH DI TENGAH PIPA" in str(exc.value)
    assert_nothing_was_sent(client)


def test_an_empty_root_is_never_announced_after_a_real_memory_was_read(db):
    """Lapis kedua SEDANG-1: latch di klien, bukan di `run_live`.

    Jalur baru yang tidak membandingkan mode tetap berhenti — alasan yang sama persis
    mengapa mode aman ditegakkan di `_send()` dan bukan di pemanggil.
    """
    seed_two_incidents(db)
    client = build_client(db=db, job_id=JOB_C, onchain_root=ZERO)
    assert client.refresh_memory_gate().decision.mode == mp.MODE_NORMAL
    assert client.observed_readable_memory is True

    for suffix in vc.MEMORY_DB_SUFFIXES:
        db.with_name(db.name + suffix).unlink(missing_ok=True)
    assert client.refresh_memory_gate().decision.mode == mp.MODE_NAIVE

    with pytest.raises(vc.MemoryRootMismatch) as exc:
        client.derived_memory_root()
    assert "ROOT KOSONG DITOLAK" in str(exc.value)
    with pytest.raises(vc.MemoryRootMismatch):
        client.post_verdict(JOB_C, vc.KIND_REJECT, b"\x01" * 32, mp.empty_memory_root())
    assert_nothing_was_sent(client)


def test_a_genuinely_naive_client_still_announces_the_empty_root(tmp_path):
    """Kontrol negatif: latch tidak boleh mematikan hari pertama yang sah (ADR-024)."""
    client = build_client(db=tmp_path / "belum-ada.db", job_id=JOB_C, onchain_root=ZERO)
    assert client.refresh_memory_gate().decision.mode == mp.MODE_NAIVE
    assert client.observed_readable_memory is False
    assert client.derived_memory_root() == mp.empty_memory_root()


# ======================================================================
# SEDANG-2 — kode keluar untuk penolakan yang bukan mode aman saat start
# ======================================================================


def run_main_with(monkeypatch, client: vc.VaultClient, argv: list[str]) -> int:
    monkeypatch.setattr(vc, "build_client", lambda private_key=None: client)
    monkeypatch.setattr(vc, "load_private_key", lambda: "0x" + "11" * 32)
    monkeypatch.setattr(vc.Account, "from_key", staticmethod(lambda key: SigningAccount()))
    return vc.main(argv)


def test_main_reports_a_refusal_with_its_own_exit_code_not_zero(db, monkeypatch, caplog):
    """Root asing di calldata bukan keadaan normal ber-ADR — dan `--job-id` yang SUKSES
    juga mengembalikan 0, jadi otomasi 2.5 tidak bisa membedakan keduanya."""
    seed_two_incidents(db)
    client = build_client(db=db, job_id=JOB_C, status=1, budget=2_000_000)

    def tolak(client_, job_id, kind, plan=None):
        raise vc.MemoryRootMismatch("ROOT BUKAN TURUNAN MEMORI: tes")

    monkeypatch.setattr(vc, "run_live", tolak)
    with caplog.at_level(logging.INFO, logger="vault_client"):
        kode = run_main_with(monkeypatch, client, ["--job-id", str(JOB_C)])

    assert kode == vc.EXIT_REFUSED
    assert kode not in (0, vc.EXIT_STOPPED_MIDWAY)
    assert vc.EXIT_REFUSED_MESSAGE in caplog.text
    assert any(r.levelno >= logging.ERROR for r in caplog.records), "penolakan wajib level error"
    assert client.sent_transactions == []


def test_safe_mode_at_start_is_still_a_clean_exit_zero(tmp_path, monkeypatch, caplog):
    """Kontrol: mode aman SAAT START tetap 0 — ia perilaku yang diinginkan (spec §3 aturan 5)."""
    client = build_client(db=tmp_path / "hilang.db", job_id=JOB_C)
    monkeypatch.setattr(vc, "build_client", lambda private_key=None: client)
    monkeypatch.setattr(vc, "load_private_key", lambda: pytest.fail("kunci tidak boleh dimuat"))

    with caplog.at_level(logging.INFO, logger="vault_client"):
        assert vc.main(["--job-id", str(JOB_C)]) == 0
    assert "MODE AMAN" in caplog.text
    assert vc.EXIT_REFUSED_MESSAGE not in caplog.text


def test_a_successful_run_and_a_refused_run_do_not_share_an_exit_code(db, monkeypatch):
    """Inti SEDANG-2: sukses dan penolakan HARUS bisa dibedakan otomasi."""
    seed_two_incidents(db)
    sukses = build_client(db=db, job_id=JOB_C, status=1, budget=2_000_000)
    assert run_main_with(monkeypatch, sukses, ["--job-id", str(JOB_C)]) == 0
    assert len(sukses.sent_transactions) == 2
    assert vc.EXIT_REFUSED != 0
