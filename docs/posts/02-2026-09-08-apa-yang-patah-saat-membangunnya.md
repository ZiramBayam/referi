---
title: "Apa yang patah saat membangunnya (dan apa yang masih patah)"
date: 2026-09-08
proyek: The Evaluator (hackathon Sibyl, Base Sepolia)
repo: EvaluatorVault 0x5c6EE4586ACABcb6326069c229E58091B21ef384
---

# Apa yang patah saat membangunnya (dan apa yang masih patah)

Dua hari sebelum submission, versi jujur dari sepuluh hari terakhir. Bukan versi mulusnya — versi yang
memuat empat hal yang patah, siapa yang menemukannya, dan apa yang kami lakukan sesudahnya.

## 1. Tes destruktif kami dulu hanya menjalankan varian yang dijamin menang

Gate hackathon ini terang-terangan: hapus lapisan memorinya, dan kalau proyeknya masih melakukan apa
yang ia klaim, itu wrapper. Kami membangun tes destruktifnya sendiri — dan versi pertamanya hanya
menjalankan **satu** varian: vault segar di Anvil lokal, memori kosong, sehingga job yang DITOLAK saat
memori ada menjadi lolos pada budget yang identik. Degradasi terlihat, panggung meriah.

Masalahnya: itu bukan satu-satunya yang terjadi kalau memori dihapus. Pada vault yang sudah hidup —
root on-chain bukan nol — menghapus `memory.db` justru memicu **mode aman**: agen berhenti total, nol
`postVerdict`, job menggantung sampai `expiredAt`, client dapat refund penuh. Menampilkan satu varian
saja berarti memilih adegan yang paling menguntungkan.

Sekarang `make demo` menjalankan **keduanya**, dan varian keduanya bukan panggung buatan sendiri: ia
dijalankan atas **vault Base Sepolia yang beku** supaya `lastMemoryRoot()` non-nol itu keadaan nyata.
Yang lebih penting, ia **menggugurkan seluruh run** kalau buktinya tidak muncul — exit agen ≠ 0, baris
`MODE AMAN:` tidak tercetak, gerbang tidak melaporkan `mode=safe`, pemicunya bukan aturan "file
hilang", ada transaksi terkirim, atau nonce wallet agen bergerak. Semuanya berbentuk
`VARIAN B GUGUR: …` di `sim/src/demo.ts:672-685`. Sentuhan jaringannya hanya baca, dan itu **diukur**
lewat nonce sebelum vs sesudah, bukan diucapkan.

Satu koreksi label yang kami minta juri catat: pada varian pertama, mode yang dilaporkan agen adalah
`normal`, **bukan** "mode naif". Yang menunjukkan degradasinya adalah dua kolom lain di baris
ringkasan — `depth=sampling` dan `cap=TANPA CAP` (ADR-026).

## 2. Penjaga root kami buta terhadap `importlib`, `sys.modules`, dan re-binding

Kami punya aturan keras: hanya satu fungsi yang boleh melahirkan `memory_root` yang dikirim ke
`postVerdict`. Penegakannya sebagian berupa pemindai statis atas sumber jalur produksi.

Review keamanan adversarial menembusnya. Pemindai versi pertama mengisi daftar modulnya **hanya** dari
simpul `import`/`from … import`, sehingga modul yang didapat lewat `importlib.import_module(...)`,
`__import__(...)`, atau `sys.modules["…"]` tidak pernah dikenali sama sekali — dan re-binding sesederhana
`alt = mp` memutus jejaknya. Enam bentuk dibuktikan lolos **tanpa satu pun tes merah**.

Perbaikannya bukan menambal satu bentuk, melainkan mengajari pemindai mengenali modul yang didapat
tanpa pernyataan import, plus melacak alias. Keenam bentuk itu sekarang menjadi tes yang harus merah:
`test_root_gate_scanner_catches_the_six_bypasses_from_the_4_1_review`
(`agent/tests/test_memory_policy.py:2175`). Pelajarannya yang kami tulis di kode: pemindai yang tidak
pernah merah tidak menjaga apa pun, jadi setiap penjaga di repo ini wajib punya buktinya sendiri bahwa
ia bisa merah — dan kontrol negatif supaya "selalu merah" tidak lolos sebagai penjaga yang bekerja.

## 3. Vault kami dibekukan sebelum sempurna, dan 62.500 unit ikut terkunci

