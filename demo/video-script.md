# Naskah video demo — TAKE-1

Naskah **operasional**: dipakai sambil merekam layar, bukan untuk dibaca saja. Setiap baris menyebut
**apa yang diketik/diklik**, **apa yang muncul di layar**, dan **apa yang diucapkan**.

- Target durasi: **4 menit 35 detik** (rentang aman 4:20–4:50; syarat rubric 2–5 menit).
- Alur = `docs/spec.md` §7 langkah 1–5. Langkah 1–4 = satu perintah `make demo`; langkah 5 = tiga rute di browser.
- Keadaan yang direkam adalah **kode yang dibekukan** (ADR-030). Jangan mengedit apa pun di antara take.
- Hard stop perekaman: **9 Sep 18:00** (ADR-028 keputusan 2).
- Kolom "Ucapan" berbahasa Indonesia. **Pasangan Inggrisnya sudah ada: `demo/video-script.en.md`** —
  struktur waktu, bagian, dan buktinya identik; hanya kolom "Ucapan" dan panduan perekam yang
  diterjemahkan, sedangkan keluaran terminal dan label UI dibiarkan berbahasa Indonesia (sesuai layar)
  dengan glosarium Inggris dalam kurung. Juri Sibyl Labs berbahasa Inggris, jadi **berkas `.en.md` itulah
  yang dipakai saat merekam**; berkas ini tetap sebagai panduan operator.

---

## A. Pra-terbang (lakukan SEBELUM tombol rekam ditekan)

| # | Perintah / aksi | Yang harus terjadi | Kalau gagal |
|---|---|---|---|
| A1 | `cd /home/zirambayam/referi && make doctor` | keluar dengan kode 0 | jangan merekam; toolchain tidak cocok `docs/versions.md` |
| A2 | Pastikan ada internet ke `https://sepolia.base.org` | `make demo` memeriksanya PREFLIGHT di detik pertama (`Makefile:50-54`) | tanpa jaringan `make demo` berhenti dengan exit 1 sebelum Anvil menyala |
| A3 | **Dry-run berwaktu**: `time make demo 2>&1 \| tee /tmp/dryrun-demo.log`, tunggu selesai | exit 0; baris `VARIAN A:` dan `VARIAN B:` tercetak; catat runtime-nya — terukur **3m23s** dan **3m56s**, jadi harapkan **Rencana B** | kalau tidak, perbaiki lingkungan dulu — jangan merekam kegagalan lalu menceritakannya sebagai sukses |
| A4 | `pnpm --filter web build` | build selesai tanpa galat | — |
| A5 | Terminal B: `DEMO_MODE=1 pnpm --filter web start` | server di `http://127.0.0.1:3000` (`-H 127.0.0.1` dipin di `web/package.json:9`) | — |
| A6 | Buka 4 tab browser, urutkan kiri→kanan: (1) `http://127.0.0.1:3000/`, (2) `http://127.0.0.1:3000/verdict/420`, (3) `http://127.0.0.1:3000/verdict/422`, (4) `https://base-sepolia.blockscout.com/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384?tab=logs` | keempatnya sudah termuat sebelum rekaman; **Blockscout**, bukan BaseScan — di sanalah nama event terdekode (lihat catatan Bagian 4) | tab yang masih loading memakan detik yang tidak Anda punya |
| A7 | Terminal A: `cd /home/zirambayam/referi && clear`, font besar (≥ 16pt), lebar ≥ 120 kolom | prompt bersih | — |
| A8 | Tutup notifikasi, tab pribadi, dan wallet extension | layar bersih | — |
| A9 | **Uji bagian 5 lebih dulu**: `/panel` → tombol "deliverable job 422" → jalankan `sampling`, lalu `full` | `sampling` → `format.no-placeholder` **pass**; `full` → **fail** | kalau hasilnya bukan itu, hapus bagian 5 dari naskah dan geser 30 detiknya ke bagian 6 — jangan menceritakan hasil yang tidak muncul |

**Catatan `DEMO_MODE=1`:** dengan gerbang itu menyala, `/panel` ikut merender **tombol hapus memori**, dan
tombol itu **di luar lingkup TAKE-1**: ia tidak ada di naskah ini dan tidak dilatih di A9. Saat merekam:
**jangan klik dan jangan menggulir sampai ke sana** (naskah ini berhenti di kartu "Hasil"). Bila Anda tidak
butuh gerbangnya, jalankan A5 tanpa `DEMO_MODE=1` — seluruh naskah tetap berjalan.

