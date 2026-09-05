"""Penegakan MODE AMAN di jalur chain — task 2.4a AC (a)(b)(c)(f)(g) + butir (3),
dikoreksi task 2.4a-fix (ADR-023).

`memory_policy.decide_mode()` hanya mengembalikan NILAI. Yang dibuktikan DI SINI adalah
penegakannya: saat mode aman, TIDAK ADA `postVerdict`/`finalize`/`setProviderCap` yang
benar-benar terkirim — dan bukan hanya "tidak di-broadcast", melainkan tidak pernah
dibangun, tidak pernah ditandatangani, dan nonce pun tidak pernah dibaca.

RPC dipalsukan seluruhnya (`FakeWeb3`), jadi tes ini offline dan deterministik. Bukti
on-chain-nya (nonce SEBELUM == SESUDAH pada wallet agen sungguhan) adalah AC (d) dan
dijalankan manual, bukan di sini.

Yang khusus dijaga tes ini, karena inilah mode kegagalan yang paling mudah terlewat:
`load_snapshot`/`memory_root` yang MELEMPAR (memori rusak, kunci single-instance tidak
didapat) WAJIB jatuh ke mode aman — bukan crash, bukan traceback, dan tentu bukan
"lanjut saja karena memorinya tidak bisa dibaca".

Tiga hal yang ditambahkan 2.4a-fix, dan ketiganya adalah temuan yang PERNAH hidup:
  - `test_two_consecutive_jobs_stay_normal` — gerbang lama membandingkan root lokal dengan
    `lastMemoryRoot()` dan karena itu mengunci agen ke mode aman sesudah job PERTAMA;
  - `test_the_gate_is_reread_before_every_transaction_local_side` +
    `test_a_stale_gate_object_cannot_authorize_a_transaction` — gerbang yang dibaca sekali
    saat start meloloskan tx meski keadaan berubah sesudahnya;
  - blok "TINGGI (i)" di akhir file — `.env` di akar repo TIDAK PERNAH terbaca, dan seluruh
    tes lama hijau justru karena mereka menyuntik nilai lewat `monkeypatch.setenv`.
"""

from __future__ import annotations

import logging
import pathlib

import pytest
from sibyl_memory_client import MemoryClient

from agent import memory_lock as ml
from agent import memory_policy as mp
from agent import vault_client as vc

ROOT_ONCHAIN = bytes.fromhex("11" * 32)
ZERO = bytes(32)
AGENT_ADDRESS = "0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894"
PROVIDER = "0x" + "ab" * 20
CLIENT = "0x" + "cc" * 20
VAULT_ADDRESS = "0x" + "11" * 20


# ----------------------------------------------------------------------
# RPC palsu — merekam SETIAP langkah menuju sebuah transaksi
# ----------------------------------------------------------------------


class FakeFunction:
    def __init__(self, contract: FakeContract, name: str, args: tuple) -> None:
        self.contract = contract
        self.fn_name = name
        self.args = args

    def call(self):
        self.contract.eth.reads.append(self.fn_name)
        return self.contract.returns[self.fn_name]

    def build_transaction(self, params):
        self.contract.eth.built.append(self.fn_name)
        return {"to": "0x" + "11" * 20, "data": "0x", **params}


class FakeFunctions:
    def __init__(self, contract: FakeContract) -> None:
        self._contract = contract

    def __getattr__(self, name: str):
        def maker(*args):
            return FakeFunction(self._contract, name, args)

        return maker


class FakeContract:
    def __init__(self, eth: FakeEth, returns: dict, address: str = "0x" + "11" * 20) -> None:
        self.eth = eth
        self.returns = returns
        # `run_job` membandingkan `getJob(...).evaluator` dengan `vault.address`, jadi
        # kontrak palsu pun harus punya alamat — sama seperti kontrak web3 sungguhan.
        self.address = address
        self.functions = FakeFunctions(self)
        self.events = FakeEvents(self)


class FakeEventType:
    """`acp.events.JobSubmitted()` palsu: nol log kecuali tes mengisinya sendiri."""

    def __init__(self, contract: FakeContract, name: str) -> None:
        self.contract = contract
        self.name = name

    def get_logs(self, argument_filters=None, from_block=None, to_block=None):
        return []


class FakeEvents:
    def __init__(self, contract: FakeContract) -> None:
        self._contract = contract

    def __getattr__(self, name: str):
        def maker():
            return FakeEventType(self._contract, name)

        return maker


