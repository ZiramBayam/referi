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
`404` seperti path karangan mana pun — bukan `403`. Gerbangnya mati ke arah aman: env yang
HADIR tetapi kosong (`DEMO_MODE= uv run python -m agent.demo_reset`) berarti MATI dan tidak
lagi jatuh ke `.env` — dulu justru itu yang MENYALAKANNYA, karena `.env` berisi `DEMO_MODE=true`.

Jalankan:

```
cd agent && DEMO_MODE=1 uv run python -m agent.demo_reset --host 127.0.0.1 --port 8010
```

Tanpa `DEMO_MODE`, prosesnya keluar dengan kode 1 dan tidak mengikat port apa pun.

### Permintaan

```
POST /demo/memory/reset
Host: 127.0.0.1:8010
Content-Type: application/json

{"db": "memory.db"}      # opsional; badan kosong = "memory.db"
```

**Header yang DIWAJIBKAN** (gerbang lintas-asal; pemanggil dari sisi server memenuhinya
tanpa perubahan apa pun):

| Header | Aturan | Gagal → |
|---|---|---|
| `Content-Type` | `application/json` PERSIS (parameter `charset` boleh) | `415 unsupported_media_type` |
| `Host` | `127.0.0.1:<port>`, `localhost:<port>`, atau `[::1]:<port>` — port wajib port server | `403 bad_host` |
| `Origin` | **tidak boleh ada sama sekali** (tidak ada allowlist asal) | `403 cross_origin_request` |
| `Sec-Fetch-Site` | boleh tidak ada; bila ada wajib `none`/`same-origin` | `403 cross_origin_request` |
| `Sec-Fetch-Mode` | boleh tidak ada; `no-cors`/`navigate`/`websocket` ditolak | `403 cross_origin_request` |

Kenapa: "loopback saja" bukan pertahanan terhadap browser — browser juri juga ada di
loopback. Satu tab jahat dengan `<form method=POST action="http://127.0.0.1:8010/demo/memory/reset">`
mengirim `Content-Type: text/plain`, yang termasuk daftar aman CORS dan karena itu lolos
tanpa preflight; penyerang tidak perlu bisa membaca jawabannya karena penghapusan sudah
terjadi. Mewajibkan `application/json` memaksa preflight, dan preflight `OPTIONS` di sini
dijawab `501` tanpa header `Access-Control-Allow-*`.

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
  "root": "data/demo",
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

`root` adalah path RELATIF terhadap paket agen (`data/demo`); jawaban ini melewati proksi ke
browser, dan nama pengguna serta tata letak disk juri tidak dibutuhkan UI untuk apa pun.

`memory.db.lock` SENGAJA tidak ikut disapu: ia bukan isi memori melainkan pemegang `flock`
mutual-exclusion, dan menghapusnya saat proses lain memegang kuncinya menghasilkan dua
proses yang sama-sama merasa memegang kunci.

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
| 415 | `unsupported_media_type` | `Content-Type` bukan `application/json` |
| 403 | `cross_origin_request` | ada `Origin`, atau `Sec-Fetch-*` dari konteks lintas-asal |
| 403 | `bad_host` | `Host` bukan loopback + port server ini (mis. DNS rebinding) |
| 500 | `delete_failed` | berkas ada tetapi gagal dihapus (mis. izin) |
| 500 | `root_is_symlink` | `agent/data/demo` ternyata symlink → nol penghapusan |
