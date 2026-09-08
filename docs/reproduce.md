# Reproduksi & tes destruktif

Nomor butir di halaman ini merujuk ke [`docs/limitations.md`](limitations.md).

## Perintah pokok

```
make doctor    # cetak versi toolchain, exit 1 bila tidak cocok docs/versions.md
make test      # forge test + uv run pytest + pnpm -r test (yang ketiga = 5 tes paritas di web/;
               # sim/ masih tanpa tes — butir 18)
make demo      # rantai §7 langkah 1-4 dari NOL di Anvil lokal, ringkasan deterministik, lalu DUA
               # varian destruktif; varian B MEMBACA vault Sepolia beku — butuh internet
               # (hanya baca: nol dana, nol transaksi — butir 34)
               # RUNTIME TERUKUR: 3m23s dan 3m56s pada dua eksekusi. Angka "~2m20s" yang pernah
               # ditulis berasal dari task 3.3, SEBELUM dua varian destruktif dan preflight
               # jaringan ditambahkan — jangan pakai untuk merencanakan rekaman.
```

`make doctor` membaca `node`/`forge` dari PATH yang hanya dimuat shell interaktif — jalankan dari terminal
biasa, bukan dari hook non-interaktif (pesan merahnya menjelaskan ini sendiri).

## Menjalankan rantai A/B/C sendiri

Rantai A/B/C dijalankan dengan perintah eksplisit, satu job per pemanggilan. Perintah ini menjalankan
rantai **baru** pada vault Anda sendiri; ia tidak mereproduksi job 418/419/420 pada vault submission, yang
`agent`-nya immutable milik kami (butir 20):

```
# 1. job A/B: createJob → setBudget → fund → submit (ketiganya lewat SDK Virtuals)
DELIVERABLE_TEXT=... pnpm --filter sim run job:min

# 2. job C: berhenti sesudah fund, supaya gating terjadi saat status Funded
BUDGET_RAW=2000000 STOP_AFTER=fund pnpm --filter sim run job:min

# 3. agen menilai satu job (tanpa --kind: exit 2, nol RPC, nol tx)
cd agent && uv run python -m agent.vault_client --job-id <jobId> --kind reject

# 4. audit root memori dari file ekspor, tanpa menyentuh DB
cd agent && uv run python -m agent.memory_export --check /tmp/mem.json

# 5. (OPSIONAL, di luar `make demo`) UI: panel juri + tombol hapus memori.
#    Terminal 1 — web:
DEMO_MODE=1 pnpm --filter web start          # http://127.0.0.1:3000/panel
#    Terminal 2 — server hapus memori DEMO; TANPA ini tombolnya menjawab 503
#    reset_server_unreachable (perintah yang sama ditampilkan di dalam panel):
cd agent && DEMO_MODE=1 uv run python -m agent.demo_reset --host 127.0.0.1 --port 8010
```

**Langkah 5 tidak dijalankan oleh `make demo` dan sengaja TIDAK dipakai di video demo.** Panel juri
(`/panel`) berjalan tanpa langkah itu — yang butuh proses kedua **hanya** tombol hapus memori, karena
database duduk di `agent/`, di luar batas folder frontend (`web/src/app/panel/MemoryControl.jsx:27-28`
menampilkan perintah yang sama di UI). Tombolnya berkuasa **hanya** atas memori demo, dan riwayat review
keamanannya ada di butir 36. Tes destruktif yang menjadi bukti submission dijalankan oleh
`make demo`, bukan oleh tombol ini.

Verdict tidak bisa dikalahkan flag: bila cek deterministik gagal (`Evaluation.passed == False`) atau gerbang
cap menolak, hasilnya REJECT apa pun isi `--kind`.

## Mereproduksi demo kedalaman (butir 25)

Menuntut DUA provider, karena yang membedakan job 421 dan 422 hanyalah riwayat providernya. Pemilihnya
`PROVIDER_SLOT` (`sim/src/client_min.ts:102,160-162`), dengan dua nilai sah: `alpha` (default, kunci
`PROVIDER_PRIVATE_KEY` — provider yang di rantai kami sudah punya dua insiden) dan `beta`
(`PROVIDER2_PRIVATE_KEY` — provider bersih):

