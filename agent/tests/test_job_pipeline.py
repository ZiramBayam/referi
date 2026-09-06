"""Jalur `--job-id` tanpa polling — task 2.4-min (ADR-022 keputusan 2-3, ADR-019 keputusan 2).

Yang dibuktikan di sini, dan hanya ini:
  (a) `getJob` dibaca SEKALI, `client`/`provider`/`evaluator` ikut terbaca dan tercetak, dan
      job yang `evaluator != VAULT` DITOLAK — nol transaksi, nonce tidak pernah dibaca;
  (b) `client_address` yang sampai ke `record_job_outcome` berasal dari `getJob` itu, bukan
      dari tebakan — tanpa itu ADR-021 keputusan 2 mati diam-diam;
  (d) `DeliverableUnverifiedError` diperlakukan SEKELAS `SafeModeStop`: pemanggil menangkap,
      memasang kunci, dan sejak itu `_send()` menolak semuanya;
  (e) `DELIVERABLE_DIR` dibaca dengan pola `config_value` lalu DITERUSKAN sebagai argumen
      `deliverable_dir=`, karena `checks.source.deliverable_dir()` sengaja hanya membaca
      environment sungguhan (impor melingkar).

RPC dipalsukan seluruhnya: offline, deterministik, tanpa kunci. Bukti on-chain-nya (nonce
wallet agen sungguhan sebelum == sesudah) dijalankan manual, bukan di sini.
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
FOREIGN_EVALUATOR = "0x24BfA961e97FCb92186De4d8a2BaD8E62972C4f9"  # evaluator job ACP #1 nyata
ZERO_ADDRESS = "0x" + "00" * 20
JOB_ID = 4242
BUDGET = 1_000_000
DESCRIPTION = "Tulis ringkasan singkat pekerjaan"

DELIVERABLE_TEXT = "# Summary\nRingkasan pekerjaan yang sudah selesai dan lengkap.\n"
DELIVERABLE_HASH = bytes(Web3.keccak(text=DELIVERABLE_TEXT))

# topic0 `JobSubmitted` terverifikasi (docs/api-facts.md §A, `cast sig-event`, 2026-09-03).
# Nilainya hidup DI TES, bukan di modul: task 2.4b melarang konstanta 32-byte di jalur
# produksi, dan satu-satunya gunanya memang membuktikan fragmen ABI `vault_client.ACP_ABI`
# menghasilkan topic yang sama.
JOB_SUBMITTED_TOPIC0 = "0x80c17db79857f338a6a6df68a6883ecc0ce78e2202fe61ed979733573f40538e"


# ----------------------------------------------------------------------
# RPC palsu — mencatat setiap langkah menuju sebuah transaksi
# ----------------------------------------------------------------------


class FakeFunction:
    def __init__(self, contract: FakeContract, name: str, args: tuple) -> None:
        self.contract = contract
        self.fn_name = name
        self.args = args

    def call(self):
        self.contract.eth.reads.append((self.fn_name, self.args))
        return self.contract.returns[self.fn_name]

    def build_transaction(self, params):
        self.contract.eth.built.append(self.fn_name)
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
        self.contract.eth.log_queries.append((self.name, dict(argument_filters or {}), from_block, to_block))
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


class FakeEth:
    def __init__(self, returns: dict, logs: dict) -> None:
        self.returns = returns
        self.logs = logs
        self.reads: list[tuple] = []
        self.built: list[str] = []
        self.sent: list[bytes] = []
        self.log_queries: list[tuple] = []
        self.nonce_reads = 0
        self.chain_id = 84532
        self.block_number = 46_400_000

    def contract(self, address=None, abi=None):
        return FakeContract(self, self.returns, address)

    def get_transaction_count(self, address):
        self.nonce_reads += 1
        return 75

    def send_raw_transaction(self, raw):
        self.sent.append(raw)
        return b"\xaa" * 32


class FakeWeb3:
    def __init__(self, returns: dict, logs: dict) -> None:
        self.eth = FakeEth(returns, logs)

    @staticmethod
    def to_checksum_address(value):
        return Web3.to_checksum_address(value)


class FakeAccount:
    address = "0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894"

    def sign_transaction(self, tx):
        return type("Signed", (), {"raw_transaction": b"\xbb" * 32})()


def build_client(
    *,
    db: pathlib.Path,
    evaluator: str = VAULT_ADDRESS,
    status: int = 1,
    client_address: str = CLIENT,
    provider: str = PROVIDER,
    budget: int = BUDGET,
    deliverable: bytes | None = None,
) -> vc.VaultClient:
    returns = {
        "lastMemoryRoot": bytes.fromhex("11" * 32),
        "jobs": (client_address, status, provider, 0, evaluator, ZERO_ADDRESS, budget, DESCRIPTION),
        "verdicts": (0, bytes(32), bytes(32), 0, False, ZERO_ADDRESS),
    }
    logs: dict[str, list] = {"JobSubmitted": []}
    if deliverable is not None:
        logs["JobSubmitted"].append(
            {
                "blockNumber": 46_399_500,
                "args": {"jobId": JOB_ID, "provider": provider, "deliverable": deliverable},
            }
        )
    w3 = FakeWeb3(returns, logs)
    return vc.VaultClient(w3, VAULT_ADDRESS, ACP_ADDRESS, FakeAccount(), 84532, db_path=db)


@pytest.fixture
def db(tmp_path) -> pathlib.Path:
    """DB memori yang BENAR-BENAR ada dan kosong — bukan `None`, bukan hilang.

    Tanpa file, `decide_mode` jatuh ke mode aman (ADR-024 keputusan 2 cabang 2) dan setiap
    tes di bawah akan hijau karena alasan yang SALAH.
    """
    path = tmp_path / "memory.db"
    MemoryClient.local(str(path))
    return path


@pytest.fixture
def artifacts(tmp_path) -> pathlib.Path:
    return tmp_path / "deliverables"


def write_artifact(directory: pathlib.Path, job_id: int, text: str) -> None:
    """Menulis artefak ADR-019 keputusan 1 persis seperti `sim/`."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{job_id}.json").write_text(
        json.dumps(
            {"jobId": job_id, "text": text, "sha_keccak": "0x" + Web3.keccak(text=text).hex()}
        ),
        encoding="utf-8",
    )