class FakeEth:
    def __init__(self, returns: dict) -> None:
        self.returns = returns
        self.reads: list[str] = []
        self.built: list[str] = []
        self.sent: list[bytes] = []
        self.nonce_reads = 0
        self.chain_id = 84532
        self.block_number = 46_400_000

    def contract(self, address=None, abi=None):
        return FakeContract(self, self.returns, address or "0x" + "11" * 20)

    def get_transaction_count(self, address):
        self.nonce_reads += 1
        return 75

    def send_raw_transaction(self, raw):
        self.sent.append(raw)
        return b"\xaa" * 32


class FakeWeb3:
    def __init__(self, returns: dict) -> None:
        self.eth = FakeEth(returns)


class FakeAccount:
    address = AGENT_ADDRESS

    def sign_transaction(self, tx):
        raise AssertionError("mode aman tidak boleh sampai ke penandatanganan")


def build_client(
    *, onchain_root: bytes = ROOT_ONCHAIN, job_status: int = 1, db: pathlib.Path | None = None
) -> vc.VaultClient:
    """Klien palsu. `db` WAJIB diisi bila tx boleh sampai ke gerbang: tanpa path memori
    `_send()` menolak semuanya, dan tanpa itu tes bisa diam-diam membaca `./data/memory.db`
    milik repo."""
    returns = {
        "lastMemoryRoot": onchain_root,
        # `evaluator` SENGAJA = alamat vault klien ini: tes di file ini menguji gerbang
        # memori, bukan penyaringan "job milik siapa" (itu tests/test_job_pipeline.py).
        "jobs": (CLIENT, job_status, PROVIDER, 0, VAULT_ADDRESS, "0x" + "00" * 20, 1, ""),
        "verdicts": (0, ZERO, ZERO, 0, False, "0x" + "00" * 20),
    }
    w3 = FakeWeb3(returns)
    return vc.VaultClient(
        w3, VAULT_ADDRESS, "0x" + "22" * 20, FakeAccount(), 84532, db_path=db
    )


def seed_memory(db: pathlib.Path, jobs: int = 1, provider: str = "0x" + "a9" * 20):
    """DB yang berisi `jobs` job outcome. Sejak ADR-024 jumlahnya tidak memutuskan mode."""
    memori = MemoryClient.local(str(db))
    for i in range(jobs):
        mp.record_job_outcome(memori, provider, job_id=500 + i, budget=1_000_000, passed=True)
    return memori


def attempt_all_three(client: vc.VaultClient) -> list[Exception]:
    """Ketiga jalur tulis dicoba SUNGGUHAN; kesalahannya dikembalikan untuk diperiksa."""
    errors = []
    for call in (
        lambda: client.post_verdict(1, vc.KIND_COMPLETE, b"\x01" * 32, b"\x02" * 32),
        lambda: client.finalize(1),
        lambda: client.set_provider_cap(PROVIDER, 250_000),
    ):
        with pytest.raises(vc.SafeModeStop) as exc:
            call()
        errors.append(exc.value)
    return errors


def assert_nothing_was_sent(client: vc.VaultClient) -> None:
    eth = client.w3.eth
    assert eth.sent == [], f"ada transaksi terkirim: {eth.sent}"
    assert eth.built == [], f"ada transaksi dibangun: {eth.built}"
    assert eth.nonce_reads == 0, "nonce dibaca — artinya jalur tx sudah dimulai"


@pytest.fixture
def db(tmp_path) -> pathlib.Path:
    return tmp_path / "memory.db"


# ----------------------------------------------------------------------
# (a) memori lokal HILANG sementara vault sudah pernah mengumumkan root
# ----------------------------------------------------------------------


def test_missing_memory_with_nonzero_onchain_root_sends_nothing(db):
    client = build_client(db=db)
    gate = vc.evaluate_memory_gate(client, db)

    assert gate.is_safe
    assert gate.decision.mode == mp.MODE_SAFE
    assert gate.local.status == mp.LOCAL_MEMORY_MISSING
    assert gate.origin.startswith(vc.MISSING_LOCAL_MEMORY)
    assert gate.onchain_hex == "0x" + ROOT_ONCHAIN.hex()

    errors = attempt_all_three(client)
    assert len(errors) == 3
    assert_nothing_was_sent(client)


def test_the_three_memory_files_are_reported_together(db):
    """"Hapus memori" berarti TIGA file (api-facts §C) — laporannya pun bertiga."""
    laporan = vc.memory_files_report(db)
    assert laporan == {"memory.db": False, "memory.db-wal": False, "memory.db-shm": False}
    MemoryClient.local(str(db))
    assert vc.memory_files_report(db)["memory.db"] is True


# ----------------------------------------------------------------------
# (b) ADR-023: DB ADA tetapi NOL job outcome = memori dihapus → mode aman
# ----------------------------------------------------------------------