ADR-022 membekukan `0x5c6EE45…f384` sebagai kontrak submission. Keputusan itu diambil ketika perbaikan
yang sudah ditulis di sumber — `sweepToken(address,address)` untuk menarik fee ERC-20 — belum sempat
mendarat di bytecode. Konsekuensinya kami terima terbuka: fungsi itu **tidak ada** di kontrak
terdeploy, dan 62.500 unit token escrow yang dipegang vault (5% dari dua job yang diluluskan)
**hangus permanen**.

Kenapa tetap dibekukan: seluruh bukti on-chain yang kami tawarkan — job 417 sampai 422, delapan event
`MemoryRootUpdated`, `JobRejected` job 420 — melekat pada alamat itu. Redeploy berarti rantai bukti
yang lebih rapi tetapi lebih muda, dan cerita yang harus dimulai ulang dua hari sebelum tenggat. Kami
memilih bukti yang cacat tapi utuh daripada bukti yang bersih tapi baru. Ini keputusan yang bisa dinilai
salah, dan kami tidak memakai kata "audited" atau "production-ready" untuk menutupinya.

Ikutan yang sama pahitnya, dan sudah tertulis di README: `arbiter()` == `agent()` pada instans ini, dan
itu permanen karena kontraknya immutable.

## 4. `make demo` sekarang menuntut internet — dan kami memilih gagal keras

Konsekuensi dari poin 1: perintah demo kami tidak lagi sepenuhnya offline, karena varian kedua membaca
vault Sepolia yang beku. Ada pilihan yang lebih nyaman: lewati diam-diam kalau jaringan tidak ada, cetak
"skipped", run tetap hijau.

Kami menolaknya. Varian kedua adalah klimaks tes destruktif kami; run yang hijau tanpa menjalankannya
adalah run yang berbohong tentang apa yang sudah diperiksa. Jadi tanpa internet, `make demo` tidak
selesai — dan itu perilaku yang disengaja, dicatat sebagai batasan, bukan sebagai fitur.

Satu kejutan kecil yang ikut kami cetak apa adanya alih-alih disembunyikan: pada vault segar, invokasi
pertama agen **melahirkan** `memory.db` di tengah jalan, sehingga mode yang direncanakan tidak lagi sama
dengan mode yang dibaca sesaat sebelum menandatangani, dan penjaga `MODE_DRIFT` menolak bertransaksi —
exit code 4, nol transaksi, fail-closed. Invokasi kedua berjalan sampai selesai. `make demo` mencetak
`agent.retry … firstExit=4` apa adanya (ADR-026).

## 5. Panel juri: cek sungguhan di browser — dan permukaan yang baru saja gagal review keamanan

Bukti yang hanya bisa dibaca sebagai tabel di README gampang dicurigai sebagai hasil yang sudah
disiapkan. Jadi `web/` punya tiga rute: timeline job 418-422 dengan tautan tx `VerdictPosted` ke
BaseScan, halaman verdict + bukti per kriteria, dan **panel juri** tempat siapa pun bisa menempel
teksnya sendiri, memilih kedalaman, lalu menjalankan ceknya. Yang berjalan di sana bukan pemutar ulang:
cek deterministik `format` dan `links` **diport** dari `agent/agent/checks/` ke
`web/src/lib/checks.js` dan dijalankan lewat `POST /api/evaluate`, dan port itu menghasilkan array
`checks` yang identik dengan bundel bukti 418/419/421/422 — sampai ke string `detail` dan `proof`.

Kalimat itu, sampai kemarin, hanya **pernah diperiksa sekali dengan tangan** — dan klaim yang hanya
diperiksa dengan tangan akan patah diam-diam pada sentuhan berikutnya. Sekarang ia **dijaga tes**:
`web/test/checks-parity.test.js` membaca teks dari `web/public/deliverables/<jobId>.json`, harapannya
dari `web/public/verdicts/<jobId>.json` (bundel yang hash-nya sudah diumumkan on-chain), memeriksa lebih
dulu bahwa `sha_keccak` teks memang sama dengan `deliverable` yang dicatat bundel, lalu membandingkan
**seluruh objek cek** field demi field — `check`, `criterion`, `depth`, `detail`, `pattern`, `proof`,
`section`, `status` — plus `failed_checks`, `unverified`, `category`, `verdict`, dan katalog kriteria
deterministik. Tidak ada satu pun string harapan yang diketik ulang di dalam tesnya. Runner-nya
`node:test` bawaan Node 24, **nol dependensi baru**, dan `pnpm -r test` — yang dulu hijau atas nol
proyek — kini menjalankan 5 tes.

