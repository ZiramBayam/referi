"""Kebijakan memori evaluator — skema `docs/spec.md` §3 + `derive_cap` + fail-closed.

Modul ini adalah SATU-SATUNYA tempat kode agen menyentuh Sibyl Memory. Ia dibagi tegas
menjadi tiga bagian, dan pemisahan itu bukan gaya penulisan melainkan kontrol keamanan:

  BAGIAN 1 — pemetaan tier §3 (I/O memori mentah).
  BAGIAN 2 — JALUR KEPUTUSAN. Satu-satunya pintu baca adalah `DecisionMemoryView`, yang
             HANYA mengizinkan entity `provider` dan reference berawalan `pattern:`.
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
  - docs/decisions.md ADR-001 (cap 0 di kontrak = TANPA BATAS), ADR-002 (karantina =
    entity, bukan tier), ADR-007 + amandemennya (fail-closed), ADR-011 (root yang pernah
    diumumkan), ADR-019 keputusan 4 (median saat himpunan budget lolos kosong).

Modul ini MURNI lokal: tidak ada jaringan, tidak ada chain, tidak ada LLM.

BATAS YANG DIAKUI — KETERSEDIAAN (jangan dianggap tidak ada karena tidak disebut):
  Modul ini fail-closed dan TIDAK punya jalur pemulihan sendiri. Bila `list_entities`
  menyentuh `LIST_LIMIT`, bila ada dua nama entity provider yang bertabrakan setelah
  normalisasi, bila body sebuah entity rusak, atau bila sebuah `reference:pattern` hilang,
  maka `memory_root()` MELEMPAR — dan ia akan terus melempar sampai seseorang memperbaiki
  isi memori dari luar. Konsekuensinya bagi agen: mode aman (task 2.4a), yaitu tidak ada
  `postVerdict`/`finalize`/`setProviderCap`, job MENGGANTUNG sampai `expiredAt`, lalu siapa
  pun boleh `claimRefund` dan client menerima refund penuh. Jadi pihak yang bisa menulis ke
  `memory.db` bisa mematikan ketersediaan evaluator, TIDAK bisa mencuri dana, dan TIDAK bisa
  memaksa verdict. Itu pertukaran yang dipilih sadar (ADR-020 keputusan 8), bukan kelalaian.

UTANG YANG DIAKUI (jangan dibaca seolah sudah selesai):
  - Bentuk AKHIR encoding preimage `memory_root` MENUNGGU putusan product-manager.
    Yang sudah ditegakkan di sini: preimage memakai BODY MENTAH yang tersimpan (bukan
    proyeksi), menolak tabrakan nama, dan bebas dari bilangan JSON (semua integer menjadi
    string desimal bertanda) supaya dapat direkonstruksi di TypeScript/JS. Formatnya
    boleh berubah bila PM memutuskan lain — 2.1b/2.4b memakai fungsi ini, bukan salinan.
  - Idempotensi tulisan provider dijaga CAS versi, tetapi store-nya TIDAK transaksional
    (api-facts §C tidak punya transaksi) — dua proses agen pada satu `memory.db` tetap
    DILARANG secara operasional, bukan dicegah oleh kode.
  - Cap BUKAN deteksi (ADR-021 keputusan 4). Ia hanya membatasi UKURAN kerugian per job;
    yang mendeteksi deliverable curang adalah cek deterministik (task 2.3), dan yang
    menghentikan agen saat memori tidak dipercaya adalah mode aman (task 2.4a).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final

from sibyl_memory_client import MemoryClient, NotFoundError

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
ADDRESS_RE: Final = re.compile(r"^0x[0-9a-f]{40}$")
PATTERN_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_PROOF_LEN: Final = 512
MAX_UINT256: Final = 2**256 - 1


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


def _canonical_value(value: Any, depth: int = 0) -> Any:
    """Bentuk kanonik lintas-bahasa: tanpa bilangan JSON, tanpa float, kunci ASCII."""
    if depth > 32:
        raise MemoryIntegrityError("body memori terlalu dalam untuk dikanonikkan")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return {NUMBER_TAG: str(value)}
    if isinstance(value, float):
        raise MemoryIntegrityError(
            "float tidak boleh masuk preimage memory_root (tidak dapat direproduksi lintas bahasa)"
        )
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise MemoryIntegrityError(f"kunci body harus string ASCII, dapat {key!r}")
            if key == NUMBER_TAG:
                raise MemoryIntegrityError(f"kunci {NUMBER_TAG!r} dipesan untuk penanda integer")
            out[key] = _canonical_value(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item, depth + 1) for item in value]
    raise MemoryIntegrityError(f"tipe {type(value).__name__} tidak dapat dikanonikkan")


def canonical_json(value: Any) -> str:
    """JSON kanonik: kunci terurut, tanpa spasi, ASCII murni, tanpa bilangan JSON.

    `ensure_ascii=True` + kunci wajib ASCII disengaja: hasilnya bebas dari pilihan
    encoding, locale, maupun perbedaan urutan sort antar bahasa.
    """
    return json.dumps(_canonical_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sorted_pairs(mapping: Mapping[str, Any]) -> list[list[Any]]:
    """Pasangan (kunci, isi) terurut menurut BYTE kuncinya — bukan menurut locale."""
    return [[key, mapping[key]] for key in sorted(mapping, key=lambda k: k.encode("utf-8"))]


def _keccak(data: bytes) -> bytes:
    # Impor lokal: web3 hanya dibutuhkan untuk hash, dan modul ini harus tetap ringan
    # bila dipakai dari alat ekspor.
    from web3 import Web3

    return bytes(Web3.keccak(data))


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
    """Keputusan gating saat `JobFunded` (spec §5 langkah 2)."""

    accept: bool
    reason: str
    cap: CapPlan
    mode: ModeDecision
    depth: str


@dataclass(frozen=True)
class MemorySnapshot:
    """Potongan memori yang menjadi PREIMAGE `memory_root` (spec §3 baris 123).

    Isinya adalah BODY MENTAH yang tersimpan di Sibyl, bukan proyeksi `ProviderProfile`:
    proyeksi bersifat lossy, sehingga field asing, perbedaan tipe, dan bahkan entity yang
    saling menimpa setelah normalisasi nama akan menghasilkan root yang IDENTIK — artinya
    root tidak lagi mengikat isi memori yang diaudit.

    Satu jalur mengisinya dari DB Sibyl (`load_snapshot`), jalur lain dari file JSON hasil
    ekspor (task 2.1b) — keduanya memakai `memory_root()` yang SAMA, bukan salinan.
    """

    providers: dict[str, Any] = field(default_factory=dict)
    patterns: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, providers: Mapping[str, Any], patterns: Mapping[str, Any]) -> MemorySnapshot:
        """Membangun snapshot TANPA menormalkan kunci; tabrakan nama DITOLAK, bukan digabung."""
        checked: dict[str, Any] = {}
        seen: dict[str, str] = {}
        for name, body in providers.items():
            normalized = normalize_address(name)
            if normalized in seen:
                raise MemoryIntegrityError(
                    f"dua entity provider bertabrakan setelah normalisasi: {seen[normalized]!r} "
                    f"dan {name!r} — satu di antaranya akan tersembunyi dari audit"
                )
            seen[normalized] = name
            checked[name] = body
        return cls(providers=checked, patterns={str(k): v for k, v in patterns.items()})

    def to_canonical_obj(self) -> dict[str, Any]:
        """Bentuk kanonik yang di-hash. Urutan penyisipan tidak berpengaruh."""
        return {
            "providers": _sorted_pairs(self.providers),
            "patterns": _sorted_pairs(self.patterns),
        }

    def preimage(self) -> bytes:
        return canonical_json(self.to_canonical_obj()).encode("utf-8")


# ======================================================================
# BAGIAN 1 — pemetaan tier §3 (I/O memori mentah)
# ======================================================================


def set_active_job(client: MemoryClient, job_id: int | str, body: Mapping[str, Any]) -> None:
    """HOT — spec §3 "Job aktif": `set_state("job:{id}", {...})`."""
    client.set_state(f"{STATE_KEY_PREFIX}{job_id}", dict(body))


def get_active_job(client: MemoryClient, job_id: int | str) -> dict[str, Any] | None:
    """HOT — `get_state` mengembalikan PEMBUNGKUS `{'body':…}` (api-facts §C), bukan body."""
    row = client.get_state(f"{STATE_KEY_PREFIX}{job_id}")
    return None if row is None else row["body"]


def save_provider(client: MemoryClient, profile: ProviderProfile) -> ProviderProfile:
    """WARM — spec §3 "Profil provider"."""
    client.set_entity(CATEGORY_PROVIDER, profile.address, profile.to_body())
    return profile


def save_client_profile(client: MemoryClient, address: str, body: Mapping[str, Any]) -> None:
    """WARM — spec §3 "Profil client" (kualitas kriteria, sengketa yang ternyata salah)."""
    client.set_entity(CATEGORY_CLIENT, normalize_address(address), dict(body))


def write_journal(client: MemoryClient, acted: Sequence[Mapping[str, Any]]) -> str:
    """COLD — spec §3 "Verdict & cek". `write_event` SELURUHNYA keyword-only (api-facts §C)."""
    return client.write_event(acted=[dict(item) for item in acted])


def set_rubric(client: MemoryClient, category: str, body: Mapping[str, Any]) -> None:
    """REFERENCE — spec §3 "Rubric per kategori"."""
    client.set_reference(f"{REFERENCE_RUBRIC_PREFIX}{category}", dict(body))


def get_rubric(client: MemoryClient, category: str) -> dict[str, Any] | None:
    return _read_reference_body(client, f"{REFERENCE_RUBRIC_PREFIX}{category}")


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


@decision_path
def _guard_reference_key(key: Any) -> str:
    """Reference yang boleh dibaca jalur keputusan.

    HANYA `pattern:`. `rubric:` SENGAJA TIDAK diizinkan di sini meskipun ADR-020
    keputusan 7 memasukkannya ke cakupan root: penjangkarannya (`reference:rubric:*` dan
    pattern YATIM) baru mendarat di task 2.1r. Urutannya jangkar dulu, baru baca —
    melebarkan baca lebih dulu justru MEMPERLUAS keadaan "dibaca tapi tidak dijangkar",
    yaitu permukaan tempat teks pihak bisa memengaruhi keputusan tanpa mengubah root.
    Sampai 2.1r hijau, batas ini juga tetap sama persis dengan spec §3 aturan 1 yang
    belum diamandemen (`provider` + `reference:pattern`).
    """
    if not isinstance(key, str) or not key.startswith(REFERENCE_PATTERN_PREFIX):
        raise ForbiddenReadError(
            f"jalur keputusan hanya boleh membaca reference berawalan "
            f"{REFERENCE_PATTERN_PREFIX!r}, diminta {key!r} (docs/spec.md §3 aturan 1)"
        )
    return key


class _GuardedReader:
    """Klien memori TERBATAS: satu-satunya benda yang dipegang jalur keputusan.

    Ini penegakan STRUKTURAL, bukan konvensi. Sebelumnya penjaga adalah panggilan
    SUKARELA: metode `DecisionMemoryView` memegang klien Sibyl penuh, jadi satu baris
    `self.__client.list_entities("suspicion")` (nama kategori boleh disamarkan agar tes
    sumber buta, dan disyaratkan pada masukan yang tidak ada di ruang sampel tes properti)
    melewati ketiga lapis tes sekaligus. Sekarang klien penuh TIDAK PERNAH terjangkau dari
    jalur keputusan: yang dipegang adalah objek ini, dan objek ini melempar untuk kategori
    /kunci di luar daftar putih, DAN untuk metode apa pun yang tidak tercantum di bawah
    (`get_state`, `read_events`, `search`, `search_entities`, `set_*`, …).

    Karena penjaga hidup di LAPISAN KLIEN, "lupa memanggil penjaga" bukan lagi mode
    kegagalan yang mungkin.
    """

    __slots__ = ("__client",)

    def __init__(self, client: MemoryClient) -> None:
        self.__client = client

    def get_entity(self, category: str, name: str) -> dict[str, Any]:
        return self.__client.get_entity(_guard_category(category), name)

    def list_entities(
        self, category: str | None = None, *, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        return self.__client.list_entities(_guard_category(category), status=status, limit=limit)

    def get_reference(self, key: str) -> dict[str, Any] | None:
        return self.__client.get_reference(_guard_reference_key(key))

    def __getattr__(self, name: str) -> Any:
        raise ForbiddenReadError(
            f"jalur keputusan tidak boleh memanggil {name!r} pada memori; hanya "
            "get_entity/list_entities('provider') dan get_reference('pattern:*') "
            "(docs/spec.md §3 aturan 1)"
        )


class DecisionMemoryView:
    """Pintu baca TUNGGAL jalur keputusan.

    Empat hal yang disengaja:
      1. Yang disimpan adalah `_GuardedReader`, BUKAN klien Sibyl. Jadi tidak ada jalan
         dari dalam kelas ini menuju kategori `suspicion` — penjaga tidak bisa "tidak
         dipanggil", karena ia ada di lapisan klien.
      2. Atribut ber-name-mangling + `__slots__`: tidak ada `view._client`, dan tidak ada
         atribut baru yang bisa ditanam dari modul lain.
      3. Penjaga membandingkan dengan KONSTANTA LITERAL, bukan daftar putih yang bisa
         dilebarkan dari file lain.
      4. `gate_job` menuntut tipe PERSIS kelas ini, jadi subclass yang melonggarkan
         penjaga pun tidak diterima.
    """

    __slots__ = ("__reader",)

    def __init__(self, client: MemoryClient) -> None:
        self.__reader = client if isinstance(client, _GuardedReader) else _GuardedReader(client)

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
def decide_mode(onchain_root: Any, local_root: Any) -> ModeDecision:
    """spec §3 aturan 5 — fail-closed. Fungsi MURNI: tanpa I/O jaringan maupun chain.

    Pembacaan `lastMemoryRoot()` dan penegakan "tidak mengirim tx" adalah task 2.4a; di
    sini modenya dikembalikan sebagai nilai.

      - root onchain TERBACA dan bernilai nol (hari pertama) → NAIF (stateless), wajar;
      - root onchain ada DAN memori lokal cocok                → NORMAL;
      - root onchain ada TAPI lokal hilang/tidak cocok         → AMAN;
      - root onchain TIDAK TERBACA (None, "0x", "", tipe asing)→ AMAN.

    Baris terakhir memisahkan "root terbaca = 0" dari "root tidak terbaca". Keduanya
    tampak seperti "kosong", tetapi hanya yang pertama berarti hari pertama; yang kedua
    berarti kita tidak tahu keadaan chain, dan ketidaktahuan TIDAK PERNAH boleh memberi
    izin lebih besar.

    Dalam mode AMAN `postVerdict` juga ditahan: ADR-011 mencatat bahwa fail-closed kini
    murni dijaga di sisi agen — tidak ada root baru diumumkan, jadi tidak ada verdict baru
    yang bisa difinalisasi. (Spec §3 baris 117 secara harfiah hanya melarang `finalize`;
    ADR-011 lebih ketat dan itu yang diikuti.)
    """
    onchain, onchain_ok = _read_root(onchain_root)
    local, local_ok = _read_root(local_root)

    if not onchain_ok:
        return _safe_decision("root onchain tidak terbaca (nilai tidak sah) → tidak boleh menebak")

    if onchain == ZERO_ROOT:
        return ModeDecision(
            mode=MODE_NAIVE,
            reason="root onchain terbaca dan bernilai nol (hari pertama) → evaluasi stateless",
            depth=DEPTH_SAMPLING,
            forced_risk=None,
            allow_finalize=True,
            allow_post_verdict=True,
            allow_set_provider_cap=True,
        )

    if local_ok and local != ZERO_ROOT and local == onchain:
        return ModeDecision(
            mode=MODE_NORMAL,
            reason="root lokal cocok dengan root onchain",
            depth=DEPTH_SAMPLING,
            forced_risk=None,
            allow_finalize=True,
            allow_post_verdict=True,
            allow_set_provider_cap=True,
        )

    hilang = (not local_ok) or local == ZERO_ROOT
    return _safe_decision(
        "root onchain ada tetapi memori lokal hilang"
        if hilang
        else "root onchain ada tetapi root lokal tidak cocok"
    )


# ADR-020 keputusan 8. Kalimat ini dibawa APA ADANYA ke `reason` mode aman: konsekuensinya
# diucapkan, bukan diperhalus menjadi "ditolak dengan aman".
SAFE_MODE_CONSEQUENCE: Final = (
    "agen berhenti total: tidak ada postVerdict, tidak ada finalize, tidak ada setProviderCap; "
    "job MENGGANTUNG sampai expiredAt, lalu siapa pun boleh claimRefund dan client menerima "
    "refund penuh"
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
def safe_mode(onchain_root: Any, local_root: Any) -> bool:
    """Pintasan boolean atas `decide_mode` (spec §3 aturan 5)."""
    return decide_mode(onchain_root, local_root).is_safe


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

    Cap juga MONOTON TIDAK-NAIK per provider: bila profil sudah punya `cap_usdc`, hasilnya
    tidak pernah melebihi nilai itu. Pemulihan reputasi adalah v2 dan DILARANG diklaim hidup.
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
) -> GateDecision:
    """spec §5 langkah 2 — gating saat `JobFunded`, murni dari `provider` + mode."""
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

    if cap.cap_usdc is not None and int(budget) > cap.cap_usdc:
        incidents = len(profile.incident_jobs)
        return GateDecision(
            accept=False,
            reason=(
                f"budget {budget} melebihi cap milestone provider ini "
                f"({cap.cap_usdc}; riwayat: {incidents} insiden terkonfirmasi)"
            ),
            cap=cap,
            mode=mode,
            depth=depth,
        )
    return GateDecision(
        accept=True, reason="budget dalam batas cap", cap=cap, mode=mode, depth=depth
    )


# ----------------------------------------------------------------------
# Jangkar memori (spec §3 baris 123) — jalur keputusan & jalur audit yang SAMA
# ----------------------------------------------------------------------


@decision_path
def load_snapshot(client: MemoryClient) -> MemorySnapshot:
    """Membaca preimage root dari DB: entity `provider` + reference `pattern:*`.

    Yang dimasukkan adalah NAMA dan BODY apa adanya dari baris DB, bukan hasil parsing —
    kalau tidak, field asing dan perbedaan tipe tidak akan mengubah root, dan root
    berhenti menjadi bukti atas isi memori yang diaudit.

    Daftar pattern diturunkan dari gabungan `confirmed_patterns` seluruh provider, bukan
    dari enumerasi reference: paket 0.7.0 tidak punya `list_references` yang terverifikasi
    (api-facts §C), dan promosi (BAGIAN 3) selalu menulis KEDUANYA sekaligus. Bila sebuah
    pattern tercatat di provider tetapi referensinya hilang, itu memori yang rusak → dilempar,
    dan pemanggil (task 2.4a) memperlakukannya sebagai mode AMAN.
    """
    view = DecisionMemoryView(client)
    raw = view.raw_providers()
    snapshot = MemorySnapshot.from_mapping(dict(raw), {})
    if len(snapshot.providers) != len(raw):
        raise MemoryIntegrityError("nama entity provider duplikat pada hasil list_entities")

    pattern_ids: set[str] = set()
    for name, body in raw:
        pattern_ids.update(ProviderProfile.from_body(name, body).confirmed_patterns)

    patterns: dict[str, Any] = {}
    for pattern_id in sorted(pattern_ids):
        body = view.raw_pattern(pattern_id)
        if body is None:
            raise MemoryIntegrityError(
                f"pattern {pattern_id!r} tercatat di provider tetapi reference-nya hilang"
            )
        patterns[f"{REFERENCE_PATTERN_PREFIX}{pattern_id}"] = body

    return MemorySnapshot(providers=snapshot.providers, patterns=patterns)


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


# ADR-020 keputusan 6: encoding preimage BELUM BEKU. Yang sudah mendarat di sini: preimage
# dari body MENTAH, integer sebagai string desimal, dan penolakan tabrakan kunci. Yang BELUM
# (milik task 2.1r): kunci panjang-berprefiks, dan cakupan penuh keputusan 7 — semua
# `reference:pattern:*` TERMASUK YANG YATIM plus semua `reference:rubric:*`. `load_snapshot`
# hari ini hanya menjangkau pattern yang dirujuk provider, jadi pattern yatim BELUM terjangkar.
MEMORY_ROOT_ENCODING_FROZEN: Final = False


def memory_root_for_onchain(source: MemorySnapshot | MemoryClient) -> bytes:
    """Satu-satunya pintu root yang boleh dipakai `vault_client`/`postVerdict`.

    Selama encoding belum dibekukan (task 2.1r), ia MENOLAK — mengumumkan root dari
    encoding yang masih berubah berarti `knownRoots` di vault berisi nilai yang tidak bisa
    direkonstruksi siapa pun, persis kegagalan yang dihancurkan juri fase 1.
    """
    if not MEMORY_ROOT_ENCODING_FROZEN:
        raise MemoryPolicyError(
            "encoding memory_root belum dibekukan (ADR-020 keputusan 6, task 2.1r) — "
            "DILARANG mengumumkan root turunan-memori on-chain sebelum itu"
        )
    return memory_root(source)


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


def _save_provider_cas(
    client: MemoryClient, profile: ProviderProfile, expected_version: int
) -> ProviderProfile:
    """Tulis provider hanya bila versinya masih seperti saat dibaca.

    JUJUR TENTANG BATASNYA: ini compare-and-swap di atas store yang TIDAK transaksional —
    `sibyl-memory-client` 0.7.0 tidak mengekspos transaksi (api-facts §C), jadi jendela
    antara baca-versi dan tulis tidak atomik. Yang dijamin: tulisan yang dibangun dari
    snapshot USANG ditolak, sehingga satu tulisan basi tidak bisa mengembalikan provider
    ber-insiden ke risk 0 tanpa cap (dan tidak bisa membuka kembali replay). Yang TIDAK
    dijamin: keamanan dua proses agen yang menulis DB yang sama secara bersamaan — itu
    tetap DILARANG secara operasional, bukan dicegah oleh kode ini.
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

    `client_address` (opsional, diambil watcher dari `getJob(jobId)` — `client` TIDAK
    indexed di `JobFunded`) dipakai untuk ADR-021 keputusan 2: bila ia PERSIS sama dengan
    alamat provider, budgetnya dibuang dan `stats.jobs` tetap naik.

    Job yang DITOLAK/Expired hanya menaikkan `stats.reject` (dan, bila ada cek deterministik
    yang gagal, menjadi insiden). Budgetnya TIDAK disimpan di mana pun — ADR-020 keputusan 2.

    IDEMPOTEN PER `job_id`. Job yang sudah pernah tercatat (`recorded_jobs`) tidak pernah
    dihitung dua kali, dan pemanggilan ulangnya TIDAK menulis apa pun. Dedup ada DI SISI
    MEMORI, bukan diserahkan ke watcher, karena watcher bukan satu-satunya sumber
    pemanggilan: replay log dan `last_block` yang mundur sesudah reorg sama-sama masuk
    lewat sini.

    BATAS YANG DIAKUI (jangan dibaca lebih jauh dari ini): idempotensi itu cek-lalu-tulis
    di atas store yang TIDAK transaksional. Tulisan yang dibangun dari snapshot USANG
    ditolak oleh CAS versi (`_save_provider_cas`, `StaleWriteError`), tetapi jendela antara
    baca dan tulis tidak atomik — dua proses agen pada satu `memory.db` tetap DILARANG
    secara operasional dan tidak dicegah oleh kode ini.
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
    self_funded = client_address is not None and normalize_address(
        client_address
    ) == normalize_address(provider_address)

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


def store_provider_cap(client: MemoryClient, provider_address: str, decision: CapPlan) -> ProviderProfile:
    """Menyimpan cap terakhir ke profil provider (untuk audit; keputusan tetap dihitung ulang)."""
    profile = _load_provider_for_write(client, provider_address)
    return _save_provider_cas(client, replace(profile, cap_usdc=decision.cap_usdc), profile.version)
