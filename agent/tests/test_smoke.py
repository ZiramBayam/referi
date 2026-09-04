"""Smoke: paket Sibyl Memory terpasang PERSIS seperti yang dicatat docs/api-facts.md §C.

Kenapa ada: task 0.2 memverifikasi signature di venv SEKALI-PAKAI di luar repo. Venv itu sudah
hilang, jadi tidak ada yang menjaga bahwa venv proyek berisi paket yang sama. Tes ini menjalankan
ulang verifikasi yang sama (`inspect.signature`) pada SETIAP `pytest`, atas metode yang akan dipakai
`memory_policy.py` (task 2.1) sesuai skema spec §3.

Sumber kebenaran tabel di bawah = docs/api-facts.md §C, disalin dari blok signature di sana.
Bila tes ini MERAH: JANGAN menyesuaikan tabel ke paket — laporkan penyimpangannya ke
@agent-api-verifier lebih dulu (aturan anti-halusinasi CLAUDE.md).

Semua yang dijalankan di sini offline: `MemoryClient.local()` tidak butuh `sibyl init` maupun
jaringan (api-facts §C, "diverifikasi offline 2026-09-02").
"""

from __future__ import annotations

import importlib.metadata
import inspect
import json

import pytest
from sibyl_memory_client import MemoryClient, NotFoundError

# Versi yang dipin di docs/versions.md baris "sibyl-memory-client | 0.7.0".
EXPECTED_VERSION = "0.7.0"

# Penanda "tidak punya nilai default" — dibedakan dari default `None` yang sah.
NO_DEFAULT = inspect.Parameter.empty

POS = inspect.Parameter.POSITIONAL_OR_KEYWORD
KW = inspect.Parameter.KEYWORD_ONLY

# (nama metode, [(nama parameter, kind, default), ...]) — SALINAN docs/api-facts.md §C.
# `self` dibuang; `local` adalah classmethod sehingga `cls` juga tidak muncul.
EXPECTED_SIGNATURES: dict[str, list[tuple[str, object, object]]] = {
    # MemoryClient.local(path='~/.sibyl-memory/memory.db', *, tenant_id=…, tier='free', …)
    "local": [
        ("path", POS, "~/.sibyl-memory/memory.db"),
        ("tenant_id", KW, "00000000-0000-0000-0000-000000000001"),
        ("tier", KW, "free"),
        ("account_id", KW, None),
        ("session_token", KW, None),
        ("credentials_claim", KW, None),
        ("credentials_signature", KW, None),
    ],
    # HOT — spec §3 "Job aktif"
    "set_state": [("key", POS, NO_DEFAULT), ("body", POS, NO_DEFAULT)],
    "get_state": [("key", POS, NO_DEFAULT)],
    # WARM — spec §3 "Profil provider" / "Profil client" / "Karantina"
    # PERINGATAN api-facts §C: parameter pertama bernama `category`, BUKAN `kind`.
    "set_entity": [
        ("category", POS, NO_DEFAULT),
        ("name", POS, NO_DEFAULT),
        ("body", POS, NO_DEFAULT),
        ("status", KW, None),
    ],
    "get_entity": [("category", POS, NO_DEFAULT), ("name", POS, NO_DEFAULT)],
    "list_entities": [
        ("category", POS, None),
        ("status", KW, None),
        ("limit", KW, 100),
    ],
    "search_entities": [
        ("query", POS, NO_DEFAULT),
        ("limit", KW, 20),
        ("prefix", KW, False),
        ("category", KW, None),
    ],
    # COLD — spec §3 "Verdict & cek"; SEMUA keyword-only.
    "write_event": [
        ("evaluated", KW, None),
        ("acted", KW, None),
        ("forward", KW, None),
        ("extra", KW, None),
        ("ts", KW, None),
    ],
    "read_events": [("limit", KW, 50), ("since", KW, None), ("until", KW, None)],
    # REFERENCE — spec §3 "Pola curang terkonfirmasi" (`pattern:*`) + "Rubric per kategori"
    "set_reference": [("key", POS, NO_DEFAULT), ("body", POS, NO_DEFAULT), ("metadata", KW, None)],
    "get_reference": [("key", POS, NO_DEFAULT)],
    # ARCHIVE / hapus permanen — spec §3 "Job final" + tes destruktif §7 langkah 3
    "archive_entity": [
        ("category", POS, NO_DEFAULT),
        ("name", POS, NO_DEFAULT),
        ("reason", POS, None),
    ],
    "delete_entity": [("category", POS, NO_DEFAULT), ("name", POS, NO_DEFAULT)],
}


