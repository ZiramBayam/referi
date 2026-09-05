"""Root & reasonHash yang diumumkan WAJIB turunan memori — task 2.4b (T2 laporan fase-1).

Yang dibuktikan di sini, dan hanya ini:
  (a) tidak ada konstanta 32-byte di jalur produksi `agent/agent/*.py`;
  (b) tidak ada lagi identifier root konstanta (`LIVE_MEMORY_ROOT`/`SELFTEST_MEMORY_ROOT`),
      dan satu-satunya `memory-root/v1` yang tersisa adalah LABEL ENCODING BEKU;
  (c) jalur `--selftest` — yang mengumumkan root konstanta atas jobId sintetis — DICABUT;
  (d) `post_verdict()` dengan root != `memory_root` saat itu MELEMPAR, nol transaksi:
      tidak dibangun, tidak ditandatangani, nonce tidak dibaca;
  (e) root yang diumumkan IDENTIK dengan root yang dicetak `agent/memory_export.py` atas DB
      yang sama — bukti "satu implementasi, bukan salinan". Inilah invarian yang membuat
      mutan "kembalikan konstanta dari `memory_root`" merah di kedua alat sekaligus.

RPC dipalsukan seluruhnya: offline, deterministik, tanpa kunci.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from sibyl_memory_client import MemoryClient
from web3 import Web3

from agent import memory_export as me
from agent import memory_policy as mp
from agent import vault_client as vc

ROOT_ONCHAIN = bytes.fromhex("11" * 32)
ZERO = bytes(32)
VAULT_ADDRESS = "0x" + "11" * 20
ACP_ADDRESS = "0x" + "22" * 20
PROVIDER = "0x" + "ab" * 20
CLIENT = "0x" + "cc" * 20
AGENT_ADDRESS = "0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894"
ASING = bytes.fromhex("02" * 32)  # root yang BUKAN turunan memori mana pun


# ----------------------------------------------------------------------
# RPC palsu — mencatat setiap langkah menuju sebuah transaksi
# ----------------------------------------------------------------------


class FakeFunction:
    def __init__(self, contract: FakeContract, name: str, args: tuple, kwargs: dict) -> None:
        self.contract = contract
        self.fn_name = name
        self.args = args
        self.kwargs = kwargs

    def call(self):
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


class FakeContract:
    def __init__(self, eth: FakeEth, returns: dict, address: str) -> None:
        self.eth = eth
        self.returns = returns
        self.address = address
        self.functions = FakeFunctions(self)


class FakeEth:
    def __init__(self, returns: dict) -> None:
        self.returns = returns
        self.built: list[str] = []
        self.sent: list[bytes] = []
        self.nonce_reads = 0
        self.chain_id = 84532
        self.block_number = 46_400_000

    def contract(self, address=None, abi=None):
        return FakeContract(self, self.returns, address or VAULT_ADDRESS)

    def get_transaction_count(self, address):
        self.nonce_reads += 1
        return 75

    def send_raw_transaction(self, raw):
        self.sent.append(raw)
        return b"\xaa" * 32


class FakeWeb3:
    def __init__(self, returns: dict) -> None:
        self.eth = FakeEth(returns)


class SigningAccount:
    address = AGENT_ADDRESS

    def sign_transaction(self, tx):
        class Signed:
            raw_transaction = b"\x99" * 8

        return Signed()


def build_client(db: pathlib.Path | None, *, onchain_root: bytes = ROOT_ONCHAIN) -> vc.VaultClient:
    returns = {
        "lastMemoryRoot": onchain_root,
        "jobs": (CLIENT, 1, PROVIDER, 0, VAULT_ADDRESS, "0x" + "00" * 20, 1, ""),
        "verdicts": (0, ZERO, ZERO, 0, False, "0x" + "00" * 20),
    }
    client = vc.VaultClient(
        FakeWeb3(returns), VAULT_ADDRESS, ACP_ADDRESS, SigningAccount(), 84532, db_path=db
    )
    return client


def assert_nothing_was_sent(client: vc.VaultClient) -> None:
    eth = client.w3.eth
    assert eth.built == [], f"transaksi dibangun: {eth.built}"
    assert eth.sent == [], f"transaksi terkirim: {eth.sent}"
    assert eth.nonce_reads == 0, "nonce dibaca — jalur tx sudah dimulai"
    assert client.sent_transactions == []


@pytest.fixture
def db(tmp_path) -> pathlib.Path:
    """DB berisi satu job outcome — memori yang BENAR-BENAR punya root turunan file."""
    path = tmp_path / "memory.db"
    memori = MemoryClient.local(str(path))
    mp.record_job_outcome(memori, PROVIDER, job_id=501, budget=1_000_000, passed=True)
    return path


# `rglob`, BUKAN `glob`: AC 2.4b berbunyi `agent/`, dan `glob("*.py")` melewatkan
# `agent/agent/checks/*.py` seluruhnya — sebuah konstanta 32-byte di sana lolos pemindai
# ini tanpa satu pun tes merah.
AGENT_MODULES = sorted(
    b for b in pathlib.Path(mp.__file__).parent.rglob("*.py") if "__pycache__" not in b.parts
)


# ----------------------------------------------------------------------
# (a) nol konstanta 32-byte di jalur produksi
# ----------------------------------------------------------------------


def test_no_production_module_contains_a_32_byte_constant():
    """AC (a): `grep -rnE "0x[0-9a-fA-F]{64}" agent/ --include=*.py | grep -v tests/` kosong.

    Bentuk `bytes.fromhex("…")` (tanpa `0x`) ikut dijaga: 64 digit hex adalah 64 digit hex,
    dan pemindai yang hanya melihat awalan `0x` akan hijau atas konstanta yang sama persis.
    """
    hex64 = re.compile(r"(?:0x)?[0-9a-fA-F]{64}")
    pelanggar = {}
    for berkas in AGENT_MODULES:
        temuan = hex64.findall(berkas.read_text(encoding="utf-8"))
        if temuan:
            pelanggar[berkas.name] = temuan
    assert pelanggar == {}, f"konstanta 32-byte di jalur produksi: {pelanggar}"


# ----------------------------------------------------------------------
# (b) identifier root konstanta hilang; `memory-root/v1` hanya label encoding
# ----------------------------------------------------------------------


def test_the_constant_root_identifiers_are_gone():
    """AC (b): `LIVE_MEMORY_ROOT`/`SELFTEST_MEMORY_ROOT` tidak ada lagi, di mana pun."""
    terlarang = re.compile(r"LIVE_MEMORY_ROOT|SELFTEST_MEMORY_ROOT", re.IGNORECASE)
    pelanggar = [b.name for b in AGENT_MODULES if terlarang.search(b.read_text(encoding="utf-8"))]
    assert pelanggar == [], f"identifier root konstanta masih hidup: {pelanggar}"
    for nama in ("LIVE_MEMORY_ROOT", "SELFTEST_MEMORY_ROOT", "LIVE_REASON_HASH", "SELFTEST_REASON_HASH"):
        assert not hasattr(vc, nama), f"vault_client masih mengekspor {nama}"


def test_the_only_memory_root_v1_left_is_the_frozen_encoding_label():
    """Sisa `memory-root/v1` HANYA `MEMORY_ROOT_ENCODING_VERSION` — dan itu WAJIB tinggal.

    Label ini ikut ter-hash ke preimage (`MemorySnapshot.preimage`), jadi mengubahnya
    mengubah `memory_root` setiap memori dan membatalkan vektor beku
    `tests/fixtures/memory_root_vector.json` — persis alarm yang dilarang "diperbarui supaya
    hijau" tanpa ADR. Yang dilarang task 2.4b adalah root KONSTANTA, bukan label encoding;
    tes ini mengunci perbedaan itu supaya tidak ada yang menyelundupkan konstanta baru di
    balik pola grep yang sama.
    """
    pola = re.compile(r"memory-root/v1", re.IGNORECASE)
    temuan = {
        b.name: [garis for garis in b.read_text(encoding="utf-8").splitlines() if pola.search(garis)]
        for b in AGENT_MODULES
    }
    temuan = {k: v for k, v in temuan.items() if v}
    assert set(temuan) == {"memory_policy.py"}, f"pemakai lain memory-root/v1: {temuan}"
    assert temuan["memory_policy.py"] == [
        'MEMORY_ROOT_ENCODING_VERSION: Final = "evaluator-memory-root/v1"'
    ]


# ----------------------------------------------------------------------
# (c) jalur --selftest dicabut
# ----------------------------------------------------------------------


def test_the_selftest_path_is_gone():
    """AC (c): tidak ada lagi jalur yang mengumumkan root uji ke `knownRoots` (ADR-011)."""
    assert not hasattr(vc, "run_selftest")
    assert not hasattr(vc, "pick_selftest_job_id")
    with pytest.raises(SystemExit) as exc:
        vc.main(["--selftest"])
    assert exc.value.code == 2  # argparse: opsi tidak dikenal


def test_running_without_a_subcommand_prints_usage_and_does_not_fall_back_to_a_pipeline():
    """Dulu jalur "tanpa argumen" jatuh ke selftest; sekarang ia tidak mengerjakan apa pun."""
    assert vc.main([]) == 2


# ----------------------------------------------------------------------
# (d) root asing → MELEMPAR, nol transaksi
# ----------------------------------------------------------------------


def test_post_verdict_with_a_foreign_root_raises_and_sends_nothing(db):
    """AC (d) inti: konstanta apa pun ditolak, dan penolakannya sebelum tx dibangun."""
    client = build_client(db)
    with pytest.raises(vc.MemoryRootMismatch) as exc:
        client.post_verdict(1, vc.KIND_REJECT, b"\x01" * 32, ASING)

    pesan = str(exc.value)
    assert "ROOT BUKAN TURUNAN MEMORI" in pesan
    assert "0x" + ASING.hex() in pesan, "root yang ditolak wajib disebut apa adanya"
    assert "0x" + client.derived_memory_root().hex() in pesan, "root yang benar wajib disebut"
    assert_nothing_was_sent(client)


def test_the_derived_root_actually_sends(db):
    """Kontrol positif: tanpa ini, tes di atas bisa hijau karena SEMUANYA ditolak."""
    client = build_client(db)
    root = client.refresh_memory_gate().local.root
    assert client.post_verdict(1, vc.KIND_REJECT, b"\x01" * 32, root)
    assert client.w3.eth.built == ["postVerdict"]
    assert len(client.w3.eth.sent) == 1


def test_a_foreign_root_is_caught_even_when_send_is_called_directly(db):
    """Penjaganya di `_send()`, bukan di `post_verdict()`.

    Jalur baru yang membangun `postVerdict` sendiri — melewati `post_verdict()` dan seluruh
    penjaganya — tetap berhenti. Ini alasan yang sama persis mengapa `SafeModeStop`
    ditegakkan di `_send()`: penjaga yang bisa dilewati dengan tidak memanggilnya bukan
    penjaga.
    """
    client = build_client(db)
    with pytest.raises(vc.MemoryRootMismatch):
        client._send(client.vault.functions.postVerdict(1, vc.KIND_REJECT, b"\x01" * 32, ASING))
    assert_nothing_was_sent(client)


def test_the_root_is_read_from_the_call_arguments_including_keyword_form(db):
    """`memoryRoot=` sebagai keyword tidak boleh menembus penjaga.

    web3.py 7.16.0 menyimpan argumen di `ContractFunction.args` DAN `.kwargs`
    (`web3/_utils/contracts.py:404`); penjaga yang hanya melihat `args` akan buta terhadap
    bentuk keyword dan meloloskan root apa pun.
    """
    client = build_client(db)
    fungsi = client.vault.functions.postVerdict(1, vc.KIND_REJECT, b"\x01" * 32, memoryRoot=ASING)
    assert vc.contract_call_root(fungsi) == ASING
    with pytest.raises(vc.MemoryRootMismatch):
        client._send(fungsi)
    assert_nothing_was_sent(client)


def test_postverdict_without_any_root_argument_is_refused(db):
    """Tidak ada root sama sekali = tidak ada yang bisa dibuktikan = tolak, bukan "0 saja"."""
    client = build_client(db)
    with pytest.raises(vc.MemoryRootMismatch):
        client._send(client.vault.functions.postVerdict(1, vc.KIND_REJECT))
    assert_nothing_was_sent(client)


def test_a_root_that_was_correct_before_a_memory_write_is_refused_afterwards(db):
    """Root basi = root asing. Memori yang maju satu tulisan membuat root lama tidak sah lagi.

    Inilah bentuk kegagalan yang paling mungkin di jalur nyata (spec §5 langkah 5 menulis
    memori di antara dua transaksi), dan ia harus berhenti, bukan mengumumkan keadaan yang
    sudah tidak ada.
    """
    client = build_client(db)
    root_lama = client.refresh_memory_gate().local.root

    memori = MemoryClient.local(str(db))
    mp.record_job_outcome(memori, PROVIDER, job_id=777, budget=2_000_000, passed=False,
                          failed_checks=["chain"])

    assert client.refresh_memory_gate().local.root != root_lama
    with pytest.raises(vc.MemoryRootMismatch):
        client.post_verdict(1, vc.KIND_REJECT, b"\x01" * 32, root_lama)
    assert_nothing_was_sent(client)


# ----------------------------------------------------------------------
# (e) SATU implementasi: root yang diumumkan == root yang diekspor
# ----------------------------------------------------------------------


def test_the_announced_root_equals_the_exported_root(db, tmp_path):
    """Invarian anti-mutan: `vault_client` dan `agent/memory_export.py` menghitung SATU root.

    Mutan "kembalikan konstanta dari `memory_root`" membuat kedua sisi berubah bersamaan,
    sehingga tes ini saja tidak cukup — ia dipasangkan dengan vektor beku 2.1r
    (`tests/test_memory_policy.py::FROZEN_ROOT_HEX`), yang MERAH begitu nilainya bukan lagi
    turunan file. Yang dijamin di sini: tidak ada jalur kedua yang diam-diam menghitung
    root sendiri untuk `postVerdict`.
    """
    client = build_client(db)
    diumumkan = client.refresh_memory_gate().local.root
    hasil = me.export_memory(db, tmp_path / "mem.json")

    assert "0x" + diumumkan.hex() == hasil.root
    assert me.root_from_file(tmp_path / "mem.json") == hasil.root


def test_an_empty_database_exports_the_same_root_the_naive_branch_announces(tmp_path):
    """Cabang naif mengumumkan root memori KOSONG — dan nilainya bisa dihitung ulang siapa pun.

    Ia satu-satunya cabang tanpa file untuk diturunkan (`memory.db` belum ada DAN vault
    belum pernah mengumumkan root, ADR-024 keputusan 2). Yang membuatnya bukan "konstanta
    lain": nilainya lahir dari encoding beku yang sama, dan `memory_export` atas DB kosong
    mencetak nilai yang IDENTIK.
    """
    kosong = tmp_path / "kosong.db"
    MemoryClient.local(str(kosong))
    hasil = me.export_memory(kosong, None)

    assert "0x" + mp.empty_memory_root().hex() == hasil.root

    client = build_client(None, onchain_root=ZERO)
    client.db_path = tmp_path / "tidak-ada.db"
    gerbang = client.refresh_memory_gate()
    assert gerbang.decision.mode == mp.MODE_NAIVE
    assert client.derived_memory_root() == mp.empty_memory_root()


def test_an_unreadable_memory_yields_no_root_at_all_not_the_empty_one(tmp_path):
    """Cabang fail-closed `ROOT_UNREADABLE_TEMPLATE` — DIUJI, bukan sekadar ditulis.

    Mutan `if gate.decision.mode == MODE_NAIVE:` → `if True:` di `derived_memory_root()`
    dulu LOLOS nol tes merah: setiap tes lain berhenti lebih dulu di `_require_memory_gate`,
    jadi cabangnya tidak pernah dieksekusi. Konsekuensi mutan itu persis kebalikan
    fail-closed: memori yang RUSAK (kita tidak tahu isinya) diumumkan sebagai memori KOSONG.
    """
    rusak = tmp_path / "memory.db"
    rusak.write_bytes(b"ini bukan basis data sqlite")
    client = build_client(rusak)

    gerbang = client.refresh_memory_gate()
    assert gerbang.local.status == mp.LOCAL_MEMORY_ERROR
    assert gerbang.decision.mode == mp.MODE_SAFE
    assert gerbang.local.root is None

    with pytest.raises(vc.MemoryRootMismatch) as exc:
        client.derived_memory_root()
    assert "ROOT TIDAK BISA DITURUNKAN" in str(exc.value)
    assert mp.empty_memory_root().hex() not in str(exc.value)
    assert_nothing_was_sent(client)


def test_a_missing_memory_never_yields_a_root_outside_naive_mode(tmp_path):
    """Memori hilang + vault sudah hidup = MODE AMAN, dan tidak ada root yang diumumkan."""
    client = build_client(tmp_path / "tidak-ada.db")
    assert client.refresh_memory_gate().decision.mode == mp.MODE_SAFE
    with pytest.raises(vc.SafeModeStop):
        client.post_verdict(1, vc.KIND_REJECT, b"\x01" * 32, mp.empty_memory_root())
    assert_nothing_was_sent(client)


# ----------------------------------------------------------------------
# reasonHash: turunan bukti job, bukan konstanta
# ----------------------------------------------------------------------


class DummyEvaluation:
    """`Evaluation` seminimal mungkin: yang diuji bundelnya, bukan isi cek."""

    def __init__(self, job_id: int, passed: bool) -> None:
        self.job_id = job_id
        self.passed = passed

    def to_body(self) -> dict:
        return {"job": self.job_id, "verdict": 1 if self.passed else 2, "checks": []}


def build_plan(job_id: int, *, passed: bool = True) -> vc.JobPlan:
    job = vc.JobView(
        job_id=job_id,
        client_address=CLIENT,
        provider=PROVIDER,
        evaluator=VAULT_ADDRESS,
        status=2,
        budget=1_000_000,
        expired_at=0,
        description="",
        hook="0x" + "00" * 20,
    )
    mode = mp.decide_mode(
        ROOT_ONCHAIN,
        mp.LocalMemoryEvidence.ok(job_outcomes=1, root=ROOT_ONCHAIN, detail="tes"),
    )
    cap = mp.CapPlan(cap_usdc=None, require_milestone=False, basis="tes", sample_size=0)
    return vc.JobPlan(
        job=job,
        mode=mode,
        gate=mp.GateDecision(
            accept=True, reason="tes", cap=cap, mode=mode, depth=mode.depth
        ),
        evaluation=DummyEvaluation(job_id, passed),
        deliverable=None,
    )


def test_the_reason_hash_is_derived_and_binds_the_root(db):
    root = build_client(db).refresh_memory_gate().local.root
    bundel = vc.verdict_evidence(build_plan(1), root, vc.KIND_COMPLETE)

    assert bundel["memory_root"] == "0x" + root.hex()
    assert bundel["version"] == vc.VERDICT_EVIDENCE_VERSION
    # Deterministik atas masukan yang sama…
    assert vc.verdict_reason_hash(bundel) == vc.verdict_reason_hash(bundel)
    # …dan BUKAN nilai tetap: job lain, hasil lain, atau root lain → hash lain.
    assert vc.verdict_reason_hash(bundel) != vc.verdict_reason_hash(
        vc.verdict_evidence(build_plan(2), root, vc.KIND_COMPLETE)
    )
    assert vc.verdict_reason_hash(bundel) != vc.verdict_reason_hash(
        vc.verdict_evidence(build_plan(1, passed=False), root, vc.KIND_COMPLETE)
    )
    assert vc.verdict_reason_hash(bundel) != vc.verdict_reason_hash(
        vc.verdict_evidence(build_plan(1), ASING, vc.KIND_COMPLETE)
    )
    # …termasuk ARAH verdict yang diumumkan (v3): satu bundel tidak boleh membenarkan dua arah.
    assert vc.verdict_reason_hash(bundel) != vc.verdict_reason_hash(
        vc.verdict_evidence(build_plan(1), root, vc.KIND_REJECT)
    )


def test_the_reason_hash_is_keccak_of_the_canonical_bundle(db):
    """Bisa dihitung ulang auditor mana pun dari bundel yang sama — tanpa menebak encoding."""
    root = build_client(db).refresh_memory_gate().local.root
    bundel = vc.verdict_evidence(build_plan(9), root, vc.KIND_COMPLETE)
    assert vc.verdict_reason_hash(bundel) == bytes(
        Web3.keccak(text=mp.canonical_json(bundel))
    )


def test_a_verdict_without_evidence_is_refused(db):
    """Tanpa `Evaluation` tidak ada bukti untuk di-hash — dan verdict tanpa bukti dicabut 2.4b."""
    plan = build_plan(1)
    kosong = vc.JobPlan(
        job=plan.job, mode=plan.mode, gate=plan.gate, evaluation=None, deliverable=None
    )
    with pytest.raises(vc.MemoryRootMismatch):
        vc.verdict_evidence(kosong, mp.empty_memory_root(), vc.KIND_REJECT)


def test_run_live_refuses_without_a_plan(db):
    """`run_live` tanpa rencana tidak boleh mengarang root maupun reasonHash."""
    client = build_client(db)
    with pytest.raises(vc.MemoryRootMismatch):
        vc.run_live(client, 1, vc.KIND_REJECT)
    assert_nothing_was_sent(client)


# ----------------------------------------------------------------------
# Penjaga diuji terhadap objek web3 SUNGGUHAN, bukan hanya kontrak palsu
# ----------------------------------------------------------------------


def test_contract_call_root_reads_a_real_web3_contract_function():
    """`ContractFunction.args`/`.kwargs` web3.py 7.16.0, bukan atribut karangan.

    Kontrak palsu di file ini meniru bentuk itu; kalau bentuk aslinya berbeda, penjaga di
    `_send()` akan selalu membaca `None` dan MELOLOSKAN root apa pun sementara seluruh tes
    tetap hijau. Karena itu bentuknya diperiksa pada objek web3 sungguhan (offline: hanya
    membangun panggilan, tidak mengirim apa pun) dengan `VAULT_ABI` yang dipakai produksi.

    Sumber: `web3/_utils/contracts.py` `copy_contract_function` menyalin `*args`/`**kwargs`
    ke klon yang dikembalikan `ContractFunction.__call__`; `BaseContractFunction` mendeklarasikan
    `fn_name`, `args`, dan `kwargs`.
    """
    kontrak = Web3().eth.contract(address=Web3.to_checksum_address(VAULT_ADDRESS), abi=vc.VAULT_ABI)
    posisional = kontrak.functions.postVerdict(1, vc.KIND_REJECT, b"\x01" * 32, ASING)
    assert posisional.fn_name == vc.POST_VERDICT_FN
    assert vc.contract_call_root(posisional) == ASING

    keyword = kontrak.functions.postVerdict(1, vc.KIND_REJECT, b"\x01" * 32, memoryRoot=ASING)
    assert vc.contract_call_root(keyword) == ASING

    # Fungsi lain tidak punya root, dan penjaga tidak boleh mengarangnya dari argumen lain.
    assert vc.contract_call_root(kontrak.functions.finalize(1)) is None
