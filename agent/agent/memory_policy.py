"""Kebijakan memori evaluator — skema `docs/spec.md` §3 + `derive_cap` + fail-closed.

Modul ini adalah SATU-SATUNYA tempat kode agen menyentuh Sibyl Memory. Ia dibagi tegas
menjadi tiga bagian, dan pemisahan itu bukan gaya penulisan melainkan kontrol keamanan:

  BAGIAN 1 — pemetaan tier §3 (I/O memori mentah).
  BAGIAN 2 — JALUR KEPUTUSAN. Satu-satunya pintu baca adalah `DecisionMemoryView`, yang
             HANYA mengizinkan entity `provider` dan reference berawalan `pattern:`/`rubric:`
             — himpunan yang SAMA PERSIS dengan yang dijangkar `memory_root`
             (ADR-020 keputusan 7).
             Setiap fungsi di jalur ini ditandai `@decision_path` dan dijaga dua tes:
             tes SUMBER (kata terlarang tidak boleh muncul) dan tes PROPERTI runtime
             (keputusan pada DB dengan-vs-tanpa karantina harus identik untuk ratusan
             masukan acak, termasuk paritas budget ganjil/genap).
  BAGIAN 3 — jalur promosi karantina. Bagian INI memang membaca & menulis entity karantina;
             itu sah (spec §3 aturan 2) selama hasilnya hanya masuk ke jalur keputusan
             lewat `provider.confirmed_patterns` + `reference:pattern`.

Acuan:
  - docs/spec.md §3 (tabel tier, aturan 1-6, definisi jangkar `memory_root` baris 123).
  - docs/api-facts.md §C — signature `sibyl-memory-client==0.7.0` APA ADANYA.
    Yang mengikat di sini: `set_entity(category, name, body, *, status)` (BUKAN `kind`),
    `get_entity` MELEMPAR `NotFoundError`, `get_state`/`get_reference` mengembalikan
    pembungkus/None, `set_reference` menyimpan dict sebagai STRING JSON, `write_event`
    seluruhnya keyword-only, `list_entities` default `limit=100` (diam-diam memotong).
  - docs/api-facts.md §C.1 — enumerasi reference lewat `search(prefix=True, tiers=("reference",))`
    beserta TIGA jebakannya (superset lintas prefiks & body, urutan bm25 bukan urutan kunci,
    pemotongan senyap). Ketiganya ditangani di `_reference_keys()`.
  - docs/decisions.md ADR-001 (cap 0 di kontrak = TANPA BATAS), ADR-002 (karantina =
    entity, bukan tier), ADR-007 + amandemennya (fail-closed), ADR-011 (root yang pernah
    diumumkan), ADR-020 keputusan 6-7 (encoding & cakupan root), ADR-021 (plafon cap),
    ADR-023 (pemicu mode aman bukan lagi perbandingan sepasang root) + ADR-024 (pemicunya
    adalah memori lokal yang TIDAK TERBACA / HILANG; aturan "nol job outcome" dicabut).

Modul ini MURNI lokal: tidak ada jaringan, tidak ada chain, tidak ada LLM.

BATAS YANG DIAKUI — PENULIS `memory.db` (jangan dibaca lebih ringan dari ini):
  1) KETERSEDIAAN. Modul ini fail-closed dan TIDAK punya jalur pemulihan sendiri. Bila
     `list_entities`/`search` menyentuh batasnya, bila nama entity provider bukan alamat,
     bila body sebuah entity rusak, atau bila `reference:pattern` yang dirujuk provider
     hilang, maka `memory_root()` MELEMPAR — dan terus melempar sampai isi memori
     diperbaiki dari luar. Konsekuensinya: mode aman (task 2.4a) — tidak ada
     `postVerdict`/`finalize`/`setProviderCap`, job MENGGANTUNG sampai `expiredAt`, lalu
     siapa pun boleh `claimRefund` dan client menerima refund penuh.
  2) CAP BISA DILONGGARKAN SAMPAI TANPA BATAS. Ini yang lebih tajam dan sempat kurang
     dinyatakan: penulis `memory.db` tidak hanya bisa mematikan agen, ia bisa MENIMPA body
     provider menjadi `risk_level: 0` tanpa `cap_usdc`, sehingga `derive_cap` mengembalikan
     `NO_CAP` → `cap_to_onchain` = 0 → di kontrak berarti TANPA BATAS (ADR-001). Monoton
     tidak-naik tidak menolong: jangkarnya adalah `cap_usdc` yang tersimpan di body yang
     sama, dan penyerang menghapusnya bersamaan. Ia juga bisa menghapus `incident_jobs`,
     `confirmed_patterns`, dan seluruh entity provider sekaligus.
  3) PENAWARNYA TERBATAS, dan sejak ADR-023 batasnya lebih sempit daripada yang pernah
     ditulis di sini. `memory_root` (encodingnya beku sejak 2.1r) tetap MENGIKAT seluruh
     himpunan yang boleh dibaca, sehingga setiap suntingan di atas mengubah root yang
     diumumkan `postVerdict` dan auditor bisa membuktikannya SESUDAHNYA. Yang TIDAK lagi
     terjadi: root lokal DIBANDINGKAN dengan `lastMemoryRoot()` sebelum bertransaksi.
     Perbandingan itu dicabut ADR-023 karena ia mengunci agen ke mode aman permanen (spec §5
     menulis memori SESUDAH `postVerdict`, jadi root lokal selalu satu langkah di depan).
     Yang tersisa sebagai pemicu otomatis hanyalah KEADAAN FILE memori: hilang di hadapan
     vault yang sudah pernah mengumumkan root, tidak bisa dibaca, atau terkunci instans lain
     → mode AMAN. `memory.db` yang DIGANTI DB lain — kosong maupun terisi — TIDAK terdeteksi
     hari ini; itu kehilangan yang diterima sadar (ADR-024 konsekuensi) dan wajib disebut di
     README §Batasan.
  Jadi pihak yang bisa menulis `memory.db` bisa mematikan ketersediaan evaluator dan bisa
  melonggarkan cap; ia TIDAK bisa mencuri dana dan TIDAK bisa memaksa verdict lolos, karena
  verdict berasal dari cek deterministik (task 2.3), bukan dari memori. Itu pertukaran yang
  dipilih sadar (ADR-020 keputusan 8, ADR-023), bukan kelalaian.

UTANG YANG DIAKUI (jangan dibaca seolah sudah selesai):
  - Encoding preimage `memory_root` sudah DIBEKUKAN (ADR-020 keputusan 6, task 2.1r):
    body mentah, integer sebagai string desimal, kunci & body dibingkai panjang-berprefiks,
    label versi ikut ter-hash. 2.1b/2.4b memakai fungsi INI, bukan salinan. Yang masih utang:
    ekspor `agent/memory_export.py` (2.1b) belum ada, jadi bukti lintas-bahasa hari ini
    berjalan di atas fixture JSON yang ditulis tangan dari `to_canonical_obj()`, bukan di
    atas keluaran alat ekspor yang sesungguhnya.
  - Kesamaan "dijangkar == dibaca" (ADR-020 keputusan 7) ditegakkan dengan MENOLAK nama
    entity provider yang tidak kanonik, bukan dengan menerimanya lalu menjelaskannya. Itu
    berarti satu entity bernama aneh MEMATIKAN perhitungan root sampai ia dibetulkan dari
    luar — konsekuensi ketersediaan yang sama dengan butir 1 di atas, dipilih sadar karena
    alternatifnya (menjangkar sesuatu yang tidak pernah dibaca) adalah kebohongan senyap.
  - Idempotensi tulisan provider dijaga CAS versi, dan jendela cek-lalu-tulisnya TIDAK BISA
    diatomkan lewat API publik: `Storage.transaction()` ADA dan atomik, tetapi metode TULIS
    SDK membuka transaksinya sendiri sehingga tidak boleh bersarang di dalamnya
    (api-facts §C.2). Sejak task 2.4a jendela itu ditutup dari luar oleh
    KUNCI SINGLE-INSTANCE (`agent/memory_lock.py`): setiap baca-hitung dan setiap tulis
    memegang `flock` eksklusif atas `<memory.db>.lock`, dan instans kedua BERHENTI
    (fail-closed) alih-alih menimpa. Yang TIDAK ditutup: kunci itu KOOPERATIF — proses yang
    membuka `memory.db` dengan `sqlite3` mentah, editor, atau `rm` tidak terhalang.
  - Cap BUKAN deteksi (ADR-021 keputusan 4). Ia hanya membatasi UKURAN kerugian per job;
    yang mendeteksi deliverable curang adalah cek deterministik (task 2.3), dan yang
    menghentikan agen saat memori tidak dipercaya adalah mode aman (task 2.4a).
"""

from __future__ import annotations

import functools
import json
import logging
import re
import weakref
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final

from sibyl_memory_client import MemoryClient, NotFoundError

from agent.memory_lock import locked_client

log = logging.getLogger("memory_policy")

# ----------------------------------------------------------------------
# Konstanta skema (spec §3 tabel tier)
# ----------------------------------------------------------------------

CATEGORY_PROVIDER: Final = "provider"
CATEGORY_CLIENT: Final = "client"
CATEGORY_QUARANTINE: Final = "suspicion"  # ADR-002; dipakai HANYA di BAGIAN 3
CATEGORY_JOB: Final = "job"

STATE_KEY_PREFIX: Final = "job:"
REFERENCE_RUBRIC_PREFIX: Final = "rubric:"
REFERENCE_PATTERN_PREFIX: Final = "pattern:"

QUARANTINE_STATUS_PENDING: Final = "pending"
QUARANTINE_STATUS_PROMOTED: Final = "promoted"

# `list_entities` memotong diam-diam pada 100 (api-facts §C) → selalu eksplisit, DAN
# setiap pemakaian WAJIB lewat `_list_all()` yang melempar bila hasilnya menyentuh batas.
LIST_LIMIT: Final = 10_000

# `search` memotong diam-diam pada 20 (api-facts §C.1 jebakan 3) → sama seperti `LIST_LIMIT`,
# batas ini SELALU eksplisit dan pemakaiannya WAJIB lewat `_reference_keys()` yang melempar
# bila hasil menyentuh batas. Nilainya dibaca dari GLOBAL modul saat dipanggil supaya tes
# bisa mengecilkannya dan membuktikan pemotongan benar-benar terdeteksi.
SEARCH_LIMIT: Final = 10_000

# Cek deterministik yang sah sebagai bukti (spec §5 langkah 3, modul `agent/checks/*`).
# Klaim pihak / skor LLM TIDAK ada di sini dan TIDAK PERNAH boleh masuk (spec §3 aturan 3).
DETERMINISTIC_CHECK_IDS: Final[frozenset[str]] = frozenset({"chain", "links", "format", "sandbox"})

MAX_RISK_LEVEL: Final = 2

# Mode pemeriksaan (spec §3 aturan 5 + §5 langkah 2).
MODE_NAIVE: Final = "naive"
MODE_NORMAL: Final = "normal"
MODE_SAFE: Final = "safe"

# Kedalaman cek. spec §3 aturan 6 + §7 langkah 4: memori mengubah KALIBRASI, yaitu
# kedalaman cek — bukan keberadaan evaluator. `check_depth()` yang memetakannya.
DEPTH_SAMPLING: Final = "sampling"
DEPTH_FULL: Final = "full"

ZERO_ROOT: Final[bytes] = bytes(32)

# Keadaan memori lokal (ADR-024 keputusan 2). EMPAT, bukan dua: "tidak ada" dan "tidak bisa
# dibaca" berujung pada mode yang BERBEDA, dan meruntuhkan keduanya menjadi satu boolean
# adalah persis cara aturan yang benar berubah menjadi aturan yang salah.
LOCAL_MEMORY_OK: Final = "ok"
LOCAL_MEMORY_MISSING: Final = "missing"
LOCAL_MEMORY_ERROR: Final = "error"
LOCAL_MEMORY_LOCK_FAILED: Final = "lock_failed"

# Batas tunggu kunci `memory.db` untuk PEMBACAAN GERBANG saja (task 2.4a-fix). Jalur TULIS
# tetap memakai `memory_lock.DEFAULT_TIMEOUT_SECONDS` (10 detik) karena tulisan yang gagal
# berarti kehilangan hasil kerja; pembacaan gerbang terjadi berkali-kali per transaksi dan
# kegagalannya SUDAH punya jawaban yang benar (mode aman), jadi menunggu penuh hanya
# memakan anggaran waktu ADR-014 tanpa menambah keamanan.
GATE_LOCK_TIMEOUT_SECONDS: Final = 1.0

# ADR-001: di EvaluatorVault/`providerCap`, nilai 0 berarti TANPA BATAS. Karena itu
# "tanpa cap" TIDAK PERNAH direpresentasikan sebagai 0 di dalam Python — ia `None` —
# dan cap hasil `derive_cap` DILARANG nol (ADR-019 keputusan 4).
NO_CAP: Final[None] = None
ONCHAIN_UNLIMITED_CAP: Final = 0

# ADR-020 keputusan 3: saat provider belum pernah punya job LOLOS, cap berasal dari
# KONSTANTA, bukan statistik. 1 USDC (6 desimal) dipilih agar spec §7 langkah 3 muat di
# 2 USDC yang sudah dimiliki wallet client: job C 2 USDC > cap 0,25 USDC → REJECT,
# pecahan 0,2 USDC lolos.
BASELINE_CAP_USDC: Final = 1_000_000
# ADR-020 keputusan 5: lantai bermakna (0,25 USDC), bukan `1` yang menyamarkan
# "blokir segalanya" sebagai angka. "Blokir total" BUKAN keluaran sah `derive_cap`;
# satu-satunya jalur berhenti-total adalah mode aman.
MIN_CAP_USDC = 250_000

# Batas bentuk masukan. Nama entity & id pola dibatasi ketat supaya pemisah `:` pada
# nama karantina `f"{addr}:{pattern}"` tidak bisa dipalsukan.
ADDRESS_RE: Final = re.compile(r"^0x[0-9a-f]{40}\Z")
PATTERN_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}\Z")
# Kategori rubric memakai bentuk yang SAMA: kunci `reference:rubric:*` ikut dijangkar
# `memory_root`, jadi ia tunduk pada batas yang sama dengan `reference:pattern:*`.
RUBRIC_CATEGORY_RE: Final = PATTERN_ID_RE
MAX_PROOF_LEN: Final = 512
MAX_UINT256: Final = 2**256 - 1
# Jumlah digit maksimum satu integer di preimage: uint256 = 78 digit. Batas ini WAJIB
# eksplisit, bukan diserahkan ke `int()`: CPython >= 3.11 melempar `ValueError` sendiri di
# 4300 digit (`sys.int_max_str_digits`), sedangkan pembaca lain (JS) hanya mencocokkan regex
# dan tetap menghitung — satu file, satu sisi mati, sisi lain mencetak root.
MAX_DECIMAL_DIGITS: Final = 78


class MemoryPolicyError(RuntimeError):
    """Kesalahan kebijakan memori (pelanggaran invarian, bukan kegagalan I/O)."""


class ForbiddenReadError(MemoryPolicyError):
    """Jalur keputusan mencoba membaca sesuatu di luar `provider` + `reference:pattern`."""


class StaleWriteError(MemoryPolicyError):
    """Tulisan berbasis snapshot provider yang sudah usang (CAS versi gagal)."""


class MemoryIntegrityError(MemoryPolicyError):
    """Memori tidak bisa dijadikan preimage yang jujur (tabrakan nama, hasil terpotong)."""


# ----------------------------------------------------------------------
# Utilitas kanonik — dipakai BERSAMA oleh `memory_root()` dan `agent/memory_export.py`
# ----------------------------------------------------------------------


def normalize_address(address: str) -> str:
    """Alamat EVM dinormalkan ke huruf kecil, dan divalidasi bentuknya.

    Validasi ketat (bukan sekadar `lower()`) karena alamat menjadi NAMA entity dan
    komponen pertama nama karantina `f"{addr}:{pattern}"`. Tanpa ini, "alamat" berisi
    `:` atau spasi bisa membuat entri karantina milik satu provider terbaca sebagai
    milik provider lain.
    """
    if not isinstance(address, str):
        raise ValueError(f"alamat provider harus string, dapat {type(address).__name__}")
    candidate = address.strip().lower()
    if not ADDRESS_RE.match(candidate):
        raise ValueError(f"alamat provider tidak berbentuk 0x + 40 hex: {address!r}")
    return candidate