def assert_nothing_was_sent(client: vc.VaultClient) -> None:
    eth = client.w3.eth
    assert eth.sent == [], f"ada transaksi terkirim: {eth.sent}"
    assert eth.built == [], f"ada transaksi dibangun: {eth.built}"
    assert eth.nonce_reads == 0, "nonce dibaca — artinya jalur tx sudah dimulai"
    assert client.sent_transactions == []


# ----------------------------------------------------------------------
# Fragmen ABI: topic0 yang dihasilkan WAJIB sama dengan yang diverifikasi
# ----------------------------------------------------------------------


def test_job_submitted_fragment_produces_the_verified_topic0():
    """Salah ketik nama/urutan tipe = filter log diam-diam kosong = setiap deliverable ditolak."""
    fragment = next(f for f in vc.ACP_ABI if f.get("name") == "JobSubmitted")
    signature = "JobSubmitted(" + ",".join(i["type"] for i in fragment["inputs"]) + ")"
    assert signature == "JobSubmitted(uint256,address,bytes32)"
    assert "0x" + Web3.keccak(text=signature).hex() == JOB_SUBMITTED_TOPIC0
    # Hanya jobId & provider yang indexed (docs/api-facts.md §A) — deliverable ada di `data`.
    assert [i["indexed"] for i in fragment["inputs"]] == [True, True, False]