Dan seperti penjaga lain di repo ini, ia harus dibuktikan bisa merah: mengubah satu kata pada string
`detail` membuat keempat job merah, dan menaikkan `SAMPLING_SECTION_LIMIT` dari 2 ke 3 membuat job 421
berubah dari lulus menjadi gagal; dipulihkan, 5/5 hijau lagi.

Batasnya ditulis di halamannya sendiri: panel tidak menjalankan gerbang cap, tidak membaca memori, tidak
memanggil gerbang 402, tidak mengirim transaksi. Tidak ada RPC dari browser; datanya JSON statis di
`web/public/`. Dependensinya tiga, semuanya sudah dipin di `docs/versions.md` (next 16.3.2,
react 19.2.8, typescript 7.0.2).

Ada juga tombol hapus memori di panel, untuk mempertunjukkan tes destruktif di depan penonton — dan di
sinilah kami harus berhenti memuji diri sendiri. **Permukaan tombol itu baru saja diberi verdict BLOKIR
oleh review keamanan, dengan dua temuan TINGGI:** CSRF pada endpoint hapusnya (menghapus adalah efek
samping, bukan bacaan, jadi CORS tidak pernah menjadi pertahanan), dan proksi Next yang mengekspos
penghapus loopback ke LAN karena default Next mengikat `0.0.0.0`. **Perbaikannya belum selesai saat post
ini ditulis.** Sebagian mitigasi sudah mendarat dan bisa dibaca di
`web/src/app/api/demo/memory/reset/route.js` (gerbang `DEMO_MODE` per permintaan, penolakan
`Sec-Fetch-Site`/`Origin` yang bukan same-origin, penolakan target di luar loopback, `-H 127.0.0.1`
dipin di `web/package.json`), tetapi verdict reviewer belum dicabut, dan sampai itu terjadi jangan
menjalankan `web/` dengan `DEMO_MODE=1` di jaringan yang tidak Anda percayai. Ini butir 36 di README.

Satu batas yang sengaja kami pasang sejak awal dan tidak digeser saat panik: tombol itu hanya berkuasa
atas memori **demo** (`agent/data/demo/`). Ia tidak pernah bisa menyentuh `agent/data/chain-abc/memory.db`
— satu-satunya berkas yang bisa merekonstruksi root on-chain.

## Yang MASIH belum beres

Ini bagian yang paling ingin kami tulis lebih pendek, dan justru karena itu ia ditulis penuh di README
pada bagian "Batasan & asumsi kepercayaan", di atas pitch mana pun:

- **Insentifnya belum diperbaiki.** Fee hanya cair saat `Completed`; wasit ini masih dibayar hanya kalau
  ia meluluskan. Fee di muka (ADR-004) adalah rancangan, dan gerbang 402 yang ada belum dikonsumsi jalur
  job mana pun.
- **Taruhannya nol.** `MIN_BOND` = 0. `challenge`/`resolve` stub, jadi jendela 120 detik itu latensi
  dengan nol perlindungan: verdict salah tidak bisa dibatalkan siapa pun.
- **Jangkar root melingkar**, dan dari delapan root vault hanya root job 418 yang bisa dihitung ulang
  hari ini.
- **`memory.db` yang ditukar DB lain tidak terdeteksi** — mode aman memeriksa keadaan file, bukan isinya.
- **Tes destruktif belum berartefak**: `make demo` menjalankan keduanya tetapi tidak meninggalkan log
  atau fixture di repo, jadi yang bisa Anda cocokkan hari ini adalah run Anda sendiri.
- **`sim/` tidak punya satu pun tes otomatis** — satu-satunya kode yang menyentuh SDK Virtuals dijaga
  hanya oleh rantai on-chain yang dijalankan tangan (`web/` sudah punya, poin 5) — dan kontraknya belum
  terverifikasi di Sourcify/BaseScan.
- **Permukaan hapus-memori di panel juri masih di bawah verdict BLOKIR** review keamanan (poin 5 di atas).

Video demonya direkam besok. Yang akan Anda lihat di sana adalah perintah yang sama persis dengan yang
ada di README — termasuk exit code 4 itu.