def _observed(method_name: str) -> list[tuple[str, object, object]]:
    """Parameter NYATA metode, `self` dibuang, dalam urutan deklarasi."""
    params = list(inspect.signature(getattr(MemoryClient, method_name)).parameters.values())
    if params and params[0].name == "self":
        params = params[1:]
    return [(p.name, p.kind, p.default) for p in params]


def test_installed_version_matches_pin():
    assert importlib.metadata.version("sibyl_memory_client") == EXPECTED_VERSION


@pytest.mark.parametrize("method_name", sorted(EXPECTED_SIGNATURES))
def test_signature_matches_api_facts(method_name):
    """Nama, urutan, kind (posisional vs keyword-only), dan default parameter cocok §C."""
    assert _observed(method_name) == EXPECTED_SIGNATURES[method_name], (
        f"MemoryClient.{method_name} menyimpang dari docs/api-facts.md §C — "
        "laporkan ke @agent-api-verifier, JANGAN sesuaikan tes ini ke paket."
    )


def test_local_is_classmethod():
    """§C menandai `local` sebagai classmethod; `memory_policy` memanggilnya tanpa instance."""
    assert inspect.ismethod(MemoryClient.local)


def test_no_extra_or_missing_public_params():
    """Tidak ada metode §C yang hilang dari paket terpasang."""
    missing = [name for name in EXPECTED_SIGNATURES if not hasattr(MemoryClient, name)]
    assert missing == []


def test_set_entity_rejects_kind_keyword():
    """Fakta yang sering salah (§C): `kind=` bukan nama parameter dan HARUS TypeError."""
    with pytest.raises(TypeError):
        MemoryClient.set_entity(object(), kind="provider", name="0x0", body={})


def test_notfound_error_is_importable():
    """`get_entity`/`archive_entity` melempar ini; `get_state`/`get_reference` mengembalikan None."""
    assert issubclass(NotFoundError, Exception)


@pytest.fixture
def client(tmp_path):
    """Klien lokal pada DB temp — offline, tanpa `sibyl init` (api-facts §C)."""
    return MemoryClient.local(str(tmp_path / "memory.db"))


def test_local_creates_db_offline(client, tmp_path):
    assert (tmp_path / "memory.db").exists()


def test_entity_roundtrip_uses_category_positional(client):
    """Bentuk panggilan yang akan dipakai `memory_policy.get_entity("provider", addr)`."""
    row = client.set_entity("provider", "0xabc", {"risk_level": 0}, status="active")
    assert row["category"] == "provider"
    assert client.get_entity("provider", "0xabc")["body"] == {"risk_level": 0}


def test_get_entity_raises_notfound(client):
    with pytest.raises(NotFoundError):
        client.get_entity("provider", "0xtidak-ada")


def test_get_state_returns_wrapper_not_body(client):
    """§C: `get_state` mengembalikan {'body':…, 'updated_at':…}, bukan body mentah."""
    assert client.get_state("job:1") is None
    client.set_state("job:1", {"criteria": []})
    got = client.get_state("job:1")
    assert got["body"] == {"criteria": []}


def test_get_reference_body_is_json_string(client):
    """§C: dict di `set_reference` disimpan sebagai string JSON → perlu json.loads."""
    client.set_reference("pattern:demo", {"detector": "chain"})
    body = client.get_reference("pattern:demo")["body"]
    assert isinstance(body, str)
    assert json.loads(body) == {"detector": "chain"}


def test_delete_entity_is_idempotent(client):
    client.set_entity("provider", "0xdead", {"risk_level": 2})
    assert client.delete_entity("provider", "0xdead") is True
    assert client.delete_entity("provider", "0xdead") is False