> Ini catatan LINGKUP, bukan catatan keselamatan. Permukaan itu sempat diberi verdict **BLOKIR** oleh review
> keamanan; **blokir itu sudah DICABUT** — review ulang mengembalikan nol KRITIS dan nol TINGGI, dan temuan
> SEDANG terakhir (TOCTOU pada komponen leluhur path) ditutup lewat jalur `dir_fd`. Riwayat lengkapnya,
> termasuk risiko RENDAH yang masih diterima, ada di `docs/limitations.md` **butir 36**. Ia tetap ditinggalkan dari
> TAKE-1 karena naskahnya sudah penuh di 4:35 dan tombolnya belum pernah dilatih — bukan karena ia tidak
> aman. Di depan kamera: jangan mengomentarinya ke arah mana pun.

---

## B. Tata letak layar

- **Terminal A** (kiri / layar penuh saat bagian 1 dan 6): tempat `make demo` berjalan.
- **Browser** (bagian 2–5): empat tab dari A6.
- **MULAILAH DENGAN ASUMSI RENCANA B (bagian G).** Runtime `make demo` yang **terukur** adalah
  **3m23s dan 3m56s** pada dua eksekusi — lebih lama daripada jendela ± 2 menit 35 detik yang dipakai
  bagian 2–5. Artinya bila Anda menjalankannya live, saat kembali ke Terminal A perintahnya
  **kemungkinan besar belum selesai**. Angka "~2m20s" yang pernah beredar berasal dari task 3.3, sebelum
  dua varian destruktif dan preflight jaringan ditambahkan; jangan memakainya untuk merencanakan rekaman.
- Rencana A (live) hanya masuk akal bila dry-run A3 **di mesin Anda** selesai di bawah ± 2m30s. Ukur dulu
  (`time make demo`), jangan menebak.

---

## C. Naskah

### Bagian 1 — Masalah + jalankan demo (0:00 – 0:40, 40 dtk)

| Waktu | Aksi (ketik/klik) | Layar | Ucapan |
|---|---|---|---|
| 0:00 | Tidak ada; Terminal A bersih | prompt kosong di repo | "ERC-8183 memberi satu peran kekuasaan penuh: evaluator. Ia menentukan job dibayar penuh atau di-refund penuh — tidak ada pembayaran parsial. Dan evaluator standar tidak punya ingatan: provider yang sama bisa mengulang trik yang sama besok, dan wasitnya tidak akan tahu." |
| 0:20 | Ketik dan jalankan: `make demo 2>&1 \| tee /tmp/take1-demo.log` | baris `[demo] start …`, `[demo] anvil.up …` mulai mengalir | "Ini The Evaluator: wasit ERC-8183 yang ingatannya tentang tiap provider bisa dihitung ulang dari file. Satu perintah ini membangun rantainya dari nol di Anvil lokal, lalu membaca satu vault beku di Base Sepolia — hanya dua panggilan `eth_call` view: **nol dana, nol transaksi**. Selagi ia berjalan, saya tunjukkan yang sudah mendarat di chain." |

> Bukti di layar: `Makefile:62-63`; syarat internet `Makefile:50-54`; `sim/src/demo.ts:610-611`
> ("hanya dua `eth_call` view").

### Bagian 2 — Timeline job 418–422 (0:40 – 1:25, 45 dtk)

| Waktu | Aksi | Layar | Ucapan |
|---|---|---|---|
| 0:40 | Pindah ke tab 1 (`/`) | tabel "Timeline job 418–422 (Base Sepolia)" | "Lima job yang benar-benar mendarat di Base Sepolia. Job 418 dan 419: provider yang sama, cek deterministik `format` gagal dua kali — dua insiden dari dua job berbeda." |
| 1:00 | Sorot baris 418, 419, lalu 420 dengan kursor | kolom Verdict `reject`, kolom "tx VerdictPosted" berisi tautan BaseScan | "Job 420 adalah yang menarik: ia ditolak **saat masih `Funded`** — sebelum provider sempat menyerahkan apa pun. Bentuk bundelnya `gate-rejection`." |
| 1:15 | Klik "buka bukti" pada baris **420** (atau pindah ke tab 2) | halaman `/verdict/420` termuat | "Kenapa? Bukti lengkapnya ada di halaman ini." |