def test_empty_memory_with_nonzero_onchain_root_actually_builds_postverdict(db):
    """AC (a1) 2.4a-fix / ADR-024: DB BERSIH + root non-nol → NORMAL, dan tx TERBANGUN.

    Inilah keadaan job A rantai 2.5 di vault beku ADR-022 (`lastMemoryRoot` non-nol
    permanen). Aturan (b) yang dicabut menahan `postVerdict` di sini, sehingga outcome
    pertama tidak pernah lahir dan seluruh rantai menghasilkan `tx = []`.
    """
    MemoryClient.local(str(db))  # DB ada, nol job outcome
    client = build_client(db=db)
    client.account = _SigningAccount()
    gate = vc.evaluate_memory_gate(client, db)

    assert gate.local.local_memory_readable is True
    assert gate.local.job_outcomes == 0
    assert gate.decision.mode == mp.MODE_NORMAL
    assert gate.is_safe is False

    client.post_verdict(1, vc.KIND_REJECT, b"\x01" * 32, gate.local.root)
    client.set_provider_cap(PROVIDER, 250_000)
    client.finalize(1)
    assert client.w3.eth.built == ["postVerdict", "setProviderCap", "finalize"]
    assert len(client.w3.eth.sent) == 3


def test_memory_with_job_outcomes_runs_normally_even_though_roots_differ(db):
    """KONTROL ADR-023: root lokal SENGAJA berbeda dari root on-chain → tetap NORMAL.

    Inilah keadaan normal spec §5 (memori ditulis SESUDAH `postVerdict`). Gerbang lama
    membaca keadaan ini sebagai "tidak cocok" dan mengunci agen selamanya.
    """
    seed_memory(db)
    client = build_client(db=db)
    gate = vc.evaluate_memory_gate(client, db)

    assert gate.local.root is not None and gate.local.root != ROOT_ONCHAIN
    assert gate.decision.mode == mp.MODE_NORMAL
    assert gate.is_safe is False
    assert gate.line.startswith("MODE NORMAL: ")
    assert "(konteks saja)" in gate.line
    assert "memori lokal 1 job" in gate.line


# ----------------------------------------------------------------------
# (c) kontrol: root on-chain == 0 → mode naif, agen berjalan
# ----------------------------------------------------------------------


def test_zero_onchain_root_is_naive_mode_and_actually_sends(db):
    client = build_client(onchain_root=ZERO, db=db)
    client.account = _SigningAccount()
    gate = vc.evaluate_memory_gate(client, db)

    assert gate.decision.mode == mp.MODE_NAIVE
    assert gate.is_safe is False
    assert gate.line.startswith("MODE NAIF: ")

    # Mode naif TIDAK punya `memory.db`, jadi rootnya adalah root memori KOSONG —
    # dihitung dari encoding beku, bukan konstanta (task 2.4b). Root lain DITOLAK.
    root = mp.empty_memory_root()
    tx_hash = client.post_verdict(1, vc.KIND_COMPLETE, b"\x01" * 32, root)
    assert tx_hash
    assert client.w3.eth.sent, "mode naif seharusnya benar-benar mengirim (kontrol negatif)"
    assert client.w3.eth.built == ["postVerdict"]
    with pytest.raises(vc.MemoryRootMismatch):
        client.post_verdict(1, vc.KIND_COMPLETE, b"\x01" * 32, b"\x02" * 32)
    assert client.w3.eth.built == ["postVerdict"], "root asing tidak boleh membangun tx"


class _SigningAccount(FakeAccount):
    def sign_transaction(self, tx):
        class Signed:
            raw_transaction = b"\x99" * 8

        return Signed()


# ----------------------------------------------------------------------
# butir (3): memori yang MELEMPAR jatuh ke mode aman, bukan crash
# ----------------------------------------------------------------------


def test_memory_integrity_error_falls_back_to_safe_mode_not_a_crash(db):
    """`reference:pattern` yang dirujuk provider HILANG → `load_snapshot` MELEMPAR."""
    memori = MemoryClient.local(str(db))
    mp.save_provider(
        memori,
        mp.ProviderProfile(address="0x" + "a3" * 20, confirmed_patterns=("pola-hilang",)),
    )
    with pytest.raises(mp.MemoryIntegrityError):
        mp.local_memory_evidence(memori)

    bukti = vc.read_local_memory(db)
    assert bukti.status == mp.LOCAL_MEMORY_ERROR
    assert "MemoryIntegrityError" in bukti.detail

    client = build_client(db=db)
    assert vc.evaluate_memory_gate(client, db).is_safe
    attempt_all_three(client)
    assert_nothing_was_sent(client)