def test_job_struct_has_no_deliverable_field():
    """Kenapa log dibutuhkan sama sekali: `jobs(uint256)` tidak mengembalikan deliverable."""
    jobs = next(f for f in vc.ACP_ABI if f.get("name") == "jobs")
    assert [o["name"] for o in jobs["outputs"]] == [
        "client",
        "status",
        "provider",
        "expiredAt",
        "evaluator",
        "hook",
        "budget",
        "description",
    ]


# ----------------------------------------------------------------------
# (a) getJob: client/provider/evaluator terbaca, evaluator asing DITOLAK
# ----------------------------------------------------------------------


def test_job_view_maps_the_acp_struct_field_by_field(db):
    client = build_client(db=db, status=2)
    job = client.job(JOB_ID)

    assert job.job_id == JOB_ID
    assert job.client_address == CLIENT
    assert job.provider == PROVIDER
    assert job.evaluator == VAULT_ADDRESS
    assert job.status == 2
    assert job.budget == BUDGET
    assert job.description == DESCRIPTION
    assert client.w3.eth.reads == [("jobs", (JOB_ID,))], "getJob dibaca lebih dari sekali"


def test_job_line_names_client_provider_and_evaluator(db, caplog):
    client = build_client(db=db, evaluator=FOREIGN_EVALUATOR)
    with caplog.at_level(logging.INFO, logger="vault_client"):
        vc.run_job(client, JOB_ID, vc.KIND_REJECT)
    assert f"client={CLIENT}" in caplog.text
    assert f"provider={PROVIDER}" in caplog.text
    assert f"evaluator={FOREIGN_EVALUATOR}" in caplog.text


def test_foreign_evaluator_is_refused_with_zero_transactions(db, caplog):
    """AC (a): exit 0, nol tx, nonce tidak pernah dibaca."""
    client = build_client(db=db, evaluator=FOREIGN_EVALUATOR)
    with caplog.at_level(logging.INFO, logger="vault_client"):
        assert vc.run_job(client, JOB_ID, vc.KIND_REJECT) == 0
    assert "JOB BUKAN MILIK VAULT INI" in caplog.text
    assert_nothing_was_sent(client)


def test_unknown_job_id_yields_a_zero_struct_and_is_refused(db):
    """`getJob` tidak revert untuk id tak dikenal (api-facts §A) → evaluator nol → ditolak."""
    client = build_client(db=db, evaluator=ZERO_ADDRESS, client_address=ZERO_ADDRESS)
    assert vc.run_job(client, JOB_ID, vc.KIND_REJECT) == 0
    assert_nothing_was_sent(client)


def test_checksum_difference_alone_does_not_make_a_job_foreign(db):
    client = build_client(db=db, evaluator=VAULT_ADDRESS.lower(), status=0)
    job = client.job(JOB_ID)
    assert job.is_for_evaluator(VAULT_ADDRESS) is True
    assert job.is_for_evaluator(FOREIGN_EVALUATOR) is False


def test_a_refused_job_locks_every_later_transaction(db):
    """Kunci sekali-jalan: jalur baru yang lupa memeriksa nilai balik tetap berhenti."""
    client = build_client(db=db, evaluator=FOREIGN_EVALUATOR)
    vc.run_job(client, JOB_ID, vc.KIND_REJECT)

    for call in (
        lambda: client.post_verdict(JOB_ID, vc.KIND_REJECT, b"\x01" * 32, b"\x02" * 32),
        lambda: client.finalize(JOB_ID),
        lambda: client.set_provider_cap(PROVIDER, 250_000),
    ):
        with pytest.raises(vc.SafeModeStop):
            call()
    assert_nothing_was_sent(client)


# ----------------------------------------------------------------------
# (d) DELIVERABLE TIDAK TERVERIFIKASI = berhenti sekelas mode aman
# ----------------------------------------------------------------------