> Bukti di layar: `web/src/app/page.jsx:13`; data dari `web/public/jobs.json`; halaman ini nol RPC —
> ia hanya menampilkan artefak repo.

### Bagian 3 — Gerbang cap: apa yang memori putuskan (1:25 – 2:05, 40 dtk)

| Waktu | Aksi | Layar | Ucapan |
|---|---|---|---|
| 1:25 | Gulir ke kartu "Keputusan gerbang" | `diterima? reject`, `budget 2000000`, `cap provider 250000 (basis baseline-constant, sample_size 0)`, `risk level 2`, `job insiden yang mendasarinya: 418, 419` | "Budget dua juta unit, cap dua ratus lima puluh ribu, ditolak. Dua job insiden yang mendasarinya ditulis di bundel — 418 dan 419 — dan bisa Anda klik." |
| 1:45 | Tunjuk `sample_size 0` dengan kursor | field yang sama | "Satu kejujuran yang kami tulis sendiri di bundelnya: `sample_size` nol. **Angka** dua ratus lima puluh ribu itu konstanta tim dibagi empat — yang dipelajari dari memori adalah **tingkat risikonya**, dan risk itulah yang memilih pembaginya. Memori di sini hanya bisa **mengetatkan** cap, tidak pernah melonggarkannya." |
| 1:57 | Tunjuk field `memory_root` dan `tx VerdictPosted` di kartu atas | `memory_root 0xcfdab1b0…`, tautan tx | "Dan alasan ini terikat hash: seluruh isi halaman ini adalah bundel yang di-keccak menjadi `reasonHash` di transaksinya." |

> Bukti di layar: bundel `web/public/verdicts/420.json`; `docs/limitations.md` butir 8 (`basis: baseline-constant`,
> `sample_size: 0`), butir 17 (penegakan ada di agen, kontrak hanya menerbitkan cap).

### Bagian 4 — Teks identik, verdict berbeda + jejak on-chain (2:05 – 2:45, 40 dtk)

| Waktu | Aksi | Layar | Ucapan |
|---|---|---|---|
| 2:05 | Pindah ke tab 3 (`/verdict/422`) | judul "Verdict job 422 — reject", `kedalaman cek: full`, `hash deliverable 0x246071b3…0a51` | "Job 421 dan 422 memakai deliverable yang **sama byte demi byte** — hash keccak-nya identik, budgetnya sama. Job 421 lulus. Job 422 ditolak." |
| 2:18 | Gulir ke "Bukti per-kriteria" | cek `format.no-placeholder` **fail**, `section 2`, `depth full` | "Bedanya hanya providernya: yang satu bersih, yang satu punya dua insiden. Riwayat itu menaikkan kedalaman pemeriksaan dari `sampling` ke `full`, dan cacatnya — sebuah `TODO` di bagian ketiga — hanya terlihat pada `full`." |
| 2:30 | Gulir sedikit ke kartu kuning "Kriteria yang TIDAK dinilai" | `qualitative.0` + `unscored_reason` | "Perlu saya sebut: tidak ada penilaian kualitatif dan tidak ada LLM di jalur mana pun. Kriteria kualitatif dicatat `unscored` apa adanya." |
| 2:37 | Pindah ke tab 4 (Blockscout, halaman **Logs** vault), tunjuk entri paling atas: `MemoryRootUpdated` dengan root `0x999a9570…9b7d` (tx `0xe95910d2…5830`) | daftar log vault dengan **nama event terdekode**: `MemoryRootUpdated`, `VerdictPosted`, `Finalized`, `ProviderCapSet` | "Dan ini jejaknya di chain. Nama eventnya terbaca — `MemoryRootUpdated` — karena kontraknya terverifikasi di Sourcify, `exact_match`, dari commit `8d3e596`. Root inilah yang diumumkan **sebelum** eksekusi." |