def test_corrupt_provider_name_also_falls_back_to_safe_mode(db):
    """Memori rusak yang melempar `ValueError` MENTAH pun berakhir di mode aman.

    Yang dijamin di sini hanya akibatnya: apa pun jenis kesalahannya, agen berhenti dan
    tidak mengirim tx — bukan crash dengan traceback dan bukan "lanjut karena memorinya
    tidak bisa dibaca".
    """
    memori = MemoryClient.local(str(db))
    memori.set_entity(mp.CATEGORY_PROVIDER, "bukan-alamat", {"risk_level": 0})
    with pytest.raises(ValueError):
        mp.local_memory_evidence(memori)

    client = build_client(db=db)
    gate = vc.evaluate_memory_gate(client, db)
    assert gate.is_safe
    assert "ValueError" in gate.local.detail
    attempt_all_three(client)
    assert_nothing_was_sent(client)


def _kunci_gagal(monkeypatch):
    def _boom(_client, **_kwargs):
        raise ml.MemoryLockError("memory.db sedang dipakai proses lain")

    monkeypatch.setattr(vc, "local_memory_evidence", _boom)


def test_lock_failure_falls_back_to_safe_mode(db, monkeypatch):
    """Instans agen LAIN memegang `memory.db` → kita tidak tahu isinya → mode aman."""
    seed_memory(db)
    _kunci_gagal(monkeypatch)

    client = build_client(db=db)
    gate = vc.evaluate_memory_gate(client, db)
    assert gate.is_safe
    assert gate.local.status == mp.LOCAL_MEMORY_LOCK_FAILED
    assert "MemoryLockError" in gate.local.detail
    attempt_all_three(client)
    assert_nothing_was_sent(client)


def test_lock_failure_is_safe_mode_even_on_a_fresh_vault(db, monkeypatch):
    """ADR-024 cabang (1) mendahului cabang (2), termasuk saat root on-chain NOL.

    Rantai yang ditutup, terukur reviewer: instans-2 gagal kunci → (dulu) NAIF → tx sampai
    ke PENANDATANGANAN → `postVerdict` mendarat → `lastMemoryRoot` jadi non-nol →
    `record_job_outcome` instans-2 melempar `MemoryLockError` yang tidak ditangkap siapa
    pun. Kontensi sementara berubah jadi kerusakan yang bertahan.
    """
    seed_memory(db)
    _kunci_gagal(monkeypatch)

    client = build_client(onchain_root=ZERO, db=db)
    client.account = _SigningAccount()
    gate = vc.evaluate_memory_gate(client, db)

    assert gate.decision.mode == mp.MODE_SAFE, "kegagalan kunci TIDAK boleh jadi NAIF"
    assert "kunci single-instance" in gate.decision.reason
    attempt_all_three(client)
    assert_nothing_was_sent(client)


def test_gate_reads_do_not_wait_the_full_write_timeout():
    """Anggaran waktu ADR-014: pembacaan gerbang tidak menunggu 10 detik milik jalur TULIS."""
    assert mp.GATE_LOCK_TIMEOUT_SECONDS < ml.DEFAULT_TIMEOUT_SECONDS
    assert mp.GATE_LOCK_TIMEOUT_SECONDS <= 2.0


def test_unreadable_onchain_root_is_safe_mode(db):
    """`eth_call` gagal / kontrak salah → root TIDAK TERBACA → izin PALING KECIL.

    Diuji pada memori yang HILANG: sejak ADR-024 itulah satu-satunya cabang yang membaca
    root on-chain, dan satu-satunya tempat "tidak terbaca" masih bisa menyesatkan.
    """
    client = build_client(db=db)

    def _gagal():
        raise RuntimeError("RPC mati")

    client.vault.functions = _FunctionsThatFail(_gagal)
    gate = vc.evaluate_memory_gate(client, db)

    assert gate.onchain_hex == "TIDAK TERBACA"
    assert gate.is_safe
    attempt_all_three(client)
    assert client.w3.eth.sent == []


class _FunctionsThatFail:
    def __init__(self, boom):
        self._boom = boom

    def __getattr__(self, name):
        def maker(*args):
            class F:
                fn_name = name

                def call(_self):
                    self._boom()

                def build_transaction(_self, params):
                    raise AssertionError("tidak boleh membangun tx")

            return F()

        return maker


def test_send_refuses_when_the_client_has_no_memory_path(db):
    """Klien tanpa path memori tidak bisa membaca gerbangnya → ia menolak semua tx.

    "Lupa memberi tahu di mana memorinya" BUKAN izin, dan ia juga tidak boleh diam-diam
    jatuh ke `./data/memory.db` milik siapa pun yang kebetulan menjadi cwd.
    """
    client = build_client()
    assert client.db_path is None
    with pytest.raises(vc.SafeModeStop) as exc:
        client.post_verdict(1, vc.KIND_COMPLETE, b"\x01" * 32, b"\x02" * 32)
    assert "tanpa path memori" in str(exc.value)
    assert_nothing_was_sent(client)


