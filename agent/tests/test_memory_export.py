"""Tes `agent/memory_export.py` — task 2.1b (spec §3 baris 123-124, ADR-020 keputusan 6-7).

Yang dijaga di sini, dan kenapa masing-masing ada:
  (1) SATU pembacaan DB. File ekspor dan root berasal dari objek `MemorySnapshot` yang SAMA.
      Sibyl 0.7.0 tidak punya transaksi (api-facts §C), jadi membaca DB dua kali bisa
      menghasilkan root yang mengikat state yang TIDAK PERNAH ADA. Diuji dua arah: penghitung
      panggilan, DAN penulisan yang menyusup TEPAT sesudah snapshot diambil.
  (2) Alat audit tidak boleh menerima ekspor yang agen sendiri TOLAK — paritas
      `from_export_obj` vs `from_mapping` diuji dengan payload reviewer apa adanya.
  (3) Kunci objek ber-escape ditolak DI SUMBER (bukan hanya dekode ilegal), di Python DAN di
      Node; dan keluaran eksportir dijamin tidak pernah memuatnya.
  (4) Rantai lengkap: DB → file → root dihitung ulang dari file (Python + Node) → identik
      dengan `memory_root_hex()` langsung dari DB.

BATAS YANG DIAKUI, dicatat di kode supaya tidak hilang: AC 2.1b menuntut root ini identik
dengan argumen `MemoryRootUpdated` TERAKHIR di Sepolia. Perbandingan itu TIDAK bisa dibuat
hari ini dan itu disengaja — satu-satunya root yang pernah diumumkan on-chain adalah dua
konstanta palsu (ADR-011), dan ADR-020 keputusan 6 melarang root turunan-memori diumumkan
sebelum encodingnya beku (baru mendarat di 2.1r). Root turunan-memori yang PERTAMA baru
lahir di task 2.4/2.5. Tes di file ini membuktikan rantainya sejauh yang ada hari ini:
DB → file → dua bahasa. Tidak lebih, dan tidak berpura-pura lebih.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest
from sibyl_memory_client import MemoryClient

from agent import memory_export as me
from agent import memory_policy as mp

NODE_SCRIPT = pathlib.Path(mp.__file__).parent.parent / "tools" / "memory_root_check.mjs"


def addr(n: int) -> str:
    return f"0x{n:040x}"


@pytest.fixture
def client(tmp_path):
    return MemoryClient.local(str(tmp_path / "memory.db"))


def _seed(client) -> None:
    """Memori yang cukup kaya: provider, pola dipromosikan, pola YATIM, rubric, int > 2^53."""
    a, b = addr(0xA1), addr(0xB2)
    mp.save_provider(
        client,
        mp.ProviderProfile(address=a, risk_level=2, passed_budgets=(1_000_000, 2**200 + 1)),
    )
    mp.save_provider(client, mp.ProviderProfile(address=b, risk_level=0))
    for job in (1, 2):
        mp.record_suspicion(client, a, "angka-tidak-cocok", mp.Evidence(job, "chain"))
    mp.promote_suspicions(client, a)
    client.set_reference("pattern:yatim", {"catatan": "tidak dirujuk provider mana pun"})
    client.set_reference("rubric:defi", {"bobot": {"angka": 3}, "teks": "π dan 日本語"})


def _node(path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", str(NODE_SCRIPT), str(path)], capture_output=True, text=True, timeout=120
    )


requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="node tidak tersedia")


# ----------------------------------------------------------------------
# (4) rantai ekspor: DB → file → root, di dua bahasa
# ----------------------------------------------------------------------


def test_exported_file_reproduces_the_root_computed_straight_from_the_db(client, tmp_path, capsys):
    _seed(client)
    out = tmp_path / "keluar" / "mem.json"  # direktori induk sengaja BELUM ada
    hasil = me.export_memory(tmp_path / "memory.db", out)

    dari_db = mp.memory_root_hex(client)
    dari_file = me.root_from_file(out)
    print(f"root dari DB   : {dari_db}")
    print(f"root dari file : {dari_file}")
    assert hasil.root == dari_db == dari_file
    assert hasil.counts == {"providers": 2, "patterns": 2, "rubrics": 1}
    # Pattern YATIM ikut terekspor (ADR-020 keputusan 7) dan `suspicion` TIDAK.
    obj = json.loads(out.read_text(encoding="utf-8"))
    kunci_pola = {k for k, _ in obj["patterns"]}
    assert "pattern:yatim" in kunci_pola
    assert "suspicion" not in out.read_text(encoding="utf-8")


@requires_node
def test_node_recomputes_the_root_of_the_real_export_file(client, tmp_path, capsys):
    """AC 2.1b inti: file keluaran ALAT (bukan fixture) dibaca ulang di luar Python."""
    _seed(client)
    out = tmp_path / "mem.json"
    hasil = me.export_memory(tmp_path / "memory.db", out)
    proses = _node(out)
    assert proses.returncode == 0, proses.stderr
    baris = dict(
        (bagian[0].strip(), bagian[1].strip())
        for bagian in (b.split(":", 1) for b in proses.stdout.splitlines())
        if len(bagian) == 2
    )
    print(proses.stdout)
    assert baris["memory_root"] == hasil.root == mp.memory_root_hex(client)
    assert baris["encoding"] == mp.MEMORY_ROOT_ENCODING_VERSION


def test_export_is_byte_stable_across_runs(client, tmp_path):
    _seed(client)
    satu = me.export_memory(tmp_path / "memory.db", tmp_path / "a.json")
    dua = me.export_memory(tmp_path / "memory.db", tmp_path / "b.json")
    assert satu.text == dua.text
    assert satu.root == dua.root


def test_export_of_empty_memory_is_valid_and_differs_from_populated(client, tmp_path):
    kosong = me.export_memory(tmp_path / "memory.db", tmp_path / "kosong.json")
    _seed(client)
    isi = me.export_memory(tmp_path / "memory.db", tmp_path / "isi.json")
    assert kosong.root != isi.root
    assert me.root_from_file(tmp_path / "kosong.json") == kosong.root


def test_export_fails_closed_when_memory_is_inconsistent(client, tmp_path):
    """Memori rusak → alat BERHENTI, bukan menerbitkan root atas memori yang rusak."""
    mp.save_provider(
        client, mp.ProviderProfile(address=addr(0xC3), confirmed_patterns=("hantu",))
    )
    with pytest.raises(mp.MemoryIntegrityError):
        me.export_memory(tmp_path / "memory.db", tmp_path / "mem.json")
    assert not (tmp_path / "mem.json").exists()


# ----------------------------------------------------------------------
# (1) SATU pembacaan DB — file dan root dari objek snapshot yang SAMA
# ----------------------------------------------------------------------


class CountingClient:
    """Pembungkus yang MENGHITUNG setiap pembacaan (dan menolak tulisan)."""

    def __init__(self, inner: MemoryClient) -> None:
        self._inner = inner
        self.calls: list[str] = []

    @property
    def storage(self):
        """Diteruskan apa adanya — kunci single-instance (task 2.4a) membaca path DB
        dari `client.storage.db_path`. `storage` BUKAN pembacaan memori, jadi ia sengaja
        tidak dicatat di `calls`."""
        return self._inner.storage

    def get_entity(self, category, name):
        self.calls.append("get_entity")
        return self._inner.get_entity(category, name)

    def list_entities(self, category=None, *, status=None, limit=100):
        self.calls.append("list_entities")
        return self._inner.list_entities(category, status=status, limit=limit)

    def search(self, query, *, limit=20, prefix=False, tiers=None):
        self.calls.append("search")
        return self._inner.search(query, limit=limit, prefix=prefix, tiers=tiers)

    def get_reference(self, key):
        self.calls.append("get_reference")
        return self._inner.get_reference(key)


def test_export_reads_the_database_exactly_once(client, tmp_path, monkeypatch, capsys):
    """Membaca DB dua kali = root bisa mengikat state yang tidak pernah ada (tanpa transaksi)."""
    _seed(client)
    spy = CountingClient(client)
    monkeypatch.setattr(me, "open_memory", lambda db: spy)

    hasil = me.export_memory(tmp_path / "memory.db", tmp_path / "mem.json")

    print(f"panggilan baca: {spy.calls}")
    assert spy.calls.count("list_entities") == 1
    assert spy.calls.count("search") == 2  # satu untuk `pattern:`, satu untuk `rubric:`
    assert spy.calls.count("get_reference") == len(hasil.snapshot.patterns) + len(
        hasil.snapshot.rubrics
    )
    # Sesudah snapshot terbentuk, tidak ada pembacaan tambahan apa pun.
    jumlah_sesudah_snapshot = len(spy.calls)
    me.export_snapshot(hasil.snapshot, tmp_path / "lagi.json", tmp_path / "memory.db")
    assert len(spy.calls) == jumlah_sesudah_snapshot


def test_export_binds_one_state_even_when_memory_is_written_mid_export(
    client, tmp_path, monkeypatch
):
    """Sisi MUTASI: penulisan menyusup TEPAT sesudah snapshot diambil.

    Ini bukan skenario dua-proses: promosi karantina (`memory_policy` BAGIAN 3) menulis
    provider + reference dari proses yang SAMA. Kalau eksportir membaca ulang DB untuk
    menulis file, file akan memuat state SESUDAH dan root state SEBELUM — dan keduanya
    tidak pernah ada bersamaan. Yang WAJIB terjadi: file dan root sepakat, keduanya
    mengikat state SEBELUM, dan root itu berhenti cocok dengan DB (yang benar: memori
    berubah, jadi root berikutnya memang harus berbeda).
    """
    _seed(client)
    asli = me.load_snapshot

    def load_lalu_tulis(c):
        snapshot = asli(c)
        client.set_reference("pattern:disusupkan", {"x": 1})
        mp.save_provider(client, mp.ProviderProfile(address=addr(0xD4), risk_level=1))
        return snapshot

    monkeypatch.setattr(me, "load_snapshot", load_lalu_tulis)
    out = tmp_path / "mem.json"
    hasil = me.export_memory(tmp_path / "memory.db", out)

    isi = out.read_text(encoding="utf-8")
    assert "pattern:disusupkan" not in isi
    assert addr(0xD4) not in isi
    assert me.root_from_file(out) == hasil.root
    assert hasil.root != mp.memory_root_hex(client)  # DB sudah berubah — dan itu terlihat


# ----------------------------------------------------------------------
# (2) paritas validasi: alat audit tidak boleh menerima yang agen tolak
# ----------------------------------------------------------------------

REVIEWER_PAYLOAD = {
    "version": mp.MEMORY_ROOT_ENCODING_VERSION,
    "providers": [["hello-i-am-not-an-address", {}]],
    "patterns": [["bukan-pattern-prefix", "{}"]],
    "rubrics": [],
}


def test_export_obj_refuses_the_exact_payload_the_reviewer_smuggled_through():
    """Sebelum 2.1b payload ini DITERIMA `from_export_obj` padahal `from_mapping` menolaknya.

    Catatan review menyebut root `0x308c810e…` untuk payload ini; angka itu TIDAK bisa
    direproduksi dari payload yang tertulis, dan reviewer mengonfirmasinya. Yang benar-benar
    dihitung (lewat konstruktor langsung, tanpa validasi) adalah `0x1863baf2…` untuk body
    pattern `"{}"` — bentuk yang dipakai di sini — dan `0xed577ed9…` untuk body `{}`. Yang
    mengikat adalah faktanya (dulu diterima, kini ditolak), bukan digit yang tidak diverifikasi.
    """
    with pytest.raises((ValueError, mp.MemoryIntegrityError)):
        mp.MemorySnapshot.from_export_obj(REVIEWER_PAYLOAD)
    with pytest.raises((ValueError, mp.MemoryIntegrityError)):
        me.snapshot_from_text(json.dumps(REVIEWER_PAYLOAD))


@pytest.mark.parametrize(
    "providers, patterns, rubrics",
    [
        ({"hello-i-am-not-an-address": {}}, {}, {}),  # nama bukan alamat
        ({"0X" + "A" * 40: {}}, {}, {}),  # alamat tidak kanonik
        ({}, {"bukan-pattern-prefix": "{}"}, {}),  # awalan kunci pattern salah
        ({}, {"rubric:salah-seksi": "{}"}, {}),  # kunci rubric di seksi pattern
        ({}, {}, {"pattern:salah-seksi": "{}"}),  # dan sebaliknya
        ({}, {}, {"tanpa-awalan": "{}"}),
    ],
)
def test_both_entry_points_refuse_the_same_inputs(providers, patterns, rubrics):
    """Paritas DUA ARAH: apa pun yang ditolak `from_mapping` juga ditolak `from_export_obj`,
    dengan tipe galat yang SAMA — karena keduanya memang kode yang sama, bukan salinan."""
    with pytest.raises(Exception) as lewat_mapping:  # noqa: B017 - tipenya yang dibandingkan
        mp.MemorySnapshot.from_mapping(providers, patterns, rubrics)
    ekspor = {
        "version": mp.MEMORY_ROOT_ENCODING_VERSION,
        "providers": [[k, v] for k, v in providers.items()],
        "patterns": [[k, v] for k, v in patterns.items()],
        "rubrics": [[k, v] for k, v in rubrics.items()],
    }
    with pytest.raises(Exception) as lewat_ekspor:  # noqa: B017
        mp.MemorySnapshot.from_export_obj(ekspor)
    assert type(lewat_mapping.value) is type(lewat_ekspor.value)


# ----------------------------------------------------------------------
# (2b) PARITAS LINTAS BAHASA — setiap payload di bawah WAJIB ditolak Python DAN Node
# ----------------------------------------------------------------------
# Sampai review 2.1b, seluruh penjaga hanya ada di Python: Node menghitung root untuk
# kedelapan payload ini. Yang paling tajam adalah `pasangan-3-elemen`: vektor beku yang
# disisipi elemen ketiga berisi profil palsu tetap mencetak root JUJUR `0x0af7c372…`, jadi
# alat audit PUBLIK kita mengikat root on-chain ke file yang isinya bukan itu.

# Surrogate yatim TIDAK boleh muncul sebagai literal di sumber tes: pytest meng-compile ulang
# file ini dan `compile()` menolak sumber yang tidak bisa di-encode UTF-8.
SUR_HI = chr(0xD800)
SUR_LO = chr(0xDFFF)

VEKTOR_BEKU = pathlib.Path(mp.__file__).parent.parent / "tests" / "fixtures" / "memory_root_vector.json"


def _vektor_beku_disisipi():
    obj = json.loads(VEKTOR_BEKU.read_text(encoding="utf-8"))
    obj["providers"][0].append(
        {
            "risk_level": 0,
            "cap_usdc": None,
            "NOTE": "body yang DITAMPILKAN ke manusia, tidak ikut ter-hash",
        }
    )
    obj["catatan_untuk_juri"] = "field top-level asing"
    return obj


def _ekspor(providers=(), patterns=(), rubrics=(), **tambahan_field):
    obj = {
        "version": mp.MEMORY_ROOT_ENCODING_VERSION,
        "providers": list(providers),
        "patterns": list(patterns),
        "rubrics": list(rubrics),
    }
    obj.update(tambahan_field)
    return obj


PAYLOAD_TOLAK = {
    "nama-bukan-alamat": _ekspor(providers=[["hello-i-am-not-an-address", {}]]),
    "awalan-pattern-salah": _ekspor(patterns=[["bukan-pattern-prefix", "{}"]]),
    "alamat-tidak-kanonik": _ekspor(providers=[["0X" + "AA" * 20, {}]]),
    "penanda-integer-bercampur": _ekspor(
        providers=[[addr(1), {"b": {"$u": "5", "other": "x"}}]]
    ),
    "desimal-nol-di-depan": _ekspor(providers=[[addr(1), {"b": {"$u": "007"}}]]),
    "minus-nol": _ekspor(providers=[[addr(1), {"b": {"$u": "-0"}}]]),
    "seksi-null": {
        "version": mp.MEMORY_ROOT_ENCODING_VERSION,
        "providers": None,
        "patterns": [],
        "rubrics": [],
    },
    "pasangan-3-elemen": _vektor_beku_disisipi(),
    # Kunci seksi adalah NILAI di dalam array, jadi ia lolos pemindai nama-properti. Python
    # `str.encode("utf-8")` melempar, Node `Buffer.from(s,"utf8")` menukarnya dengan U+FFFD
    # dan tetap menghitung — sehingga `\ud800`, `\udfff`, dan `\ufffd` yang SAH runtuh jadi
    # satu root di sisi Node. Dua baris berikut adalah kedua sisi tabrakan itu.
    "kunci-seksi-surrogate": _ekspor(patterns=[[f"pattern:{SUR_HI}", "{}"]]),
    "tabrakan-surrogate-fffd": _ekspor(patterns=[[f"pattern:{SUR_LO}", "{}"]]),
    "nilai-body-surrogate": _ekspor(providers=[[addr(1), {"b": SUR_HI}]]),
    # `DECIMAL_RE` identik di kedua sisi, tetapi batas sesungguhnya ada di `int()`:
    # CPython melempar di 4300 digit, JS hanya mencocokkan regex dan menghitung.
    "desimal-terlalu-panjang": _ekspor(providers=[[addr(1), {"b": {"$u": "1" + "0" * 5000}}]]),
    "desimal-di-atas-uint256": _ekspor(providers=[[addr(1), {"b": {"$u": str(2**256)}}]]),
    "field-top-level-asing": _ekspor(catatan="tidak ikut ter-hash"),
}


@pytest.mark.parametrize("nama", sorted(PAYLOAD_TOLAK))
def test_python_refuses_every_payload_in_the_parity_table(nama):
    with pytest.raises(Exception) as galat:  # noqa: B017 - yang penting: TIDAK menghitung root
        me.root_from_text(json.dumps(PAYLOAD_TOLAK[nama]))
    assert not isinstance(galat.value, AssertionError)


@requires_node
@pytest.mark.parametrize("nama", sorted(PAYLOAD_TOLAK))
def test_node_refuses_every_payload_in_the_parity_table(nama, tmp_path):
    berkas = tmp_path / f"{nama}.json"
    berkas.write_text(json.dumps(PAYLOAD_TOLAK[nama]), encoding="utf-8")
    proses = _node(berkas)
    assert proses.returncode != 0, f"Node MENGHITUNG root untuk {nama}:\n{proses.stdout}"
    assert "memory_root" not in proses.stdout


@requires_node
def test_the_doctored_frozen_vector_no_longer_prints_the_honest_root(tmp_path, capsys):
    """Skenario reviewer apa adanya: file palsu tidak boleh meminjam root yang jujur."""
    jujur = _node(VEKTOR_BEKU)
    assert jujur.returncode == 0 and "0x0af7c372" in jujur.stdout

    palsu = tmp_path / "doctored.json"
    palsu.write_text(json.dumps(_vektor_beku_disisipi()), encoding="utf-8")
    proses = _node(palsu)
    print(f"vektor beku : {jujur.stdout.strip().splitlines()[-1]}")
    print(f"file disisipi: exit={proses.returncode} {proses.stderr.strip().splitlines()[0]}")
    assert proses.returncode != 0
    assert "0af7c372" not in proses.stdout
    with pytest.raises(mp.MemoryIntegrityError):
        me.root_from_text(palsu.read_text(encoding="utf-8"))



@requires_node
def test_lone_surrogate_keys_cannot_borrow_the_root_of_a_legal_key(tmp_path, capsys):
    """TIGA kunci berbeda TIDAK boleh menghasilkan satu root (janji bingkai panjang-berprefiks).

    Skenarionya konkret: agen mem-post root untuk memori berkunci `pattern:\ufffd` (SAH),
    lalu penyerang menerbitkan file berkunci `pattern:\\ud800` yang isinya BUKAN memori itu.
    Sebelum perbaikan ini auditor Node menjawab "cocok" sementara auditor Python mati.
    """
    hasil = {}
    for label, kunci in (
        ("d800", f"pattern:{SUR_HI}"),
        ("dfff", f"pattern:{SUR_LO}"),
        ("fffd", "pattern:" + chr(0xFFFD)),
    ):
        berkas = tmp_path / f"{label}.json"
        berkas.write_text(json.dumps(_ekspor(patterns=[[kunci, "{}"]])), encoding="utf-8")
        proses = _node(berkas)
        try:
            py = me.root_from_file(berkas)
        except mp.MemoryIntegrityError:
            py = "TOLAK"
        node_root = "TOLAK" if proses.returncode else proses.stdout.strip().splitlines()[-1][-66:]
        hasil[label] = (py, node_root)
        print(f"{label}: python={py[:14]} node={node_root[:14]}")

    assert hasil["d800"] == ("TOLAK", "TOLAK")
    assert hasil["dfff"] == ("TOLAK", "TOLAK")
    # Kunci U+FFFD adalah kunci yang SAH: ia tetap dihitung, dan dihitung SAMA di dua bahasa.
    py_fffd, node_fffd = hasil["fffd"]
    assert py_fffd != "TOLAK" and py_fffd == node_fffd


@requires_node
def test_decimal_length_is_bounded_on_both_sides_not_by_cpython_int_limit(tmp_path, capsys):
    """Batas 78 digit (uint256) ditegakkan EKSPLISIT, di kedua bahasa.

    Tanpa itu paritasnya bergantung pada `sys.int_max_str_digits` CPython — batas yang tidak
    dimiliki JS sama sekali, sehingga file yang sama membuat satu sisi mati dan sisi lain
    mencetak root.
    """
    panjang = tmp_path / "panjang.json"
    panjang.write_text(
        json.dumps(PAYLOAD_TOLAK["desimal-terlalu-panjang"]), encoding="utf-8"
    )
    proses = _node(panjang)
    print(f"5001 digit : node exit={proses.returncode} | {proses.stderr.strip().splitlines()[0][:70]}")
    assert proses.returncode != 0
    with pytest.raises(mp.MemoryIntegrityError, match="78"):
        me.root_from_file(panjang)

    # Kontrol: uint256 MAKSIMUM (78 digit) tetap dihitung, dan dihitung sama.
    batas = tmp_path / "batas.json"
    batas.write_text(
        json.dumps(_ekspor(providers=[[addr(1), {"b": {"$u": str(mp.MAX_UINT256)}}]])),
        encoding="utf-8",
    )
    node_batas = _node(batas)
    py_batas = me.root_from_file(batas)
    print(f"uint256 max: python={py_batas}")
    assert node_batas.returncode == 0 and py_batas in node_batas.stdout


def test_oversized_integer_in_the_database_fails_closed_instead_of_exporting(client, tmp_path):
    """Sisi TULIS: angka di luar uint256 tidak bisa menjadi file ekspor sama sekali."""
    client.set_entity(mp.CATEGORY_PROVIDER, addr(0xF6), {"b": 10**79})
    with pytest.raises(mp.MemoryIntegrityError, match="78"):
        me.export_memory(tmp_path / "memory.db", tmp_path / "mem.json")
    assert not (tmp_path / "mem.json").exists()


@requires_node
def test_illegal_utf8_is_refused_by_both_instead_of_silently_becoming_fffd(tmp_path):
    """Node `toString('utf8')` menukar byte rusak dengan U+FFFD tanpa keluhan; Python MATI.
    Dua perilaku atas file yang sama = alat audit yang tidak bisa dipakai berdebat."""
    berkas = tmp_path / "rusak.json"
    berkas.write_bytes(json.dumps(_ekspor()).encode("utf-8").replace(b'"version"', b'"versi\xffn"'))
    assert _node(berkas).returncode != 0
    with pytest.raises(me.MemoryExportError, match="UTF-8"):
        me.root_from_file(berkas)
    assert me.main(["--check", str(berkas)]) == me.EXIT_ERROR


@requires_node
def test_minus_zero_can_no_longer_produce_two_roots_from_one_file(tmp_path, capsys):
    """SATU FILE, DUA ROOT — kalimat yang dijual di tiga tempat dalam repo ini.

    `-0` lolos regex desimal lama, `int("-0") == 0`, dan Python meng-encode ulang `"0"`
    sementara Node menghash `"-0"` apa adanya: dua root, dua-duanya exit 0. Sekarang KEDUANYA
    menolak. Bentuk kanoniknya (`"0"`) tetap dihitung, dan dihitung SAMA.
    """
    minus = tmp_path / "minus-nol.json"
    minus.write_text(json.dumps(PAYLOAD_TOLAK["minus-nol"]), encoding="utf-8")
    node_minus = _node(minus)
    print(f"minus-nol  : node exit={node_minus.returncode}")
    assert node_minus.returncode != 0
    with pytest.raises(mp.MemoryIntegrityError, match="KANONIK"):
        me.root_from_file(minus)

    nol = tmp_path / "nol.json"
    nol.write_text(
        json.dumps(_ekspor(providers=[[addr(1), {"b": {"$u": "0"}}]])), encoding="utf-8"
    )
    node_nol = _node(nol)
    py_nol = me.root_from_file(nol)
    print(f"nol kanonik: python={py_nol}")
    print(f"nol kanonik: {node_nol.stdout.strip().splitlines()[-1]}")
    assert node_nol.returncode == 0
    assert py_nol in node_nol.stdout


def test_valid_export_still_passes_so_the_guards_are_not_merely_strict(client, tmp_path):
    """Kontrol: penjaga di atas tidak menolak ekspor yang SAH (termasuk `rubric:pattern:trap`,
    kunci yang sengaja menyerempet awalan seksi lain — lihat api-facts §C.1 jebakan 1)."""
    _seed(client)
    client.set_reference("rubric:pattern:trap", {"x": "1"})
    hasil = me.export_memory(tmp_path / "memory.db", tmp_path / "mem.json")
    assert "rubric:pattern:trap" in hasil.text
    assert me.root_from_file(tmp_path / "mem.json") == hasil.root


# ----------------------------------------------------------------------
# (3) kunci ber-escape ditolak DI SUMBER, bukan hanya dekode ilegal
# ----------------------------------------------------------------------

# Kunci yang MENDEKODE menjadi `kB` — legal di kedua sisi sesudah dekode. Justru itu
# masalahnya: V8 mengintern nama properti ber-backslash lintas panggilan `JSON.parse` dalam
# satu isolate, jadi dokumen berikutnya bisa membaca nama hasil intern dokumen sebelumnya.
ESCAPED_BUT_LEGAL = (
    '{"version":"'
    + mp.MEMORY_ROOT_ENCODING_VERSION
    + '","providers":[["'
    + addr(1)
    + '",{"k\\u0042":"1"}]],"patterns":[],"rubrics":[]}'
)


def test_source_level_escaped_key_is_refused_even_though_it_decodes_to_a_legal_key():
    assert json.loads(ESCAPED_BUT_LEGAL)["providers"][0][1] == {"kB": "1"}  # dekode SAH
    with pytest.raises(mp.MemoryIntegrityError, match="escape"):
        me.snapshot_from_text(ESCAPED_BUT_LEGAL)
    # Kontrol: bentuk TANPA escape dari isi yang sama diterima.
    polos = ESCAPED_BUT_LEGAL.replace("k\\u0042", "kB")
    assert me.root_from_text(polos).startswith("0x")


@requires_node
def test_node_also_refuses_the_source_level_escaped_key(tmp_path):
    jahat = tmp_path / "escaped-source.json"
    jahat.write_text(ESCAPED_BUT_LEGAL, encoding="utf-8")
    proses = _node(jahat)
    assert proses.returncode != 0, proses.stdout
    assert "butuh escape" in proses.stderr
    polos = tmp_path / "polos.json"
    polos.write_text(ESCAPED_BUT_LEGAL.replace("k\\u0042", "kB"), encoding="utf-8")
    assert _node(polos).returncode == 0


def test_escaped_object_key_scanner_ignores_string_values():
    """Nilai string BOLEH ber-escape (ia tidak pernah menjadi nama properti); hanya nama yang
    dibatasi. Tanpa pembedaan ini penjaga akan menolak seluruh vektor beku."""
    teks = json.dumps({"a": "kutip \" dan backslash \\ dan π", "b": {"c": "1"}})
    assert me.escaped_object_keys(teks) == []
    assert me.escaped_object_keys('{"a\\n":1}') == ['"a\\n"']
    assert me.escaped_object_keys('{"π":1}') == ['"π"']


def test_exporter_output_never_contains_an_escaped_object_key(client, tmp_path):
    """Kewajiban EKSPORTIR (bukan sekadar kewajiban pembaca): keluarannya diperiksa."""
    _seed(client)
    client.set_reference("pattern:nilai-aneh", {"teks": 'kutip " backslash \\ kontrol \x01 🎯'})
    hasil = me.export_memory(tmp_path / "memory.db", tmp_path / "mem.json")
    assert me.escaped_object_keys(hasil.text) == []
    assert '\\"' in hasil.text and "\\\\" in hasil.text  # escape memang ADA, di NILAI
    assert me.root_from_file(tmp_path / "mem.json") == hasil.root


def test_body_key_that_needs_escaping_can_never_be_exported(client, tmp_path):
    """Sisi hulu: kunci body yang butuh escape ditolak sebelum sempat menjadi file."""
    client.set_entity(mp.CATEGORY_PROVIDER, addr(0xE5), {"k\n": "1"})
    with pytest.raises(mp.MemoryIntegrityError):
        me.export_memory(tmp_path / "memory.db", tmp_path / "mem.json")


@requires_node
def test_frozen_vector_still_passes_both_guards():
    """Vektor beku 2.1r tidak boleh menjadi korban penjaga baru — rootnya WAJIB tetap sama."""
    fixture = pathlib.Path(mp.__file__).parent.parent / "tests" / "fixtures" / "memory_root_vector.json"
    assert me.root_from_file(fixture) == mp.memory_root_hex(
        mp.MemorySnapshot.from_export_obj(json.loads(fixture.read_text(encoding="utf-8")))
    )
    assert _node(fixture).returncode == 0


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def test_cli_prints_the_root_and_writes_the_file(client, tmp_path, capsys):
    _seed(client)
    out = tmp_path / "keluar" / "mem.json"
    kode = me.main(["--db", str(tmp_path / "memory.db"), "--out", str(out)])
    keluaran = capsys.readouterr().out
    assert kode == 0
    assert mp.memory_root_hex(client) in keluaran
    assert out.is_file()


def test_cli_check_recomputes_from_an_existing_file(client, tmp_path, capsys):
    _seed(client)
    out = tmp_path / "mem.json"
    hasil = me.export_memory(tmp_path / "memory.db", out)
    assert me.main(["--check", str(out)]) == 0
    assert hasil.root in capsys.readouterr().out


def test_cli_refuses_a_missing_database_with_a_clear_message(tmp_path, capsys):
    """`data/` ter-gitignore dan sering belum ada. `MemoryClient.local` akan MEMBUAT DB baru
    di path itu — dan ekspor memori kosong punya root yang sah, persis seperti memori yang
    DIHAPUS. Karena itu alat ini berhenti, dan tidak meninggalkan file apa pun."""
    hilang = tmp_path / "data" / "memory.db"
    kode = me.main(["--db", str(hilang), "--out", str(tmp_path / "mem.json")])
    galat = capsys.readouterr().err
    assert kode == me.EXIT_ERROR
    assert "tidak ditemukan" in galat and str(hilang) in galat
    assert not hilang.exists()
    assert not (tmp_path / "mem.json").exists()


def test_cli_refuses_a_directory_as_database(tmp_path, capsys):
    kode = me.main(["--db", str(tmp_path), "--out", str(tmp_path / "mem.json")])
    assert kode == me.EXIT_ERROR
    assert "direktori" in capsys.readouterr().err


def test_cli_refuses_check_combined_with_export(tmp_path, capsys):
    kode = me.main(["--check", str(tmp_path / "x.json"), "--db", str(tmp_path / "memory.db")])
    assert kode == me.EXIT_ERROR
    assert "tidak dapat digabung" in capsys.readouterr().err


def test_cli_without_db_explains_itself(capsys):
    assert me.main([]) == me.EXIT_ERROR
    assert "--db wajib" in capsys.readouterr().err


def test_cli_works_on_any_path_not_only_data_memory_db(client, tmp_path):
    """AC menyebut `./data/memory.db`, tapi alat ini tidak boleh mengunci path apa pun."""
    _seed(client)
    aneh = tmp_path / "sub dir" / "nama.aneh.db"
    aneh.parent.mkdir()
    # SQLite WAL: memori adalah TIGA file (`memory.db`, `-wal`, `-shm`) — menyalin satu file
    # saja memberi memori yang lebih tua, dan rootnya berbeda. Fakta yang sama yang membuat
    # TASKS 2.4a/3.3b menuntut penghapusan menyapu ketiganya.
    for sumber in sorted(tmp_path.glob("memory.db*")):
        shutil.copy(sumber, aneh.parent / sumber.name.replace("memory.db", "nama.aneh.db"))
    hasil = me.export_memory(aneh, tmp_path / "lain" / "keluaran.json")
    assert hasil.root == mp.memory_root_hex(client)