> Bukti di layar: `docs/limitations.md` butir 25 (tabel 421 vs 422 + empat hash tx), butir 33 (`unscored`),
> butir 7 (riwayat `MemoryRootUpdated`), butir 15 (Sourcify `exact_match` dari commit `8d3e596`).
>
> **Kenapa Blockscout, bukan BaseScan:** verifikasi Sourcify ditarik Blockscout sehingga nama event
> benar-benar terlihat di kamera; Etherscan/BaseScan tidak mengimpor dari Sourcify dan verifikasi di sana
> menuntut API key yang tidak ada di repo ini, jadi status di BaseScan **tidak kita klaim ke arah mana
> pun** (`deployments/84532.json:32`). Alternatif yang sah bila Anda lebih percaya terminal daripada
> explorer: jalankan `cast logs` sesuai blok yang `docs/limitations.md` butir 7 sebutkan — tetapi keluarannya topic
> mentah, jadi nama eventnya tidak terlihat di layar.

### Bagian 5 — Panel juri: coba sendiri (2:45 – 3:15, 30 dtk)

| Waktu | Aksi | Layar | Ucapan |
|---|---|---|---|
| 2:45 | Buka `http://127.0.0.1:3000/panel`, klik tombol **"deliverable job 422"** | textarea terisi tiga bagian: `# Summary`, `## Cara kerja`, `## Catatan lanjutan` | "Panel juri. Muat deliverable job 422, lalu pilih kedalamannya sendiri." |
| 2:55 | Pilih `sampling (2 bagian pertama)` → klik **Jalankan cek** | kartu "Hasil": `format.no-placeholder` **pass** | "Pada `sampling`: lolos." |
| 3:03 | Pilih `full (seluruh bagian)` → klik **Jalankan cek** | kartu "Hasil": `format.no-placeholder` **fail**, bagian ketiga | "Pada `full`: gagal. Teks yang sama, kedalaman berbeda. Batasnya saya sebut: panel ini menjalankan cek `format` dan `links` saja di proses Next lokal — ia tidak membaca memori dan tidak mengirim transaksi." |

> Bukti di layar: `web/src/app/panel/page.jsx:41-48` (kartu batas), paritas port cek dijaga
> `web/test/checks-parity.test.js` (5 tes, `pnpm -r test`).

### Bagian 6 — Puncak: hapus memorinya (3:15 – 4:10, 55 dtk)

| Waktu | Aksi | Layar | Ucapan |
|---|---|---|---|
| 3:15 | Kembali ke Terminal A; `make demo` sudah selesai | baris terakhir `[demo] done …` | "Perintah tadi selesai. Pertanyaan juri yang paling wajar: kalau memorinya dihapus, apakah ada yang berubah?" |
| 3:22 | Ketik: `grep -E '^(VARIAN \|\[demo\] claim )' /tmp/take1-demo.log` | empat blok baris tercetak | — |
| 3:28 | Sorot baris `claim step=C-vs-D` | `budgetRaw=2000000`, `gateWithMemory="DITOLAK (budget 2000000 melebihi cap milestone provider ini (250000; riwayat: 2 insiden terkonfirmasi))"`, `gateWithoutMemory="lolos (budget dalam batas cap)"` | "Ini barisnya. Budget yang **identik** — dua juta unit. Dengan memori: ditolak, dengan alasan yang menyebut dua insiden terkonfirmasi. Tanpa memori: lolos. Yang berbeda hanya memorinya. Dan agennya dipanggil sebagai **proses baru** untuk tiap job — ingatan itu datang dari file, bukan dari sesi yang sama." |
| 3:48 | Sorot baris `VARIAN A:` | `ROOT ONCHAIN DIRESET, cap hilang (TANPA CAP), mode sampling, cacat halus LOLOS (job 4: LOLOS), cacat kasar DITOLAK (job 5: GAGAL ['format']), 5 tx baru` | "Yang hilang saat memori dihapus adalah **kalibrasi**: capnya hilang, kedalamannya turun ke `sampling`, dan cacat halus lolos. Yang **tidak** hilang: cacat kasar tetap ditolak — evaluatornya tidak mati, ia jadi dangkal. Hapus memori kami, dan Anda dapat evaluator stateless biasa — persis pesaing kami." |
| 4:00 | Sorot baris `VARIAN B:` | `MODE AMAN, 0 tx baru, nonce 89 -> 89, job menggantung sampai expiredAt, pulih dengan memory.db dari backup` | "Itu di vault segar. Di vault yang sudah hidup, memori yang hilang memicu **mode aman**: nol transaksi — diukur dari nonce wallet agen, bukan diucapkan — job menggantung sampai kedaluwarsa, client dapat refund penuh." |