def test_missing_artifact_stops_the_pipeline_with_zero_transactions(db, artifacts, caplog):
    """AC (d): `evaluate_job` melempar → pemanggil berhenti, nol postVerdict/finalize."""
    client = build_client(db=db, status=2, deliverable=DELIVERABLE_HASH)
    with caplog.at_level(logging.INFO, logger="vault_client"):
        assert vc.run_job(client, JOB_ID, vc.KIND_COMPLETE, deliverable_dir=artifacts) == 0

    assert vc.REFUSAL_LINE in caplog.text
    assert_nothing_was_sent(client)
    with pytest.raises(vc.SafeModeStop):
        client.post_verdict(JOB_ID, vc.KIND_COMPLETE, b"\x01" * 32, b"\x02" * 32)
    assert_nothing_was_sent(client)


def test_a_text_that_is_not_the_preimage_is_refused(db, artifacts):
    """Otoritasnya hash on-chain: teks lokal yang berbeda satu byte pun tidak menilai apa pun."""
    write_artifact(artifacts, JOB_ID, DELIVERABLE_TEXT + "tambahan")
    client = build_client(db=db, status=2, deliverable=DELIVERABLE_HASH)
    assert vc.run_job(client, JOB_ID, vc.KIND_COMPLETE, deliverable_dir=artifacts) == 0
    assert client.refusal is not None and client.refusal.startswith(vc.REFUSAL_LINE)
    assert_nothing_was_sent(client)


def test_a_missing_jobsubmitted_log_is_a_refusal_not_a_pass(db, artifacts):
    """Tidak ada hash on-chain = tidak ada yang bisa dibuktikan = REFUSE, bukan 'nilai saja'."""
    write_artifact(artifacts, JOB_ID, DELIVERABLE_TEXT)
    client = build_client(db=db, status=2, deliverable=None)
    assert vc.run_job(client, JOB_ID, vc.KIND_COMPLETE, deliverable_dir=artifacts) == 0
    assert client.refusal is not None and client.refusal.startswith(vc.REFUSAL_LINE)
    assert_nothing_was_sent(client)


def test_deliverable_lookup_walks_backwards_in_windows_the_public_rpc_accepts(db):
    """RPC publik membatasi selisih blok ke 10.000 (>= 10.001 → 413) → jendela 9.999."""
    client = build_client(db=db, status=2, deliverable=None)
    assert client.job_deliverable(JOB_ID, lookback_blocks=30_000) is None
    lebar = [int(hi) - int(lo) for _, _, lo, hi in client.w3.eth.log_queries]
    assert lebar and max(lebar) <= vc.LOG_WINDOW_BLOCKS
    assert all(f == {"jobId": JOB_ID} for _, f, _, _ in client.w3.eth.log_queries)


def test_a_funded_job_is_planned_without_touching_the_logs(db):
    """spec §5 langkah 2 berjalan sebelum ada deliverable; langkah 3 belum waktunya."""
    client = build_client(db=db, status=1)
    plan = vc.plan_job(client, client.job(JOB_ID), deliverable_dir=db.parent)
    assert plan.evaluation is None
    assert plan.deliverable is None
    assert client.w3.eth.log_queries == []
    assert plan.gate.accept in (True, False)  # keputusannya milik 2.5, keberadaannya milik sini


# ----------------------------------------------------------------------
# (b) client_address berasal dari getJob dan sampai ke record_job_outcome
# ----------------------------------------------------------------------


def build_plan(client: vc.VaultClient, artifacts: pathlib.Path) -> vc.JobPlan:
    write_artifact(artifacts, JOB_ID, DELIVERABLE_TEXT)
    return vc.plan_job(client, client.job(JOB_ID), deliverable_dir=artifacts)


def test_record_outcome_uses_the_client_address_from_getJob(db, artifacts):
    client = build_client(db=db, status=2, deliverable=DELIVERABLE_HASH)
    plan = build_plan(client, artifacts)
    assert plan.evaluation is not None and plan.evaluation.passed

    terekam: dict = {}
    asli = vc.record_job_outcome

    def spy(*args, **kwargs):
        terekam.update(kwargs)
        terekam["args"] = args
        return asli(*args, **kwargs)

    vc.record_job_outcome = spy
    try:
        vc.record_outcome(client, plan)
    finally:
        vc.record_job_outcome = asli

    assert terekam["client_address"] == CLIENT
    assert terekam["args"][1] == PROVIDER
    assert terekam["args"][2] == JOB_ID