```
# provider BERSIH → depth sampling → dua bagian pertama saja → LULUS
PROVIDER_SLOT=beta  BUDGET_RAW=250000 DELIVERABLE_FILE=sim/scenarios/depth-demo.md \
  pnpm --filter sim run job:min

# provider BERISIKO (2 insiden) → depth full → bagian ketiga terbaca → DITOLAK
PROVIDER_SLOT=alpha BUDGET_RAW=250000 DELIVERABLE_FILE=sim/scenarios/depth-demo.md \
  pnpm --filter sim run job:min
```

Sama seperti rantai A/B/C, ini menjalankan job **baru** pada vault Anda sendiri dan **tidak** mereproduksi
job 421/422 pada vault submission (butir 20). Yang menentukan hasilnya bukan flag mana pun,
melainkan apakah memori provider itu sudah memuat dua insiden — jadi urutan menjalankannya penting.

## Troubleshooting: exit code 4 pada vault segar

**Pada vault SEGAR, langkah 3 butuh DUA invokasi, dan yang pertama keluar dengan exit code 4.** Itu bukan
kerusakan: invokasi pertama melahirkan `memory.db` di tengah jalan, sehingga mode yang direncanakan
(`naive`) tidak lagi sama dengan mode yang dibaca sesaat sebelum menandatangani (`normal`), dan penjaga
`MODE_DRIFT` menolak bertransaksi — **nol tx, fail-closed**. Invokasi kedua atas job yang sama berjalan
sampai selesai dan keluar 0.

**Exit 4 itu TIDAK bisa dilewati dengan melahirkan DB lebih dulu.** README versi sebelumnya menyarankan
`memory_export --db … --out …` untuk itu; resep tersebut **tidak bisa dijalankan**, karena alat ekspor
sengaja menolak membuat DB baru (lihat butir 7):

```
$ cd agent && uv run python -m agent.memory_export --db ./data/baru/memory.db --out /tmp/mem.json
GAGAL: MemoryExportError: DB memori tidak ditemukan: ./data/baru/memory.db — jalankan agen dulu, atau
tunjuk file yang ada dengan --db (alat ini sengaja TIDAK membuat DB baru)
```

Jadi jalannya memang **menjalankan agen dua kali**: invokasi pertama melahirkan DB-nya dan keluar 4 dengan
nol transaksi, invokasi kedua menghasilkan verdict. `make demo` melakukan persis itu dan mencetaknya apa
adanya (`agent.retry … firstExit=4`), bukan menyembunyikannya.

Ini diputuskan dan diukur di **ADR-026** (keputusan 6 mewajibkan README menyebutkannya), dan konsekuensinya
nol byte on-chain: root, depth, dan cap yang diumumkan sama saja pada kedua jalur.

## Tes destruktif

Pertanyaan yang paling wajar dari juri: kalau memorinya dihapus, apakah ada yang berubah?
Dijalankan **6 Sep 2026 di Anvil lokal** (nol transaksi ke Base Sepolia; vault submission dan file memori
rantai A/B/C tidak berubah — md5 identik sebelum/sesudah).

> **Baca tabel ini sebagai laporan, bukan sebagai bukti.** Skripnya kini ADA — `make demo` menjalankan
> kedua varian destruktif (butir 19) — tetapi ia tidak meninggalkan satu berkas pun: tidak ada log,
> fixture, atau berkas pendamping di repo yang bisa Anda cocokkan dengan tabel ini, dan md5 di atas juga
> tidak punya pendamping. Yang bisa Anda verifikasi sendiri hari ini: rantai A/B/C on-chain, dan
> `make demo` yang Anda jalankan sendiri lalu bandingkan dengan mata.

```
# vault SEGAR di Anvil: lastMemoryRoot() = 0, providerCap(provider) = 0
# SIBYL_DB_PATH diarahkan ke path yang belum pernah ada; agent/data/ TIDAK dihapus
cd agent && uv run python -m agent.vault_client --job-id <job C> --kind reject
```

