"""Tes `agent/memory_policy.py` — AC task 2.1 + batas §3 aturan 1 + temuan security-reviewer.

Tes di file ini MENJAGA kontrak keamanan memori, bukan sekadar perilaku:
  (a) entity karantina tidak memengaruhi keputusan (spec §3 aturan 1, ADR-002) —
      diuji sebagai PROPERTI atas masukan acak, bukan atas satu masukan tetap;
  (b) promosi menuntut >= 2 job_id BERBEDA dengan bukti deterministik (aturan 2);
  (c) `memory_root` deterministik, kanonik, dan MENGIKAT body mentah (spec §3 baris 123);
  (d) root onchain tidak cocok ATAU tidak terbaca → mode AMAN (aturan 5, ADR-007);
  (e) cap TIDAK PERNAH nol untuk risk >= 1 (ADR-019 keputusan 4 + ADR-001);
  (f) determinisme root diuji dengan MENGACAK urutan penyisipan;
  (g) `record_job_outcome` idempoten terhadap replay (reorg / restart watcher).

CLAUDE.md: "Pengambil keputusan memori DILARANG membaca entity `suspicion`. Tes unit
menjaganya; jangan hapus tes itu." Tiga tes yang menjaganya, dan ketiganya diperlukan:
  - `test_decision_path_source_never_mentions_quarantine` (statis, atas sumber);
  - `test_quarantine_never_changes_decisions_property` (PROPERTI: DB kembar dengan-vs-tanpa
    karantina, ratusan masukan acak — inilah yang membunuh mutan bersyarat-input);
  - `test_decision_path_never_touches_quarantine_at_runtime` (klien mata-mata).
Tes statis SAJA tidak cukup (nama kategori bisa disamarkan); tes contoh-tunggal SAJA juga
tidak cukup (mutan bisa bersyarat pada input yang tidak pernah diuji).
"""

from __future__ import annotations

import inspect
import json
import random

import pytest
from sibyl_memory_client import MemoryClient

from agent import memory_policy as mp

# Kata yang dilarang muncul di sumber jalur keputusan. Ditulis sebagai potongan agar
# konstanta modul (`CATEGORY_QUARANTINE = "suspicion"`) tetap terdeteksi.
QUARANTINE_WORDS = ("suspicion", "quarantine", "karantina")

DET_CHECK = "chain"

ROOT_ZERO_HEX = "0x" + "00" * 32
ROOT_A = bytes.fromhex("11" * 32)
ROOT_B = bytes.fromhex("22" * 32)

# Mode NAIF yang sah: root onchain TERBACA dan bernilai nol (hari pertama).
NAIVE = mp.decide_mode(ROOT_ZERO_HEX, None)


def addr(n: int) -> str:
    return f"0x{n:040x}"


@pytest.fixture
def client(tmp_path):
    """Klien Sibyl lokal pada DB temp — offline, tanpa `sibyl init` (api-facts §C)."""
    return MemoryClient.local(str(tmp_path / "memory.db"))


class SpyClient:
    """Pembungkus yang MEREKAM setiap pembacaan memori beserta kategori/kuncinya."""

    def __init__(self, inner: MemoryClient) -> None:
        self._inner = inner
        self.reads: list[tuple[str, str]] = []

    def get_entity(self, category, name):
        self.reads.append(("get_entity", category))
        return self._inner.get_entity(category, name)

    def list_entities(self, category=None, *, status=None, limit=100):
        self.reads.append(("list_entities", str(category)))
        return self._inner.list_entities(category, status=status, limit=limit)

    def search_entities(self, query, *, limit=20, prefix=False, category=None):
        self.reads.append(("search_entities", str(category)))
        return self._inner.search_entities(query, limit=limit, prefix=prefix, category=category)

    def get_reference(self, key):
        self.reads.append(("get_reference", key))
        return self._inner.get_reference(key)

    def get_state(self, key):
        self.reads.append(("get_state", key))
        return self._inner.get_state(key)

    def read_events(self, **kwargs):
        self.reads.append(("read_events", ""))
        return self._inner.read_events(**kwargs)


def _resolve(qualname: str):
    """Objek fungsi dari qualname yang dicatat `@decision_path`."""
    target = mp
    for part in qualname.split("."):
        target = getattr(target, part)
    return target


def _seed_provider(client, address, **kwargs) -> mp.ProviderProfile:
    profile = mp.ProviderProfile(address=mp.normalize_address(address), **kwargs)
    return mp.save_provider(client, profile)


def _poison_quarantine(client, address: str, patterns: int = 5, jobs: int = 50) -> None:
    """Menanam karantina EKSTREM: banyak pola, count raksasa, semua BELUM dipromosikan."""
    for i in range(patterns):
        for job in range(jobs):
            mp.record_suspicion(
                client,
                address,
                f"pola-ekstrem-{i}",
                mp.Evidence(job_id=job, check_id=DET_CHECK, proof=f"bukti-{job}"),
            )


def _all_decisions(client, address: str, budget: int, mode: mp.ModeDecision):
    """Seluruh keluaran jalur keputusan untuk satu masukan — dibandingkan apa adanya."""
    view = mp.DecisionMemoryView(client)
    profile = view.provider(address)
    return (
        profile,
        mp.effective_risk(profile, mode),
        mp.check_depth(profile, mode),
        mp.derive_cap(profile, mode),
        mp.gate_job(view, address, budget, mode),
        mp.memory_root(client),
    )


# ----------------------------------------------------------------------
# (a) karantina tidak memengaruhi keputusan — spec §3 aturan 1
# ----------------------------------------------------------------------


def test_decision_path_source_never_mentions_quarantine():
    """Statis: sumber SETIAP fungsi `@decision_path` bebas dari karantina.

    JANGAN hapus atau longgarkan tes ini (CLAUDE.md). Ia lapis pertama; lapis kedua
    (properti) dan ketiga (mata-mata) ada di bawah karena nama kategori bisa disamarkan.
    """
    assert mp.DECISION_PATH_FUNCTIONS, "penanda @decision_path hilang dari modul"
    pelanggar = []
    for qualname in sorted(mp.DECISION_PATH_FUNCTIONS):
        source = inspect.getsource(_resolve(qualname)).lower()
        if any(word in source for word in QUARANTINE_WORDS):
            pelanggar.append(qualname)
    assert pelanggar == [], f"jalur keputusan menyebut karantina: {pelanggar}"