def validate_pattern_id(pattern_id: str) -> str:
    """Id pola dibatasi `[a-z0-9._-]` supaya tidak bisa menyelipkan `:` ke nama entity."""
    if not isinstance(pattern_id, str) or not PATTERN_ID_RE.match(pattern_id):
        raise ValueError(f"pattern_id tidak sah (huruf kecil/angka/._- maks 64): {pattern_id!r}")
    return pattern_id


# Penanda integer di preimage. Semua integer ditulis sebagai STRING DESIMAL di dalam
# pembungkus ini, JANGAN sebagai bilangan JSON: `JSON.parse` di JS memakai float 64-bit,
# sehingga uint256 (budget, cap, root) rusak DIAM-DIAM di atas 2^53. Klaim "siapa pun
# bisa merekonstruksi root" harus berlaku juga bagi yang tidak memakai Python.
NUMBER_TAG: Final = "$u"

# Kunci objek di dalam body: HANYA ASCII cetak, dan TANPA karakter yang butuh escape JSON
# (`"` dan `\`). Batas ini bukan kerapian — ia menutup SELURUH kelas "dua bahasa membaca
# nama properti yang sama secara berbeda". Nama properti adalah satu-satunya tempat di
# encoding ini yang harus dilewatkan ke `JSON.parse` pihak lain sebagai NAMA (kunci seksi
# adalah nilai string di dalam array, jadi tidak melewati jalur itu), dan implementasi
# `JSON.parse` bebas punya cache nama properti sendiri. Kalau tidak ada satu pun kunci yang
# butuh escape, tidak ada yang bisa didekode berbeda. `agent/tools/memory_root_check.mjs`
# MENOLAK himpunan yang sama, jadi keduanya sepakat secara konstruksi: sama-sama menghitung
# atau sama-sama menolak — tidak pernah menghasilkan dua angka.
# `\Z`, BUKAN `$`: `$` di Python juga cocok TEPAT SEBELUM newline penutup, sehingga
# kunci "lf\n" akan lolos diam-diam — persis kelas karakter yang dilarang di sini.
BODY_KEY_RE: Final = re.compile(r"^[\x20-\x21\x23-\x5b\x5d-\x7e]*\Z")

# ADR-020 keputusan 6 — versi encoding preimage. Ia ikut ter-hash sebagai bingkai pertama,
# jadi perubahan encoding berikutnya menghasilkan root yang JELAS berbeda, bukan diam-diam
# tabrakan dengan root lama yang sudah terdaftar di `knownRoots` (ADR-011).
MEMORY_ROOT_ENCODING_VERSION: Final = "evaluator-memory-root/v1"

# Label seksi. Urutannya BAGIAN DARI ENCODING dan tidak boleh diubah-ubah.
SECTION_PROVIDER: Final = "provider"
SECTION_PATTERN: Final = "reference:pattern"
SECTION_RUBRIC: Final = "reference:rubric"

# Field top-level yang SAH di file ekspor. Apa pun di luar ini ditolak (lihat `from_export_obj`).
EXPORT_FIELDS: Final = frozenset({"version", "providers", "patterns", "rubrics"})