# ----------------------------------------------------------------------
# 2.4a-fix / ADR-023 — self-brick mati, dan gerbang dibaca ULANG tiap tx
# ----------------------------------------------------------------------


def test_two_consecutive_jobs_stay_normal(db):
    """AC3 2.4a-fix: mode SESUDAH `record_job_outcome` BUKAN aman.

    Naskah persis §5/§7: job A di-postVerdict (vault mengumumkan root R1), memori ditulis
    SESUDAHNYA sehingga root lokal berpindah ke R2, lalu job B masuk. Gerbang lama
    membandingkan R2 dengan R1 dan mengunci agen ke mode aman di sini — "bahkan pada vault
    baru, agen berhenti sesudah job A". Sekarang keduanya wajib NORMAL, dan `postVerdict`
    kedua benar-benar terkirim.
    """
    memori = seed_memory(db, jobs=1, provider=PROVIDER)
    client = build_client(db=db)
    client.account = _SigningAccount()

    mode_a = client.refresh_memory_gate().decision.mode
    root_a = client.memory_gate.local.root
    client.post_verdict(1, vc.KIND_REJECT, b"\x01" * 32, root_a)

    # spec §5 langkah 5: memori ditulis SESUDAH postVerdict → root lokal maju.
    mp.record_job_outcome(memori, PROVIDER, job_id=777, budget=1_000_000, passed=False,
                          failed_checks=["chain"])
    mode_b = client.refresh_memory_gate().decision.mode
    root_b = client.memory_gate.local.root

    assert root_b != root_a, "prasyarat tes: root lokal harus berubah sesudah job A"
    assert (mode_a, mode_b) == (mp.MODE_NORMAL, mp.MODE_NORMAL)
    assert client.memory_gate.is_safe is False

    client.post_verdict(2, vc.KIND_REJECT, b"\x02" * 32, root_b)
    client.finalize(2)
    assert client.w3.eth.built == ["postVerdict", "postVerdict", "finalize"]
    assert len(client.w3.eth.sent) == 3


def test_the_gate_is_reread_before_every_transaction_local_side(db):
    """TINGGI (ii): memori yang diracuni SESUDAH gerbang lolos tetap tertangkap.

    Gerbang start memang NORMAL. Lalu `memory.db` dihapus pihak lain (kuncinya kooperatif,
    jadi ini bukan skenario khayalan) — tx berikutnya WAJIB berhenti, bukan memakai hasil
    pembacaan lama.
    """
    seed_memory(db)
    client = build_client(db=db)
    client.account = _SigningAccount()
    assert client.refresh_memory_gate().decision.mode == mp.MODE_NORMAL

    client.post_verdict(1, vc.KIND_COMPLETE, b"\x01" * 32, client.memory_gate.local.root)
    assert client.w3.eth.built == ["postVerdict"]

    for suffix in vc.MEMORY_DB_SUFFIXES:
        db.with_name(db.name + suffix).unlink(missing_ok=True)

    with pytest.raises(vc.SafeModeStop):
        client.finalize(1)
    assert client.w3.eth.built == ["postVerdict"], "tx kedua tidak boleh pernah dibangun"
    assert len(client.w3.eth.sent) == 1


def test_a_stale_gate_object_cannot_authorize_a_transaction(db):
    """Gerbang basi yang DIPASANG TANGAN pun tidak meloloskan apa pun.

    Reviewer memperagakan `mode saat start: naive` + root on-chain berubah → `postVerdict`
    dan `finalize` tetap terkirim. Di sini gerbang naif itu dipasang langsung ke klien,
    lalu root on-chain berubah menjadi non-nol sementara memori kosong.
    """
    client = build_client(onchain_root=ZERO, db=db)
    client.account = _SigningAccount()
    naif = client.refresh_memory_gate()
    assert naif.decision.mode == mp.MODE_NAIVE

    client.w3.eth.returns["lastMemoryRoot"] = ROOT_ONCHAIN
    client.memory_gate = naif  # persis gerbang basi yang dipakai reviewer

    for panggil in (
        lambda: client.post_verdict(1, vc.KIND_COMPLETE, b"\x01" * 32, b"\x02" * 32),
        lambda: client.finalize(1),
        lambda: client.set_provider_cap(PROVIDER, 250_000),
    ):
        with pytest.raises(vc.SafeModeStop):
            panggil()
    assert_nothing_was_sent(client)
    assert client.memory_gate.is_safe, "gerbang yang dipasang tangan wajib tertimpa pembacaan baru"


# ----------------------------------------------------------------------
# (g) baris keluaran menyebut AKIBATNYA apa adanya
# ----------------------------------------------------------------------