> Bukti di layar: baris keluaran `make demo` (`sim/src/demo.ts:902-949`); mode aman digugurkan run-nya
> bila buktinya tidak muncul (`sim/src/demo.ts:672-687`); agen dipanggil per job (`docs/limitations.md` butir 9).
> **Jangan** menyebut varian A "mode naif": label modenya `normal`; yang menunjukkan degradasi adalah
> `depth=sampling` dan `cap=TANPA CAP` (ADR-026, `docs/limitations.md` butir 34).

### Bagian 7 — Kejujuran + penutup (4:10 – 4:35, 25 dtk)

| Waktu | Aksi | Layar | Ucapan |
|---|---|---|---|
| 4:10 | Buka `README.md` di editor/GitHub, gulir ke bagian **"Batasan & asumsi kepercayaan"** | daftar butir bernomor terlihat di layar (daftar lengkap 36 butir: `docs/limitations.md`) | "Terakhir, dan ini bukan catatan kaki: proyek ini mendaftarkan batasannya sendiri — ringkasannya di README, daftar penuh tiga puluh enam butirnya di `docs/limitations.md` — verdict yang salah tidak bisa dibatalkan siapa pun, bond evaluator hari ini nol, dan dana yang masuk vault terjebak permanen." |
| 4:25 | Gulir ke bagian "Cara menjalankan" | blok `make doctor` / `make test` / `make demo` | "Semuanya bisa Anda jalankan sendiri: `make doctor`, `make test`, `make demo`. Repo publik, lisensi MIT. Terima kasih." |

---

## D. Kalimat yang DILARANG diucapkan (naskah gagal kalau ini keluar)

| Jangan ucapkan | Kenapa | Ganti dengan |
|---|---|---|
| "mode naif" untuk varian A | label modenya `normal`; naif hanya baris log invokasi pertama yang berakhir nol transaksi (ADR-026, `docs/limitations.md` butir 34) | "`depth=sampling`, `cap=TANPA CAP`" |
| "menilai kualitas", "LLM menilai", "rubric AI" | rubric LLM dipotong; kriteria kualitatif dicatat `unscored` (`docs/limitations.md` butir 33) | "cek deterministik `format`, `links`, `chain`" |
| "evaluator mempertaruhkan bond" | `MIN_BOND` = 0 pada kontrak terdeploy (`docs/limitations.md` butir 1, 28) | "yang dipertaruhkan hari ini nol — itu ada di daftar batasan" |
| "jendela challenge melindungi" | `challenge`/`resolve` stub; jendela 120 detik murni latensi, verdict salah tidak bisa dibatalkan siapa pun (`docs/limitations.md` butir 2, 26) | jangan sebut jendelanya sama sekali, kecuali sebagai batasan |
| "agen otonom", "watcher memantau chain" | agen dipanggil per job dengan `--job-id` (ADR-022, `docs/limitations.md` butir 9) | "agen dijalankan per job, sebagai proses baru" |
| "audited", "production-ready", "100% coverage", angka performa | tidak ada laporan yang menghasilkannya | — |
| "dibayar sama besar entah meluluskan atau menolak" | fee di muka via x402 adalah **rancangan** ADR-004, bukan fitur (`docs/limitations.md` butir 14, 23; ADR-025 kep. 3) | "insentif fee-nya belum kami perbaiki, dan itu ada di daftar batasan kami" |
| "provider membangun kepercayaan lewat riwayat baik" | cap satu arah, hanya bisa mengetat (`docs/limitations.md` butir 8) | "memori hanya bisa mengetatkan cap" |

## E. Yang WAJIB terucap minimal sekali

1. `make demo` butuh internet ke `sepolia.base.org` — **dua `eth_call` view, nol dana, nol transaksi** (bagian 1).
2. Budget **identik**, yang berbeda hanya memori (bagian 6, baris `claim step=C-vs-D`).
3. Cacat kasar **tetap ditolak** tanpa memori (bagian 6, baris `VARIAN A`).
4. Kalimat: "Hapus memori kami, dan Anda dapat evaluator stateless biasa — persis pesaing kami." (bagian 6).
5. Batasan yang didaftarkan sendiri: verdict tak terbatalkan, bond nol, dana terjebak (bagian 7).
6. Tidak ada LLM / penilaian kualitatif (bagian 4).