def test_quarantine_never_changes_decisions_property(tmp_path):
    """PROPERTI (a): DUA DB dengan riwayat tulis IDENTIK, satu diracuni karantina.

    Untuk RATUSAN masukan acak (alamat dikenal & tak dikenal, budget ganjil & genap,
    besar & kecil, semua mode) seluruh keluaran jalur keputusan harus IDENTIK. Tes contoh
    tunggal tidak cukup: mutan bisa dibuat bersyarat pada paritas budget atau pada alamat
    tertentu dan lolos. Di sini masukannya yang berkeliaran, bukan asersinya.
    """
    rng = random.Random(20260905)
    providers = [addr(0xA00 + i) for i in range(4)]

    bersih = MemoryClient.local(str(tmp_path / "bersih.db"))
    teracun = MemoryClient.local(str(tmp_path / "teracun.db"))

    # Riwayat TULIS yang persis sama di kedua DB.
    for db in (bersih, teracun):
        for i, provider in enumerate(providers):
            mp.record_job_outcome(db, provider, job_id=100 + i, budget=1_000_000 + i, passed=True)
            if i % 2 == 1:
                mp.record_job_outcome(
                    db, provider, job_id=200 + i, budget=7_000_003, passed=False,
                    failed_checks=[DET_CHECK],
                )
        # satu pola BENAR-BENAR dipromosikan di kedua DB (jalur sah menuju keputusan)
        mp.record_suspicion(db, providers[0], "pola-sah", mp.Evidence(1, DET_CHECK))
        mp.record_suspicion(db, providers[0], "pola-sah", mp.Evidence(2, DET_CHECK))
        mp.promote_suspicions(db, providers[0])

    # HANYA DB kedua yang diracuni: karantina yang TIDAK memenuhi syarat promosi.
    for provider in providers:
        _poison_quarantine(teracun, provider, patterns=3, jobs=7)
    mp.record_suspicion(teracun, providers[1], "hampir-lolos", mp.Evidence(9, DET_CHECK))

    modes = [
        NAIVE,
        mp.decide_mode(ROOT_A, ROOT_A),
        mp.decide_mode(ROOT_A, None),
    ]
    budgets_diuji = []
    for _ in range(240):
        target = rng.choice([*providers, addr(rng.randrange(1, 2**32))])
        budget = rng.choice([
            rng.randrange(1, 50_000_000),
            rng.randrange(1, 50_000_000) * 2 + 1,  # dijamin ganjil
            2**200 + 1,
            1,
        ])
        mode = rng.choice(modes)
        budgets_diuji.append(budget)
        assert _all_decisions(bersih, target, budget, mode) == _all_decisions(
            teracun, target, budget, mode
        ), f"karantina mengubah keputusan untuk {target} budget={budget} mode={mode.mode}"

    assert any(b % 2 == 1 for b in budgets_diuji)
    assert any(b % 2 == 0 for b in budgets_diuji)
    # Kontrol: DB kedua memang berisi karantina, jadi properti di atas bukan hijau palsu.
    baris_bersih = bersih.list_entities(mp.CATEGORY_QUARANTINE, limit=mp.LIST_LIMIT)
    baris_teracun = teracun.list_entities(mp.CATEGORY_QUARANTINE, limit=mp.LIST_LIMIT)
    assert len(baris_bersih) == 1  # hanya pola yang SAH (sudah dipromosikan)
    assert len(baris_teracun) >= 13
    assert {r["body"]["count"] for r in baris_teracun} >= {7}


def test_decision_path_never_touches_quarantine_at_runtime(client):
    """Dinamis: seluruh jalur keputusan dijalankan, tidak satu pun membaca karantina."""
    address = addr(0xAA)
    _seed_provider(client, address, risk_level=2, passed_budgets=(1_000_000, 3_000_000))
    _poison_quarantine(client, address)

    spy = SpyClient(client)
    view = mp.DecisionMemoryView(spy)
    gate = mp.gate_job(view, address, budget=9_000_001, mode=NAIVE)
    mp.memory_root(spy)

    assert gate.accept is False
    kategori = {c for _, c in spy.reads}
    assert mp.CATEGORY_QUARANTINE not in kategori
    for method, key in spy.reads:
        if method == "get_reference":
            assert key.startswith(mp.REFERENCE_PATTERN_PREFIX)
        else:
            assert key == mp.CATEGORY_PROVIDER, f"pembacaan terlarang: {method}({key})"


def test_view_refuses_forbidden_category_and_reference():
    view = mp.DecisionMemoryView(object())
    with pytest.raises(mp.ForbiddenReadError):
        view._guard_category(mp.CATEGORY_QUARANTINE)
    with pytest.raises(mp.ForbiddenReadError):
        view._guard_category(mp.CATEGORY_CLIENT)
    # `rubric:` DITOLAK sampai 2.1r menjangkarnya (ADR-020 keputusan 6-7): melebarkan BACA
    # sebelum penjangkarannya memperluas keadaan "dibaca tapi tidak dijangkar", yaitu
    # permukaan tempat teks bisa memengaruhi keputusan tanpa mengubah memory_root.
    assert view._guard_reference_key("pattern:x") == "pattern:x"
    for terlarang in ("rubric:defi", "job:1", "suspicion:0x1", "pattern", "", None):
        with pytest.raises(mp.ForbiddenReadError):
            view._guard_reference_key(terlarang)
    assert not hasattr(view, "rubric")


def test_view_hides_its_client_and_refuses_new_attributes(client):
    """Penjaga tidak bisa dilewati lewat atribut privat, dan tidak bisa dilebarkan."""
    view = mp.DecisionMemoryView(client)
    assert not hasattr(view, "_client")
    with pytest.raises(AttributeError):
        view.ALLOWED_ENTITY_CATEGORIES = frozenset({"provider", mp.CATEGORY_QUARANTINE})
    with pytest.raises(AttributeError):
        view.apa_saja = 1


def test_gate_job_refuses_subclass_that_widens_the_guard(client):
    class ViewLonggar(mp.DecisionMemoryView):
        def _guard_category(self, category):  # noqa: D102 - sengaja melonggarkan
            return category

    with pytest.raises(TypeError):
        mp.gate_job(ViewLonggar(client), addr(1), 1, NAIVE)


def test_extreme_quarantine_does_not_change_any_decision(client):
    """AC (a), sisi TULIS: tanam karantina ekstrem → cap, gate, dan root TIDAK berubah."""
    address = addr(0xBB)
    _seed_provider(client, address, risk_level=1, passed_budgets=(2_000_000, 4_000_000))
    sebelum = _all_decisions(client, address, 3_500_001, NAIVE)
    _poison_quarantine(client, address)
    assert _all_decisions(client, address, 3_500_001, NAIVE) == sebelum


def test_quarantine_rows_really_exist_so_the_test_is_not_vacuous(client):
    """Kontrol: karantina benar-benar tertulis — tes di atas bukan hijau palsu."""
    address = addr(0xCC)
    _poison_quarantine(client, address)
    rows = client.list_entities(mp.CATEGORY_QUARANTINE, limit=mp.LIST_LIMIT)
    assert len(rows) == 5
    assert rows[0]["body"]["count"] == 50


# ----------------------------------------------------------------------
# (b) promosi butuh >= 2 job_id BERBEDA — spec §3 aturan 2
# ----------------------------------------------------------------------


def test_promotion_needs_two_distinct_jobs(client):
    address = addr(0xDD)
    mp.record_suspicion(client, address, "supply-salah", mp.Evidence(7, DET_CHECK, "a"))
    assert mp.promote_suspicions(client, address) == []

    # Job yang SAMA diulang (check berbeda) tetap tidak boleh menaikkan count efektif.
    mp.record_suspicion(client, address, "supply-salah", mp.Evidence(7, "format", "b"))
    assert mp.promote_suspicions(client, address) == []

    mp.record_suspicion(client, address, "supply-salah", mp.Evidence(9, DET_CHECK, "c"))
    assert mp.promote_suspicions(client, address) == ["supply-salah"]

    profile = mp.DecisionMemoryView(client).provider(address)
    assert profile.confirmed_patterns == ("supply-salah",)
    assert profile.risk_level == mp.MAX_RISK_LEVEL
    assert mp.DecisionMemoryView(client).pattern("supply-salah")["pattern_id"] == "supply-salah"