def test_safe_mode_line_states_the_consequence_verbatim(db):
    baris = vc.evaluate_memory_gate(build_client(db=db), db).line

    assert baris.startswith("MODE AMAN: ")
    # AC (a4) ADR-024: jalur PEMULIHAN disebut, bukan hanya akibatnya. Tanpa ini operator
    # membaca mode aman sebagai "agennya rusak", bukan "agennya sedang menolak".
    assert "pulihkan memory.db dari backup" in baris
    # Path memori ABSOLUT: tanpa ini tidak ada yang bisa membuktikan FILE MANA yang menahan.
    assert str(db) in baris and db.is_absolute()
    assert f"root onchain=0x{ROOT_ONCHAIN.hex()}" in baris
    # ADR-023 keputusan 1: root on-chain hanya konteks, dan barisnya mengatakannya.
    assert "(konteks saja)" in baris
    assert f"memori lokal {vc.MISSING_LOCAL_MEMORY}" in baris
    # AC (f): KETIGANYA disebut, bukan hanya postVerdict/finalize.
    assert "menolak postVerdict/finalize/setProviderCap" in baris
    # AC (g) + ADR-020 keputusan 8: akibatnya apa adanya, DILARANG diperhalus.
    assert "job menggantung sampai expiredAt" in baris
    assert "refund lewat claimRefund publik" in baris
    assert "ditolak dengan aman" not in baris
    # `decide_mode` membawa konsekuensi yang sama di `reason` (ADR-020 keputusan 8).
    assert "claimRefund" in vc.evaluate_memory_gate(build_client(db=db), db).decision.reason


# ----------------------------------------------------------------------
# CLI: `python -m agent.vault_client --job-id <terminal milik pihak lain>`
# ----------------------------------------------------------------------


def test_cli_prints_safe_mode_and_sends_nothing(db, monkeypatch, caplog):
    """AC (d) versi offline: yang menahan agen adalah MEMORINYA, bukan status job.

    Job sengaja dibuat TERMINAL (Completed=3) dan milik pihak lain. Kalau gerbang memori
    dijalankan terlambat, keluarannya akan berbunyi "VERDICT DIANULIR PIHAK KETIGA" dan
    AC (d) gagal meski nol tx.
    """
    dibangun = {}

    def _fake_build_client(private_key: str | None = None) -> vc.VaultClient:
        # Kunci privat TIDAK diteruskan: `main()` membangun klien baca-saja lebih dulu,
        # justru supaya keputusan MODE AMAN tidak menuntut kunci penandatangan.
        assert private_key is None
        client = build_client(job_status=3, db=db)
        dibangun["client"] = client
        return client

    def _kunci_tidak_boleh_dimuat():
        raise AssertionError("mode aman tidak boleh sampai memuat kunci privat")

    monkeypatch.setattr(vc, "load_private_key", _kunci_tidak_boleh_dimuat)
    monkeypatch.setattr(vc, "build_client", _fake_build_client)

    # `logging.basicConfig` di `main()` tidak berefek di bawah pytest (root logger sudah
    # punya handler), jadi keluarannya dibaca dari `caplog`. Di CLI sungguhan baris yang
    # SAMA pergi ke stdout — itulah yang dibuktikan AC (d) secara manual.
    with caplog.at_level(logging.INFO, logger="vault_client"):
        # `--kind` WAJIB eksplisit sejak temuan TINGGI-B: tidak ada verdict default.
        kode = vc.main(["--job-id", "407", "--kind", "reject"])
    keluaran = caplog.text

    assert kode == 0
    assert "MODE AMAN: " in keluaran
    assert "job menggantung sampai expiredAt, refund lewat claimRefund publik" in keluaran
    assert "VERDICT DIANULIR" not in keluaran
    client = dibangun["client"]
    assert client.w3.eth.sent == []
    assert client.w3.eth.built == []
    assert client.w3.eth.nonce_reads == 0
    # Job pun tidak pernah dibaca: gerbang berjalan lebih dulu.
    assert client.w3.eth.reads == ["lastMemoryRoot"]


def test_cli_reads_db_path_from_env(db, monkeypatch):
    monkeypatch.setenv("SIBYL_DB_PATH", str(db))
    assert vc.memory_db_path() == db


# ----------------------------------------------------------------------
# TINGGI: path memori TIDAK BOLEH ditentukan direktori kerja
# ----------------------------------------------------------------------