## F. Ceklis pasca-rekam (sebelum unggah)

- [ ] Durasi total 2:00–5:00 (target 4:35).
- [ ] Tidak ada satu pun kalimat dari tabel D.
- [ ] Tidak ada kunci privat, isi `.env`, atau alamat pribadi yang terlihat di layar (cek bilah judul terminal juga).
- [ ] Baris `claim step=C-vs-D` terbaca jelas pada resolusi unggah (uji dengan menonton di 720p).
- [ ] Tombol hapus memori `/panel` tidak pernah muncul/diklik.
- [ ] `make demo` dalam rekaman keluar 0.

## G. Rencana B — JALUR NORMAL untuk TAKE-1 (bukan rencana darurat)

Runtime terukur **3m23s–3m56s** membuat eksekusi live tidak muat di jendela bagian 2–5 (± 2m35s), jadi
perlakukan bagian ini sebagai **jalur utama**, bukan cadangan. `make demo` deterministik (dua eksekusi
berturut-turut memberi ringkasan yang identik), jadi Rencana B tidak mengubah satu angka pun — hanya
sumber layarnya:

1. Jalankan `make demo 2>&1 | tee /tmp/take1-demo.log` **sebelum** merekam, biarkan Terminal A memegang
   keluaran lengkapnya.
2. Di bagian 1, ganti kalimat "selagi ia berjalan" menjadi: **"Perintah ini saya jalankan tepat sebelum
   rekaman; ini keluarannya apa adanya."** — sebutkan itu, jangan biarkan penonton mengira ini live.
3. Bagian 6 tidak berubah: `grep` atas `/tmp/take1-demo.log` yang sama.

Yang **tidak boleh** dilakukan: memotong bagian gagal lalu tetap mengucapkan hasilnya, atau menempel
keluaran dari run yang berbeda dengan yang disebut di layar.

## H. Klaim → bukti (untuk juri yang mengecek video baris demi baris)

| Klaim di video | Bukti |
|---|---|
| lima job nyata di Base Sepolia, 418–422 | `web/public/jobs.json`; tautan tx di kolom "tx VerdictPosted"; `docs/limitations.md` butir 25 |
| job 420 ditolak saat `Funded` karena budget > cap | `/verdict/420` kartu gerbang; tx `JobRejected` `0x78a3a65d…989e` (`docs/evidence.md` "Rantai A → B → C") |
| cap 250.000, `sample_size` 0, insiden 418 & 419 | bundel `web/public/verdicts/420.json`; `docs/limitations.md` butir 8 |
| deliverable 421 == 422 byte demi byte, verdict berbeda | `sha_keccak` `0x246071b3…0a51` di `demo/deliverables/421.json` & `422.json`; `docs/limitations.md` butir 25 |
| `MemoryRootUpdated` job 422, root `0x999a9570…9b7d` | tx `0xe95910d2…5830`; topic0 `0xc6028d32…7923` (`docs/limitations.md` butir 7 & 22) |
| panel menjalankan cek deterministik sungguhan | `web/src/lib/checks.js`, `POST /api/evaluate`; paritas dijaga `web/test/checks-parity.test.js` |
| kriteria kualitatif `unscored`, nol LLM | `agent/agent/criteria.py:121-124`, dikunci `agent/tests/test_criteria.py:336-337`; `docs/limitations.md` butir 33 |
| budget identik, hanya memori yang berbeda | baris `[demo] claim step=C-vs-D` (`sim/src/demo.ts:902-908`) |
| tanpa memori: `depth=sampling`, `cap=TANPA CAP`, cacat kasar tetap ditolak | baris `VARIAN A:` (`sim/src/demo.ts:929-935`) |
| memori hilang di vault hidup → mode aman, nol tx | baris `VARIAN B:` (`sim/src/demo.ts:946-949`); penjaga gugur `sim/src/demo.ts:672-687` |
| `make demo` hanya membaca Sepolia, nol dana/tx | `Makefile:50-54`; `sim/src/demo.ts:610-611`; nonce sebelum/sesudah di baris `VARIAN B` |
| batasan didaftarkan sendiri | `README.md` bagian "Batasan & asumsi kepercayaan" (ringkasan); `docs/limitations.md` butir 1, 4, 26 |
| lisensi MIT | `LICENSE` |