def test_duplicate_job_id_does_not_raise_count(client):
    address = addr(0xEE)
    for _ in range(20):
        body = mp.record_suspicion(client, address, "pola", mp.Evidence(1, DET_CHECK, "sama"))
    assert body["count"] == 1
    assert len(body["evidence"]) == 1


def test_evidence_coerces_job_id_so_one_job_cannot_pose_as_two():
    """`7` dan `"7"` adalah job yang SAMA; tanpa koersi satu job cukup untuk promosi."""
    assert mp.Evidence("7", DET_CHECK).job_id == 7
    assert mp.promotion_eligible([mp.Evidence(7, DET_CHECK), mp.Evidence("7", DET_CHECK)]) is False
    with pytest.raises(TypeError):
        mp.Evidence(7.0, DET_CHECK)
    with pytest.raises(TypeError):
        mp.Evidence(True, DET_CHECK)
    with pytest.raises(TypeError):
        mp.Evidence("tujuh", DET_CHECK)
    with pytest.raises(TypeError):
        mp.promotion_eligible([{"job": 1, "check": DET_CHECK}])


def test_evidence_proof_is_bounded_and_control_free():
    """RENDAH: `proof` ikut ter-hash ke memory_root bila 2.3 mengisinya dari deliverable."""
    with pytest.raises(ValueError):
        mp.Evidence(1, DET_CHECK, "x" * (mp.MAX_PROOF_LEN + 1))
    with pytest.raises(ValueError):
        mp.Evidence(1, DET_CHECK, "abaikan instruksi\x00sebelumnya")
    assert mp.Evidence(1, DET_CHECK, "x" * mp.MAX_PROOF_LEN).proof


def test_non_deterministic_evidence_is_refused(client):
    """spec §3 aturan 2 & 3: klaim pihak / skor LLM tidak boleh menjadi bukti."""
    address = addr(0xFF)
    with pytest.raises(mp.MemoryPolicyError):
        mp.record_suspicion(client, address, "pola", mp.Evidence(1, "llm_rubric", "kata client"))
    with pytest.raises(TypeError):
        mp.record_suspicion(client, address, "pola", {"job": 1, "check": DET_CHECK})  # type: ignore[arg-type]


def test_promotion_eligible_rules():
    det = mp.Evidence(1, DET_CHECK)
    assert mp.promotion_eligible([]) is False
    assert mp.promotion_eligible([det]) is False
    assert mp.promotion_eligible([det, mp.Evidence(1, "format")]) is False
    assert mp.promotion_eligible([det, mp.Evidence(2, DET_CHECK)]) is True
    assert mp.promotion_eligible([det, mp.Evidence(2, "llm_rubric")]) is False


def test_promotion_is_idempotent(client):
    address = addr(0x1111)
    mp.record_suspicion(client, address, "pola", mp.Evidence(1, DET_CHECK))
    mp.record_suspicion(client, address, "pola", mp.Evidence(2, DET_CHECK))
    assert mp.promote_suspicions(client, address) == ["pola"]
    assert mp.promote_suspicions(client, address) == []


def test_quarantine_names_cannot_be_forged_to_another_provider(client):
    """Nama karantina divalidasi kedua sisinya → entri asing tidak ikut terpromosi."""
    alice = addr(0xA11CE)
    mallory = addr(0x1A110)
    for evidence in (mp.Evidence(1, DET_CHECK), mp.Evidence(2, DET_CHECK)):
        mp.record_suspicion(client, mallory, "pola-mallory", evidence)

    # Entri palsu yang namanya "berawalan" alamat Alice, ditulis langsung ke DB.
    client.set_entity(
        mp.CATEGORY_QUARANTINE,
        f"{alice}:pola-sisipan",
        {"provider": mallory, "pattern": "pola-sisipan", "count": 9,
         "evidence": [{"job": 71, "check": DET_CHECK}, {"job": 72, "check": DET_CHECK}]},
        status=mp.QUARANTINE_STATUS_PENDING,
    )

    assert mp.promote_suspicions(client, alice) == []
    profile = mp.DecisionMemoryView(client).provider(alice)
    assert profile.confirmed_patterns == ()
    assert profile.incident_jobs == ()
    assert profile.risk_level == 0

    with pytest.raises(ValueError):
        mp.quarantine_name(alice, "pola:sisipan")
    with pytest.raises(ValueError):
        mp.normalize_address("  BUKAN ALAMAT SAMA SEKALI  ")
    with pytest.raises(ValueError):
        mp.normalize_address(f"{alice}:jahat")
    assert mp.split_quarantine_name("bukan-nama") is None


# ----------------------------------------------------------------------
# (g) idempotensi tulis — replay event, reorg, restart watcher
# ----------------------------------------------------------------------


def test_record_job_outcome_idempotent(client):
    """AC (h): event SAMA diputar 3x → body entity BYTE-identik dan cap identik."""
    address = addr(0x2D2D)

    def snapshot_bytes():
        row = client.get_entity(mp.CATEGORY_PROVIDER, address)
        return json.dumps(row["body"], sort_keys=True).encode()

    mp.record_job_outcome(client, address, 5, 2_000_000, passed=True)
    sekali, cap_sekali = snapshot_bytes(), mp.derive_cap(mp.DecisionMemoryView(client).provider(address))
    for _ in range(3):
        mp.record_job_outcome(client, address, 5, 2_000_000, passed=True)
        assert snapshot_bytes() == sekali
    assert mp.derive_cap(mp.DecisionMemoryView(client).provider(address)) == cap_sekali


def test_record_job_outcome_is_idempotent_under_replay(client):
    """KRITIS: replay satu event tidak boleh menggeser median → tidak boleh melebarkan cap."""
    address = addr(0x2A2A)
    mp.record_job_outcome(client, address, 1, 1_000_000, passed=False, failed_checks=[DET_CHECK])
    mp.record_job_outcome(client, address, 2, 3_000_000, passed=False, failed_checks=[DET_CHECK])
    sebelum = _all_decisions(client, address, 20_000_000, NAIVE)

    for _ in range(5):
        mp.record_job_outcome(client, address, 3, 99_000_000, passed=False, failed_checks=[DET_CHECK])
    satu_kali = _all_decisions(client, address, 20_000_000, NAIVE)
    for _ in range(5):
        mp.record_job_outcome(client, address, 3, 99_000_000, passed=False, failed_checks=[DET_CHECK])

    profile = mp.DecisionMemoryView(client).provider(address)
    assert profile.stats_jobs == 3
    assert profile.recorded_jobs == (1, 2, 3)
    # ADR-020 keputusan 2: budget job yang DITOLAK tidak disimpan di mana pun.
    assert profile.passed_budgets == ()
    assert _all_decisions(client, address, 20_000_000, NAIVE) == satu_kali
    # Job 20 juta tetap DITOLAK; sebelum perbaikan, replay 5x membuatnya lolos.
    assert satu_kali[4].accept is False
    assert sebelum[4].accept is False


def test_replay_does_not_change_memory_root(client):
    address = addr(0x2B2B)
    mp.record_job_outcome(client, address, 1, 5_000_000, passed=True)
    root = mp.memory_root(client)
    for _ in range(10):
        mp.record_job_outcome(client, address, 1, 5_000_000, passed=True)
    assert mp.memory_root(client) == root