def _record_outcome_calls_missing_client_address(source: str) -> list[str]:
    """Panggilan `record_job_outcome` di sebuah modul yang TIDAK mengetik `client_address`.

    Pemindaian AST, bukan substring: docstring dan pesan galat memuat kata
    `client_address` apa adanya (dan memang harus), jadi pemindai substring akan hijau
    justru pada file yang salah. Yang dilacak sama seperti pemindai gerbang root:
      - alias impor (`from agent.memory_policy import record_job_outcome as tulis`);
      - bentuk atribut (`mp.record_job_outcome(...)`);
      - `**kwargs` dan `*args` pada panggilan itu — dua jalur yang bisa MENGHILANGKAN
        argumennya tanpa satu pun karakter yang bisa dibaca manusia sebagai kelalaian.
    `def record_job_outcome(...)` sendiri BUKAN panggilan, jadi definisinya tidak ikut.
    """
    import ast

    tree = ast.parse(source)
    nama = "record_job_outcome"
    alias: set[str] = {nama}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == nama:
                    alias.add(a.asname or a.name)

    def menunjuk_record(func) -> bool:
        if isinstance(func, ast.Name):
            return func.id in alias
        # Bentuk atribut: yang menentukan adalah FUNGSI yang dipanggil, bukan lewat modul
        # mana ia diambil (`mp.`, `memory_policy.`, `vc.` — semuanya fungsi yang sama).
        return isinstance(func, ast.Attribute) and func.attr == nama

    pelanggar: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not menunjuk_record(node.func):
            continue
        if any(isinstance(a, ast.Starred) for a in node.args):
            pelanggar.append(f"{node.lineno} (*args)")
            continue
        if any(k.arg is None for k in node.keywords):
            pelanggar.append(f"{node.lineno} (**kwargs)")
            continue
        # `client_address` adalah parameter ke-7; mengisinya secara posisional pun sah.
        if any(k.arg == "client_address" for k in node.keywords) or len(node.args) >= 7:
            continue
        pelanggar.append(str(node.lineno))
    return pelanggar


def test_every_production_call_of_record_job_outcome_passes_client_address():
    """AC (h) 2.4a: pemindai MEKANIS, karena kelalaian di sini tidak berbunyi.

    `client_address` berdefault `None` supaya "tidak diketahui" bisa diucapkan — dan
    justru default itu yang membuat pemanggil BERIKUTNYA bisa melupakannya tanpa satu pun
    galat, satu pun baris log, atau satu pun tes merah. Yang mati diam-diam adalah filter
    ADR-021 keputusan 2 (`client == provider` -> budget dibuang): provider mendanai jobnya
    sendiri lewat EOA kedua, budgetnya masuk median, dan cap tidak pernah turun.

    Hari ini pemanggil produksinya SATU (`vault_client.record_outcome`). Tes ini yang
    membuat kalimat itu tetap benar besok — bukan disiplin, bukan review.
    """
    paket = pathlib.Path(vc.__file__).parent
    pelanggar: list[str] = []
    for berkas in sorted(paket.rglob("*.py")):
        for baris in _record_outcome_calls_missing_client_address(
            berkas.read_text(encoding="utf-8")
        ):
            pelanggar.append(f"{berkas.relative_to(paket)}:{baris}")
    assert pelanggar == [], (
        "record_job_outcome dipanggil TANPA client_address di jalur produksi "
        f"{pelanggar} — filter ADR-021 keputusan 2 (client == provider -> budget dibuang) "
        "MATI DIAM-DIAM di setiap panggilan itu: tidak ada galat, tidak ada log, hanya "
        "cap yang tidak pernah turun. Teruskan `getJob(jobId).client` ke sana."
    )