| Kondisi | Hasil |
|---|---|
| **Tanpa file memori, invokasi PERTAMA** | gerbang start membaca `mode=naive`, lalu `plan_job` **MEMBUAT** `memory.db` saat membuka `MemoryClient.local()`; gerbang yang dibaca ulang sebelum tx kini melihat file itu ADA → `mode=normal`, sementara `plan.mode` masih `naive` → penjaga **`MODE_DRIFT`** menolak. Hasil: **`EXIT_REFUSED` (exit code 4)**, `sent_transactions == []`, **nol `postVerdict`**, `cast logs JobRejected` KOSONG |
| **Tanpa file memori, invokasi KEDUA** (job yang sama) | berjalan sampai selesai: `mode=normal`, `depth=sampling`, `cap=TANPA CAP gate=lolos`, `postVerdict` + `finalize` mendarat, **exit 0** |
| **File memori dikembalikan** (chain yang sama, perintah yang sama) | `cap=250000 gate=DITOLAK` → `postVerdict(REJECT)` → `Finalized(kind=2)`, `JobRejected` MUNCUL, job jadi status 4, client refund penuh |

**Baris pertama adalah PENOLAKAN, bukan penerimaan — dan README versi sebelumnya menuliskannya seperti
penerimaan.** Yang terjadi bukan "agen lolos-kan job karena memorinya hilang"; yang terjadi adalah agen
**menolak bertransaksi sama sekali** karena mode yang ia rencanakan tidak lagi sama dengan mode yang ia
baca sesaat sebelum menandatangani. Perilakunya fail-closed dan sembuh sendiri pada invokasi berikutnya.
Ini dicatat dan diterima apa adanya di **ADR-026**, termasuk konsekuensinya: **pada vault segar, hari
pertama menuntut DUA invokasi `--job-id`, dan yang pertama keluar dengan exit code 4.** Operator yang tidak
diberi tahu akan membaca exit 4 itu sebagai kerusakan. ADR-026 keputusan (e) juga mengukur bahwa selisih ini
**nol byte on-chain**: `empty_memory_root()` dan root atas DB kosong yang baru dibuat adalah nilai yang sama
persis (`0x4e2a1ca1…ff5a`), dan depth serta cap-nya identik.

Konsekuensi yang harus ikut dibaca: **`MODE NAIF` tidak pernah menjadi mode yang melahirkan verdict lewat
CLI.** Ia hanya muncul sebagai baris log invokasi pertama (ADR-026 keputusan 4 dan konsekuensi). README,
video, dan post build-in-public **dilarang** menyajikannya seolah ia jalur produksi.

Kosongnya hasil pada baris pertama bukan lulus palsu: kontrol positif `JobFunded` pada rentang dan bentuk
filter yang IDENTIK tetap mengembalikan log. Dan bundel bukti pada baris kedua menyebut `cap.usdc 250000` +
`incident_jobs [418, 419]` — **keberadaan** cap itu terlacak ke job A dan B di Base Sepolia, bukan ke aturan
yang menyala tanpa riwayat. Yang perlu dibaca bersamanya: **angka** 250.000 sendiri tetap konstanta tim
dibagi 4, dengan `sample_size: 0` di bundel yang sama (butir 8). Yang berubah karena memori adalah **ada
atau tidak adanya gate**, bukan besar angkanya.

> **Hapus memori kami, dan kamu dapat evaluator stateless biasa — persis pesaing kami.**

Yang **tidak** berubah saat memori hilang: lapis kriteria dan cek deterministik tetap berjalan, jadi cacat
kasar tetap ditolak. Yang hilang hanyalah kalibrasi — kedalaman cek, pola curang yang sudah dipelajari, dan
gating cap (`docs/spec.md` §3 aturan 6). Catatan penting: "cacat kasar" adalah **posisi** token `TODO` yang
sama di dalam jendela sampling, bukan tingkat keparahan yang dinilai — butir 19.

Catatan jujur soal lingkungan: varian di atas berjalan pada vault **segar** (root on-chain = 0). Pada vault
submission yang sudah hidup, menghapus `memory.db` memicu **mode aman**, bukan degradasi — agen berhenti
total dan job menggantung sampai `expiredAt` (butir 10). **Kedua varian kini dijalankan oleh satu
perintah `make demo`**: varian A di Anvil lokal, varian B atas vault Sepolia yang beku — hanya baca, nol
dana, nol transaksi, dan run digugurkan bila buktinya tidak muncul (butir 19 dan 34). Yang belum
ada bukan otomasinya melainkan artefaknya: perintah itu tidak meninggalkan log atau fixture di repo.