def _wellformed_text(text: str) -> str:
    """String yang BISA di-encode UTF-8. Surrogate yatim ditolak, tidak diperbaiki diam-diam.

    Ditegakkan untuk SETIAP string yang masuk preimage — kunci seksi maupun nilai di dalam
    body. Alasannya paritas, bukan estetika: Python melempar saat encode, Node menukar
    surrogate yatim dengan U+FFFD dan terus menghitung. Selama salah satu sisi "memperbaiki"
    masukan rusak, dua alat audit bisa menjawab berbeda atas file yang sama.
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise MemoryIntegrityError(
            f"string preimage bukan UTF-8 well-formed (surrogate yatim): {text!r}"
        ) from exc
    return text


def _checked_decimal(text: str) -> str:
    """Batas PANJANG desimal, ditegakkan di jalur tulis MAUPUN baca preimage.

    Dua hal sekaligus. (a) Paritas: tanpa batas eksplisit, `{"$u": "1" + "0"*5000}` membuat
    Python melempar `ValueError` dari `int()` (batas 4300 digit CPython) sementara pembaca JS
    yang hanya mencocokkan regex MENCETAK root — persis "satu file, dua perilaku" yang tidak
    boleh ada di alat audit. (b) Isi memori ini uint256 (budget, cap, root): 78 digit sudah
    mencakup seluruh rentangnya, jadi angka di luar itu bukan data kita.
    """
    digits = len(text) - 1 if text.startswith("-") else len(text)
    if digits > MAX_DECIMAL_DIGITS:
        # Dicek dari PANJANG dulu, sebelum `int()`: pada 5000 digit `int()` sendiri yang
        # melempar (`sys.int_max_str_digits`), dan pesannya menjadi detail CPython — bukan
        # aturan encoding yang bisa ditiru implementasi lain.
        raise MemoryIntegrityError(
            f"integer {digits} digit melewati batas {MAX_DECIMAL_DIGITS} (uint256) — "
            "encoding ini menolaknya di kedua bahasa, bukan mati di salah satu"
        )
    if abs(int(text)) > MAX_UINT256:
        raise MemoryIntegrityError(
            f"integer {text} di luar rentang uint256 (78 digit tidak cukup sebagai batas: "
            "2**256 juga 78 digit)"
        )
    return text


def _canonical_value(value: Any, depth: int = 0) -> Any:
    """Bentuk kanonik lintas-bahasa: tanpa bilangan JSON, tanpa float, kunci ASCII."""
    if depth > 32:
        raise MemoryIntegrityError("body memori terlalu dalam untuk dikanonikkan")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return {NUMBER_TAG: _checked_decimal(str(value))}
    if isinstance(value, float):
        raise MemoryIntegrityError(
            "float tidak boleh masuk preimage memory_root (tidak dapat direproduksi lintas bahasa)"
        )
    if isinstance(value, str):
        return _wellformed_text(value)
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not BODY_KEY_RE.match(key):
                raise MemoryIntegrityError(
                    f"kunci body harus ASCII cetak tanpa karakter yang butuh escape JSON "
                    f'(tanpa " dan \\ dan tanpa kontrol), dapat {key!r}'
                )
            if key == NUMBER_TAG:
                raise MemoryIntegrityError(f"kunci {NUMBER_TAG!r} dipesan untuk penanda integer")
            out[key] = _canonical_value(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item, depth + 1) for item in value]
    raise MemoryIntegrityError(f"tipe {type(value).__name__} tidak dapat dikanonikkan")


# Bentuk desimal KANONIK, satu bentuk per angka. `-?` di depan `0` sengaja TIDAK dipakai:
# `-0` lolos regex lama, `int("-0") == 0`, lalu ter-encode ULANG menjadi `{"$u":"0"}` —
# sedangkan pembaca yang mengambil string apa adanya (skrip Node) menghash `"-0"`. Satu file,
# dua root, dua-duanya "berhasil". Itu membatalkan kalimat "tidak pernah dua angka dari satu
# file", jadi bentuk non-kanonik (`-0`, `007`, `+1`, spasi) DITOLAK di kedua sisi.
_DECIMAL_RE: Final = re.compile(r"^(0|-?[1-9][0-9]*)\Z")


def decanonical_value(value: Any, depth: int = 0) -> Any:
    """Kebalikan `_canonical_value`: `{"$u": "<desimal>"}` kembali menjadi `int`.

    Dipakai membaca file EKSPOR (task 2.1b) agar root bisa dihitung ulang dari file itu
    dengan fungsi yang SAMA. Tidak ada ambiguitas: `_canonical_value` MELARANG `$u` sebagai
    kunci body, jadi satu-satunya dict berkunci tunggal `$u` adalah integer yang di-encode.
    """
    if depth > 32:
        raise MemoryIntegrityError("body ekspor terlalu dalam untuk didekanonikkan")
    if isinstance(value, Mapping):
        if set(value) == {NUMBER_TAG}:
            text = value[NUMBER_TAG]
            if not isinstance(text, str) or not _DECIMAL_RE.match(text):
                raise MemoryIntegrityError(
                    f"penanda integer {value!r} bukan desimal KANONIK (satu bentuk per angka: "
                    "tanpa -0, tanpa nol di depan, tanpa tanda +)"
                )
            return int(_checked_decimal(text))
        if NUMBER_TAG in value:
            # `{"$u": …, "lain": …}`: `_canonical_value` melarang `$u` sebagai kunci body,
            # jadi bentuk ini tidak pernah bisa dihasilkan eksportir. Python akan menolaknya
            # nanti saat menghash; pembaca yang menghash objek apa adanya TIDAK. Ditolak di
            # sini supaya kedua sisi berhenti di titik yang sama.
            raise MemoryIntegrityError(
                f"kunci {NUMBER_TAG!r} hanya sah sebagai penanda integer tunggal, dapat {value!r}"
            )
        return {k: decanonical_value(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [decanonical_value(v, depth + 1) for v in value]
    if isinstance(value, float):
        raise MemoryIntegrityError("ekspor memuat bilangan JSON; encoding ini melarangnya")
    if isinstance(value, int) and not isinstance(value, bool):
        raise MemoryIntegrityError("ekspor memuat bilangan JSON; encoding ini melarangnya")
    return value


def canonical_json(value: Any) -> str:
    """JSON kanonik: kunci terurut, tanpa spasi, ASCII murni, tanpa bilangan JSON.

    `ensure_ascii=True` + kunci wajib ASCII disengaja: hasilnya bebas dari pilihan
    encoding, locale, maupun perbedaan urutan sort antar bahasa.
    """
    return json.dumps(_canonical_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _frame(text: str) -> bytes:
    """Bingkai PANJANG-BERPREFIKS (netstring): `<jumlah byte>:<isi utf-8>,`.

    Inilah yang membuat "dua kunci berbeda runtuh jadi satu" mustahil (ADR-020 keputusan 6).
    Penggabungan biasa (`key + body`) bisa ditabrak: nama `"0xa" , body "b:c"` dan nama
    `"0xa:b"`, body `"c"` menghasilkan byte yang sama. Dengan panjang di depan, batas setiap
    potongan ditentukan oleh angka yang ikut ter-hash, bukan oleh pemisah yang bisa ditiru.
    Panjang dihitung dalam BYTE UTF-8 (bukan karakter) supaya kunci non-ASCII — yang MEMANG
    bisa disimpan sebagai kunci reference (api-facts §C.1) — tetap bisa direkonstruksi di JS
    lewat `Buffer.byteLength`.
    """
    # Surrogate YATIM (`\ud800`) ditolak DI SINI, bukan diserahkan ke perilaku encoder:
    # Python melempar, sedangkan `Buffer.from(s,"utf8")` di Node menukarnya dengan `EF BF BD`
    # (U+FFFD) DIAM-DIAM dan tetap menghitung, sehingga tiga kunci berbeda (`\ud800`,
    # `\udfff`, `\ufffd` yang SAH) runtuh menjadi SATU root di sisi Node — persis yang
    # dijanjikan mustahil oleh bingkai panjang-berprefiks. Kedua sisi kini MENOLAK.
    raw = _wellformed_text(text).encode("utf-8")
    return str(len(raw)).encode("ascii") + b":" + raw + b","


def _frame_section(tag: str, mapping: Mapping[str, Any]) -> bytes:
    """Satu seksi preimage: label, jumlah entri, lalu pasangan (kunci, body kanonik).

    Kunci diurutkan MENURUT BYTE UTF-8 di sini — TIDAK PERNAH mengandalkan urutan yang
    dikembalikan store. api-facts §C.1 jebakan 2: `search` mengurutkan `ORDER BY rank`
    (bm25) dengan seri dipecah rowid = urutan INSERT, sehingga hasilnya berubah bila body
    diedit atau urutan tulis berbeda. Urutan yang stabil bukan urutan yang kanonik.
    Jumlah entri ikut di-hash supaya seksi kosong dan seksi hilang tidak pernah sama.
    """
    parts = [_frame(tag), _frame(str(len(mapping)))]
    # `_wellformed_text` dipanggil DI KUNCI SORT: pengurutan sendiri sudah meng-encode UTF-8,
    # jadi tanpa ini surrogate yatim keluar sebagai `UnicodeEncodeError` mentah sebelum
    # `_frame` sempat menolaknya dengan pesan yang benar.
    for key in sorted(mapping, key=lambda k: _wellformed_text(k).encode("utf-8")):
        parts.append(_frame(key))
        parts.append(_frame(canonical_json(mapping[key])))
    return b"".join(parts)


def _sorted_pairs(mapping: Mapping[str, Any]) -> list[list[Any]]:
    """Pasangan (kunci, isi) terurut menurut BYTE kuncinya — bukan menurut locale."""
    return [
        [key, mapping[key]]
        for key in sorted(mapping, key=lambda k: _wellformed_text(k).encode("utf-8"))
    ]


def _keccak(data: bytes) -> bytes:
    # Impor lokal: web3 hanya dibutuhkan untuk hash, dan modul ini harus tetap ringan
    # bila dipakai dari alat ekspor.
    from web3 import Web3

    return bytes(Web3.keccak(data))


def decision_path_forward[F: Callable[..., Any]](fn: F) -> F:
    """Sama dengan `@decision_path`, tetapi untuk fungsi yang berada di atas definisinya.

    Penandaannya dilakukan sekali di akhir modul (`_register_forward_decision_paths`),
    sehingga fungsi ini ikut diperiksa tes sumber & tes properti karantina yang sama.
    """
    _FORWARD_DECISION_PATHS.append(fn)
    return fn


_FORWARD_DECISION_PATHS: list[Callable[..., Any]] = []


def _list_all(client: MemoryClient, category: str, *, status: str | None = None) -> list[dict[str, Any]]:
    """`list_entities` dengan batas EKSPLISIT dan penolakan pemotongan senyap.

    api-facts §C: default `limit=100` memotong diam-diam. Pemotongan pada jalur ini
    berarti provider hilang dari `memory_root` (audit bohong) atau terbaca risk 0 tanpa
    cap (gating hilang) — keduanya tanpa satu pun pesan. Karena itu: dilempar.
    """
    rows = client.list_entities(category, status=status, limit=LIST_LIMIT)
    if len(rows) >= LIST_LIMIT:
        raise MemoryIntegrityError(
            f"list_entities({category!r}) menyentuh batas {LIST_LIMIT}; hasil mungkin terpotong"
        )
    return rows


@decision_path_forward
def _reference_keys(reader: Any, prefix: str) -> list[str]:
    """Enumerasi kunci `reference:<prefix>*` — MENANGANI KETIGA JEBAKAN api-facts §C.1.

    1. BOCOR LINTAS PREFIKS. `prefix=True` bukan prefiks-kunci melainkan prefiks-TOKEN FTS
       atas kunci DAN body: `search("pattern:")` mengembalikan `rubric:pattern:trap`,
       `other:pattern-trap`, bahkan `rubric:defi` yang BODY-nya sekadar menyebut kata
       "pattern". Hasil mentahnya SUPERSET → disaring `key.startswith(prefix)` di sini.
    2. URUTAN. Hasil datang `ORDER BY rank` (bm25; seri dipecah rowid = urutan INSERT),
       jadi TIDAK terurut kunci. Kami mengurutkan sendiri; `rank` dan `snippet` diabaikan.
    3. POTONG SENYAP. `search` default `limit=20` dan tidak memberi tanda "masih ada sisa".
       Batas diberikan EKSPLISIT, dan bila hasil MENYENTUHNYA batas dinaikkan sekali (10x)
       sebelum menyerah — baru sesudah itu dilempar. Dua sisi yang harus ditutup sekaligus:
       menerima hasil terpotong berarti reference hilang dari preimage tanpa satu pun pesan
       (audit berbohong), sedangkan melempar pada percobaan PERTAMA membuat siapa pun yang
       bisa menulis reference `other:*` berbody kata "pattern" mematikan agen dengan derau
       yang bahkan tidak masuk cakupan root (kebocoran jebakan 1 dipakai balik sebagai DoS).

    `body` hasil `search` juga TIDAK dipakai: setelah kunci diketahui, isinya diambil lewat
    `get_reference` yang sudah ada di api-facts §C. Satu sumber kebenaran untuk body.
    """
    rows: list[dict[str, Any]] = []
    for limit in (SEARCH_LIMIT, SEARCH_LIMIT * 10):
        rows = reader.search_references(prefix, limit=limit)
        if len(rows) < limit:
            break
    else:
        raise MemoryIntegrityError(
            f"search({prefix!r}) menyentuh batas {SEARCH_LIMIT * 10}; hasil mungkin terpotong"
        )
    keys = {str(row["key"]) for row in rows if str(row.get("key", "")).startswith(prefix)}
    return sorted(keys, key=lambda k: k.encode("utf-8"))


# ----------------------------------------------------------------------
# Struktur data
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """Satu bukti insiden. HANYA berasal dari cek deterministik agen sendiri."""

    job_id: int
    check_id: str
    proof: str = ""

    def __post_init__(self) -> None:
        # Koersi + validasi di konstruktor: `promotion_eligible` menghitung job BERBEDA
        # lewat himpunan, dan tanpa koersi `7` vs `"7"` terhitung dua job sehingga satu
        # job saja cukup untuk promosi.
        if isinstance(self.job_id, bool) or not isinstance(self.job_id, (int, str)):
            raise TypeError(f"job_id harus int, dapat {type(self.job_id).__name__}")
        try:
            job_id = int(self.job_id)
        except ValueError as exc:
            raise TypeError(f"job_id harus bilangan bulat, dapat {self.job_id!r}") from exc
        if job_id < 0:
            raise ValueError("job_id tidak boleh negatif")
        object.__setattr__(self, "job_id", job_id)

        if not isinstance(self.check_id, str):
            raise TypeError(f"check_id harus string, dapat {type(self.check_id).__name__}")

        if not isinstance(self.proof, str):
            raise TypeError(f"proof harus string, dapat {type(self.proof).__name__}")
        if len(self.proof) > MAX_PROOF_LEN:
            raise ValueError(f"proof melebihi {MAX_PROOF_LEN} karakter")
        # `proof` bisa berisi kutipan dari deliverable (task 2.3) dan ikut ter-hash ke
        # memory_root; ia DATA, bukan instruksi (§3 aturan 3). Karakter kontrol dibuang
        # supaya teks pihak tidak bisa menyelundupkan pemisah/kendali terminal.
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in self.proof):
            raise ValueError("proof tidak boleh memuat karakter kontrol")

    def is_deterministic(self) -> bool:
        return self.check_id in DETERMINISTIC_CHECK_IDS

    def to_body(self) -> dict[str, Any]:
        return {"job": int(self.job_id), "check": self.check_id, "proof": str(self.proof)}

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> Evidence:
        return cls(
            job_id=int(body.get("job", -1)),
            check_id=str(body.get("check", "")),
            proof=str(body.get("proof", "")),
        )


@dataclass(frozen=True)
class ProviderProfile:
    """Isi entity WARM `provider` (spec §3 baris 100), sebagai struktur yang bisa diuji."""

    address: str
    risk_level: int = 0
    confirmed_patterns: tuple[str, ...] = ()
    incident_jobs: tuple[int, ...] = ()
    recorded_jobs: tuple[int, ...] = ()
    passed_budgets: tuple[int, ...] = ()
    stats_jobs: int = 0
    stats_pass: int = 0
    stats_reject: int = 0
    cap_usdc: int | None = None
    last_seen: str | None = None
    # Penghitung CAS: dinaikkan tiap tulisan yang lolos cek versi (lihat `_save_provider_cas`).
    version: int = 0

    def to_body(self) -> dict[str, Any]:
        return {
            "risk_level": int(self.risk_level),
            "cap_usdc": self.cap_usdc,
            "stats": {
                "jobs": int(self.stats_jobs),
                "pass": int(self.stats_pass),
                "reject": int(self.stats_reject),
            },
            "confirmed_patterns": sorted(set(self.confirmed_patterns)),
            "incident_jobs": sorted(set(int(j) for j in self.incident_jobs)),
            # Daftar job yang SUDAH pernah tercatat — inti idempotensi `record_job_outcome`.
            "recorded_jobs": sorted(set(int(j) for j in self.recorded_jobs)),
            # HANYA budget job yang LOLOS. ADR-020 keputusan 1: budget yang dikendalikan
            # provider (job yang ia danai lalu ditolak) DILARANG masuk rumus cap dalam
            # bentuk apa pun — dihapus, bukan disaring.
            "budgets": {"passed": sorted(int(b) for b in self.passed_budgets)},
            "last_seen": self.last_seen,
            "version": int(self.version),
        }

    @classmethod
    def from_body(cls, address: str, body: Mapping[str, Any] | None) -> ProviderProfile:
        """Body rusak → `MemoryIntegrityError`, BUKAN `ValueError` mentah.

        Pemanggil (task 2.4a) memakai satu jenis kesalahan untuk memutuskan mode aman;
        `invalid literal for int()` yang bocor dari sini akan MEMBUAT AGEN CRASH alih-alih
        masuk mode aman — yaitu kebalikan fail-closed.
        """
        try:
            return cls._from_body_unchecked(address, body)
        except MemoryPolicyError:
            raise
        except (TypeError, ValueError, AttributeError) as exc:
            raise MemoryIntegrityError(f"body entity provider {address!r} rusak: {exc}") from exc

    @classmethod
    def _from_body_unchecked(cls, address: str, body: Mapping[str, Any] | None) -> ProviderProfile:
        body = body or {}
        stats = body.get("stats") or {}
        budgets = body.get("budgets") or {}
        return cls(
            address=normalize_address(address),
            risk_level=int(body.get("risk_level", 0) or 0),
            confirmed_patterns=tuple(sorted(set(str(p) for p in body.get("confirmed_patterns", [])))),
            incident_jobs=tuple(sorted(set(int(j) for j in body.get("incident_jobs", [])))),
            recorded_jobs=tuple(sorted(set(int(j) for j in body.get("recorded_jobs", [])))),
            passed_budgets=tuple(sorted(int(b) for b in budgets.get("passed", []))),
            stats_jobs=int(stats.get("jobs", 0) or 0),
            stats_pass=int(stats.get("pass", 0) or 0),
            stats_reject=int(stats.get("reject", 0) or 0),
            cap_usdc=(None if body.get("cap_usdc") in (None, "") else int(body["cap_usdc"])),
            last_seen=body.get("last_seen"),
            version=int(body.get("version", 0) or 0),
        )


@dataclass(frozen=True)
class LocalMemoryEvidence:
    """Keadaan memori lokal — masukan `decide_mode` (ADR-023 keputusan 2, ADR-024).

    NAMA & KLAIM (ADR-024 keputusan 4): kelas ini TIDAK membuktikan asal-usul apa pun. Ia
    hanya melaporkan apakah `memory.db` ADA dan apakah ia BISA DIBACA. Pembuktian asal-usul
    menuntut log root lokal yang belum ada (v2), dan menamai sesuatu lebih besar daripada
    yang dikerjakannya adalah cara paling murah menipu diri sendiri.

    Root memori ikut dibawa, tetapi HANYA sebagai konteks yang dicetak/diumumkan
    (`postVerdict`) — bukan bahan perbandingan: root lokal selalu satu tulisan di depan root
    yang diumumkan on-chain, jadi membandingkan keduanya selalu berakhir mode aman sesudah
    job pertama (ADR-023).

      - `status`       : salah satu dari EMPAT keadaan, dan pemisahannya menentukan mode:
          `ok`          — `memory.db` ada dan seluruh pembacaannya berhasil;
          `missing`     — file utama TIDAK ADA (memori dihapus / belum pernah dibuat);
          `error`       — ada tetapi pembacaannya MELEMPAR (rusak, enumerasi terpotong, …);
          `lock_failed` — kunci single-instance tidak didapat, yaitu ADA INSTANS AGEN LAIN.
        `error` dan `lock_failed` TIDAK PERNAH boleh runtuh menjadi `missing`: yang pertama
        berarti kita tidak tahu isi memori, yang terakhir berarti memori memang tidak ada.
      - `job_outcomes` : banyaknya JOB BERBEDA yang meninggalkan jejak di entity `provider`.
                         SEJAK ADR-024 ia TIDAK memutuskan apa pun — nol job outcome adalah
                         mode NORMAL tanpa kalibrasi. Ia tetap dilaporkan karena itulah
                         angka yang membuat baris `MODE NORMAL` bisa dibaca manusia.
      - `root`         : `memory_root` lokal; `None` bila tidak terbaca.
      - `detail`       : asal angka-angka di atas, apa adanya, untuk log dan pesan.
    """

    status: str
    job_outcomes: int
    root: bytes | None
    detail: str

    @classmethod
    def ok(cls, *, job_outcomes: int, root: bytes, detail: str) -> LocalMemoryEvidence:
        return cls(status=LOCAL_MEMORY_OK, job_outcomes=job_outcomes, root=root, detail=detail)

    @classmethod
    def missing(cls, detail: str) -> LocalMemoryEvidence:
        """File utama tidak ada. SATU-SATUNYA keadaan yang boleh berujung NAIF."""
        return cls(status=LOCAL_MEMORY_MISSING, job_outcomes=0, root=None, detail=detail)

    @classmethod
    def error(cls, detail: str) -> LocalMemoryEvidence:
        """Ada tetapi tidak bisa dibaca. Ketidaktahuan tidak pernah memberi izin lebih besar."""
        return cls(status=LOCAL_MEMORY_ERROR, job_outcomes=0, root=None, detail=detail)

    @classmethod
    def lock_failed(cls, detail: str) -> LocalMemoryEvidence:
        """Kunci single-instance tidak didapat — ada instans agen LAIN yang berjalan."""
        return cls(status=LOCAL_MEMORY_LOCK_FAILED, job_outcomes=0, root=None, detail=detail)

    @property
    def local_memory_readable(self) -> bool:
        """Persis itu, tidak lebih: memori lokal ada DAN terbaca (ADR-024 keputusan 4)."""
        return self.status == LOCAL_MEMORY_OK

    @property
    def is_missing(self) -> bool:
        return self.status == LOCAL_MEMORY_MISSING

    @property
    def root_hex(self) -> str:
        return "UNREADABLE" if self.root is None else "0x" + self.root.hex()


@dataclass(frozen=True)
class ModeDecision:
    """Hasil `decide_mode` — nilai murni yang bisa diuji tanpa chain (task 2.4a memakainya)."""

    mode: str
    reason: str
    depth: str
    forced_risk: int | None
    allow_finalize: bool
    allow_post_verdict: bool
    allow_set_provider_cap: bool

    @property
    def is_safe(self) -> bool:
        return self.mode == MODE_SAFE


@dataclass(frozen=True)
class CapPlan:
    """Rencana cap hasil `derive_cap`.

    `cap_usdc is None` = TANPA cap; nilai 0 DILARANG (ADR-001). Tidak ada field "blokir":
    ADR-020 keputusan 5 — berhenti total hanya ada di mode aman, bukan di cap.
    """

    cap_usdc: int | None
    require_milestone: bool
    basis: str
    sample_size: int

    @property
    def has_cap(self) -> bool:
        return self.cap_usdc is not None


@dataclass(frozen=True)
class GateDecision:
    """Keputusan gating saat `JobFunded` (spec §5 langkah 2).

    `risk_level` + `incident_jobs` ikut dibawa karena keputusan ini adalah SATU-SATUNYA
    bukti yang ada saat job masih `Funded`: belum ada deliverable, jadi belum ada
    `Evaluation`. Bundel bukti `reasonHash` untuk penolakan gerbang (`vault_client
    .verdict_evidence`) dibangun dari nilai-nilai ini, dan tanpa jobId insiden yang
    mendasarinya bundel itu hanya berisi angka cap tanpa asal-usul — auditor tidak bisa
    menelusuri kembali ke job yang melahirkan capnya.

    Keduanya berasal dari entity `provider` (`DecisionMemoryView.provider`), bukan dari
    karantina: spec §3 aturan 1 tetap berlaku utuh di sini.
    """

    accept: bool
    reason: str
    cap: CapPlan
    mode: ModeDecision
    depth: str
    risk_level: int = 0
    incident_jobs: tuple[int, ...] = ()
    onchain_cap: int | None = None
    effective_cap: int | None = None


def _checked_reference_keys(
    mapping: Mapping[str, Any], prefix: str, label: str
) -> dict[str, Any]:
    """Kunci reference WAJIB memakai awalan seksinya — di KEDUA jalur (DB dan ekspor).

    Alasannya sama dengan tuntutan kanonisitas nama provider: seksi `patterns` dijangkar
    root sebagai `reference:pattern`, tetapi `DecisionMemoryView` hanya bisa membaca kunci
    berawalan `pattern:` (jalur bacanya `raw_references(REFERENCE_PATTERN_PREFIX)`). Entri
    berkunci `bukan-pattern-prefix` karena itu dijangkar tetapi TIDAK PERNAH dibaca — bukti
    palsu. Di jalur DB syarat ini otomatis terpenuhi (kunci datang dari enumerasi berawalan);
    yang benar-benar ditutup di sini adalah jalur EKSPOR, yang sebelumnya menerimanya.
    """
    out: dict[str, Any] = {}
    for key, body in mapping.items():
        text = str(key)
        if not text.startswith(prefix):
            raise MemoryIntegrityError(
                f"kunci reference {text!r} di seksi {label!r} tidak berawalan {prefix!r} — "
                "ia akan dijangkar root tetapi TIDAK PERNAH dibaca jalur keputusan"
            )
        out[text] = body
    return out


@dataclass(frozen=True)
class MemorySnapshot:
    """Potongan memori yang menjadi PREIMAGE `memory_root` (spec §3 baris 123).

    Isinya adalah BODY MENTAH yang tersimpan di Sibyl, bukan proyeksi `ProviderProfile`:
    proyeksi bersifat lossy, sehingga field asing, perbedaan tipe, dan bahkan entity yang
    saling menimpa setelah normalisasi nama akan menghasilkan root yang IDENTIK — artinya
    root tidak lagi mengikat isi memori yang diaudit.

    Cakupan (ADR-020 keputusan 7): SELURUH memori yang boleh dibaca pengambil keputusan —
    semua entity `provider`, semua `reference:pattern:*`, dan semua `reference:rubric:*`,
    TERMASUK pattern YATIM yang tidak dirujuk provider mana pun. Entity `suspicion` TIDAK
    ikut (ADR-002): ia tidak boleh dibaca jalur keputusan, jadi ia tidak dijangkar.

    Satu jalur mengisinya dari DB Sibyl (`load_snapshot`), jalur lain dari file JSON hasil
    ekspor (task 2.1b) — keduanya memakai `memory_root()` yang SAMA, bukan salinan.
    """

    providers: dict[str, Any] = field(default_factory=dict)
    patterns: dict[str, Any] = field(default_factory=dict)
    rubrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        providers: Mapping[str, Any],
        patterns: Mapping[str, Any],
        rubrics: Mapping[str, Any] | None = None,
    ) -> MemorySnapshot:
        """Nama entity provider WAJIB sudah KANONIK: `name == normalize_address(name)`.

        Ini inti ADR-020 keputusan 7, dan bukan sekadar kebersihan. Satu entity bernama
        `"  0X5A5A…  "` sudah cukup — tanpa tabrakan apa pun — untuk membuat ekspor publik
        bercerita lain daripada agen: root MENJANGKARNYA (risk 2, cap 250.000, 3 insiden),
        tetapi `DecisionMemoryView.provider()` mencarinya dengan nama TERNORMALKAN, tidak
        menemukannya, dan memakai profil kosong (risk 0, `cap_usdc=None` → `cap_to_onchain`
        = 0 = TANPA BATAS, ADR-001). Root tetap cocok, mode tetap NORMAL, nol deteksi,
        permanen. Menerima keduanya sebagai dua entri terpisah TIDAK menolong: yang salah
        bukan tabrakannya, melainkan adanya entri yang dijangkar tapi tidak pernah dibaca.

        Menuntut kanonisitas membuat tabrakan mustahil SECARA KONSTRUKSI (dua nama kanonik
        yang menormalkan sama adalah nama yang sama), jadi tidak perlu aturan anti-tabrakan
        terpisah. Ia juga tidak menambah permukaan DoS: fungsi ini memang sudah memanggil
        `normalize_address` dan sudah melempar untuk nama yang bukan alamat; yang berubah
        hanya kelas "alamat tetapi tidak kanonik", yang sebelumnya menghasilkan kebohongan
        senyap. Penulisan lewat modul ini selalu kanonik (`save_provider` memakai
        `ProviderProfile.address` yang ternormalkan).
        """
        checked: dict[str, Any] = {}
        for name, body in providers.items():
            kanonik = normalize_address(name)
            if str(name) != kanonik:
                raise MemoryIntegrityError(
                    f"nama entity provider {name!r} tidak kanonik (seharusnya {kanonik!r}) — "
                    "ia akan dijangkar root tetapi TIDAK PERNAH dibaca jalur keputusan"
                )
            checked[kanonik] = body
        return cls(
            providers=checked,
            patterns=_checked_reference_keys(patterns, REFERENCE_PATTERN_PREFIX, "patterns"),
            rubrics=_checked_reference_keys(rubrics or {}, REFERENCE_RUBRIC_PREFIX, "rubrics"),
        )

    def to_canonical_obj(self) -> dict[str, Any]:
        """Bentuk EKSPOR (task 2.1b): pasangan terurut + body yang sudah dikanonikkan.

        Objek ini bebas dari bilangan JSON (semua integer sudah menjadi `{"$u":"…"}`),
        jadi `JSON.parse` di JS tidak merusak uint256 di atas 2^53 dan pembaca lain bisa
        menghitung ulang root dari file ekspor saja.
        """
        return {
            "version": MEMORY_ROOT_ENCODING_VERSION,
            "providers": [[k, _canonical_value(v)] for k, v in _sorted_pairs(self.providers)],
            "patterns": [[k, _canonical_value(v)] for k, v in _sorted_pairs(self.patterns)],
            "rubrics": [[k, _canonical_value(v)] for k, v in _sorted_pairs(self.rubrics)],
        }

    @classmethod
    def from_export_obj(cls, obj: Mapping[str, Any]) -> MemorySnapshot:
        """Kebalikan `to_canonical_obj` — dipakai alat audit (2.1b) dan vektor uji beku."""
        version = obj.get("version")
        if version != MEMORY_ROOT_ENCODING_VERSION:
            raise MemoryIntegrityError(
                f"ekspor memakai encoding {version!r}, modul ini {MEMORY_ROOT_ENCODING_VERSION!r}"
            )
        asing = set(obj) - EXPORT_FIELDS
        if asing:
            # Field top-level asing TIDAK ikut ter-hash. Ekspor yang memuatnya bisa
            # menampilkan satu cerita ke manusia sementara rootnya mengikat cerita lain.
            raise MemoryIntegrityError(
                f"ekspor memuat field top-level yang tidak dijangkar root: {sorted(asing)}"
            )

        def pairs(name: str) -> dict[str, Any]:
            rows = obj.get(name, [])
            if not isinstance(rows, list):
                raise MemoryIntegrityError(
                    f"seksi {name!r} harus array, dapat {type(rows).__name__}"
                )
            out: dict[str, Any] = {}
            for item in rows:
                # PERSIS dua elemen. Elemen ketiga yang diabaikan diam-diam adalah tempat
                # sempurna menyembunyikan "profil yang ditampilkan ke manusia" di samping
                # body yang ter-hash.
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    raise MemoryIntegrityError(
                        f"entri seksi {name!r} harus pasangan [kunci, body], dapat {item!r}"
                    )
                key, body = item
                if not isinstance(key, str):
                    raise MemoryIntegrityError(
                        f"kunci seksi {name!r} harus string, dapat {type(key).__name__}"
                    )
                if key in out:
                    raise MemoryIntegrityError(f"kunci {key!r} muncul dua kali di seksi {name!r}")
                out[key] = decanonical_value(body)
            return out

        # Validasi lewat `from_mapping` yang SAMA, bukan salinan yang lebih longgar.
        # Sebelum task 2.1b jalur ini tidak memvalidasi apa pun: alat audit JS/Python
        # MENERIMA ekspor bernama `hello-i-am-not-an-address` dan berkunci
        # `bukan-pattern-prefix` — ekspor yang agen sendiri TOLAK — lalu mencetak root
        # untuknya. Root yang bisa dihitung untuk memori yang tidak akan pernah dibaca
        # agen adalah bukti palsu, persis kelas kegagalan yang ditutup ADR-020 keputusan 7.
        return cls.from_mapping(pairs("providers"), pairs("patterns"), pairs("rubrics"))

    def preimage(self) -> bytes:
        """PREIMAGE BEKU (ADR-020 keputusan 6). Urutan seksi bagian dari encoding.

            frame(versi) || seksi(provider) || seksi(reference:pattern) || seksi(reference:rubric)

        dengan `frame(s) = desimal(len(utf8(s))) || ":" || utf8(s) || ","` dan
        `seksi(tag, m) = frame(tag) || frame(jumlah) || untuk tiap kunci TERURUT:
        frame(kunci) || frame(canonical_json(body))`.
        """
        return b"".join(
            [
                _frame(MEMORY_ROOT_ENCODING_VERSION),
                _frame_section(SECTION_PROVIDER, self.providers),
                _frame_section(SECTION_PATTERN, self.patterns),
                _frame_section(SECTION_RUBRIC, self.rubrics),
            ]
        )


# ----------------------------------------------------------------------
# Kunci single-instance (task 2.4a butir 1) — lihat `agent/memory_lock.py`
# ----------------------------------------------------------------------


def under_memory_lock[F: Callable[..., Any]](fn: F) -> F:
    """Memegang kunci `memory.db` selama SELURUH pemanggilan fungsi ini.

    Dipakai pada DUA jenis operasi, dan keduanya perlu alasan terpisah:

      - BACA-HITUNG (`load_snapshot`, dan lewat itu seluruh `memory_root*`). Rangkaiannya
        1x `list_entities` + 2x `search` + N x `get_reference`, dan rangkaian itu TIDAK
        dibungkus `Storage.transaction()` (yang ada dan atomik — api-facts §C.2). Tanpa
        penutup, tulisan yang mendarat di tengah menghasilkan root untuk
        keadaan yang TIDAK PERNAH ADA — dan file ekspor pun cocok dengan root itu, jadi
        cacatnya tidak terlihat dari file.
      - TULIS (`record_job_outcome`, `promote_suspicions`, `store_provider_cap`, dan seluruh
        setter mentah). `_save_provider_cas` hanya CAS versi cek-lalu-tulis; jendela antara
        keduanya tidak atomik dan TIDAK BISA diatomkan lewat API publik (metode tulis SDK
        tidak boleh bersarang dalam transaksi — api-facts §C.2), jadi kunci inilah satu-satunya
        yang menutupnya.

    Fungsi yang dibungkus WAJIB menerima klien memori sebagai argumen PERTAMA. Kunci ini
    REENTRAN, jadi fungsi tingkat atas dan helper yang dipanggilnya boleh sama-sama memakai
    dekorator ini tanpa saling mengunci.
    """

    @functools.wraps(fn)
    def wrapper(client: Any, *args: Any, **kwargs: Any) -> Any:
        with locked_client(client):
            return fn(client, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


# ======================================================================
# BAGIAN 1 — pemetaan tier §3 (I/O memori mentah)
# ======================================================================


@under_memory_lock
def set_active_job(client: MemoryClient, job_id: int | str, body: Mapping[str, Any]) -> None:
    """HOT — spec §3 "Job aktif": `set_state("job:{id}", {...})`."""
    client.set_state(f"{STATE_KEY_PREFIX}{job_id}", dict(body))


def get_active_job(client: MemoryClient, job_id: int | str) -> dict[str, Any] | None:
    """HOT — `get_state` mengembalikan PEMBUNGKUS `{'body':…}` (api-facts §C), bukan body."""
    row = client.get_state(f"{STATE_KEY_PREFIX}{job_id}")
    return None if row is None else row["body"]


@under_memory_lock
def save_provider(client: MemoryClient, profile: ProviderProfile) -> ProviderProfile:
    """WARM — spec §3 "Profil provider"."""
    client.set_entity(CATEGORY_PROVIDER, profile.address, profile.to_body())
    return profile


@under_memory_lock
def save_client_profile(client: MemoryClient, address: str, body: Mapping[str, Any]) -> None:
    """WARM — spec §3 "Profil client" (kualitas kriteria, sengketa yang ternyata salah)."""
    client.set_entity(CATEGORY_CLIENT, normalize_address(address), dict(body))


@under_memory_lock
def write_journal(client: MemoryClient, acted: Sequence[Mapping[str, Any]]) -> str:
    """COLD — spec §3 "Verdict & cek". `write_event` SELURUHNYA keyword-only (api-facts §C)."""
    return client.write_event(acted=[dict(item) for item in acted])


def validate_rubric_category(category: str) -> str:
    """Cermin `validate_pattern_id` untuk kunci `reference:rubric:*` (task 2.4a-fix).

    Alasannya SAMA PERSIS dan bukan kerapian:
      - kunci rubric ikut DIJANGKAR `memory_root` (ADR-020 keputusan 7), jadi kategori
        sembarang — `""`, `"a:b"`, `"de fi"`, `"de\\fi"`, `"kucing-🐈"`, atau kalimat
        "IGNORE PREVIOUS INSTRUCTIONS…" — masuk ke preimage yang diaudit publik;
      - `:` di dalam kategori membuat satu kunci bisa terbaca sebagai kunci lain, persis
        lubang yang ditutup `validate_pattern_id` di sisi pattern;
      - namespace `rubric:*` yang tak terbatas adalah jalur DoS: banjir kunci membuat
        `_reference_keys()` menyentuh batas `search` → `MemoryIntegrityError` → seluruh
        `memory_root` melempar → MODE AMAN permanen.
    Yang menahan enam payload di atas sebelum ini bukan kode kita, melainkan validator
    Sibyl — dan itu bukan penjaga yang boleh kita andalkan.
    """
    if not isinstance(category, str) or not RUBRIC_CATEGORY_RE.match(category):
        raise ValueError(
            f"kategori rubric tidak sah (huruf kecil/angka/._- maks 64): {category!r}"
        )
    return category


@under_memory_lock
def set_rubric(client: MemoryClient, category: str, body: Mapping[str, Any]) -> None:
    """REFERENCE — spec §3 "Rubric per kategori". Kategori DIVALIDASI, lihat di atas."""
    client.set_reference(f"{REFERENCE_RUBRIC_PREFIX}{validate_rubric_category(category)}", dict(body))


def get_rubric(client: MemoryClient, category: str) -> dict[str, Any] | None:
    """Pembacaan memakai validator yang SAMA: kunci yang tidak bisa ditulis juga tidak
    boleh bisa dicari (kalau tidak, penulis lain tetap punya kunci yang hanya kita yang
    membacanya)."""
    return _read_reference_body(
        client, f"{REFERENCE_RUBRIC_PREFIX}{validate_rubric_category(category)}"
    )


@under_memory_lock
def archive_job(client: MemoryClient, job_id: int | str) -> dict[str, Any] | None:
    """ARCHIVE — spec §3 "Job final". `archive_entity` MELEMPAR NotFoundError (api-facts §C)."""
    try:
        return client.archive_entity(CATEGORY_JOB, str(job_id))
    except NotFoundError:
        log.info("archive_job: entity job tidak ada", extra={"job_id": str(job_id)})
        return None


def _read_reference_body(client: MemoryClient, key: str) -> dict[str, Any] | None:
    """`set_reference` menyimpan dict sebagai STRING JSON (api-facts §C) → json.loads."""
    row = client.get_reference(key)
    if row is None:
        return None
    body = row["body"]
    if isinstance(body, str):
        return json.loads(body)
    return body


# ======================================================================
# BAGIAN 2 — JALUR KEPUTUSAN
# Hanya entity `provider` + reference `pattern:*` (spec §3 aturan 1, ADR-002).
# ======================================================================

DECISION_PATH_FUNCTIONS: set[str] = set()


def decision_path[F: Callable[..., Any]](fn: F) -> F:
    """Menandai fungsi sebagai bagian jalur pengambilan keputusan.

    Penanda ini dibaca `tests/test_memory_policy.py`, yang MEMBACA SUMBER setiap fungsi
    bertanda dan menjadikan tes MERAH bila salah satunya menyebut karantina. Jangan
    menghapus penanda ini untuk "menyederhanakan" — ia yang membuat batas §3 aturan 1
    bisa dibuktikan, bukan sekadar dijanjikan. Penanda sumber SAJA tidak cukup (nama
    kategori bisa disamarkan), karena itu ada tes properti runtime sebagai lapis kedua.
    """
    DECISION_PATH_FUNCTIONS.add(fn.__qualname__)
    return fn


@decision_path
def _guard_category(category: Any) -> str:
    """Kategori entity yang boleh dibaca jalur keputusan — spec §3 aturan 1."""
    if category != CATEGORY_PROVIDER:
        raise ForbiddenReadError(
            f"jalur keputusan hanya boleh membaca kategori {CATEGORY_PROVIDER!r}, "
            f"diminta {category!r} (docs/spec.md §3 aturan 1)"
        )
    return category


# ADR-020 keputusan 7 (task 2.1r): cakupan BACA jalur keputusan == cakupan JANGKAR root.
# `rubric:` masuk kembali di sini PERSIS karena `memory_root` kini menjangkarnya; sebelum
# 2.1r ia sengaja ditutup supaya tidak ada keadaan "dibaca tapi tidak dijangkar". Kedua
# daftar ini WAJIB tetap sama — ada tes yang membandingkannya.
DECISION_REFERENCE_PREFIXES: Final[tuple[str, ...]] = (
    REFERENCE_PATTERN_PREFIX,
    REFERENCE_RUBRIC_PREFIX,
)


@decision_path
def _guard_reference_key(key: Any) -> str:
    """Reference yang boleh dibaca jalur keputusan: `pattern:` dan `rubric:`.

    Keduanya, dan HANYA keduanya, dijangkar `memory_root` (ADR-020 keputusan 7). Aturannya
    satu kalimat: root menjangkar persis himpunan yang boleh dibaca pengambil keputusan,
    sehingga keadaan "saya membacanya tapi tidak menjangkarnya" mustahil.
    """
    if not isinstance(key, str) or not key.startswith(DECISION_REFERENCE_PREFIXES):
        raise ForbiddenReadError(
            f"jalur keputusan hanya boleh membaca reference berawalan "
            f"{list(DECISION_REFERENCE_PREFIXES)}, diminta {key!r} (docs/spec.md §3 aturan 1)"
        )
    return key


@decision_path
def _guard_reference_prefix(prefix: Any) -> str:
    """Awalan yang boleh DIENUMERASI. Pencocokan PERSIS, bukan `startswith`.

    `search` mencocokkan token atas kunci DAN body, jadi awalan sembarang akan menarik
    baris dari tier reference mana pun (api-facts §C.1 jebakan 1). Yang boleh diminta
    hanya dua konstanta di `DECISION_REFERENCE_PREFIXES`.
    """
    if prefix not in DECISION_REFERENCE_PREFIXES:
        raise ForbiddenReadError(
            f"jalur keputusan hanya boleh mengenumerasi {list(DECISION_REFERENCE_PREFIXES)}, "
            f"diminta {prefix!r} (docs/spec.md §3 aturan 1)"
        )
    return prefix


# Registri identitas reader yang benar-benar dibuat `_guarded_reader()`. `WeakSet` supaya
# view yang dibuang tidak menahan memori. Ini yang membuat penerimaan reader di
# `DecisionMemoryView` sekaku penolakan subclass di `gate_job` — dua sisi pintu yang sama.
_GENUINE_READERS: weakref.WeakSet[Any] = weakref.WeakSet()


class _GuardedReader:
    """Klien memori TERBATAS: satu-satunya benda yang dipegang jalur keputusan.

    KLAIMNYA, tepat sejauh yang benar: reader ini tidak punya satu pun atribut DATA —
    `__slots__` kosong, tanpa `__dict__`, dan klien Sibyl penuh hidup hanya di dalam CLOSURE
    metodenya. Jadi tidak ada `reader._GuardedReader__client`, tidak ada `vars(reader)`, dan
    setiap nama lain jatuh ke `__getattr__` yang MELEMPAR — termasuk nama yang dirakit saat
    runtime agar tes sumber buta.

    YANG TIDAK DIKLAIM: kurungan. `type(reader).get_entity.__closure__[0].cell_contents`
    adalah rantai atribut biasa dan MENYERAHKAN klien penuh; begitu pula `gc.get_referents`,
    atau sekadar `import sibyl_memory_client` lalu membuat klien baru. Python tidak punya
    kurungan yang sungguh-sungguh, jadi apa pun yang berbunyi seperti "klien tidak pernah
    terjangkau" akan salah. Yang dibeli oleh bentuk ini hanyalah: "lupa memanggil penjaga"
    dan "ambil klien lewat name-mangling" berhenti menjadi mode kegagalan yang WAJAR.
    Kontrol sesungguhnya tetap tiga tes karantina (sumber, properti runtime, klien
    mata-mata) — bukan kelas ini.
    """

    # `__weakref__` diperlukan registri identitas di atas; ia BUKAN atribut data.
    __slots__ = ("__weakref__",)

    def get_entity(self, category: str, name: str) -> dict[str, Any]:
        raise ForbiddenReadError("gunakan _guarded_reader() untuk membuat reader")

    def list_entities(
        self, category: str | None = None, *, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        raise ForbiddenReadError("gunakan _guarded_reader() untuk membuat reader")

    def get_reference(self, key: str) -> dict[str, Any] | None:
        raise ForbiddenReadError("gunakan _guarded_reader() untuk membuat reader")

    def search_references(self, prefix: str, *, limit: int) -> list[dict[str, Any]]:
        raise ForbiddenReadError("gunakan _guarded_reader() untuk membuat reader")

    def __getattr__(self, name: str) -> Any:
        raise ForbiddenReadError(
            f"jalur keputusan tidak boleh memanggil {name!r} pada memori; hanya "
            "get_entity/list_entities('provider'), get_reference('pattern:*'|'rubric:*') "
            "dan search_references atas kedua awalan itu (docs/spec.md §3 aturan 1)"
        )


@decision_path
def _guarded_reader(client: MemoryClient) -> _GuardedReader:
    """Membuat reader yang menyimpan `client` HANYA di closure, bukan di atribut.

    Kelasnya dibuat per pemanggilan supaya metodenya bisa menutup `client` tanpa satu pun
    slot/atribut instans. Biayanya satu objek kelas per view; imbalannya: `_GuardedReader`
    tidak lagi punya atribut ber-name-mangling yang bisa dijangkau lewat lookup NORMAL.

    Setiap instans didaftarkan di `_GENUINE_READERS` (identitas, bukan tipe). Itulah yang
    dipakai `DecisionMemoryView` untuk menolak reader PALSU: subclass `_GuardedReader`
    ber-`__slots__ = ()` yang meng-override `list_entities` lolos `isinstance` dengan mudah,
    dan lewat situ `raw_providers()` bisa mengembalikan baris dari kategori entity LAIN
    seolah-olah ia provider.
    """

    class GuardedReader(_GuardedReader):
        __slots__ = ()

        def get_entity(self, category: str, name: str) -> dict[str, Any]:
            return client.get_entity(_guard_category(category), name)

        def list_entities(
            self, category: str | None = None, *, status: str | None = None, limit: int = 100
        ) -> list[dict[str, Any]]:
            return client.list_entities(_guard_category(category), status=status, limit=limit)

        def get_reference(self, key: str) -> dict[str, Any] | None:
            return client.get_reference(_guard_reference_key(key))

        def search_references(self, prefix: str, *, limit: int) -> list[dict[str, Any]]:
            """`search` DIKUNCI ke tier reference dan ke dua awalan yang sah.

            api-facts §C.1: `tiers=("reference",)` RAPAT (tidak bocor lintas tier), tetapi
            `prefix=True` mencocokkan TOKEN atas kunci DAN body sehingga hasilnya SUPERSET.
            Penyaringan kunci, pengurutan, dan deteksi pemotongan dikerjakan pemanggil
            (`_reference_keys`), bukan di sini — supaya ketiganya bisa diuji terpisah.
            """
            return client.search(
                _guard_reference_prefix(prefix), limit=limit, prefix=True, tiers=("reference",)
            )

        def __repr__(self) -> str:  # pragma: no cover - hanya untuk pesan galat
            return "<_GuardedReader provider+pattern/rubric>"

    reader = GuardedReader()
    _GENUINE_READERS.add(reader)
    return reader


class DecisionMemoryView:
    """Pintu baca TUNGGAL jalur keputusan.

    Empat hal yang disengaja:
      1. Yang disimpan adalah `_GuardedReader`, BUKAN klien Sibyl. Reader itu tidak punya
         atribut data sama sekali (klien hidup di closure), jadi tidak ada JALUR ATRIBUT
         dari dalam kelas ini menuju kategori `suspicion`, dan penjaga tidak bisa "tidak
         dipanggil" karena ia ada di lapisan klien. Introspeksi runtime (`__closure__`,
         `gc`) tetap bisa menembusnya — lihat catatan batas di `_GuardedReader`.
      2. Atribut ber-name-mangling + `__slots__`: tidak ada `view._client`, dan tidak ada
         atribut baru yang bisa ditanam dari modul lain.
      3. Penjaga membandingkan dengan KONSTANTA LITERAL, bukan daftar putih yang bisa
         dilebarkan dari file lain.
      4. `gate_job` menuntut tipe PERSIS kelas ini, jadi subclass yang melonggarkan
         penjaga pun tidak diterima — dan pintu masuknya sama kaku: reader yang diterima
         WAJIB yang benar-benar dibuat `_guarded_reader()` (dicek per IDENTITAS lewat
         `_GENUINE_READERS`), bukan sekadar `isinstance(_GuardedReader)`. Tanpa itu
         asimetrinya bisa dieksploitasi: subclass `_GuardedReader` ber-`__slots__ = ()`
         yang meng-override `list_entities` membuat `raw_providers()` mengembalikan baris
         `suspicion`, dan `gate_job` tetap lolos karena view-nya bertipe persis.
    """

    __slots__ = ("__reader",)

    def __init__(self, client: MemoryClient) -> None:
        if isinstance(client, _GuardedReader):
            if client not in _GENUINE_READERS:
                raise ForbiddenReadError(
                    "reader ini bukan hasil _guarded_reader(); subclass _GuardedReader bisa "
                    "meng-override list_entities dan menyuntikkan baris karantina sebagai "
                    "provider (docs/spec.md §3 aturan 1)"
                )
            self.__reader = client
        else:
            self.__reader = _guarded_reader(client)

    # -- penjaga (dipertahankan sebagai API agar bisa diuji langsung) --

    @decision_path
    def _guard_category(self, category: str) -> str:
        return _guard_category(category)

    @decision_path
    def _guard_reference_key(self, key: str) -> str:
        return _guard_reference_key(key)

    # -- pembacaan ----------------------------------------------------

    @decision_path
    def provider(self, address: str) -> ProviderProfile:
        """Profil provider; provider yang belum dikenal → profil kosong (risk 0)."""
        name = normalize_address(address)
        try:
            row = self.__reader.get_entity(CATEGORY_PROVIDER, name)
        except NotFoundError:
            return ProviderProfile(address=name)
        return ProviderProfile.from_body(name, row["body"])

    @decision_path
    def raw_providers(self) -> list[tuple[str, Any]]:
        """(nama APA ADANYA, body MENTAH) — preimage `memory_root` dibangun dari ini."""
        rows = _list_all(self.__reader, CATEGORY_PROVIDER)
        return [(row["name"], row["body"]) for row in rows]

    @decision_path
    def list_providers(self) -> list[ProviderProfile]:
        return [ProviderProfile.from_body(name, body) for name, body in self.raw_providers()]

    @decision_path
    def raw_pattern(self, pattern_id: str) -> Any | None:
        """Isi reference APA ADANYA (string JSON menurut api-facts §C)."""
        key = f"{REFERENCE_PATTERN_PREFIX}{validate_pattern_id(pattern_id)}"
        row = self.__reader.get_reference(key)
        return None if row is None else row["body"]

    @decision_path
    def pattern(self, pattern_id: str) -> dict[str, Any] | None:
        body = self.raw_pattern(pattern_id)
        if body is None:
            return None
        return json.loads(body) if isinstance(body, str) else body

    @decision_path
    def raw_reference(self, key: str) -> Any | None:
        """Isi reference APA ADANYA untuk kunci LENGKAP yang sudah lolos penjaga."""
        row = self.__reader.get_reference(key)
        return None if row is None else row["body"]

    @decision_path
    def rubric(self, category: str) -> dict[str, Any] | None:
        """REFERENCE `rubric:<kategori>` (spec §3) — boleh dibaca sejak root menjangkarnya.

        `set_reference` menyimpan dict sebagai STRING JSON (api-facts §C) → `json.loads`.
        Isinya DATA, bukan instruksi: ia mengkalibrasi kriteria, dan tidak pernah menjadi
        bukti (spec §3 aturan 3).
        """
        body = self.raw_reference(f"{REFERENCE_RUBRIC_PREFIX}{category}")
        if body is None:
            return None
        return json.loads(body) if isinstance(body, str) else body

    @decision_path
    def reference_keys(self, prefix: str) -> list[str]:
        """Semua kunci reference berawalan `prefix`, TERURUT dan lengkap (lihat `_reference_keys`)."""
        return _reference_keys(self.__reader, prefix)

    @decision_path
    def raw_references(self, prefix: str) -> dict[str, Any]:
        """{kunci lengkap: body MENTAH} untuk satu awalan — bahan preimage root."""
        out: dict[str, Any] = {}
        for key in self.reference_keys(prefix):
            row = self.__reader.get_reference(key)
            if row is None:
                # Kunci yang baru saja dienumerasi tetapi hilang saat dibaca = memori
                # berubah di tengah pembacaan (atau store tidak konsisten). Fail-closed.
                raise MemoryIntegrityError(
                    f"reference {key!r} muncul di enumerasi tetapi hilang saat dibaca"
                )
            out[key] = row["body"]
        return out


@decision_path
def parse_root(value: bytes | bytearray | str) -> bytes:
    """bytes32 dari `bytes` atau hex-string. Bentuk lain DITOLAK dengan `ValueError`.

    Ketat dengan sengaja: `"0x"` dan `""` adalah TEPAT yang dikembalikan `eth_call` untuk
    alamat kontrak yang salah, kontrak yang belum ter-mine, atau chain yang salah. Bila
    keduanya diterjemahkan menjadi "root nol", agen masuk mode NAIF — mode dengan izin
    PALING BESAR — persis saat ia paling tidak tahu apa-apa (kebalikan §3 aturan 5).
    """
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, str):
        text = value[2:] if value[:2].lower() == "0x" else value
        if len(text) != 64:
            raise ValueError(f"root hex harus 64 digit, dapat {len(text)}: {value!r}")
        try:
            raw = bytes.fromhex(text)
        except ValueError as exc:
            raise ValueError(f"root bukan hex yang sah: {value!r}") from exc
    else:
        raise ValueError(f"root harus bytes atau hex-string, dapat {type(value).__name__}")
    if len(raw) != 32:
        raise ValueError(f"memory root harus 32 byte, dapat {len(raw)}")
    return raw


@decision_path
def _read_root(value: Any) -> tuple[bytes | None, bool]:
    """(root, terbaca). `terbaca=False` berarti nilainya TIDAK dapat dipercaya sama sekali."""
    if value is None:
        return None, False
    try:
        return parse_root(value), True
    except ValueError:
        return None, False


@decision_path
def decide_mode(onchain_root: Any, local: LocalMemoryEvidence | None) -> ModeDecision:
    """spec §3 aturan 5 sebagaimana dibaca ulang ADR-023 dan DIKOREKSI ADR-024. MURNI.

    PRESEDENSI, tepat urutan ini (ADR-024 keputusan 2) — urutannya bagian dari aturannya:

      (1) kunci single-instance gagal, ATAU pembacaan memori MELEMPAR   → AMAN;
      (2) `memory.db` HILANG: root onchain nol → NAIF; selain itu (termasuk root yang tidak
          terbaca)                                                      → AMAN;
      (3) selebihnya                                                    → NORMAL, TERMASUK
          memori kosong dengan nol job outcome.

    `lastMemoryRoot()` dibaca HANYA di cabang (2), dan hanya untuk membedakan "hari pertama"
    dari "vault yang sudah hidup". Di semua cabang lain ia log/UI saja (ADR-023 keputusan 1).

    DUA HAL YANG DICABUT, jangan dikembalikan tanpa ADR baru:
      - perbandingan root lokal vs `lastMemoryRoot()` (ADR-023). Vault beku ADR-022 menyimpan
        root konstanta pipa 1.3d yang tidak bisa diturunkan dari `memory.db` mana pun, dan
        spec §5 langkah 5 menulis memori SESUDAH `postVerdict` sehingga root lokal selalu
        satu langkah di depan — agen berhenti sesudah job PERTAMA bahkan di vault baru;
      - aturan (b) "DB ada tapi NOL job outcome + root non-nol → AMAN" (ADR-024). Ia
        memindahkan self-brick, tidak membunuhnya: di vault beku root SELALU non-nol, jadi
        (b) menahan `postVerdict` job A dan outcome pertama tidak pernah lahir (`tx = []`).
        Ia juga dipenuhi DB tiga baris buatan tangan, jadi yang ditegakkannya "DB tidak
        kosong" — nilainya NOL terhadap pihak yang bisa menulis `memory.db`.

    BOOTSTRAP job A TIDAK punya jalur khusus (ADR-024 keputusan 3): memori kosong = mode
    NORMAL tanpa kalibrasi, dan perilakunya memang sama dengan evaluator stateless
    (spec §3 aturan 6). Pengecualian "postVerdict pertama", entity `origin`, dan seeding di
    `make demo` semuanya DITOLAK PM.

    YANG HILANG, disebut apa adanya (ADR-024 konsekuensi): `memory.db` yang DIGANTI DB lain —
    kosong maupun terisi — tidak terdeteksi. Pemulihannya butuh log root lokal (v2).

    Dalam mode AMAN `postVerdict` juga ditahan: ADR-011 mencatat bahwa fail-closed kini
    murni dijaga di sisi agen — tidak ada root baru diumumkan, jadi tidak ada verdict baru
    yang bisa difinalisasi. (Spec §3 baris 117 secara harfiah hanya melarang `finalize`;
    ADR-011 lebih ketat dan itu yang diikuti.)
    """
    if local is not None and not isinstance(local, LocalMemoryEvidence):
        # Sebuah root telanjang (bytes/hex) DITOLAK KERAS, bukan diterima diam-diam:
        # pemanggil gaya lama akan tampak "hijau" sambil kehilangan seluruh isi aturan 5.
        raise TypeError(
            "decide_mode menerima LocalMemoryEvidence (ADR-023), bukan root lokal "
            f"({type(local).__name__}) — perbandingan sepasang root sudah dicabut"
        )

    evidence = local if local is not None else LocalMemoryEvidence.error("no evidence supplied")

    # (1) Kunci gagal / pembacaan melempar → AMAN, mendahului SEGALANYA.
    #
    # Kunci yang tidak didapat bukan pernyataan tentang isi chain maupun isi memori: ia
    # berarti ADA INSTANS AGEN LAIN. Rantai yang menuntut presedensi ini terukur: instans-2
    # gagal kunci → (dulu) NAIF → ia menandatangani `postVerdict` dari wallet yang sama →
    # dua instans menulis nonce yang sama, dan tulisan memorinya sendiri melempar. Dua
    # instans yang menandatangani dari satu wallet adalah masalah yang lebih besar daripada
    # kalibrasi yang hilang.
    if evidence.status == LOCAL_MEMORY_LOCK_FAILED:
        return _safe_decision(
            f"the single-instance memory.db lock was not acquired ({evidence.detail}) -> "
            "another agent instance exists, and two instances signing from one wallet must "
            "never happen"
        )
    if evidence.status == LOCAL_MEMORY_ERROR:
        return _safe_decision(f"local memory exists but cannot be read ({evidence.detail})")

    # (2) File memori HILANG. INILAH satu-satunya cabang yang membaca root on-chain, dan ia
    # membacanya untuk SATU pertanyaan saja: apakah vault ini sudah pernah hidup?
    #   - root nol  → hari pertama; tidak ada apa pun yang bisa hilang → NAIF (stateless).
    #                 §7 langkah 4 / 3.3b varian A menuntut agen TETAP BERJALAN di vault
    #                 SEGAR yang memorinya dihapus, supaya degradasinya terlihat; cabang
    #                 inilah yang membuatnya mungkin — tanpanya keadaan itu jadi mode aman,
    #                 run keluar 0 sebelum menyentuh path DB, dan agen tidak pernah
    #                 bootstrap. Yang TIDAK boleh diklaim (task 2.5a, ADR-026): bahwa
    #                 verdict varian A diumumkan DALAM mode ini. Lewat `--job-id` tidak:
    #                 `plan_job` membuat `memory.db`, jadi invokasi pertama berakhir
    #                 MODE_DRIFT (nol tx) dan yang kedua mengumumkan dalam mode `normal`
    #                 atas DB kosong — depth, cap, dan root-nya identik.
    #   - selain itu → vault sudah hidup tetapi memorinya lenyap → AMAN.
    #   - tidak terbaca → kita tidak bisa membedakan keduanya, dan ketidaktahuan TIDAK
    #                 PERNAH memberi izin lebih besar → AMAN.
    if evidence.is_missing:
        onchain, onchain_ok = _read_root(onchain_root)
        if not onchain_ok:
            return _safe_decision(
                f"local memory is missing ({evidence.detail}) and the onchain root is "
                "unreadable (invalid value) -> guessing which one is day one is not allowed"
            )
        if onchain == ZERO_ROOT:
            return ModeDecision(
                mode=MODE_NAIVE,
                reason=(
                    f"local memory is missing ({evidence.detail}) but the vault has never "
                    "announced a root (day one) -> stateless evaluation"
                ),
                depth=DEPTH_SAMPLING,
                forced_risk=None,
                allow_finalize=True,
                allow_post_verdict=True,
                allow_set_provider_cap=True,
            )
        return _safe_decision(
            f"local memory is missing ({evidence.detail}) even though the vault has already "
            "announced a root -> memory was wiped"
        )

    # (3) Selebihnya NORMAL — TERMASUK memori kosong dengan nol job outcome (ADR-024
    # keputusan 1 & 3). Aturan (b) lama ("nol outcome + root non-nol → AMAN") DICABUT: pada
    # vault beku ADR-022 root selalu non-nol, jadi (b) menahan `postVerdict` job A, dan
    # outcome pertama tidak pernah lahir — rantai 2.5 menghasilkan `tx = []`. Ia juga
    # dipenuhi oleh DB tiga baris buatan tangan, jadi yang ditegakkannya adalah "DB tidak
    # kosong", bukan asal-usul. JANGAN dikembalikan tanpa ADR baru.
    return ModeDecision(
        mode=MODE_NORMAL,
        reason=(
            f"local memory exists and is readable: {evidence.job_outcomes} job outcome(s) "
            f"recorded ({evidence.detail})"
        ),
        depth=DEPTH_SAMPLING,
        forced_risk=None,
        allow_finalize=True,
        allow_post_verdict=True,
        allow_set_provider_cap=True,
    )


# ADR-020 keputusan 8. Kalimat ini dibawa APA ADANYA ke `reason` mode aman: konsekuensinya
# diucapkan, bukan diperhalus menjadi "ditolak dengan aman".
SAFE_MODE_CONSEQUENCE: Final = (
    "the agent halts completely: no postVerdict, no finalize, no setProviderCap; "
    "the job HANGS until expiredAt, after which anyone may call claimRefund and the client "
    "receives a full refund"
)


@decision_path
def _safe_decision(reason: str) -> ModeDecision:
    return ModeDecision(
        mode=MODE_SAFE,
        reason=f"{reason} — {SAFE_MODE_CONSEQUENCE}",
        depth=DEPTH_FULL,
        forced_risk=MAX_RISK_LEVEL,
        allow_finalize=False,
        allow_post_verdict=False,
        allow_set_provider_cap=False,
    )


@decision_path
def safe_mode(onchain_root: Any, local: LocalMemoryEvidence | None) -> bool:
    """Pintasan boolean atas `decide_mode` (spec §3 aturan 5 + ADR-023)."""
    return decide_mode(onchain_root, local).is_safe


@decision_path
def effective_risk(profile: ProviderProfile, mode: ModeDecision | None = None) -> int:
    """Risk yang dipakai keputusan. Mode AMAN memaksa risk MAKSIMUM (spec §3 aturan 5)."""
    risk = max(0, min(MAX_RISK_LEVEL, int(profile.risk_level)))
    if mode is not None and mode.forced_risk is not None:
        risk = max(risk, mode.forced_risk)
    return risk


@decision_path
def check_depth(profile: ProviderProfile, mode: ModeDecision | None = None) -> str:
    """Kalibrasi kedalaman cek dari memori (spec §3 aturan 6, §7 langkah 4).

    Inilah yang hilang saat memori dihapus: provider ber-insiden turun dari `full` ke
    `sampling`, sehingga cacat HALUS di bagian yang tidak tersampling lolos, sedangkan
    cacat kasar tetap tertangkap. Pemilihan cek mana yang dijalankan pada tiap kedalaman
    adalah milik task 2.3/2.4a; di sini hanya kalibrasinya.
    """
    if mode is not None and mode.depth == DEPTH_FULL:
        return DEPTH_FULL
    return DEPTH_FULL if effective_risk(profile, mode) >= 1 else DEPTH_SAMPLING


@decision_path
def _median_ceil(values: Sequence[int]) -> int:
    """Median dibulatkan KE ATAS, aritmetika BULAT sepenuhnya.

    Tanpa float: budget adalah uint256 dan `(a+b)/2` kehilangan presisi di atas 2^53,
    sehingga cap bisa meleset diam-diam pada angka besar.
    """
    ordered = sorted(int(v) for v in values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return -(-(ordered[mid - 1] + ordered[mid]) // 2)


@decision_path
def derive_cap(provider: ProviderProfile, mode: ModeDecision | None = None) -> CapPlan:
    """spec §3 aturan 4 SEBAGAIMANA DIGANTI ADR-020 (yang mencabut ADR-019 keputusan 4).

      - risk 0    → TANPA cap (`cap_usdc is None`). BUKAN 0: di kontrak 0 = TANPA BATAS
                    (ADR-001), jadi "tanpa cap" dan "diblokir" tidak boleh bertemu nilai.
      - risk 1    → median budget job yang LOLOS, atau `BASELINE_CAP_USDC` bila belum ada.
      - risk >= 2 → 25% dari angka itu + wajib milestone.

    SATU-SATUNYA masukan numerik adalah budget job yang benar-benar LOLOS cek deterministik
    kita, dan sebuah konstanta. Budget job yang DITOLAK tidak pernah masuk: `reject`
    mengembalikan 100% budget ke client dan fee evaluator 0 (api-facts §A), dan token
    escrow testnet punya `mint()` tanpa kontrol akses — jadi provider bisa mendanai job
    raksasa sendiri, minta ditolak, dan menaikkan capnya sendiri tanpa biaya. Itulah
    rantai yang dieksekusi security-reviewer (500.000 → 24.750.000 dalam tiga ronde).

    Cap juga MONOTON TIDAK-NAIK per provider — DENGAN SATU PENGECUALIAN yang disebut apa
    adanya: monoton diterapkan LEBIH DULU (`min(kandidat, cap sebelumnya)`), lalu LANTAI
    `MIN_CAP_USDC` diterapkan pada hasilnya. Jadi cap tersimpan yang lebih kecil dari lantai
    akan NAIK ke lantai: `previous=1, risk=2` menghasilkan 250_000, bukan 1. Itu disengaja
    (ADR-020 keputusan 5: "blokir total" bukan keluaran sah `derive_cap`; satu-satunya jalur
    berhenti-total adalah mode aman), dan batas atasnya tetap `BASELINE_CAP_USDC` karena
    ADR-021 keputusan 1 memplafon kontribusi tiap job. Yang benar-benar dijamin: cap tidak
    pernah melampaui `max(cap sebelumnya, MIN_CAP_USDC)`, dan riwayat baik tidak pernah
    menaikkannya. Pemulihan reputasi adalah v2 dan DILARANG diklaim hidup.
    """
    risk = effective_risk(provider, mode)
    previous = provider.cap_usdc
    if previous is not None and previous <= 0:
        log.warning(
            "cap tersimpan tidak sah (<= 0) diabaikan; 0 on-chain berarti TANPA BATAS",
            extra={"provider": provider.address, "stored_cap": previous},
        )
        previous = None

    if risk == 0:
        if previous is None:
            return CapPlan(
                cap_usdc=NO_CAP, require_milestone=False, basis="risk-0-no-cap", sample_size=0
            )
        # Monoton TIDAK-NAIK berlaku juga di sini. Tanpa cabang ini, provider yang risk-nya
        # turun kembali ke 0 akan mendapat `NO_CAP` → on-chain 0 → TANPA BATAS (ADR-001),
        # yaitu kenaikan cap paling ekstrem yang mungkin, lewat pintu belakang.
        return CapPlan(
            cap_usdc=max(MIN_CAP_USDC, int(previous)),
            require_milestone=False,
            basis="monotone-previous",
            sample_size=0,
        )

    # ADR-021 keputusan 1 — PLAFON PERTUMBUHAN: kontribusi tiap job LOLOS dibatasi
    # `BASELINE_CAP_USDC`. `passed_budgets` masih dikendalikan provider (tidak ada apa pun
    # di ERC-8183/ACP yang mengikat client != provider secara ekonomis; `ClientIsProvider()`
    # hanya melarang ALAMAT yang sama), jadi tanpa plafon ini provider bisa mendanai job
    # sendiri lewat EOA kedua, meluluskannya, dan cap ikut naik ke angka itu.
    # Akibatnya matematis dan disengaja: cap turunan riwayat TIDAK PERNAH melampaui
    # BASELINE_CAP_USDC — riwayat baik tidak bisa MENAIKKAN cap, hanya gagal menurunkannya.
    passed = [min(b, BASELINE_CAP_USDC) for b in provider.passed_budgets if b > 0]
    if passed:
        base = _median_ceil(passed)
        basis = "median-passed"
    else:
        # ADR-020 keputusan 3 — konstanta, bukan statistik.
        base = BASELINE_CAP_USDC
        basis = "baseline-constant"

    candidate = base if risk == 1 else -(-base // 4)  # ceil(base/4), aritmetika bulat
    if previous is not None and previous < candidate:
        candidate = int(previous)
        basis = "monotone-previous"

    # Lantai diterapkan pada HASIL AKHIR, sesudah monoton. Kalau tidak, cap tersimpan yang
    # kecil (mis. 1) akan menjadi PERMANEN karena monoton tidak pernah naik — itu blacklist
    # yang menyamar jadi angka, dan ADR-020 keputusan 5 melarangnya. Satu-satunya jalur
    # "berhenti total" adalah mode aman.
    candidate = max(MIN_CAP_USDC, int(candidate))

    return CapPlan(
        cap_usdc=candidate,
        require_milestone=risk >= 2,
        basis=basis,
        sample_size=len(passed),
    )


@decision_path
def cap_to_onchain(decision: CapPlan) -> int:
    """Terjemahan ke `setProviderCap` — SATU-SATUNYA tempat cap bertemu angka 0.

    ADR-001: di kontrak, `cap == 0` berarti TANPA BATAS. Jadi hanya `NO_CAP` (None) yang
    boleh menjadi 0, dan cap bernilai 0 dari perhitungan adalah bug — ia akan diam-diam
    membuka gating sepenuhnya. Karena itu dilempar, bukan diteruskan.
    """
    if decision.cap_usdc is None:
        return ONCHAIN_UNLIMITED_CAP
    if decision.cap_usdc <= 0:
        raise MemoryPolicyError(
            "cap hasil perhitungan bernilai <= 0; on-chain nilai 0 berarti TANPA BATAS (ADR-001)"
        )
    if decision.cap_usdc > MAX_UINT256:
        raise MemoryPolicyError("cap melebihi uint256")
    return int(decision.cap_usdc)


@decision_path
def gate_job(
    view: DecisionMemoryView,
    provider_address: str,
    budget: int,
    mode: ModeDecision,
    *,
    onchain_cap: int | None,
) -> GateDecision:
    """spec §5 langkah 2 — gating saat `JobFunded`, dari `provider` + mode + lantai on-chain.

    `onchain_cap` adalah nilai `providerCap(provider)` yang DIUMUMKAN vault, dibaca oleh
    pemanggil (`vault_client.plan_job`) dan diserahkan sebagai ARGUMEN — modul ini tetap
    bebas RPC/web3 (spec §3 aturan 1; batas folder CLAUDE.md).

    Batas efektif = yang paling KETAT di antara cap memori dan cap on-chain. Sebabnya
    diukur di gerbang fase 2 (task 3.0b): tanpa ini, memori yang dikosongkan/dimundurkan
    membuat `derive_cap` mengembalikan `None` dan gerbang MENERIMA budget yang cap terbitan
    vault sendiri tolak — lantai yang dipasang 2.4b hanya menahan `setProviderCap` dari
    NAIK, bukan menahan gerbang dari MENERIMA.

    `onchain_cap` WAJIB dan TANPA DEFAULT (keyword-only). Itu disengaja: reviewer 3.0b
    membuktikan bahwa dengan default permisif, menghapus satu kata kunci di titik panggil
    mengembalikan temuan 4 juri sementara SELURUH 594 tes tetap hijau — penjaga ada,
    tidak ada yang memanggilnya, persis cacat yang task ini perbaiki. Pemanggil yang
    memang tidak punya nilainya WAJIB mengetik `onchain_cap=None` secara sadar.

    `onchain_cap == 0` berarti **TIDAK DIPASANG**, bukan "cap nol" (ADR-001), jadi ia
    diabaikan. Itulah yang menjaga AC (e) task 2.5 tetap berlaku: pada vault SEGAR capnya
    memang 0, sehingga job yang sama memang TIDAK ditolak tanpa memori.
    """
    if type(view) is not DecisionMemoryView:
        raise TypeError(
            "gate_job hanya menerima DecisionMemoryView PERSIS (subclass pun ditolak, "
            "karena ia bisa melonggarkan penjaga docs/spec.md §3 aturan 1)"
        )
    if isinstance(budget, bool) or not isinstance(budget, int):
        raise TypeError(f"budget harus int, dapat {type(budget).__name__}")

    profile = view.provider(provider_address)
    cap = derive_cap(profile, mode)
    depth = check_depth(profile, mode)
    risk = effective_risk(profile, mode)
    incidents = tuple(int(j) for j in profile.incident_jobs)

    floor = None
    if onchain_cap is not None:
        if isinstance(onchain_cap, bool) or not isinstance(onchain_cap, int):
            raise TypeError(f"onchain_cap harus int, dapat {type(onchain_cap).__name__}")
        if onchain_cap < 0:
            raise ValueError(f"onchain_cap tidak boleh negatif: {onchain_cap}")
        if onchain_cap > 0:
            floor = onchain_cap

    limits = [c for c in (cap.cap_usdc, floor) if c is not None]
    effective = min(limits) if limits else None

    if effective is not None and int(budget) > effective:
        if floor is not None and effective == floor and (
            cap.cap_usdc is None or floor < cap.cap_usdc
        ):
            reason = (
                f"budget {budget} melebihi cap yang DIUMUMKAN vault untuk provider ini "
                f"({floor}); memori lokal menghitung "
                f"{'TANPA CAP' if cap.cap_usdc is None else cap.cap_usdc}, dan yang lebih "
                f"ketat yang berlaku"
            )
        else:
            reason = (
                f"budget {budget} melebihi cap milestone provider ini "
                f"({cap.cap_usdc}; riwayat: {len(incidents)} insiden terkonfirmasi)"
            )
        return GateDecision(
            accept=False,
            reason=reason,
            cap=cap,
            mode=mode,
            depth=depth,
            risk_level=risk,
            incident_jobs=incidents,
            onchain_cap=floor,
            effective_cap=effective,
        )
    return GateDecision(
        accept=True,
        reason="budget dalam batas cap",
        cap=cap,
        mode=mode,
        depth=depth,
        risk_level=risk,
        incident_jobs=incidents,
        onchain_cap=floor,
        effective_cap=effective,
    )


# ----------------------------------------------------------------------
# Jangkar memori (spec §3 baris 123) — jalur keputusan & jalur audit yang SAMA
# ----------------------------------------------------------------------


@decision_path
@under_memory_lock
def load_snapshot(client: MemoryClient) -> MemorySnapshot:
    """Membaca preimage root dari DB: entity `provider` + `reference:pattern:*` + `reference:rubric:*`.

    Cakupannya ADR-020 keputusan 7 apa adanya: SELURUH himpunan yang boleh dibaca pengambil
    keputusan, TERMASUK pattern YATIM yang tidak dirujuk provider mana pun — bukan irisan
    yang dirujuk. Sebelum 2.1r daftar pattern diturunkan dari `confirmed_patterns` provider,
    sehingga menghapus sebuah pattern yatim tidak mengubah root sama sekali; enumerasi
    reference lewat `search` (api-facts §C.1) yang menutup lubang itu.

    Yang dimasukkan adalah NAMA dan BODY apa adanya dari baris DB, bukan hasil parsing —
    kalau tidak, field asing dan perbedaan tipe tidak akan mengubah root, dan root berhenti
    menjadi bukti atas isi memori yang diaudit.

    Fungsi ini menerima `MemoryClient` PENUH dan langsung membungkusnya jadi
    `DecisionMemoryView`; ia tidak memakai klien itu untuk apa pun yang lain. Batas §3
    aturan 1 di sini ditegakkan oleh view, bukan oleh tipe argumennya.

    Pattern yang tercatat di provider tetapi referensinya HILANG tetap memori yang rusak →
    dilempar, dan pemanggil (task 2.4a) memperlakukannya sebagai mode AMAN.
    """
    view = DecisionMemoryView(client)
    raw = view.raw_providers()
    providers = {str(name): body for name, body in raw}
    if len(providers) != len(raw):
        raise MemoryIntegrityError("nama entity provider duplikat pada hasil list_entities")
    snapshot = MemorySnapshot.from_mapping(
        providers,
        view.raw_references(REFERENCE_PATTERN_PREFIX),
        view.raw_references(REFERENCE_RUBRIC_PREFIX),
    )

    for name, body in raw:
        for pattern_id in ProviderProfile.from_body(name, body).confirmed_patterns:
            if f"{REFERENCE_PATTERN_PREFIX}{pattern_id}" not in snapshot.patterns:
                raise MemoryIntegrityError(
                    f"pattern {pattern_id!r} tercatat di provider tetapi reference-nya hilang"
                )

    return snapshot


@decision_path
def memory_root(source: MemorySnapshot | MemoryClient) -> bytes:
    """`memory_root = keccak(sorted(provider entities) || sorted(reference patterns))`.

    Menerima snapshot (dipakai `agent/memory_export.py`, task 2.1b) atau klien memori
    (dipakai agen). SATU implementasi untuk kedua jalur — bukan salinan.
    """
    snapshot = source if isinstance(source, MemorySnapshot) else load_snapshot(source)
    return _keccak(snapshot.preimage())


@decision_path
def memory_root_hex(source: MemorySnapshot | MemoryClient) -> str:
    return "0x" + memory_root(source).hex()


# ADR-020 keputusan 6 — encoding preimage DIBEKUKAN (task 2.1r). Yang dibekukan, apa adanya:
#   - preimage dari BODY MENTAH yang tersimpan, bukan proyeksi `ProviderProfile` yang lossy;
#   - setiap integer menjadi STRING DESIMAL dalam pembungkus `{"$u": "…"}` (tidak ada satu pun
#     bilangan JSON), sehingga `JSON.parse` di JS tidak merusak uint256 di atas 2^53;
#   - setiap kunci & body dibingkai PANJANG-BERPREFIKS, sehingga dua kunci berbeda mustahil
#     runtuh menjadi satu;
#   - cakupan keputusan 7: semua entity `provider` + semua `reference:pattern:*` +
#     semua `reference:rubric:*`, TERMASUK pattern yatim; `suspicion` TIDAK ikut (ADR-002);
#   - label versi ikut ter-hash, jadi encoding baru tidak bisa menyamar sebagai yang lama.
# Vektor uji beku ada di `agent/tests/fixtures/memory_root_vector.json` + root harapannya di
# `tests/test_memory_policy.py`; perubahan encoding apa pun membuatnya MERAH. Skrip
# `agent/tools/memory_root_check.mjs` menghitung ulang root yang sama di Node.
MEMORY_ROOT_ENCODING_FROZEN: Final = True


def memory_root_for_onchain(source: MemorySnapshot | MemoryClient) -> bytes:
    """Satu-satunya pintu root yang boleh dipakai `vault_client`/`postVerdict`.

    Gerbang ini tetap ada SESUDAH pembekuan: ia yang membuat "modul lain memanggil
    `memory_root` langsung" menjadi pelanggaran yang bisa dideteksi (tes memindai AST
    setiap modul agen), dan ia yang akan menolak lagi bila suatu saat encoding dibuka
    kembali. Mengumumkan root dari encoding yang masih berubah berarti `knownRoots` di
    vault berisi nilai yang tidak bisa direkonstruksi siapa pun, persis kegagalan yang
    dihancurkan juri fase 1.
    """
    if not MEMORY_ROOT_ENCODING_FROZEN:
        raise MemoryPolicyError(
            "encoding memory_root belum dibekukan (ADR-020 keputusan 6, task 2.1r) — "
            "DILARANG mengumumkan root turunan-memori on-chain sebelum itu"
        )
    return memory_root(source)


def empty_memory_root() -> bytes:
    """Root memori KOSONG — nol provider, nol pattern, nol rubric (task 2.4b).

    Dipakai HANYA oleh mode NAIF (ADR-024 keputusan 2 cabang 2: `memory.db` belum ada DAN
    vault belum pernah mengumumkan root). Di sana agen memang tidak punya satu pun profil,
    dan yang diumumkan `postVerdict` haruslah pernyataan yang BENAR tentang memori itu:
    "kosong". Membiarkan cabang naif memakai konstanta apa pun mengembalikan persis lubang
    yang ditutup 2.4b; menolak berjalan sama sekali akan mengubah mode naif menjadi mode
    aman, yang bertentangan dengan ADR-024 keputusan 3 tanpa ADR baru.

    JANGKAUAN, diukur (task 2.5a, ADR-026): lewat `--job-id` nilai ini TIDAK PERNAH sampai
    ke `postVerdict`, karena `plan_job` sudah membuat `memory.db` sebelum tx dan penjaga
    MODE_DRIFT menolak run pertama. Yang membuat itu tidak berakibat apa-apa ada di paragraf
    berikut: root DB yang baru dibuat itu SAMA PERSIS dengan nilai ini.

    Nilainya DIHITUNG dari encoding beku, bukan ditulis sebagai hex: ia otomatis ikut
    berubah bila encoding disentuh, dan ia identik dengan yang dicetak
    `python -m agent.memory_export --db <db kosong>` (dijaga tes). File memori yang hilang
    dan file memori yang ada tetapi kosong berisi hal yang SAMA — nol entri; yang dibedakan
    ADR-024 di antara keduanya adalah asal-usul, bukan isi, dan asal-usul bukan yang
    dijangkar root.
    """
    return memory_root_for_onchain(MemorySnapshot.from_mapping({}, {}, {}))


@decision_path
def count_job_outcomes(snapshot: MemorySnapshot) -> int:
    """Banyaknya JOB BERBEDA yang meninggalkan jejak di entity `provider` (ADR-023 2b).

    Dihitung dari `recorded_jobs` (setiap `record_job_outcome`) DIGABUNG `incident_jobs`
    (job yang gagal cek deterministik, termasuk yang masuk lewat promosi pola). Keduanya
    diperlukan: memori demo bisa berisi insiden hasil promosi tanpa `recorded_jobs`, dan
    memori agen berjalan bisa berisi `recorded_jobs` tanpa satu pun insiden. Union-nya
    diambil sebagai HIMPUNAN supaya satu job yang muncul di kedua daftar tidak dihitung dua
    kali dan urutan tidak berpengaruh.

    SEJAK ADR-024 angka ini TIDAK memutuskan apa pun: nol job outcome adalah mode NORMAL
    tanpa kalibrasi, bukan mode aman. Ia dilaporkan karena itulah angka yang membuat baris
    `MODE NORMAL` bisa dibaca manusia, dan karena `make demo` memakainya untuk membuktikan
    DB rantai 2.5 memang kosong sebelum job A (ADR-024 keputusan 5). Ia BUKAN ukuran
    kualitas memori dan tidak boleh dipakai sebagai itu — pihak yang bisa menulis
    `memory.db` bisa mengarangnya.

    Body yang rusak membuat `ProviderProfile.from_body` MELEMPAR; pemanggil memperlakukan
    itu sebagai memori yang tidak terbaca, yaitu mode aman.
    """
    jobs: set[int] = set()
    for name, body in snapshot.providers.items():
        profile = ProviderProfile.from_body(name, body)
        jobs.update(profile.recorded_jobs)
        jobs.update(profile.incident_jobs)
    return len(jobs)


@decision_path
def local_memory_evidence(
    client: MemoryClient, *, lock_timeout_seconds: float | None = None
) -> LocalMemoryEvidence:
    """Keadaan memori lokal dari SATU pembacaan DB (ADR-023 keputusan 2, ADR-024).

    Root dan jumlah job outcome lahir dari `MemorySnapshot` yang SAMA. Membaca DB dua kali
    berarti keduanya bisa menggambarkan dua keadaan yang berbeda (dua pembacaan terpisah
    tidak berbagi satu transaksi — api-facts §C.2), dan gerbang mode akan memutuskan atas
    keadaan yang tidak pernah ada.

    `lock_timeout_seconds` default `GATE_LOCK_TIMEOUT_SECONDS` (BUKAN 10 detik milik jalur
    TULIS): gerbang dibaca berkali-kali per transaksi, dan menunggu penuh di setiap
    pembacaan memakan anggaran waktu ADR-014 tanpa menambah keamanan apa pun — pembacaan
    yang gagal mengambil kunci sudah punya jawaban yang benar (mode aman), jadi menunggu
    lebih lama hanya menunda jawaban itu. Kunci ini REENTRAN, sehingga `load_snapshot` yang
    juga memakai `@under_memory_lock` di dalam blok ini tidak menunggu untuk kedua kalinya.

    Fungsi ini TIDAK menangkap kesalahan: `load_snapshot` yang melempar (memori rusak,
    kunci single-instance tidak didapat, hasil enumerasi terpotong) WAJIB terlihat oleh
    pemanggil, yang mengubahnya menjadi `LocalMemoryEvidence.unreadable(...)` → mode aman.
    """
    timeout = GATE_LOCK_TIMEOUT_SECONDS if lock_timeout_seconds is None else lock_timeout_seconds
    with locked_client(client, timeout_seconds=timeout):
        return _evidence_under_lock(client)


@decision_path
def _evidence_under_lock(client: MemoryClient) -> LocalMemoryEvidence:
    snapshot = load_snapshot(client)
    outcomes = count_job_outcomes(snapshot)
    return LocalMemoryEvidence.ok(
        job_outcomes=outcomes,
        root=memory_root_for_onchain(snapshot),
        detail=(
            f"{len(snapshot.providers)} provider, {len(snapshot.patterns)} pattern, "
            f"{outcomes} job outcome"
        ),
    )


# ======================================================================
# BAGIAN 3 — karantina & promosi (spec §3 aturan 2, ADR-002)
# Bagian ini BOLEH menyentuh entity karantina. Hasilnya masuk ke jalur keputusan HANYA
# lewat `provider.confirmed_patterns` + `reference:pattern`.
# ======================================================================


def quarantine_name(provider_address: str, pattern_id: str) -> str:
    """Nama entity karantina — spec §3: `f"{addr}:{pattern}"`.

    Kedua komponen divalidasi bentuknya, sehingga `:` hanya pernah muncul sebagai
    pemisah dan nama tidak bisa dipalsukan agar terbaca milik provider lain.
    """
    return f"{normalize_address(provider_address)}:{validate_pattern_id(pattern_id)}"


def split_quarantine_name(name: str) -> tuple[str, str] | None:
    """Kebalikan `quarantine_name`; `None` bila nama tidak berbentuk sah."""
    address, sep, pattern_id = name.partition(":")
    if not sep:
        return None
    try:
        return normalize_address(address), validate_pattern_id(pattern_id)
    except ValueError:
        return None


def _validated_evidence(evidence: Iterable[Evidence]) -> list[Evidence]:
    """Menolak bukti non-deterministik SEBELUM tersimpan (spec §3 aturan 2 & 3)."""
    validated: list[Evidence] = []
    for item in evidence:
        if not isinstance(item, Evidence):
            raise TypeError("bukti harus objek Evidence, bukan teks pihak")
        if not item.is_deterministic():
            raise MemoryPolicyError(
                f"check_id {item.check_id!r} bukan cek deterministik "
                f"{sorted(DETERMINISTIC_CHECK_IDS)} — klaim pihak tidak boleh menjadi bukti"
            )
        validated.append(item)
    return validated


def _parse_evidence_list(items: Iterable[Any]) -> list[Evidence]:
    """Bukti tersimpan yang rusak DILEWATI, bukan dilempar.

    Fail-closed: bukti yang tidak bisa dibaca tidak dihitung, sehingga entri rusak hanya
    bisa MENGHALANGI promosi, tidak pernah memicunya. Melempar dari sini akan membuat
    pemanggil (task 2.4a) crash pada satu baris memori rusak alih-alih masuk mode aman.
    """
    parsed: list[Evidence] = []
    for item in items:
        try:
            parsed.append(Evidence.from_body(item))
        except (TypeError, ValueError, AttributeError) as exc:
            log.warning("bukti karantina rusak dilewati", extra={"reason": str(exc)})
    return parsed


def _dedup_evidence(evidence: Iterable[Evidence]) -> list[Evidence]:
    """Duplikat (job_id, check_id) dibuang → job yang sama tidak bisa menaikkan count."""
    seen: set[tuple[int, str]] = set()
    unique: list[Evidence] = []
    for item in sorted(evidence, key=lambda e: (e.job_id, e.check_id, e.proof)):
        key = (item.job_id, item.check_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


@under_memory_lock
def record_suspicion(
    client: MemoryClient,
    provider_address: str,
    pattern_id: str,
    evidence: Evidence,
) -> dict[str, Any]:
    """WARM — spec §3 "Karantina". Menyimpan bukti; TIDAK memengaruhi keputusan apa pun.

    `count` yang disimpan adalah jumlah JOB BERBEDA, bukan jumlah bukti: bukti berulang
    dari job yang sama tidak boleh menggerakkan ambang promosi.
    """
    address = normalize_address(provider_address)
    pattern_id = validate_pattern_id(pattern_id)
    name = quarantine_name(address, pattern_id)

    existing: list[Evidence] = []
    try:
        row = client.get_entity(CATEGORY_QUARANTINE, name)
        existing = _parse_evidence_list((row["body"] or {}).get("evidence", []))
    except NotFoundError:
        existing = []

    merged = _dedup_evidence(_validated_evidence([*existing, evidence]))
    body = {
        "provider": address,
        "pattern": pattern_id,
        "count": len({e.job_id for e in merged}),
        "evidence": [e.to_body() for e in merged],
        "status": QUARANTINE_STATUS_PENDING,
    }
    client.set_entity(CATEGORY_QUARANTINE, name, body, status=QUARANTINE_STATUS_PENDING)
    write_journal(
        client,
        [{"action": "suspicion.record", "provider": address, "pattern": pattern_id,
          "job": evidence.job_id, "check": evidence.check_id, "count": body["count"]}],
    )
    return body


def promotion_eligible(evidence: Sequence[Evidence]) -> bool:
    """spec §3 aturan 2: >= 2 JOB BERBEDA dan SETIAP bukti dari cek deterministik.

    `Evidence` mengkoersi `job_id` ke int di konstruktornya, jadi `7` dan `"7"` adalah
    job yang SAMA di sini — tanpa itu satu job bisa menyamar sebagai dua.
    """
    if not evidence:
        return False
    if not all(isinstance(e, Evidence) for e in evidence):
        raise TypeError("promotion_eligible hanya menerima objek Evidence")
    if not all(e.is_deterministic() for e in evidence):
        return False
    return len({e.job_id for e in evidence}) >= 2


@under_memory_lock
def promote_suspicions(client: MemoryClient, provider_address: str) -> list[str]:
    """Mempromosikan karantina yang memenuhi syarat → `reference:pattern` + provider.

    Kepemilikan entri diperiksa TIGA kali (nama, field `provider` di body, dan bentuk
    nama yang di-parse ulang), bukan dengan `startswith` saja: pencocokan awalan pada
    nama yang tidak tervalidasi membuat entri milik provider lain ikut terpromosi.
    """
    address = normalize_address(provider_address)
    promoted: list[str] = []

    rows = _list_all(client, CATEGORY_QUARANTINE, status=QUARANTINE_STATUS_PENDING)
    for row in rows:
        parsed = split_quarantine_name(row["name"])
        if parsed is None or parsed[0] != address:
            continue
        pattern_id = parsed[1]
        body = row["body"] or {}
        if body.get("provider") != address or body.get("pattern") != pattern_id:
            log.warning(
                "entri karantina tidak konsisten dengan namanya; dilewati",
                extra={"entity_name": row["name"]},
            )
            continue

        evidence = _dedup_evidence(
            [e for e in _parse_evidence_list(body.get("evidence", [])) if e.is_deterministic()]
        )
        if not promotion_eligible(evidence):
            continue

        jobs = sorted({e.job_id for e in evidence})
        client.set_reference(
            f"{REFERENCE_PATTERN_PREFIX}{pattern_id}",
            {
                "pattern_id": pattern_id,
                "description": f"pola gagal deterministik terkonfirmasi pada {len(jobs)} job berbeda",
                "detectors": sorted({e.check_id for e in evidence}),
                "examples": [e.to_body() for e in evidence],
            },
        )
        _add_confirmed_pattern(client, address, pattern_id, jobs)
        client.set_entity(
            CATEGORY_QUARANTINE,
            row["name"],
            {**body, "status": QUARANTINE_STATUS_PROMOTED},
            status=QUARANTINE_STATUS_PROMOTED,
        )
        write_journal(
            client,
            [{"action": "suspicion.promote", "provider": address, "pattern": pattern_id, "jobs": jobs}],
        )
        promoted.append(pattern_id)

    return sorted(promoted)


def _current_provider_version(client: MemoryClient, address: str) -> int:
    try:
        row = client.get_entity(CATEGORY_PROVIDER, address)
    except NotFoundError:
        return 0
    try:
        return int((row["body"] or {}).get("version", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise MemoryIntegrityError(f"versi entity provider {address!r} rusak: {exc}") from exc


@under_memory_lock
def _save_provider_cas(
    client: MemoryClient, profile: ProviderProfile, expected_version: int
) -> ProviderProfile:
    """Tulis provider hanya bila versinya masih seperti saat dibaca.

    JUJUR TENTANG BATASNYA: ini compare-and-swap yang jendelanya TIDAK BISA diatomkan lewat
    API publik. `sibyl-memory-client` 0.7.0 MEMANG mengekspos `Storage.transaction()` yang
    atomik, tetapi `set_entity` membuka transaksinya sendiri di sambungan yang sama, jadi
    membungkus baca-versi + tulis di dalam satu transaksi melempar `cannot start a
    transaction within a transaction` dan tulisannya HILANG (api-facts §C.2). Jendela antara
    baca-versi dan tulis karena itu tetap tidak atomik. Yang dijamin: tulisan yang dibangun dari
    snapshot USANG ditolak, sehingga satu tulisan basi tidak bisa mengembalikan provider
    ber-insiden ke risk 0 tanpa cap (dan tidak bisa membuka kembali replay). Yang TIDAK
    dijamin oleh CAS itu sendiri: dua proses agen yang menulis DB yang sama. Itu ditutup
    di lapisan lain — `@under_memory_lock` memegang kunci single-instance selama SELURUH
    pemanggilan ini, jadi proses kedua berhenti dengan `MemoryLockError` alih-alih
    menyelinap ke dalam jendela cek-lalu-tulis.
    """
    current = _current_provider_version(client, profile.address)
    if current != expected_version:
        raise StaleWriteError(
            f"tulisan provider {profile.address} berbasis versi {expected_version}, "
            f"tetapi memori sudah di versi {current} — tulisan ditolak"
        )
    return save_provider(client, replace(profile, version=expected_version + 1))


def _load_provider_for_write(client: MemoryClient, address: str) -> ProviderProfile:
    """Pembacaan provider untuk jalur TULIS (di luar jalur keputusan)."""
    name = normalize_address(address)
    try:
        row = client.get_entity(CATEGORY_PROVIDER, name)
    except NotFoundError:
        return ProviderProfile(address=name)
    return ProviderProfile.from_body(name, row["body"])


def _recompute_risk(profile: ProviderProfile) -> int:
    """Risk = jumlah JOB insiden deterministik, dijepit ke `MAX_RISK_LEVEL`.

    Semuanya berasal dari cek agen sendiri (spec §3 aturan 3); tidak ada masukan dari
    teks pihak, dan entity karantina TIDAK pernah dibaca oleh jalur keputusan.
    """
    return min(MAX_RISK_LEVEL, len(set(profile.incident_jobs)))


@under_memory_lock
def _add_confirmed_pattern(
    client: MemoryClient, address: str, pattern_id: str, jobs: Sequence[int]
) -> ProviderProfile:
    profile = _load_provider_for_write(client, address)
    updated = replace(
        profile,
        confirmed_patterns=tuple(sorted({*profile.confirmed_patterns, pattern_id})),
        incident_jobs=tuple(sorted({*profile.incident_jobs, *(int(j) for j in jobs)})),
    )
    return _save_provider_cas(
        client, replace(updated, risk_level=_recompute_risk(updated)), profile.version
    )


def _client_funded_its_own_job(client_address: str | None, provider_address: str) -> bool:
    """Filter ADR-021 keputusan 2, dengan `client_address` RUSAK sebagai galat BERJENIS.

    Tiga keadaan, dan ketiganya harus dibedakan (task 2.4a AC (j)):
      - `None` = TIDAK DIKETAHUI. Sah: pemanggil yang memang tidak punya `getJob` (mis.
        pemulihan tangan) tetap boleh merekam outcome; filternya hanya tidak menyala.
      - alamat yang sah = dibandingkan PERSIS dengan provider (case-insensitive lewat
        `normalize_address`, definisi alamat yang SATU untuk seluruh modul ini).
      - apa pun yang lain (`""`, `"0x"`, bytes, int) = hasil `getJob` yang GAGAL. Ia
        DILARANG diperlakukan seperti "tidak diketahui": diam-diam menjadi
        `self_funded=False` berarti menjalankan filter ADR-021 keputusan 2 dalam keadaan
        MATI, dan budget yang dikendalikan provider masuk ke median cap tanpa satu baris
        pun yang mengatakannya. Jadi outcome-nya ditolak, bukan direkam separuh benar.

    Galatnya `MemoryIntegrityError`, bukan `ValueError` mentah: yang gagal bukan "argumen
    salah ketik" melainkan "bukti yang menjadi dasar tulisan ini tidak bisa dipercaya",
    dan itu kelas yang sama dengan memori yang tidak bisa dijadikan preimage jujur.

    Perbedaan jenis itu MENGIKAT, bukan dekoratif: `vault_client.main()` mendaftarkan
    `MemoryIntegrityError` di handler yang sama dengan `SafeModeStop` (`EXIT_REFUSED` bila
    nol tx, laporan "berhenti di tengah pipa" bila sudah ada yang mendarat), sedangkan
    `ValueError` mentah jatuh ke `except Exception` generik dan terbaca sebagai bug Python.
    Ia BUKAN turunan `SafeModeStop` — kelas itu hidup di `vault_client`, dan modul ini
    dilarang mengimpornya — jadi yang menyamakan perlakuannya adalah tuple di handler itu.
    """
    if client_address is None:
        return False
    try:
        normalized = normalize_address(client_address)
    except ValueError as exc:
        raise MemoryIntegrityError(
            f"client_address {client_address!r} tidak berbentuk alamat EVM — hasil `getJob` "
            "yang gagal DILARANG dipakai: filter ADR-021 keputusan 2 (client == provider → "
            "budget dibuang) tidak bisa dievaluasi, jadi outcome ini ditolak alih-alih "
            "direkam dengan filter yang mati"
            # Sebab aslinya menempel lewat `raise ... from exc`, TIDAK disalin ke teks:
            # pesan `normalize_address` berbunyi "alamat PROVIDER", dan menyalinnya ke
            # sini akan menunjuk operator ke alamat yang salah.
        ) from exc
    return normalized == normalize_address(provider_address)


@under_memory_lock
def record_job_outcome(
    client: MemoryClient,
    provider_address: str,
    job_id: int,
    budget: int,
    passed: bool,
    failed_checks: Sequence[str] = (),
    client_address: str | None = None,
) -> ProviderProfile:
    """Memperbarui `provider` dari HASIL CEK agen (spec §3 aturan 3), bukan dari klaim pihak.

    `client_address` diambil dari `getJob(jobId)` — `client` TIDAK indexed di `JobFunded`
    — dan dipakai untuk ADR-021 keputusan 2: bila ia PERSIS sama dengan alamat provider,
    budgetnya dibuang dan `stats.jobs` tetap naik. Nilainya boleh `None` (= TIDAK
    DIKETAHUI), tetapi TIDAK boleh RUSAK: `""`/`"0x"` dari `getJob` yang gagal menghasilkan
    `MemoryIntegrityError` (`_client_funded_its_own_job`), bukan tulisan dengan filter
    yang mati.

    Defaultnya `None` semata-mata supaya "tidak diketahui" bisa diucapkan; ia BUKAN izin
    untuk melewatkannya. Setiap pemanggil DI DALAM paket `agent/` wajib mengikat
    `client_address` (keyword atau posisi ke-7), karena satu pemanggil yang lupa membuat
    filter ADR-021 keputusan 2 mati DIAM-DIAM: tidak ada galat, tidak ada baris log, hanya
    cap yang tidak pernah turun. DUA penjaga menegakkannya, dan masing-masing hanya
    sejauh yang tertulis di sini:
      - pemindai AST atas seluruh berkas paket
        (`tests/test_job_pipeline.py::test_every_production_call_of_record_job_outcome_passes_client_address`)
        — menangkap juga kode yang TIDAK PERNAH dieksekusi suite, tetapi hanya BENTUK yang
        bisa dibaca statis; nama yang dirakit saat jalan (`"record_job" + "_outcome"`)
        tidak terlihat olehnya, dan tesnya mengatakan itu apa adanya;
      - penjaga RUNTIME (`tests/conftest.py`) yang membungkus fungsi ini selama seluruh
        suite dan menolak panggilan dari berkas di dalam `agent/agent/` yang tidak
        mengikat parameternya — bentuknya tidak relevan sama sekali, jadi `getattr`,
        `partial`, tabel dispatch dan sejenisnya ikut tertangkap.
    YANG TIDAK DIJAGA keduanya, dan sengaja: pemanggil DI LUAR paket ini (berkas tes,
    proses anak, skrip pemulihan tangan). Bagi mereka `client_address=None` yang DIKETIK
    tetap sah — yang ditolak adalah nilai RUSAK, dan itu urusan `_client_funded_its_own_job`.

    Job yang DITOLAK/Expired hanya menaikkan `stats.reject` (dan, bila ada cek deterministik
    yang gagal, menjadi insiden). Budgetnya TIDAK disimpan di mana pun — ADR-020 keputusan 2.

    IDEMPOTEN PER `job_id`. Job yang sudah pernah tercatat (`recorded_jobs`) tidak pernah
    dihitung dua kali, dan pemanggilan ulangnya TIDAK menulis apa pun. Dedup ada DI SISI
    MEMORI, bukan diserahkan ke watcher, karena watcher bukan satu-satunya sumber
    pemanggilan: replay log dan `last_block` yang mundur sesudah reorg sama-sama masuk
    lewat sini.

    BATAS YANG DIAKUI (jangan dibaca lebih jauh dari ini): idempotensi itu cek-lalu-tulis
    yang tidak bisa dibungkus satu transaksi SDK (api-facts §C.2). Tulisan dari snapshot
    USANG ditolak CAS versi
    (`_save_provider_cas`, `StaleWriteError`), dan jendela antara baca dan tulis ditutup
    `@under_memory_lock` — bukan oleh atomisitas SDK, melainkan oleh larangan instans kedua
    (`flock` atas `<memory.db>.lock`, task 2.4a). Sifatnya kooperatif: penulis DB yang tidak
    memakai modul ini tetap tidak terhalang.
    """
    for check_id in failed_checks:
        if check_id not in DETERMINISTIC_CHECK_IDS:
            raise MemoryPolicyError(
                f"check_id {check_id!r} bukan cek deterministik — risk hanya boleh naik dari cek sendiri"
            )
    if isinstance(job_id, bool) or not isinstance(job_id, int):
        raise TypeError(f"job_id harus int, dapat {type(job_id).__name__}")
    if isinstance(budget, bool) or not isinstance(budget, int):
        raise TypeError(f"budget harus int, dapat {type(budget).__name__}")
    if budget < 0 or budget > MAX_UINT256:
        raise ValueError("budget di luar rentang uint256")

    # ADR-021 keputusan 2: job yang didanai oleh alamat provider itu sendiri tidak boleh
    # menyumbang angka apa pun ke cap. Filternya di TITIK MASUK — tidak ada field baru di
    # body provider, jadi preimage `memory_root` tidak berubah sama sekali.
    # "Sekerabat" BERHENTI di kesamaan alamat PERSIS (keputusan 3): deteksi EOA kedua
    # adalah masalah Sybil terbuka, dan kita memagari BESARNYA kerugian lewat plafon
    # pertumbuhan, bukan berpura-pura menyelesaikannya.
    self_funded = _client_funded_its_own_job(client_address, provider_address)

    profile = _load_provider_for_write(client, provider_address)
    if job_id in profile.recorded_jobs:
        log.info(
            "record_job_outcome: job sudah tercatat, diabaikan (idempoten)",
            extra={"provider": profile.address, "job_id": job_id},
        )
        return profile

    incidents = set(profile.incident_jobs)
    passed_budgets = list(profile.passed_budgets)
    if passed and self_funded:
        log.warning(
            "budget job yang didanai sendiri tidak direkam (client == provider)",
            extra={"provider": profile.address, "job_id": job_id},
        )
    elif passed:
        # ADR-020 keputusan 2: budget hanya tercatat bila job berakhir Completed.
        passed_budgets.append(budget)
    elif failed_checks:
        incidents.add(job_id)

    updated = replace(
        profile,
        incident_jobs=tuple(sorted(incidents)),
        recorded_jobs=tuple(sorted({*profile.recorded_jobs, job_id})),
        passed_budgets=tuple(sorted(passed_budgets)),
        stats_jobs=profile.stats_jobs + 1,
        stats_pass=profile.stats_pass + (1 if passed else 0),
        stats_reject=profile.stats_reject + (0 if passed else 1),
    )
    updated = _save_provider_cas(
        client, replace(updated, risk_level=_recompute_risk(updated)), profile.version
    )
    write_journal(
        client,
        [{"action": "job.outcome", "provider": updated.address, "job": job_id,
          "budget": budget, "passed": bool(passed), "self_funded": self_funded,
          "failed_checks": sorted(failed_checks)}],
    )
    return updated


@under_memory_lock
def store_provider_cap(client: MemoryClient, provider_address: str, decision: CapPlan) -> ProviderProfile:
    """Menyimpan cap terakhir ke profil provider (untuk audit; keputusan tetap dihitung ulang)."""
    profile = _load_provider_for_write(client, provider_address)
    return _save_provider_cas(client, replace(profile, cap_usdc=decision.cap_usdc), profile.version)


# `@decision_path_forward` (fungsi yang berada di atas definisi `decision_path`) didaftarkan
# di sini, supaya ia diperiksa tes sumber & tes properti karantina yang SAMA.
def _register_forward_decision_paths() -> None:
    for fn in _FORWARD_DECISION_PATHS:
        DECISION_PATH_FUNCTIONS.add(fn.__qualname__)


_register_forward_decision_paths()
