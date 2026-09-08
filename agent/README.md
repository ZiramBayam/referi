# agent/ — HTTP API

Dua server HTTP, keduanya **loopback saja**, keduanya dijalankan manual (`make demo` tidak
menyalakannya). Berkas ini hanya mendokumentasikan permukaan HTTP; alasan desainnya ada di
docstring modulnya masing-masing.

## 1. Gerbang 402 — `POST /jobs/register`

Modul `agent/payment_402.py` (ADR-010 — **bukan** x402). Jalankan:

```
cd agent && uv run python -m agent.payment_402 --host 127.0.0.1 --port 8000
```

Ringkasnya: tanpa pembayaran → `402` + `WWW-Authenticate: OnchainPayment …`; dengan
`Authorization: OnchainPayment tx="0x…"` yang terverifikasi on-chain → `200`. Dalam
`DEMO_MODE` header dummy diterima, dan `200`-nya menandai dirinya (`X-Payment-Mode: demo`,
`verified_onchain: false`). Rincian lengkap: README repo, bagian "402".

## 2. Hapus memori demo — `POST /demo/memory/reset`

Modul `agent/demo_reset.py`. Dipakai kontrol "hapus memori" di `/panel`, supaya juri
benar-benar menghapus berkasnya alih-alih membaca prosedur `rm`.

**Endpoint ini TIDAK ADA tanpa `DEMO_MODE`.** Tabel rutenya kosong, jadi path-nya menjawab
`404` seperti path karangan mana pun — bukan `403`.

Jalankan:

```
cd agent && DEMO_MODE=1 uv run python -m agent.demo_reset --host 127.0.0.1 --port 8010
```

Tanpa `DEMO_MODE`, prosesnya keluar dengan kode 1 dan tidak mengikat port apa pun.

### Permintaan

```
POST /demo/memory/reset
Content-Type: application/json

{"db": "memory.db"}      # opsional; badan kosong = "memory.db"
```

`db` adalah **nama berkas**, bukan path: `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. Apa pun yang
memuat `/`, `\`, `..`, NUL, atau spasi ditolak `400`, dan tidak ada berkas yang disentuh.
Direktori kerjanya selalu `agent/data/demo/` — diturunkan dari akar paket, tidak pernah dari
permintaan, dan tidak bisa dipindahkan oleh env.

### Respons `200`

Yang disapu selalu tiga berkas: `<db>`, `<db>-wal`, `<db>-shm`.

```json
{
  "ok": true,
  "reason": "ok",
  "root": "/…/agent/data/demo",
  "db": "memory.db",
  "deleted": ["memory.db", "memory.db-wal", "memory.db-shm"],
  "missing": [],
  "refused": []
}
```

- `deleted` — berkas yang benar-benar dihapus panggilan ini;
- `missing` — memang sudah tidak ada (panggilan kedua: ketiganya di sini, `deleted` kosong —
  tampilkan "tidak ada yang terhapus");
- `refused` — ada tetapi TIDAK dihapus karena ia symlink atau direktori.

Memanggilnya dua kali sah dan tetap `200`.

### Respons galat

Semua bentuknya `{"ok": false, "reason": "<kode>"}` — tidak ada path yang dipantulkan.

| Status | `reason` | Kapan |
|---|---|---|
| 404 | `not_found` | `DEMO_MODE` mati, atau path lain |
| 405 | `method_not_allowed` | metode selain `POST` pada path yang terdaftar |
| 400 | `invalid_db_name` | `db` tidak lolos pola nama |
| 400 | `path_outside_demo_dir` | hasilnya keluar dari `agent/data/demo/` |
| 400 | `malformed_json` | badan bukan objek JSON |
| 413 | `body_too_large` | badan > 4 KiB |
| 500 | `delete_failed` | berkas ada tetapi gagal dihapus (mis. izin) |