def test_record_job_outcome_rejects_bad_types(client):
    address = addr(0x2C2C)
    with pytest.raises(TypeError):
        mp.record_job_outcome(client, address, "1", 1, passed=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        mp.record_job_outcome(client, address, 1, 1.5, passed=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        mp.record_job_outcome(client, address, 1, -1, passed=True)


# ----------------------------------------------------------------------
# (c)+(f) `memory_root` deterministik, kanonik, MENGIKAT isi memori
# ----------------------------------------------------------------------


def test_memory_root_is_stable_across_calls(client):
    _seed_provider(client, addr(0x2222), risk_level=1)
    assert mp.memory_root(client) == mp.memory_root(client)
    assert mp.memory_root_hex(client).startswith("0x")
    assert len(mp.memory_root(client)) == 32


def test_memory_root_changes_when_one_entity_changes(client):
    address = addr(0x3333)
    _seed_provider(client, address, risk_level=0)
    sebelum = mp.memory_root(client)
    _seed_provider(client, address, risk_level=2)
    assert mp.memory_root(client) != sebelum


def test_memory_root_binds_raw_body_not_a_lossy_projection(client, tmp_path):
    """TINGGI: field asing & perbedaan tipe WAJIB mengubah root.

    Bila preimage dibangun dari proyeksi `ProviderProfile`, ketiga kasus di bawah
    menghasilkan root IDENTIK dan root berhenti membuktikan isi memori.
    """
    address = addr(0x4A4A)
    dasar = {"risk_level": 2, "budgets": {"passed": [1, 2]}}

    client.set_entity(mp.CATEGORY_PROVIDER, address, dasar)
    root_dasar = mp.memory_root(client)

    client.set_entity(mp.CATEGORY_PROVIDER, address, {**dasar, "backdoor": "muatan tersembunyi"})
    assert mp.memory_root(client) != root_dasar

    client.set_entity(mp.CATEGORY_PROVIDER, address, {**dasar, "risk_level": "2"})
    assert mp.memory_root(client) != root_dasar

    client.set_entity(mp.CATEGORY_PROVIDER, address, {**dasar, "budgets": {"passed": ["1", "2"]}})
    assert mp.memory_root(client) != root_dasar

    # Float di body TIDAK diam-diam dibulatkan menjadi root yang sama: ia ditolak.
    client.set_entity(mp.CATEGORY_PROVIDER, address, {**dasar, "risk_level": 2.0})
    with pytest.raises(mp.MemoryIntegrityError):
        mp.memory_root(client)


def test_colliding_provider_names_are_refused_not_merged(client):
    """TINGGI: dua entity NYATA yang runtuh jadi satu kunci = satu entity tersembunyi."""
    address = addr(0x5A5A)
    client.set_entity(mp.CATEGORY_PROVIDER, address, {"risk_level": 0})
    client.set_entity(mp.CATEGORY_PROVIDER, f"  {address.upper()}  ", {"risk_level": 2})
    with pytest.raises(mp.MemoryIntegrityError):
        mp.memory_root(client)


def test_snapshot_refuses_provider_name_that_is_not_an_address():
    with pytest.raises(ValueError):
        mp.MemorySnapshot.from_mapping({"bukan-alamat": {}}, {})


def test_preimage_has_no_json_numbers_so_javascript_can_rebuild_it():
    """TINGGI: `JSON.parse` memakai float 64-bit → uint256 rusak DIAM-DIAM di atas 2^53."""
    besar = 2**200 + 1
    snapshot = mp.MemorySnapshot.from_mapping(
        {addr(1): {"budgets": {"passed": [besar, 9007199254740993]}}}, {}
    )
    preimage = snapshot.preimage()
    assert preimage.decode("ascii")

    def tanpa_bilangan(node):
        if isinstance(node, bool) or node is None or isinstance(node, str):
            return True
        if isinstance(node, (int, float)):
            return False
        if isinstance(node, list):
            return all(tanpa_bilangan(x) for x in node)
        return all(tanpa_bilangan(v) for v in node.values())

    parsed = json.loads(preimage)
    assert tanpa_bilangan(parsed), "preimage masih memuat bilangan JSON"
    assert str(besar).encode() in preimage
    assert b'"9007199254740993"' in preimage
    # Integer berbeda tetap menghasilkan preimage berbeda (tidak dibulatkan).
    lain = mp.MemorySnapshot.from_mapping(
        {addr(1): {"budgets": {"passed": [besar, 9007199254740992]}}}, {}
    )
    assert lain.preimage() != preimage


def test_canonical_json_refuses_values_that_cannot_be_reproduced():
    with pytest.raises(mp.MemoryIntegrityError):
        mp.canonical_json({"a": 1.5})
    with pytest.raises(mp.MemoryIntegrityError):
        mp.canonical_json({"kunci-π": 1})
    with pytest.raises(mp.MemoryIntegrityError):
        mp.canonical_json({mp.NUMBER_TAG: "1"})
    with pytest.raises(mp.MemoryIntegrityError):
        mp.canonical_json({"a": {1: "kunci bukan string"}})
    with pytest.raises(mp.MemoryIntegrityError):
        mp.canonical_json({"a": {"b"}})


def test_memory_root_ignores_insertion_order(tmp_path):
    """AC (f): urutan penyisipan diacak → root tetap identik."""
    providers = [
        mp.ProviderProfile(address=addr(i), risk_level=i % 3, passed_budgets=(i * 1000, i * 2000))
        for i in range(1, 12)
    ]
    roots = set()
    for seed in range(4):
        c = MemoryClient.local(str(tmp_path / f"m{seed}.db"))
        acak = list(providers)
        random.Random(seed).shuffle(acak)
        for profile in acak:
            mp.save_provider(c, profile)
        roots.add(mp.memory_root(c))
    assert len(roots) == 1


def test_memory_root_from_snapshot_matches_root_from_db(client):
    """Satu implementasi untuk dua jalur: DB (agen) dan struktur data (ekspor 2.1b)."""
    address = addr(0x4444)
    mp.record_suspicion(client, address, "pola", mp.Evidence(1, DET_CHECK))
    mp.record_suspicion(client, address, "pola", mp.Evidence(2, DET_CHECK))
    mp.promote_suspicions(client, address)

    snapshot = mp.load_snapshot(client)
    assert snapshot.patterns  # promosi menulis reference-nya
    ulang = mp.MemorySnapshot.from_mapping(dict(snapshot.providers), dict(snapshot.patterns))
    assert mp.memory_root(ulang) == mp.memory_root(client)


def test_snapshot_preimage_is_canonical_ascii():
    snapshot = mp.MemorySnapshot.from_mapping({addr(0xB): {"z": "1", "a": "2"}, addr(0xA): {}}, {})
    preimage = snapshot.preimage()
    assert preimage.decode("ascii")  # ASCII murni → bebas locale/encoding
    assert preimage.index(addr(0xA).encode()) < preimage.index(addr(0xB).encode())
    assert b'{"a":"2","z":"1"}' in preimage


def test_load_snapshot_fails_closed_when_pattern_reference_missing(client):
    address = addr(0x5555)
    _seed_provider(client, address, confirmed_patterns=("hantu",))
    with pytest.raises(mp.MemoryIntegrityError):
        mp.load_snapshot(client)


def test_list_entities_truncation_is_refused_not_silent(client, monkeypatch):
    """api-facts §C: `list_entities` memotong DIAM-DIAM → provider hilang dari root."""
    for i in range(3):
        _seed_provider(client, addr(0x6000 + i))
        mp.record_suspicion(client, addr(0x6000), f"pola-{i}", mp.Evidence(i, DET_CHECK))
    monkeypatch.setattr(mp, "LIST_LIMIT", 2)
    with pytest.raises(mp.MemoryIntegrityError):
        mp.memory_root(client)
    with pytest.raises(mp.MemoryIntegrityError):
        mp.promote_suspicions(client, addr(0x6000))


# ----------------------------------------------------------------------
# (d) mode aman — spec §3 aturan 5 / ADR-007
# ----------------------------------------------------------------------


def test_mode_naive_only_when_root_is_readable_zero():
    for onchain in (mp.ZERO_ROOT, ROOT_ZERO_HEX, "00" * 32):
        keputusan = mp.decide_mode(onchain, ROOT_A)
        assert keputusan.mode == mp.MODE_NAIVE
        assert keputusan.allow_finalize is True


@pytest.mark.parametrize("onchain", [None, "", "0x", 32, b"\x01" * 31, "0x" + "zz" * 32, 0, []])
def test_unreadable_onchain_root_is_safe_mode_not_naive(onchain):
    """TINGGI: `"0x"` adalah jawaban `eth_call` untuk kontrak/chain yang SALAH.

    Menerjemahkannya menjadi "hari pertama" memberi izin MAKSIMUM justru saat agen paling
    tidak tahu apa-apa — kebalikan spec §3 aturan 5.
    """
    keputusan = mp.decide_mode(onchain, ROOT_A)
    assert keputusan.mode == mp.MODE_SAFE
    assert keputusan.allow_finalize is False
    assert keputusan.allow_post_verdict is False
    assert "tidak terbaca" in keputusan.reason


def test_parse_root_is_strict():
    assert mp.parse_root("0x" + "11" * 32) == ROOT_A
    assert mp.parse_root("11" * 32) == ROOT_A
    for buruk in ("0x", "", "0x11", 32, None, b"\x01" * 31, "0x" + "zz" * 32):
        with pytest.raises(ValueError):
            mp.parse_root(buruk)


def test_mode_normal_when_roots_match():
    keputusan = mp.decide_mode(ROOT_A, ROOT_A)
    assert keputusan.mode == mp.MODE_NORMAL
    assert keputusan.allow_finalize is True
    assert mp.decide_mode("0x" + ROOT_A.hex(), ROOT_A).mode == mp.MODE_NORMAL


def test_mode_safe_when_root_mismatch_or_memory_gone():
    for lokal in (None, mp.ZERO_ROOT, ROOT_B, "0x", "bukan root"):
        keputusan = mp.decide_mode(ROOT_A, lokal)
        assert keputusan.mode == mp.MODE_SAFE
        assert keputusan.allow_finalize is False
        assert keputusan.allow_post_verdict is False
        assert keputusan.forced_risk == mp.MAX_RISK_LEVEL
        assert keputusan.depth == mp.DEPTH_FULL
        assert mp.safe_mode(ROOT_A, lokal) is True


def test_safe_mode_halts_every_transaction_and_says_so_plainly():
    """ADR-020 keputusan 8: postVerdict, finalize, DAN setProviderCap sama-sama ditahan."""
    aman = mp.decide_mode(ROOT_A, None)
    assert (aman.allow_post_verdict, aman.allow_finalize, aman.allow_set_provider_cap) == (
        False, False, False
    )
    assert mp.SAFE_MODE_CONSEQUENCE in aman.reason
    for frasa in ("berhenti total", "MENGGANTUNG sampai expiredAt", "claimRefund", "refund penuh"):
        assert frasa in aman.reason
    for boleh in (NAIVE, mp.decide_mode(ROOT_A, ROOT_A)):
        assert boleh.allow_set_provider_cap is True


def test_memory_root_is_not_allowed_on_chain_until_the_encoding_is_frozen(client):
    """ADR-020 keputusan 6 + AC task 2.1: `vault_client` tidak boleh memakai root ini."""
    assert mp.MEMORY_ROOT_ENCODING_FROZEN is False
    _seed_provider(client, addr(0x9F9F))
    assert len(mp.memory_root(client)) == 32
    with pytest.raises(mp.MemoryPolicyError):
        mp.memory_root_for_onchain(client)


def test_safe_mode_forces_maximum_risk_and_milestone_cap():
    """Semua provider diperlakukan risk maksimum, termasuk yang bersih."""
    bersih = mp.ProviderProfile(address=addr(0x6666), risk_level=0, passed_budgets=(4_000_000,))
    aman = mp.decide_mode(ROOT_A, None)
    assert mp.effective_risk(bersih, aman) == mp.MAX_RISK_LEVEL
    cap = mp.derive_cap(bersih, aman)
    assert cap.require_milestone is True
    # median passed 4.000.000 diplafon ADR-021 ke 1.000.000, lalu 25% → 250.000.
    assert cap.cap_usdc == 250_000
    assert mp.check_depth(bersih, aman) == mp.DEPTH_FULL


# ----------------------------------------------------------------------
# Kalibrasi kedalaman cek — spec §3 aturan 6 / §7 langkah 4
# ----------------------------------------------------------------------


def test_check_depth_is_calibrated_by_memory():
    bersih = mp.ProviderProfile(address=addr(0x7A7A), risk_level=0)
    berinsiden = mp.ProviderProfile(address=addr(0x7B7B), risk_level=2, incident_jobs=(1, 2))
    assert mp.check_depth(bersih, NAIVE) == mp.DEPTH_SAMPLING
    assert mp.check_depth(berinsiden, mp.decide_mode(ROOT_A, ROOT_A)) == mp.DEPTH_FULL
    # Inilah yang hilang saat memori dihapus: provider yang sama turun ke sampling.
    assert mp.check_depth(mp.ProviderProfile(address=addr(0x7B7B)), NAIVE) == mp.DEPTH_SAMPLING


# ----------------------------------------------------------------------
# (e) `derive_cap` — spec §3 aturan 4 + ADR-019 keputusan 4 + ADR-001
# ----------------------------------------------------------------------


def test_risk_zero_has_no_cap_and_maps_to_unlimited_onchain():
    profile = mp.ProviderProfile(address=addr(0x7777), risk_level=0)
    cap = mp.derive_cap(profile)
    assert cap.cap_usdc is mp.NO_CAP
    assert cap.has_cap is False
    assert cap.require_milestone is False
    # ADR-001: nilai 0 di kontrak berarti TANPA BATAS — hanya NO_CAP yang boleh jadi 0.
    assert mp.cap_to_onchain(cap) == mp.ONCHAIN_UNLIMITED_CAP


def test_risk_one_uses_median_of_passed_budgets():
    profile = mp.ProviderProfile(
        address=addr(0x8888),
        risk_level=1,
        passed_budgets=(1_000_000, 3_000_000, 5_000_000),
    )
    # ADR-021 keputusan 1: tiap kontribusi diplafon BASELINE_CAP_USDC lebih dulu,
    # jadi median (1M, 1M, 1M) = 1.000.000 — bukan 3.000.000.
    assert mp.derive_cap(profile) == mp.CapPlan(1_000_000, False, "median-passed", 3)


def test_risk_two_uses_quarter_of_median_and_requires_milestone():
    profile = mp.ProviderProfile(
        address=addr(0x9999),
        risk_level=2,
        passed_budgets=(2_000_000, 6_000_000),
    )
    cap = mp.derive_cap(profile)
    assert cap.cap_usdc == 250_000  # (2M, 6M) diplafon ke (1M, 1M) → median 1M → 25%
    assert cap.require_milestone is True
    assert cap.basis == "median-passed"


def test_median_is_exact_for_uint256_scale_numbers():
    """SEDANG: `(a+b)/2` float meleset di atas 2^53 → cap salah diam-diam."""
    a, b = 2**80 + 1, 2**80 + 3
    assert mp._median_ceil([a, b]) == 2**80 + 2
    assert mp._median_ceil([1, 2]) == 2
    assert mp._median_ceil([9007199254740993, 9007199254740995]) == 9007199254740994


def test_derive_cap_emptyPassedSet_isConstant():
    """AC (g) / ADR-020 keputusan 3: cap dari KONSTANTA, bukan statistik.

    Berlaku apa pun isi riwayat: provider yang seluruh jobnya ditolak (skenario §7
    langkah 1-2) tidak punya satu pun angka yang ia kendalikan di dalam capnya.
    """
    for insiden in [(), (1,), tuple(range(50))]:
        satu = mp.ProviderProfile(address=addr(0xA0A0), risk_level=1, incident_jobs=insiden)
        dua = mp.ProviderProfile(address=addr(0xA0A1), risk_level=2, incident_jobs=insiden)
        assert mp.derive_cap(satu).cap_usdc == mp.BASELINE_CAP_USDC == 1_000_000
        assert mp.derive_cap(dua).cap_usdc == mp.BASELINE_CAP_USDC // 4 == 250_000
        assert mp.derive_cap(satu).basis == "baseline-constant"
        assert mp.derive_cap(dua).require_milestone is True


def test_derive_cap_rejectedJobsNeverRaiseCap(client, capsys):
    """AC (f) / KRITIS-1: 10 ronde REJECT berturut-turut TIDAK boleh menaikkan cap.

    Biaya penyerang nol: `reject` mengembalikan 100% budget ke client dan fee evaluator 0
    (api-facts §A), dan token escrow testnet punya `mint()` tanpa kontrol akses. Sebelum
    ADR-020, rantai ini menaikkan cap 500.000 → 24.750.000 dan job 20 juta akhirnya LOLOS.
    """
    address = addr(0xA0FF)
    view = mp.DecisionMemoryView(client)
    mp.record_job_outcome(client, address, 1, 1_000_000, passed=False, failed_checks=[DET_CHECK])
    mp.record_job_outcome(client, address, 2, 3_000_000, passed=False, failed_checks=[DET_CHECK])
    cap_awal = mp.derive_cap(view.provider(address)).cap_usdc

    caps = [cap_awal]
    for ronde in range(10):
        budget = 5_000_000 * (ronde + 1) ** 2  # provider mendanai job makin besar, lalu ditolak
        mp.record_job_outcome(
            client, address, 10 + ronde, budget, passed=False, failed_checks=[DET_CHECK]
        )
        cap = mp.derive_cap(view.provider(address))
        mp.store_provider_cap(client, address, cap)
        caps.append(cap.cap_usdc)

    cap_akhir = caps[-1]
    print(f"cap AWAL={cap_awal} cap AKHIR={cap_akhir} seri={caps}")
    assert cap_akhir <= cap_awal
    assert max(caps) == cap_awal
    # Job 20 juta tetap ditolak sesudah sepuluh ronde.
    assert mp.gate_job(view, address, 20_000_000, NAIVE).accept is False


def test_derive_cap_monotone_nonIncreasing():
    """AC (i) / ADR-020 keputusan 4: cap tidak pernah melebihi cap yang sudah tersimpan."""
    naik = mp.ProviderProfile(
        address=addr(0xA0FE), risk_level=1, passed_budgets=(50_000_000,), cap_usdc=300_000
    )
    assert mp.derive_cap(naik).cap_usdc == 300_000
    assert mp.derive_cap(naik).basis == "monotone-previous"
    # Kandidat yang lebih kecil tetap menang (monoton TIDAK-NAIK, bukan "beku").
    turun = mp.ProviderProfile(
        address=addr(0xA0FD), risk_level=2, passed_budgets=(1_200_000,), cap_usdc=10_000_000
    )
    assert mp.derive_cap(turun).cap_usdc == 250_000
    assert mp.derive_cap(turun).basis == "median-passed"
    # Monoton berlaku JUGA saat risk turun ke 0: tanpa itu cap hilang → on-chain 0 =
    # TANPA BATAS (ADR-001), kenaikan cap paling ekstrem yang mungkin.
    pulih = mp.ProviderProfile(address=addr(0xA0FB), risk_level=0, cap_usdc=250_000)
    assert mp.derive_cap(pulih).cap_usdc == 250_000
    assert mp.derive_cap(pulih).require_milestone is False
    # Lantai diterapkan pada HASIL AKHIR: cap tersimpan 1 tidak boleh menjadi blokir permanen.
    kerdil = mp.ProviderProfile(address=addr(0xA0FA), risk_level=2, cap_usdc=1)
    assert mp.derive_cap(kerdil).cap_usdc == mp.MIN_CAP_USDC == 250_000
    # Cap tersimpan yang tidak sah (0 = TANPA BATAS on-chain, ADR-001) diabaikan.
    rusak = mp.ProviderProfile(address=addr(0xA0FC), risk_level=2, cap_usdc=0)
    assert mp.derive_cap(rusak).cap_usdc == 250_000


@pytest.mark.parametrize("risk", [1, 2])
@pytest.mark.parametrize("passed", [(), (0,), (1,), (0, 1), (1, 2, 3), (10**30,)])
def test_cap_is_never_zero_for_risk_at_least_one(risk, passed):
    """cap nol = blacklist yang tak ada di spec, dan on-chain = TANPA BATAS."""
    profile = mp.ProviderProfile(address=addr(0xB0B0), risk_level=risk, passed_budgets=passed)
    cap = mp.derive_cap(profile)
    assert cap.cap_usdc is not None
    assert cap.cap_usdc >= mp.MIN_CAP_USDC == 250_000
    assert mp.cap_to_onchain(cap) != mp.ONCHAIN_UNLIMITED_CAP


def test_cap_to_onchain_refuses_zero_cap():
    with pytest.raises(mp.MemoryPolicyError):
        mp.cap_to_onchain(mp.CapPlan(0, True, "bug", 1))


def test_gate_job_rejects_budget_above_cap_and_names_incidents(client):
    address = addr(0xC0C0)
    _seed_provider(client, address, risk_level=2, incident_jobs=(1, 2), passed_budgets=(4_000_000,))
    view = mp.DecisionMemoryView(client)
    gate = mp.gate_job(view, address, budget=4_000_000, mode=NAIVE)
    assert gate.accept is False
    assert "cap" in gate.reason and "2 insiden" in gate.reason
    assert gate.depth == mp.DEPTH_FULL
    assert mp.gate_job(view, address, budget=250_000, mode=NAIVE).accept is True


def test_gate_job_refuses_raw_client(client):
    with pytest.raises(TypeError):
        mp.gate_job(client, addr(1), 1, NAIVE)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        mp.gate_job(mp.DecisionMemoryView(client), addr(1), "1", NAIVE)  # type: ignore[arg-type]


def test_unknown_provider_is_risk_zero_and_uncapped(client):
    profile = mp.DecisionMemoryView(client).provider(addr(0xD0D0))
    assert profile.risk_level == 0
    assert mp.derive_cap(profile).cap_usdc is mp.NO_CAP


# ----------------------------------------------------------------------
# Pemetaan tier §3 + jalur tulis
# ----------------------------------------------------------------------


def test_tier_mapping_roundtrip(client):
    body = {"criteria": [], "mode": mp.DEPTH_FULL}
    mp.set_active_job(client, 42, body)
    assert mp.get_active_job(client, 42) == body
    assert mp.get_active_job(client, 43) is None

    mp.set_rubric(client, "defi", {"kriteria": ["angka vs chain"]})
    assert mp.get_rubric(client, "defi") == {"kriteria": ["angka vs chain"]}

    mp.save_client_profile(client, addr(0xE0E0), {"sengketa_salah": 0})
    assert client.get_entity(mp.CATEGORY_CLIENT, addr(0xE0E0))

    assert isinstance(mp.write_journal(client, [{"action": "verdict", "job": 1}]), str)
    assert client.read_events(limit=10)

    client.set_entity(mp.CATEGORY_JOB, "42", {"final": True})
    assert mp.archive_job(client, 42)["original_id"]
    assert mp.archive_job(client, 999) is None


def test_record_job_outcome_updates_stats_and_risk_from_checks_only(client):
    address = addr(0xF0F0)
    mp.record_job_outcome(client, address, job_id=1, budget=5_000_000, passed=True)
    mp.record_job_outcome(client, address, job_id=2, budget=9_000_000, passed=False,
                          failed_checks=[DET_CHECK])
    profile = mp.DecisionMemoryView(client).provider(address)
    assert (profile.stats_jobs, profile.stats_pass, profile.stats_reject) == (2, 1, 1)
    assert profile.passed_budgets == (5_000_000,)
    assert profile.incident_jobs == (2,)
    assert profile.risk_level == 1

    with pytest.raises(mp.MemoryPolicyError):
        mp.record_job_outcome(client, address, 3, 1, passed=False, failed_checks=["llm_rubric"])


def test_store_provider_cap_persists_value(client):
    address = addr(0x0F0F)
    _seed_provider(client, address, risk_level=1, passed_budgets=(2_000_000,))
    cap = mp.derive_cap(mp.DecisionMemoryView(client).provider(address))
    mp.store_provider_cap(client, address, cap)
    assert mp.DecisionMemoryView(client).provider(address).cap_usdc == 1_000_000


def test_addresses_are_normalized_so_one_provider_is_one_entity(client):
    mixed = "0xAbCdEf0000000000000000000000000000000000"
    _seed_provider(client, mixed, risk_level=1, passed_budgets=(1_000_000,))
    mp.record_job_outcome(client, mixed.lower(), 1, 1_000_000, passed=True)
    assert len(client.list_entities(mp.CATEGORY_PROVIDER, limit=mp.LIST_LIMIT)) == 1


# ----------------------------------------------------------------------
# Isolasi karantina STRUKTURAL (bukan sampel) — CLAUDE.md + spec §3 aturan 1
# ----------------------------------------------------------------------


def test_decision_view_never_holds_a_full_memory_client(client):
    """Jalur keputusan hanya memegang `_GuardedReader`, bukan klien Sibyl.

    Inilah yang membuat batas §3 aturan 1 STRUKTURAL: metode jalur keputusan mana pun
    yang mencoba `list_entities("suspicion")` akan MELEMPAR di lapisan klien, sehingga
    "lupa memanggil penjaga" bukan lagi mode kegagalan yang mungkin.
    """
    view = mp.DecisionMemoryView(client)
    reader = view._DecisionMemoryView__reader
    assert isinstance(reader, mp._GuardedReader)
    assert not isinstance(reader, MemoryClient)


def test_guarded_reader_refuses_forbidden_reads_at_the_client_layer(client):
    reader = mp._GuardedReader(client)
    for kategori in (mp.CATEGORY_QUARANTINE, mp.CATEGORY_CLIENT, mp.CATEGORY_JOB, None):
        with pytest.raises(mp.ForbiddenReadError):
            reader.list_entities(kategori, status="pending", limit=10)
        with pytest.raises(mp.ForbiddenReadError):
            reader.get_entity(kategori, "0x0")
    for kunci in ("rubric:defi", "suspicion:x", "job:1"):
        with pytest.raises(mp.ForbiddenReadError):
            reader.get_reference(kunci)
    # Nama kategori yang disamarkan tidak menolong: penjaganya di lapisan klien.
    with pytest.raises(mp.ForbiddenReadError):
        reader.list_entities("".join(["sus", "picion"]), limit=10)
    # Metode lain sama sekali tidak tersedia dari jalur keputusan.
    for metode in ("get_state", "read_events", "search_entities", "search", "set_entity",
                   "write_event", "delete_entity", "archive_entity", "set_reference"):
        with pytest.raises(mp.ForbiddenReadError):
            getattr(reader, metode)
    # Yang diizinkan tetap jalan.
    mp.save_provider(client, mp.ProviderProfile(address=addr(0x7E7E), risk_level=1))
    assert reader.get_entity(mp.CATEGORY_PROVIDER, addr(0x7E7E))["body"]["risk_level"] == 1
    assert reader.list_entities(mp.CATEGORY_PROVIDER, limit=10)


def test_quarantine_isolation_survives_a_high_reject_count_provider(client):
    """Ruang uji diperluas ke cabang yang dipakai mutan reviewer (`stats_reject >= 4`)."""
    address = addr(0x8E8E)
    for job in range(6):
        mp.record_job_outcome(client, address, job, 1_000_000 + job, passed=False,
                              failed_checks=[DET_CHECK])
    _poison_quarantine(client, address, patterns=2, jobs=3)

    profile = mp.DecisionMemoryView(client).provider(address)
    assert profile.stats_reject >= 4
    assert profile.risk_level == mp.MAX_RISK_LEVEL
    cap = mp.derive_cap(profile)
    assert cap.cap_usdc == 250_000
    assert mp.gate_job(mp.DecisionMemoryView(client), address, 20_000_000, NAIVE).accept is False


# ----------------------------------------------------------------------
# CAS — tulisan berbasis snapshot usang
# ----------------------------------------------------------------------


def test_stale_write_is_refused(client):
    """Interleaving nyata: baca A → tulis B → tulis A. Tulisan A harus DITOLAK."""
    address = addr(0x9A9A)
    mp.record_job_outcome(client, address, 1, 1_000_000, passed=True)
    basi = mp._load_provider_for_write(client, address)  # snapshot A

    mp.record_job_outcome(client, address, 2, 2_000_000, passed=False, failed_checks=[DET_CHECK])

    from dataclasses import replace as _replace

    with pytest.raises(mp.StaleWriteError):
        mp._save_provider_cas(client, _replace(basi, cap_usdc=None), basi.version)

    profile = mp.DecisionMemoryView(client).provider(address)
    assert profile.risk_level == 1
    assert profile.incident_jobs == (2,)
    assert profile.recorded_jobs == (1, 2)
    assert mp.record_job_outcome(client, address, 2, 2_000_000, passed=False,
                                 failed_checks=[DET_CHECK]).recorded_jobs == (1, 2)


def test_version_increases_on_every_accepted_write(client):
    address = addr(0x9B9B)
    versi = []
    for job in range(3):
        versi.append(mp.record_job_outcome(client, address, job, 1_000, passed=True).version)
    assert versi == [1, 2, 3]


# ----------------------------------------------------------------------
# Kesalahan yang seragam — pemanggil 2.4a harus bisa masuk mode aman, bukan crash
# ----------------------------------------------------------------------


def test_corrupt_provider_body_raises_memory_error_not_raw_valueerror(client):
    address = addr(0xAB01)
    client.set_entity(mp.CATEGORY_PROVIDER, address, {"risk_level": "bukan angka"})
    with pytest.raises(mp.MemoryIntegrityError):
        mp.DecisionMemoryView(client).provider(address)
    with pytest.raises(mp.MemoryIntegrityError):
        mp.memory_root(client)
    client.set_entity(mp.CATEGORY_PROVIDER, address, {"version": "x"})
    with pytest.raises(mp.MemoryIntegrityError):
        mp.record_job_outcome(client, address, 1, 1, passed=True)


def test_corrupt_quarantine_entry_is_skipped_not_raised(client):
    """Entri karantina rusak tidak boleh MELEMPAR ke pemanggil; ia dilewati (fail-closed)."""
    address = addr(0xAB02)
    client.set_entity(
        mp.CATEGORY_QUARANTINE,
        f"{address}:pola-rusak",
        {"provider": address, "pattern": "pola-rusak",
         "evidence": [{"job": -5, "check": DET_CHECK}, {"job": "x", "check": DET_CHECK}]},
        status=mp.QUARANTINE_STATUS_PENDING,
    )
    assert mp.promote_suspicions(client, address) == []
    assert mp.DecisionMemoryView(client).provider(address).confirmed_patterns == ()


# ----------------------------------------------------------------------
# ADR-021 — plafon pertumbuhan + job yang didanai sendiri
# ----------------------------------------------------------------------


def test_derive_cap_selfFundedPassedJob_doesNotRaiseCap(client, capsys):
    """AC (k): rantai reviewer — 1 job LOLOS 100 USDC lalu satu insiden → cap tetap kecil."""
    provider = addr(0xC0FF)
    view = mp.DecisionMemoryView(client)

    mp.record_job_outcome(client, provider, 1, 100_000_000, passed=True)
    cap_sebelum = mp.derive_cap(view.provider(provider))
    mp.record_job_outcome(client, provider, 2, 1_000_000, passed=False, failed_checks=[DET_CHECK])
    cap_sesudah = mp.derive_cap(view.provider(provider))

    print(f"cap SEBELUM insiden={cap_sebelum.cap_usdc} cap SESUDAH insiden={cap_sesudah.cap_usdc}")
    assert cap_sebelum.cap_usdc is mp.NO_CAP  # risk 0
    assert cap_sesudah.cap_usdc <= mp.BASELINE_CAP_USDC == 1_000_000
    assert mp.gate_job(view, provider, 20_000_000, NAIVE).accept is False


def test_record_job_outcome_ignoresBudget_whenClientEqualsProvider(client):
    """AC (l): budget dibuang, `stats.jobs` tetap naik. ADR-021 keputusan 2."""
    provider = addr(0xC0FE)
    profile = mp.record_job_outcome(
        client, provider, 1, 100_000_000, passed=True,
        client_address=provider.upper().replace("0X", "0x"),
    )
    assert profile.passed_budgets == ()
    assert profile.stats_jobs == 1
    assert profile.stats_pass == 1
    # Client yang BERBEDA tetap dihitung seperti biasa.
    lain = mp.record_job_outcome(client, provider, 2, 900_000, passed=True,
                                 client_address=addr(0xDEAD))
    assert lain.passed_budgets == (900_000,)


def test_passedBudget_cappedAtBaseline():
    """AC (m): satu job LOLOS 500 USDC berkontribusi 1.000.000, bukan 500.000.000."""
    profile = mp.ProviderProfile(address=addr(0xC0FD), risk_level=1,
                                 passed_budgets=(500_000_000,))
    assert mp.derive_cap(profile).cap_usdc == mp.BASELINE_CAP_USDC == 1_000_000
    besar = mp.ProviderProfile(address=addr(0xC0FC), risk_level=2,
                               passed_budgets=(500_000_000, 900_000_000))
    assert mp.derive_cap(besar).cap_usdc == 250_000


def test_memory_is_one_way_it_can_only_tighten_the_cap():
    """Sifat satu arah ADR-021: riwayat baik tidak pernah MENAIKKAN cap."""
    rng = random.Random(7)
    for _ in range(200):
        budgets = tuple(rng.randrange(1, 10**12) for _ in range(rng.randrange(1, 8)))
        for risk in (1, 2):
            cap = mp.derive_cap(
                mp.ProviderProfile(address=addr(0xC0FB), risk_level=risk, passed_budgets=budgets)
            ).cap_usdc
            assert mp.MIN_CAP_USDC <= cap <= mp.BASELINE_CAP_USDC


def test_self_funded_filter_does_not_change_memory_root(client, tmp_path):
    """AC (o): filter ADR-021 ada di TITIK MASUK → preimage root tidak berubah."""
    lain = MemoryClient.local(str(tmp_path / "lain.db"))
    provider = addr(0xC0FA)
    mp.record_job_outcome(client, provider, 1, 5_000, passed=False, failed_checks=[DET_CHECK])
    mp.record_job_outcome(lain, provider, 1, 5_000, passed=False, failed_checks=[DET_CHECK],
                          client_address=addr(0xBEEF))
    assert mp.memory_root(client) == mp.memory_root(lain)
    body = client.get_entity(mp.CATEGORY_PROVIDER, provider)["body"]
    assert "client" not in json.dumps(body)


# ----------------------------------------------------------------------
# Gerbang root untuk jalur produksi (2.4a/2.4b tidak boleh menembusnya)
# ----------------------------------------------------------------------


def test_no_agent_module_publishes_a_memory_derived_root_yet():
    """ADR-020 keputusan 6: sampai 2.1r hijau, tidak ada modul agen yang mengumumkan root.

    Gerbangnya bukan sekadar konvensi: `memory_root_for_onchain()` melempar. Tes ini
    menjaga sisi lainnya — tidak ada modul selain `memory_policy` yang memanggil
    `memory_root(...)` langsung dan menyelundupkannya ke `post_verdict`.
    """
    import pathlib

    paket = pathlib.Path(mp.__file__).parent
    pelanggar = []
    for berkas in sorted(paket.glob("*.py")):
        if berkas.name == "memory_policy.py":
            continue
        isi = berkas.read_text()
        if "memory_root(" in isi and "memory_root_for_onchain(" not in isi:
            pelanggar.append(berkas.name)
    assert pelanggar == [], f"modul memakai root yang encodingnya belum beku: {pelanggar}"