def test_the_scanner_itself_catches_every_way_of_dropping_the_argument():
    """Pemindai yang tidak pernah merah tidak menjaga apa pun — inilah buktinya merah."""
    impor = "from agent.memory_policy import record_job_outcome\n"
    assert _record_outcome_calls_missing_client_address(
        impor + "record_job_outcome(c, p, 1, 2, True)\n"
    )
    assert _record_outcome_calls_missing_client_address(
        impor + "record_job_outcome(c, p, 1, 2, True, failed_checks=())\n"
    )
    # Alias impor: namanya berubah, fungsinya sama.
    assert _record_outcome_calls_missing_client_address(
        "from agent.memory_policy import record_job_outcome as tulis\ntulis(c, p, 1, 2, True)\n"
    )
    # Bentuk atribut.
    assert _record_outcome_calls_missing_client_address(
        "from agent import memory_policy as mp\nmp.record_job_outcome(c, p, 1, 2, True)\n"
    )
    # Penyelundupan lewat pembongkaran: argumennya tidak terbaca mata.
    assert _record_outcome_calls_missing_client_address(
        impor + "record_job_outcome(c, p, 1, 2, True, **kw)\n"
    )
    assert _record_outcome_calls_missing_client_address(impor + "record_job_outcome(*a)\n")

    # Kontrol negatif — tanpa ini "selalu merah" akan lolos sebagai pemindai yang bekerja.
    assert not _record_outcome_calls_missing_client_address(
        impor + "record_job_outcome(c, p, 1, 2, True, client_address=x)\n"
    )
    assert not _record_outcome_calls_missing_client_address(
        impor + "record_job_outcome(c, p, 1, 2, True, client_address=None)\n"
    )
    assert not _record_outcome_calls_missing_client_address(
        impor + "record_job_outcome(c, p, 1, 2, True, (), x)\n"
    )
    # Definisinya sendiri bukan panggilan.
    assert not _record_outcome_calls_missing_client_address(
        "def record_job_outcome(c, p, j, b, passed, failed_checks=(), client_address=None):\n"
        "    return client_address\n"
    )


# ----------------------------------------------------------------------
# (j) `client_address` RUSAK dari getJob = berhenti sebelum tx pertama
# ----------------------------------------------------------------------


@pytest.mark.parametrize("rusak", ["", "0x", "0x" + "cc" * 19, "bukan-alamat"])
def test_a_broken_client_address_from_getJob_stops_the_run_with_zero_transactions(
    db, artifacts, rusak
):
    """AC (j) 2.4a: `getJob` yang gagal decode DITOLAK sebelum `postVerdict` dibangun.

    Tanpa penjaga ini urutannya adalah yang paling buruk yang mungkin: `postVerdict`
    MENDARAT, lalu `record_outcome` melempar, dan job menggantung sampai `expiredAt`
    dengan verdict yang sudah diumumkan tetapi tidak pernah difinalisasi.
    """
    client = build_client(db=db, status=2, client_address=rusak, deliverable=DELIVERABLE_HASH)
    write_artifact(artifacts, JOB_ID, DELIVERABLE_TEXT)
    with pytest.raises(vc.SafeModeStop) as exc:
        vc.run_job(client, JOB_ID, vc.KIND_COMPLETE, deliverable_dir=artifacts)
    pesan = str(exc.value)
    assert "client" in pesan and "ADR-021" in pesan, pesan
    assert repr(rusak) in pesan, pesan
    assert_nothing_was_sent(client)


def test_a_well_formed_client_address_is_not_stopped(db, artifacts):
    """Kontrol negatif: alamat sah tidak ditahan penjaga itu."""
    client = build_client(db=db, status=2, deliverable=DELIVERABLE_HASH)
    vc.require_readable_client_address(client.job(JOB_ID))  # tidak melempar