def test_relative_db_path_is_anchored_to_the_agent_root_not_the_cwd(tmp_path, monkeypatch):
    """`SIBYL_DB_PATH=./data/memory.db` menunjuk file yang SAMA dari cwd mana pun.

    Dua arah kerusakannya sama-sama nyata:
      - dari cwd penyerang, `data/memory.db` palsu berisi satu baris cukup untuk membuat
        gerbang NORMAL sekaligus membuat profil provider korban terbaca KOSONG →
        `derive_cap` → `NO_CAP` → on-chain 0 = TANPA BATAS (ADR-001);
      - dari akar repo, file yang benar tidak ketemu → MODE AMAN diam-diam, exit 0.
    """
    monkeypatch.setenv("SIBYL_DB_PATH", "./data/memory.db")
    diharapkan = (vc.agent_root() / "data" / "memory.db").resolve()

    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)
    assert vc.memory_db_path() == diharapkan
    assert vc.memory_db_path().is_absolute()

    monkeypatch.chdir(vc.repo_root())
    assert vc.memory_db_path() == diharapkan
    # Jangkarnya adalah paket agen (yang memuat `pyproject.toml`), bukan akar repo.
    assert (vc.agent_root() / "pyproject.toml").is_file()
    assert vc.agent_root() != vc.repo_root()


def test_absolute_db_path_is_used_as_given(tmp_path, monkeypatch):
    monkeypatch.setenv("SIBYL_DB_PATH", str(tmp_path / "lain" / "memory.db"))
    assert vc.memory_db_path() == tmp_path / "lain" / "memory.db"


def test_every_gate_line_names_the_absolute_db_file(db):
    """MODE NORMAL/NAIF/AMAN — ketiganya menyebut file yang dipakai."""
    seed_memory(db)
    normal = vc.evaluate_memory_gate(build_client(db=db), db)
    naif = vc.evaluate_memory_gate(build_client(onchain_root=ZERO, db=db / "tidak-ada"), db / "tidak-ada")
    kosong = db.parent / "kosong.db"
    aman = vc.evaluate_memory_gate(build_client(db=kosong), kosong)

    assert normal.decision.mode == mp.MODE_NORMAL and str(db) in normal.line
    assert naif.decision.mode == mp.MODE_NAIVE and str(db / "tidak-ada") in naif.line
    assert aman.decision.mode == mp.MODE_SAFE and str(kosong) in aman.line


# ----------------------------------------------------------------------
# RENDAH: berhenti DI TENGAH pipa bukan "berhenti bersih"
# ----------------------------------------------------------------------


def test_main_exits_nonzero_when_the_gate_stops_a_half_finished_pipeline(db, monkeypatch, caplog):
    """`postVerdict` sudah mendarat, `finalize` ditahan → exit 3, bukan 0.

    Dengan exit 0, otomasi 2.5 melaporkan sukses padahal job MENGGANTUNG sampai
    `expiredAt` — kegagalan paling mahal justru terlihat paling bersih.
    """
    seed_memory(db)
    dibangun = {}

    def _fake_build_client(private_key: str | None = None) -> vc.VaultClient:
        client = build_client(db=db)
        client.account = _SigningAccount()
        dibangun["client"] = client
        return client

    def _run_live(client, job_id, kind, plan=None):
        client.post_verdict(job_id, kind, b"\x01" * 32, client.derived_memory_root())
        for suffix in vc.MEMORY_DB_SUFFIXES:  # memori lenyap DI TENGAH pipa
            db.with_name(db.name + suffix).unlink(missing_ok=True)
        return client.finalize(job_id)

    monkeypatch.setattr(vc, "build_client", _fake_build_client)
    monkeypatch.setattr(vc, "load_private_key", lambda: "0x" + "11" * 32)
    monkeypatch.setattr(vc, "run_live", _run_live)
    monkeypatch.setattr(vc.Account, "from_key", staticmethod(lambda key: _SigningAccount()))

    with caplog.at_level(logging.INFO, logger="vault_client"):
        kode = vc.main(["--job-id", "417", "--kind", "reject"])

    assert kode == vc.EXIT_STOPPED_MIDWAY != 0
    assert vc.EXIT_STOPPED_MIDWAY_MESSAGE in caplog.text
    assert "MENGGANTUNG sampai expiredAt" in caplog.text
    client = dibangun["client"]
    assert client.w3.eth.built == ["postVerdict"]
    assert client.sent_transactions and len(client.sent_transactions) == 1


def test_a_clean_safe_mode_stop_still_exits_zero(db, monkeypatch, caplog):
    """Kontrol: berhenti SEBELUM tx apa pun tetap exit 0 (mode aman = perilaku diinginkan)."""
    dibangun = {}

    def _fake_build_client(private_key: str | None = None) -> vc.VaultClient:
        client = build_client(db=db)
        dibangun["client"] = client
        return client

    monkeypatch.setattr(vc, "build_client", _fake_build_client)
    monkeypatch.setattr(vc, "load_private_key", lambda: pytest.fail("kunci tidak boleh dimuat"))

    with caplog.at_level(logging.INFO, logger="vault_client"):
        assert vc.main(["--job-id", "417", "--kind", "reject"]) == 0
    assert dibangun["client"].sent_transactions == []
    assert vc.EXIT_STOPPED_MIDWAY_MESSAGE not in caplog.text