def test_a_self_funded_job_contributes_no_budget_through_this_path(db, artifacts):
    """ADR-021 keputusan 2 END-TO-END: client == provider → budget dibuang, jobs tetap naik."""
    client = build_client(db=db, status=2, client_address=PROVIDER, deliverable=DELIVERABLE_HASH)
    vc.record_outcome(client, build_plan(client, artifacts))

    memori = MemoryClient.local(str(db))
    profil = mp.DecisionMemoryView(memori).provider(PROVIDER)
    assert profil.passed_budgets == ()
    assert profil.stats_jobs == 1
    assert profil.stats_pass == 1


def test_a_normal_client_still_contributes_its_budget(db, artifacts):
    """Kontrol untuk tes di atas: tanpa ini, `passed_budgets == ()` bisa berarti apa saja."""
    client = build_client(db=db, status=2, deliverable=DELIVERABLE_HASH)
    vc.record_outcome(client, build_plan(client, artifacts))

    memori = MemoryClient.local(str(db))
    profil = mp.DecisionMemoryView(memori).provider(PROVIDER)
    assert profil.passed_budgets == (BUDGET,)
    assert profil.stats_jobs == 1


def test_record_outcome_writes_nothing_when_there_is_no_evaluation(db):
    """Job yang belum `Submitted` tidak punya hasil cek — dan memori tidak boleh menebak."""
    client = build_client(db=db, status=1)
    vc.record_outcome(client, vc.plan_job(client, client.job(JOB_ID), deliverable_dir=db.parent))

    memori = MemoryClient.local(str(db))
    assert mp.DecisionMemoryView(memori).list_providers() == []


# ----------------------------------------------------------------------
# (e) DELIVERABLE_DIR: pola config_value, diteruskan sebagai ARGUMEN
# ----------------------------------------------------------------------


def test_configured_deliverable_dir_follows_the_config_value_pattern(tmp_path, monkeypatch):
    monkeypatch.setenv(vc.DELIVERABLE_DIR_ENV, str(tmp_path / "dari-env"))
    assert vc.configured_deliverable_dir() == tmp_path / "dari-env"

    monkeypatch.delenv(vc.DELIVERABLE_DIR_ENV, raising=False)
    monkeypatch.setattr(vc, "_env_file_values", lambda: {vc.DELIVERABLE_DIR_ENV: "demo/lain"})
    assert vc.configured_deliverable_dir() == (vc.repo_root() / "demo/lain").resolve()

    monkeypatch.setattr(vc, "_env_file_values", dict)
    assert vc.configured_deliverable_dir() == (vc.repo_root() / vc.DEFAULT_DELIVERABLE_DIR).resolve()


def test_plan_job_passes_the_configured_directory_as_an_argument(db, tmp_path, monkeypatch):
    """`checks.source.deliverable_dir()` hanya membaca environment sungguhan; nilai dari
    `.env` repo karena itu WAJIB lewat argumen, bukan lewat `os.environ`."""
    monkeypatch.delenv(vc.DELIVERABLE_DIR_ENV, raising=False)
    monkeypatch.setattr(vc, "_env_file_values", lambda: {vc.DELIVERABLE_DIR_ENV: str(tmp_path / "x")})
    terekam: dict = {}

    def spy(job_id, onchain, **kwargs):
        terekam.update(kwargs)
        raise vc.DeliverableUnverifiedError(f"{vc.REFUSAL_LINE}: tes")

    monkeypatch.setattr(vc, "evaluate_job", spy)
    client = build_client(db=db, status=2, deliverable=DELIVERABLE_HASH)
    assert vc.run_job(client, JOB_ID, vc.KIND_COMPLETE) == 0

    assert terekam["deliverable_dir"] == (tmp_path / "x")
    assert terekam["depth"] in (mp.DEPTH_SAMPLING, mp.DEPTH_FULL)
    assert_nothing_was_sent(client)