def test_the_gate_closes_the_memory_handle_it_opened(db):
    """Gerbang dibaca berkali-kali per tx; handle sqlite tidak boleh menumpuk."""
    seed_memory(db)
    ditutup = []
    asli = vc.close_memory_client

    def _catat(client):
        ditutup.append(client)
        asli(client)

    try:
        vc.close_memory_client = _catat
        vc.read_local_memory(db)
    finally:
        vc.close_memory_client = asli
    assert len(ditutup) == 1
    # `MemoryClient` 0.7.0 tidak punya `close()`; yang dipakai `storage.close()`.
    assert hasattr(ditutup[0].storage, "close")


# ----------------------------------------------------------------------
# TINGGI (i): `.env` di AKAR REPO benar-benar terbaca
#
# Semua tes lama di file ini menyuntik konfigurasi lewat `monkeypatch.setenv`, jadi tidak
# satu pun dari mereka pernah menyentuh jalur file — dan cacatnya (`repo_root()` menunjuk
# `agent/`) hijau selama itu. Tes di bawah menguji LOKASI file dan PEMBACAAN file, bukan
# environment.
# ----------------------------------------------------------------------


def test_env_file_path_walks_up_to_the_repo_root_not_the_package_dir(tmp_path):
    akar = tmp_path / "repo"
    (akar / "agent" / "agent").mkdir(parents=True)
    (akar / ".git").mkdir()
    (akar / ".env").write_text("RPC_URL=https://contoh.invalid\n", encoding="utf-8")
    modul = akar / "agent" / "agent" / "vault_client.py"
    modul.write_text("", encoding="utf-8")

    assert vc.env_file_path(modul) == akar / ".env"
    assert vc.repo_root(modul) == akar
    # Rumus LAMA (`parent.parent`) menunjuk `…/agent`, yang tidak memuat `.env` sama sekali.
    assert not (modul.resolve().parent.parent / ".env").exists()


def test_env_file_path_stops_at_the_repo_root(tmp_path):
    """`.env` di ATAS akar repo (mis. home) tidak boleh ikut terbaca."""
    luar = tmp_path / "luar"
    akar = luar / "repo"
    (akar / "agent" / "agent").mkdir(parents=True)
    (akar / ".git").mkdir()
    (luar / ".env").write_text("RPC_URL=https://bukan-milik-repo.invalid\n", encoding="utf-8")
    modul = akar / "agent" / "agent" / "vault_client.py"
    modul.write_text("", encoding="utf-8")

    assert vc.env_file_path(modul) is None


def test_config_value_and_private_key_come_from_the_env_FILE(tmp_path, monkeypatch):
    """Nilainya datang dari FILE, bukan dari `os.environ` — tanpa satu pun `setenv`."""
    env = tmp_path / ".env"
    env.write_text(
        "SIBYL_DB_PATH=/dari/berkas/memory.db\n"
        "# komentar\n"
        "AGENT_PRIVATE_KEY=" + "1a" * 32 + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SIBYL_DB_PATH", raising=False)
    monkeypatch.delenv("AGENT_PRIVATE_KEY", raising=False)
    monkeypatch.setattr(vc, "env_file_path", lambda: env)

    assert vc.config_value("SIBYL_DB_PATH", vc.DEFAULT_DB_PATH) == "/dari/berkas/memory.db"
    assert vc.memory_db_path() == pathlib.Path("/dari/berkas/memory.db")
    assert vc.load_private_key() == "0x" + "1a" * 32


def test_the_real_repo_env_file_is_actually_reachable():
    """Angka yang diukur reviewer: `_env_file_values()` → 0 kunci. Sekarang > 0.

    Isi `.env` TIDAK PERNAH diasersikan — hanya NAMA kuncinya — supaya kegagalan tes tidak
    mencetak kunci privat ke keluaran pytest.
    """
    env = vc.env_file_path()
    if env is None:
        pytest.skip("checkout ini tidak punya .env (mis. CI bersih)")
    assert env == vc.repo_root() / ".env"
    assert (vc.repo_root() / ".git").exists()
    # Rumus lama menunjuk `<repo>/agent`; ia BUKAN akar repo.
    assert vc.repo_root() != pathlib.Path(vc.__file__).resolve().parent.parent

    kunci = sorted(vc._env_file_values())
    assert kunci, "file .env terbaca tetapi tidak menghasilkan satu pun kunci"
