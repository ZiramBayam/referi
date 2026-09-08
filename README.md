# The Evaluator

Wasit escrow ERC-8183 yang ingatannya tentang tiap provider bisa **dihitung ulang dari file**.

**Insentifnya BELUM diperbaiki.** Hari ini `evaluatorFeeBP` = 500 (5%) dan fee itu hanya cair saat job
berstatus `Completed` (`docs/spec.md` §1 baris 19, fakta ERC-8183 terverifikasi) — jadi wasit ini masih
dibayar hanya kalau ia **meluluskan**, persis bias yang menjadi alasan proyek ini ada. Pada empat job yang
ia TOLAK (418, 419, 420, 422) ia dibayar **0**; seluruh fee yang pernah ia terima — **62.500 unit dari dua
job yang ia LULUSKAN** (417 dan 421) — hangus permanen di vault yang tidak punya jalan keluar (Batasan
butir 4 dan 14).
Fee di muka lewat x402, yang akan membuat kalimat "dibayar sama besar entah ia meluluskan atau menolak"
menjadi benar, adalah **rancangan (ADR-004), bukan fitur** (Batasan butir 11). Kalimat itu berasal dari
`docs/spec.md` §0, dan §0 berjudul "Pitch satu kalimat" — aspirasi, bukan catatan fakta; README ini tidak
mengutipnya lagi sebagai fakta.

Status: **proyek hackathon di Base Sepolia (testnet), belum pernah dijalankan di mainnet.** README ini
ditulis sebelum video demo direkam. Prosa berbahasa Indonesia; identifier, perintah, dan kutipan kode
berbahasa Inggris.

Kontrak submission (BEKU, ADR-022): [`0x5c6EE4586ACABcb6326069c229E58091B21ef384`](https://sepolia.basescan.org/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384)

### Kalau Anda cuma punya 3 menit

README ini panjang (dan bagian terpanjangnya adalah daftar kelemahan kami sendiri). Tiga hal ini yang
paling kami ingin Anda periksa — semuanya bisa dibuka tanpa menjalankan apa pun:

1. **Verdict yang dibentuk riwayat, di chain.** Job 421 dan 422 memakai deliverable yang identik byte demi
   byte; 421 lulus, 422 ditolak. `postVerdict` job 422:
   [`0xe95910d2…295830`](https://base-sepolia.blockscout.com/tx/0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830)
   (Blockscout mendekode nama eventnya — butir 15). Duduk perkaranya: **butir 25**.
2. **Bundel bukti job 422**, yang hash-nya sudah diumumkan on-chain sebelum eksekusi:
   [`web/public/verdicts/422.json`](web/public/verdicts/422.json) — memuat `memory_root`, `checks`,
   `incident_jobs`, dan kriteria yang **tidak** dinilai. Cara mencocokkannya dengan chain: **butir 22**.
3. **Baris `claim step=C-vs-D`** yang dicetak `make demo` (`sim/src/demo.ts:902-907`): gerbang cap yang
   sama, dengan memori vs tanpa memori, pada budget identik. Konteks dan batasnya: **butir 19**.

Kalau Anda hanya ingin tahu apa yang TIDAK bekerja, lompat ke "Batasan & asumsi kepercayaan" di bawah —
ia ditulis lebih dulu daripada bagian pitch mana pun.

---

## Batasan & asumsi kepercayaan

Bagian ini sengaja ditaruh **paling atas** dan ditulis lebih dulu daripada bagian pitch mana pun. Butir
1-13 dipindahkan apa adanya dari ADR dan artefak deploy; butir 14-25 ditambahkan sesudah audit "klaim vs
kenyataan" dan sumbernya adalah kode serta chain yang bisa Anda buka sendiri. Angkanya tidak dilunakkan.
Butir 26-35 datang dari review keamanan atas kontrak dan agen: setiap butirnya **dibuktikan reviewer lewat
tes musuh** — peran yang mencoba dan galat yang ia terima — bukan disimpulkan dari membaca kode. Butir 36
adalah temuan review atas `web/` yang **belum selesai ditutup** pada saat README ini ditulis.

Kalau waktu Anda hanya cukup untuk empat: **butir 14** (insentif fee belum diperbaiki — pembalikan
terbesar), **butir 16** (jangkar root melingkar dan tanpa konsekuensi), **butir 19** (tes destruktif belum
berartefak), dan **butir 22** — `lastMemoryRoot()` vault **sengaja tidak sama** dengan `memory_export` atas
DB hari ini, karena memori ditulis sesudah `postVerdict`. Kalau Anda hanya akan menyalin satu blok perintah
dari README ini, baca butir 22 lebih dulu supaya Anda tahu nilai mana yang seharusnya cocok.

Dan bila dari kelompok 26-36 Anda hanya membaca satu: **butir 26** — verdict yang salah tidak bisa
dibatalkan siapa pun, sehingga `CHALLENGE_WINDOW` hari ini adalah latensi dengan nol perlindungan. Bila
Anda berniat **menjalankan** `web/` sendiri, baca **butir 36** lebih dulu — ia memuat riwayat penuh
permukaan hapus-memori: verdict BLOKIR, apa yang gagal, apa yang menutupnya, dan risiko RENDAH yang
masih kami terima.

### 1. Yang dipertaruhkan evaluator hari ini = nol

`MIN_BOND` pada kontrak terdeploy adalah **0** (`deployments/84532.json` → `"minBondWei": "0"`).
Catatan deploy yang sama, apa adanya:

> `minBondWei = 0 disengaja: vault belum punya jalur ETH keluar (ADR-013), jadi bond yang disetor akan
> terkunci permanen.`

Artinya: `deposit()` ada dan nyata, tetapi hari ini evaluator **tidak mempertaruhkan apa pun secara
on-chain**, dan ETH yang disetor tidak punya jalan keluar. Kutipan ADR-013:
"Bond evaluator lewat `deposit()` tetap nyata dan tetap dipertaruhkan secara sosial, tetapi hari ini
tidak ada jalur on-chain yang menyitanya."

### 2. `challenge`/`resolve` adalah stub — `CHALLENGE_WINDOW` murni latensi

`challenge(uint256,bytes32)` dan `resolve(uint256,bool)` ada di ABI sesuai `docs/spec.md` §4, dengan badan
`revert NotImplemented()` (ADR-013). Konsekuensinya: **jendela 120 detik**
(`deployments/84532.json` → `constants.CHALLENGE_WINDOW: 120`) adalah waktu tunggu, **bukan perlindungan**.

Verdict yang salah tidak bisa dibatalkan siapa pun sebelum `finalize`: agen ditolak `VerdictAlreadyPosted`,
penantang dan arbiter ditolak `NotImplemented` (temuan @agent-security-reviewer atas `EvaluatorVault`,
task 4.3b). "Sengketa berbond" adalah **v2**, bukan fitur hidup — ADR-013 melarang menyebutnya fitur.

### 3. `arbiter()` == `agent()`, dan itu permanen

```
$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "arbiter()(address)" --rpc-url https://sepolia.base.org
0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894

$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "agent()(address)" --rpc-url https://sepolia.base.org
0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894
```

Kedua alamat SAMA. Nilai yang sama tercatat di `deployments/84532.json` (`"agent"`, `"arbiter"`), dan
catatan file itu menyatakan akibatnya apa adanya:

> `arbiter == agent pada deploy ini, dan tetap begitu SELAMANYA: ADR-022 membekukan alamat ini sebagai
> kontrak submission, kontraknya immutable, jadi tidak ada redeploy yang memisahkannya.`

Yang meringankan, dan bisa dicek sendiri: pada kontrak ini **arbiter tidak punya wewenang on-chain apa
pun** — `resolve()` adalah stub (butir 2) dan `sweepToken` tidak ada di bytecode terdeploy (butir 4).
Arbiter terdesentralisasi (`v2: ERC-8004 validation`, `docs/spec.md` §4 baris 136) di luar scope build ini.

Yang **tidak** meringankan, dan harus diucapkan: **satu kunci, immutable, tanpa rotasi dan tanpa pause.**
`acp`, `agent`, `arbiter`, dan `MIN_BOND` dideklarasikan `immutable` tanpa satu pun setter
(`contracts/src/EvaluatorVault.sol:106-114`; catatan scope di baris 14 menyebut "pause" sebagai hal yang
sengaja TIDAK ada), dan di `deployments/84532.json` bidang `agent`, `arbiter`, dan `deployer` bernilai
alamat yang sama — satu EOA merangkap deployer, agen, arbiter, sekaligus satu-satunya penanda tangan.
Akibatnya dua arah dan permanen: **kunci hilang** → vault ini tidak akan pernah bisa `postVerdict` /
`setProviderCap` / `finalize` lagi, dan verdict yang belum final menggantung selamanya; **kunci dicuri** →
verdict, cap, dan `memoryRoot` sewenang-wenang tanpa jalur pembatalan apa pun (`resolve` stub, butir 2).

### 4. Kontrak terdeploy TIDAK punya `sweepToken`; 62.500 unit token hangus permanen

```
$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "sweepToken(address,address)" \
    0xECc22a8F6fD62388498fBa19813E214605a2BDb3 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894 \
    --rpc-url https://sepolia.base.org
execution reverted
```

`sweepToken(address,address) onlyArbiter` mendarat di **sumber** (commit `e675234`) sebagai kode + tes saja;
ADR-022 membekukan alamat di atas sebagai kontrak submission dan membatalkan redeploy, jadi fungsi itu
tidak ada di bytecode terdeploy.

Vault memegang **62.500 unit** token escrow, dan itu saldo yang masih bisa Anda baca sendiri sekarang:

```
$ cast call 0xECc22a8F6fD62388498fBa19813E214605a2BDb3 "balanceOf(address)(uint256)" \
    0x5c6EE4586ACABcb6326069c229E58091B21ef384 --rpc-url https://sepolia.base.org
62500
```

Angka itu = `evaluatorFeeBP()` 500 = 5% dari budget dua job yang pernah `Completed`: **50.000** dari job 417
(budget 1.000.000, `deployments/pipeline-84532.md:84`, tabel aliran dana) + **12.500** dari job 421
(budget 250.000, demo kedalaman — butir 25). Keduanya job yang evaluator **luluskan**; empat job yang ia
tolak menyumbang nol (butir 14). Kalimat artefak ADR-018 ditulis saat saldonya masih 50.000, dan kami
tempel apa adanya beserta koreksinya:

> `50.000 unit (0,05 USDC testnet) hangus permanen; ini dilepas secara sadar oleh ADR-018 keputusan 2,
> bukan kelalaian.`

Yang hangus hari ini **62.500**, bukan 50.000 — angka di artefak itu benar pada tanggalnya dan sudah
dilewati oleh job 421. Penalarannya tidak berubah: tidak ada jalan keluar dari vault beku ini.

### 5. `claimRefund` publik + `EVALUATOR_GRACE_PERIOD` 900 detik → verdict yatim = risiko yang DITERIMA

`claimRefund` di kontrak ACP sah dipanggil **siapa pun** dari status Open/Funded/Submitted; untuk Submitted
ada `EVALUATOR_GRACE_PERIOD` = **900 detik** sesudah `expiredAt`, dan sesudah refund itu `complete`/`reject`
oleh evaluator revert `WrongStatus()` (`docs/api-facts.md` §A KOREKSI 2026-09-03, dari fork bytecode asli +
source terverifikasi Sourcify; diringkas di ADR-014).

Kontrak kami **tidak bisa mencegahnya**: izin `claimRefund` ada di ACP, bukan di vault (ADR-014).
Mitigasinya hanya di sisi agen (pra-baca status sebelum `postVerdict` dan sebelum `finalize`), dan nilai 900
dibaca on-chain, tidak pernah di-hardcode di kode agen. Akibatnya, verdict yatim (job sudah `claimRefund`,
verdict vault hidup selamanya tanpa penanda on-chain) mungkin terjadi — ADR-015 mencatatnya sebagai
konsekuensi yang diterima, bukan bug yang belum ketahuan.

### 6. Teks deliverable TIDAK datang dari API ACP resmi

`session.submit()` SDK memanggil `api.postDeliverable` ke API off-chain Virtuals, dan API itu menolak wallet
simulator kami — `POST https://api.acp.virtuals.io/auth/agent` → **404**
`Agent not found with wallet address 0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2` (terbukti 4 Sep, ADR-019).
Jadi on-chain hanya ada `keccak256` deliverable, bukan teksnya.

Keputusan ADR-019: `sim/` menulis teks ke `demo/deliverables/<jobId>.json` (`{"jobId","text","sha_keccak"}`),
dan agen membacanya **hanya** dari sana serta wajib memverifikasi ulang bahwa `keccak256(text)` sama dengan
nilai `deliverable` on-chain sebelum menilai; tidak cocok atau file hilang → agen berhenti dengan nol
`postVerdict` dan nol `finalize`. Ini artefak lokal yang terikat ke chain, tetapi **bukan** sumber resmi ACP,
dan itu batasan nyata dari submission ini.

### 7. Tiga dari delapan root vault BUKAN turunan memori — dan satu root lagi hilang permanen

Jalur mundur ADR-018 aktif (ADR-022 membekukan v1), jadi riwayat root vault memuat sisa dari pipa awal.
Dua **nilai** root berikut adalah **konstanta berlabel**, bukan turunan memori (dan keduanya mengisi
**tiga** dari delapan event `MemoryRootUpdated` — tabel lengkapnya di bawah). **Keduanya tidak bisa
direkonstruksi dari `memory.db` mana pun**, dan preimage-nya kami tempel supaya bisa Anda cek sendiri:

```
$ cast keccak "the-evaluator/live/memory-root/v1"
0x1fa62c3db5c16f4c831ee1d9ee4c083745b8c8bae86bda3587b8b02ba52f7bf0

$ cast keccak "the-evaluator/selftest/memory-root/v1"
0x5ff921fda73362d23f66dcac204d1ace7a287fa0a2cf3bde12e4b37c6812a19e
```

- **Pipa hidup 1.3d (job 417):** `0x1fa62c3d…7bf0`. Ia sempat menjadi `lastMemoryRoot()` vault
  (ADR-023 konteks, dibuktikan lewat `cast call <vault> "lastMemoryRoot()(bytes32)"` saat itu).
- **Jalur `--selftest` (task 1.3b):** `0x5ff921fd…a19e`, dicatat ADR-023 keputusan 4 sebagai
  `SELFTEST_MEMORY_ROOT`. Definisinya masih bisa ditemukan di riwayat git — commit `26f11d6`,
  `SELFTEST_MEMORY_ROOT = bytes.fromhex("5ff921fd…a19e")` berkomentar
  `keccak256("the-evaluator/selftest/memory-root/v1")`, dicabut oleh commit `190cb44`.

Root selftest itu **benar-benar diumumkan on-chain, dua kali**, tetapi atas **jobId SINTETIS**, jadi ia tidak
pernah menyentuh satu pun job ACP nyata:

```
$ cast logs --address 0x5c6EE4586ACABcb6326069c229E58091B21ef384 \
    0xc6028d32061c1f0b8f4f1370b6f1ab5105a96bfc6631a3840371ebbcb27c7923 \
    --from-block 46355036 --to-block 46355080 --rpc-url https://sepolia.base.org

blok 46355036  jobId 0x895440 = 9000000  root(topic1) 0x5ff921fd…a19e
blok 46355080  jobId 0x895441 = 9000001  root(topic1) 0x5ff921fd…a19e
```

(`MemoryRootUpdated` kedua argumennya `indexed`, jadi root ada di **topic1** dan `data` kosong — skrip yang
men-decode `data` akan mendapat hasil kosong.)

Keduanya sudah **DICABUT dari jalur produksi** oleh task 2.4b (commit `190cb44`): satu-satunya sumber
`memory_root` yang boleh dikirim ke `postVerdict` adalah `memory_policy.memory_root()`, fungsi yang sama yang
dipakai `agent/memory_export.py`, dan `_send()` **menolak menandatangani** bila root di calldata tidak cocok
dengan memori saat itu — penegakannya di `_send()`, bukan di pemanggil (`agent/agent/vault_client.py:1339`, `_require_derived_root`, dipanggil dari `_send()` :1473).

Tetapi `postVerdict` menulis setiap root ke `knownRoots` **tanpa penghapus** (ADR-011), jadi kedua konstanta
itu tetap menjadi root sah selamanya di vault yang dibekukan. Bingkainya apa adanya: **vault submission
menyimpan jejak permanen dari fase sebelum aturan itu ada.** Itu fakta yang kami akui, bukan yang kami
sembunyikan.

**Seluruh riwayat root vault ini, kedelapannya, supaya tidak ada yang tersisa untuk ditemukan sendiri.**
`MemoryRootUpdated` diemit **delapan kali** sepanjang umur vault (`cast logs` atas topic0
`0xc6028d32…7923`, blok 46350667→46455552, dipecah jendela ≤ 9.999 blok karena batas RPC publik —
`docs/api-facts.md` §E). Root ada di topic1, jobId di topic2:

| # | root | jobId | apa itu | bisa dihitung ulang hari ini? |
|---|---|---|---|---|
| 1 | `0x5ff921fd…a19e` | 9000000 (sintetis) | konstanta selftest | tidak — konstanta berlabel, preimage di atas |
| 2 | `0x5ff921fd…a19e` | 9000001 (sintetis) | konstanta selftest | tidak — sama |
| 3 | `0x1fa62c3d…7bf0` | **417** | konstanta warisan pipa awal | tidak — konstanta berlabel, preimage di atas |
| 4 | `0x4e2a1ca1697b2a287fcfc8158fd5c460298aa69af8d5bec2d35671d71c4dff5a` | **418** | root memori **kosong** | **ya** — siapa pun bisa, dari DB baru |
| 5 | `0x3f506e52977407d8a4a1eb88179773f66679c992e6c74ac3cf20adcd7b9eecc2` | **419** | keadaan antara | **tidak — HILANG PERMANEN** |
| 6 | `0xcfdab1b0…5b26` | **420** | keadaan sesudah 419 (job 420 gerbang-rejection: tidak menulis memori) | **tidak — HILANG PERMANEN** |
| 7 | `0xcfdab1b0…5b26` | **421** | keadaan yang SAMA dengan #6 — lihat penjelasan di bawah | **tidak — HILANG PERMANEN** |
| 8 | `0x999a9570…9b7d` | **422** | keadaan sesudah job 421 menulis memori | **tidak — HILANG PERMANEN** |

Baris 4 perlu dijelaskan supaya tidak terbaca lebih hebat dari yang sebenarnya: root job 418 **identik
dengan root DB kosong**, dan itu **kebetulan mekanis**, bukan properti yang kami rancang. Sebabnya ada di
`docs/spec.md` §5 langkah 5 — memori ditulis **sesudah** `postVerdict`, jadi saat verdict job A diumumkan,
memorinya memang masih kosong. Ia bisa direproduksi siapa pun **tanpa file memori kami sama sekali**:

```
$ cd agent && uv run python -c "from agent.memory_policy import empty_memory_root; print(empty_memory_root().hex())"
4e2a1ca1697b2a287fcfc8158fd5c460298aa69af8d5bec2d35671d71c4dff5a
```

Satu koreksi terhadap cara README versi sebelumnya menulis ini: reproduksinya **bukan** lewat
`memory_export.py` atas "DB baru". Alat ekspor **sengaja menolak membuat DB** dan berhenti dengan
`MemoryExportError: DB memori tidak ditemukan … (alat ini sengaja TIDAK membuat DB baru)`, jadi tidak ada
"DB baru" yang bisa Anda arahkan padanya. Jalur yang benar adalah fungsi di atas — dan nilainya sama
persis, seperti yang sudah diukur ADR-026 keputusan (e). Justru karena itu, root ini **tidak membuktikan
apa-apa tentang isi memori** — ia hanya membuktikan memorinya kosong.

**Kenapa #6 dan #7 nilainya sama, dan kenapa itu penting.** Job 420 adalah **gerbang-rejection**: ia
ditolak saat `Funded` karena budget melebihi cap, jadi ia tidak pernah menghasilkan `evaluation` dan
karena itu **tidak menulis apa pun ke memori**. Root yang diumumkan job 421 karena itu masih keadaan yang
sama persis dengan job 420. Baru sesudah job 421 selesai dan menulis memorinya, job 422 mengumumkan nilai
yang berbeda (`0x999a9570…9b7d`). Urutan "tulis **sesudah** post" itulah yang membuat setiap root on-chain
selalu **satu langkah tulis di belakang** file memori.

Jadi klaim yang benar bukan "hanya root terakhir yang bisa diaudit", melainkan: **satu-satunya root vault
yang bisa dihitung ulang hari ini adalah 418, dan itu justru karena memorinya masih kosong saat itu.**
Root 419, 420/421, dan 422 semuanya **keadaan antara yang hilang permanen**. DB Sibyl menyimpan keadaan
**sekarang** — tidak ada tabel versi, tidak ada snapshot per job — sehingga keadaan antara tidak bisa
dibangun ulang begitu memori maju. Kesimpulannya tetap yang paling penting: **jangkar ini kedaluwarsa
setiap kali memori berubah.** Log root per job untuk audit mundur adalah v2 (ADR-023 keputusan 5).

Yang **masih** bisa Anda verifikasi sendiri hari ini, dan ini yang kami minta Anda periksa, adalah
**ikatan antara root on-chain dan bundel bukti** — lihat butir 22.

### 8. Cap awal adalah PARAMETER TIM, bukan hasil belajar

`BASELINE_CAP_USDC` = **1.000.000** (1 USDC, 6 desimal) dan lantai `MIN_CAP_USDC` = **250.000** adalah
konstanta yang dipilih tim (ADR-020 keputusan 3 dan 5). Kutipan konsekuensi ADR-020 apa adanya:

> `Cap awal kini angka pilihan tim, bukan turunan data; WAJIB disebut di README sebagai parameter, bukan
> disamarkan sebagai hasil pembelajaran.`

ADR-021 keputusan 1 memasang plafon pertumbuhan: kontribusi tiap job LOLOS ke median dibatasi
`min(budget, BASELINE_CAP_USDC)`, sehingga **cap turunan riwayat tidak pernah melampaui 1.000.000**, dan
untuk risk ≥ 2 tidak pernah melampaui 250.000. Sifatnya satu arah: **memori hanya bisa MENGETATKAN cap,
tidak pernah melonggarkannya.** "Provider membangun kepercayaan lewat riwayat baik" **bukan** klaim yang
boleh dibaca dari sistem ini — pemulihan reputasi adalah v2 (ADR-021 konsekuensi).

Yang berlaku di rantai demo, apa adanya: cap **250.000** yang menolak job C **tidak dipelajari dari data**.
Bundel bukti job 420 mencatat sendiri `"cap": {"basis": "baseline-constant", "sample_size": 0, "usdc":
250000}` — `sample_size: 0` berarti **nol** budget lolos yang ikut dihitung, sehingga angkanya adalah
`ceil(BASELINE_CAP_USDC / 4)` = `ceil(1.000.000 / 4)` dari konstanta tim
(`agent/agent/memory_policy.py:1666`, cabang `basis = "baseline-constant"`). Yang **memang** datang
dari memori adalah **tingkat risikonya** (risk = 2, hasil promosi pola di job A dan B) — dan risk itulah
yang memilih pembagi 4. Baca kolom "Yang berubah di memori" di bawah dengan batas itu.

Dan yang paling mudah salah dibaca, dari ADR-021 keputusan 4:

> `Cap BUKAN pertahanan tunggal terhadap provider curang; ia hanya membatasi UKURAN kerugian per job.
> Pertahanan terhadap deliverable curang tetap cek deterministik dan mode aman.`

### 9. Agen dipanggil per job — bukan otonom

Watcher event diturunkan dari jalur kritis (ADR-022 keputusan 3). Hari ini agen dijalankan sekali per job
dengan `--job-id <N> --kind reject|complete`; tanpa `--kind` ia keluar dengan kode 2 tanpa satu pun RPC.
Klaim "agen otonom" dilarang muncul di README/video/post oleh ADR-022 — dan tidak muncul.

### 10. Deteksi yang HILANG, disebut apa adanya

Kalimat ADR-024 (konsekuensi), apa adanya:

> `HILANG: deteksi "memory.db diganti DB LAIN", baik kosong maupun terisi.`

Mode aman v1 dipicu oleh **memori lokal yang tidak terbaca**, bukan oleh perbandingan root. Pemicunya
persis tiga, dan yang ketiga punya syarat tambahan yang mudah terlewat
(`agent/agent/memory_policy.py:1461-1500`):

1. kunci single-instance `memory.db` tidak didapat;
2. file DB ada tetapi `load_snapshot`/`memory_root` melempar;
3. file DB **hilang** — **DAN** `lastMemoryRoot()` on-chain **bukan nol**. Kalau root on-chain nol
   (vault segar / hari pertama), file DB yang hilang justru memberi **mode NAIF**, bukan mode aman.
   Syarat kedua inilah yang membuat tes destruktif di bawah bisa berjalan sama sekali.

**Akibat dari deteksi yang hilang itu, diucapkan sampai habis:** kalau `memory.db` bukan dihapus melainkan
**diganti DB lain yang terbaca**, tidak ada satu pun dari tiga pemicu di atas yang menyala. Agen masuk
**MODE NORMAL**, menerbitkan verdict penuh, dan meng-anchor root dari DB tukaran itu — selamanya, karena
`knownRoots` tidak punya penghapus (butir 7) dan tidak ada jalur pembatalan (butir 2, 16).

Penguatan berbasis log root lokal adalah v2 (ADR-023 keputusan 5, ADR-024 keputusan 2). Saat mode aman
aktif, agen berhenti total: nol `postVerdict`, nol `finalize`, nol `setProviderCap` — job menggantung
sampai `expiredAt`, lalu siapa pun
boleh `claimRefund` dan client menerima refund penuh. Itu perilaku yang diinginkan (ADR-020 keputusan 8),
dan pemulihannya adalah mengembalikan `memory.db` dari backup.

### 11. Yang ADA di spesifikasi tetapi BELUM hidup

Jangan menilai dari `docs/spec.md` saja — berikut yang belum berjalan hari ini:

| Belum hidup | Bukti |
|---|---|
| ~~`make demo`~~ | **SUDAH HIDUP** sejak commit `a03e294` — menjalankan §7 langkah 1-4 dari nol di Anvil lokal; varian destruktif KEDUA (mode aman) menyusul di commit `986fad6`. Yang masih belum: artefak (log/fixture) yang ditinggalkannya — butir 19 |
| x402 fee di muka (ADR-004) | gerbang 402-nya ADA (`agent/agent/payment_402.py`), tetapi **belum dikonsumsi jalur job** — butir 23 |
| `MemoryGateHook` | tidak ada di `contracts/src/` (hanya `EvaluatorVault.sol`, `IACP.sol`); hook butuh whitelist admin Virtuals (ADR-001) |
| Rubric LLM | dipotong; hanya cek deterministik yang jalan (`agent/agent/checks/`: `format`, `links`, `chain`) |
| `checks/sandbox` | tidak diimplementasikan dan tidak diklaim hidup |
| ~~UI web / panel juri~~ | **SUDAH HIDUP** — `web/` punya tiga rute (`web/src/app/page.jsx` timeline job 418-422 dengan tautan tx `VerdictPosted`; `web/src/app/verdict/[jobId]/page.jsx`; `web/src/app/panel/page.jsx`), dan panel juri menjalankan cek deterministik **sungguhan** di browser lewat `POST /api/evaluate` atas port `format`+`links` di `web/src/lib/checks.js`. Paritas port itu **dijaga tes** (`web/test/checks-parity.test.js`, 5 tes lewat `pnpm -r test` — butir 18). Yang BELUM: panel tidak menjalankan gerbang cap, tidak membaca memori, tidak mengirim tx (dinyatakan di halamannya sendiri), dan permukaan hapus-memori `DEMO_MODE` sempat gagal review keamanan sebelum ditutup — riwayat lengkap + risiko RENDAH yang masih diterima ada di butir 36 |
| Watcher event | butir 9 |

### 12. Batasan artefak: file memori tidak ikut di-commit

`data/` ada di `.gitignore:3`, jadi `memory.db` rantai A/B/C dan bundel bukti `reasonHash` **tidak ada di
repo publik**. Rekonstruksi root oleh pihak ketiga menuntut file itu diserahkan lebih dulu; perintah
verifikasinya (`agent/memory_export.py --check`) tidak menyentuh DB. Klaim "siapa pun bisa merekonstruksi
root" karena itu benar secara mekanis, tetapi hari ini belum ada publikasi filenya.

### 13. Token escrow di Base Sepolia BUKAN USDC Circle

`paymentToken()` kontrak ACP = `0xECc22a8F6fD62388498fBa19813E214605a2BDb3`, dan itu **bukan** USDC Circle
`0x036CbD53842c5426634e7929541eC2318f3dCF7e`. Keduanya bersimbol `USDC`, jadi bandingkan **alamat**, bukan
`symbol()` (`deployments/84532.json` → `notes`). Token testnet itu juga punya `mint()` tanpa kontrol akses
(ADR-017/ADR-021) — fakta yang ikut membentuk keputusan cap di butir 8.

### 14. Insentif evaluator BELUM diperbaiki — wasit ini masih dibayar hanya kalau ia meluluskan

Ini pembalikan terbesar dalam repo ini, jadi ia diulang di sini setelah disebut di paragraf pembuka.

`evaluatorFeeBP()` pada kontrak ACP = **500** (5%), dan fee itu **hanya cair saat job `Completed`**
(`docs/spec.md` §1 baris 19; tabel aliran dana `deployments/pipeline-84532.md:84`). Konsekuensi aritmetiknya
pada chain hari ini:

- job **417** (`Completed`, dan job yang evaluator **LULUSKAN**) → vault menerima **50.000** unit;
- job **418, 419, 420** (rantai demo A/B/C, tiga-tiganya **REJECT**) → vault menerima **0**;
- job **421** (`Completed`, demo kedalaman — evaluator **LULUSKAN**) → vault menerima **12.500** unit
  (5% dari budget 250.000);
- job **422** (**REJECT**, deliverable yang sama persis dengan 421 — butir 25) → vault menerima **0**.

Totalnya bisa Anda baca sendiri, dan angkanya **naik** justru pada job yang diluluskan:

```
$ cast call 0xECc22a8F6fD62388498fBa19813E214605a2BDb3 "balanceOf(address)(uint256)" \
    0x5c6EE4586ACABcb6326069c229E58091B21ef384 --rpc-url https://sepolia.base.org
62500
```

**62.500 = 50.000 (job 417) + 12.500 (job 421), dan dua-duanya berasal dari job yang DILULUSKAN.** Empat
job yang ditolak menyumbang nol rupiah. Seluruh 62.500 itu **hangus permanen** karena `sweepToken` tidak ada
di bytecode terdeploy (butir 4).

Jadi pada submission ini fee memang mengalir persis mengikuti bias yang dikritik ERC-8183: bayaran datang
hanya bersama kelulusan. Perbaikannya — client membayar di muka lewat x402 dengan tarif identik untuk
`complete` maupun `reject` — dirancang di ADR-004, dan gerbang 402-nya **ada** hari ini
(`agent/agent/payment_402.py`) tetapi **belum dikonsumsi jalur job** (butir 23). Yang mencegah bias itu
berlaku hari ini bukan struktur insentif, melainkan hal yang jauh lebih lemah: fee-nya terkunci di vault
sehingga tidak ada pihak yang bisa menikmatinya.

### 15. Kontrak submission KINI terverifikasi di Sourcify (`exact_match`) — dari commit `8d3e596`, bukan HEAD

Versi README sebelumnya menyatakan kueri Sourcify mengembalikan
`{"match":null,"creationMatch":null,"runtimeMatch":null}`. Itu **sudah tidak berlaku** sejak 8 Sep 2026:

```
$ curl -s https://sourcify.dev/server/v2/contract/84532/0x5c6EE4586ACABcb6326069c229E58091B21ef384
match: exact_match   creationMatch: exact_match   runtimeMatch: exact_match
```

Nilainya dicatat di `deployments/84532.json:36-44` (`sourcify`), beserta perintah pengecekan ulangnya dan
tautan repo Sourcify. **Yang membuat klaim ini bisa ditelusuri adalah dari mana ia diverifikasi**: sumber
**commit `8d3e596`**, BUKAN HEAD — HEAD sudah memuat `sweepToken` yang tidak ada di bytecode on-chain
(butir 4). Sebelum diunggah, build dibandingkan dengan `cast code` dan angkanya dicatat apa adanya
(`deployments/84532.json:31-32`):

- panjang runtime **sama, 3518 byte**;
- **174 byte berbeda, SELURUHNYA di dalam `immutableReferences`** (`acp`, `agent`, `arbiter`, `MIN_BOND`)
  — nol byte berbeda di luar span immutable;
- **hash metadata 32 byte terakhir IDENTIK** (jebakan yang kami tabrak: `lib/` sebagai symlink membuat
  remapping absolut masuk metadata solc, dan diff palsu naik jadi 206 byte — jadi worktree verifikasinya
  menyalin `lib/` secara fisik).

**Batas yang tetap berlaku, dan tolong jangan digeneralisasi ke semua explorer.** Blockscout menarik
verifikasi Sourcify itu dan kini **mendekode event vault dengan nama** — `Finalized`,
`MemoryRootUpdated`, `VerdictPosted`, `ProviderCapSet`, `FinalizeFailed`
(`https://base-sepolia.blockscout.com/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384?tab=logs`).
**BaseScan tidak ikut**, karena Etherscan tidak mengimpor dari Sourcify dan verifikasi di sana menuntut
API key yang tidak ada di repo ini; status di BaseScan karena itu **tidak kami klaim ke arah mana pun**.
Di explorer mana pun, transaksi, event, dan hasil `cast call` yang dijadikan bukti di README ini tetap
nyata dengan atau tanpa verifikasi source.

Satu batas provenance lama yang **tidak** berubah: artefak `contracts/broadcast/Deploy.s.sol/84532/
run-1788469622537.json` — yang merekam sendiri `"commit": "8d3e596"` dan init code byte-identik dengan
build revisi itu — dibuang oleh `.gitignore:6`, jadi **ia tidak ada di repo publik**. Sourcify kini
menutup kebutuhan akan artefak itu untuk pertanyaan "sumber mana yang jadi bytecode ini"; yang masih
menuntutnya hanyalah pemeriksaan init code + argumen konstruktor secara mandiri.

### 16. Jangkar root itu melingkar, dan tidak ada konsekuensi bagi root karangan

Dua fakta yang harus dibaca berdampingan:

- **Off-chain:** `_require_derived_root` membandingkan root di calldata dengan root yang **baru saja
  dihitung agen dari file yang ia baca sendiri** (`agent/agent/vault_client.py:1339`, `_require_derived_root`).
- **On-chain:** `postVerdict` hanya menolak root **nol** (`if (memoryRoot == bytes32(0)) revert
  ZeroMemoryRoot();`, `contracts/src/EvaluatorVault.sol:303`). Root **apa pun** yang bukan nol diterima.

Artinya root membuktikan "**agen men-hash sebuah file**", bukan "**file itu memori yang sebenarnya**".
Dan bila root itu karangan, tidak ada satu pun konsekuensi yang menunggu: `MIN_BOND` = 0 (butir 1),
`challenge`/`resolve` stub (butir 2), arbiter == agen (butir 3). Digabung dengan butir 10, jalur terburuknya
utuh: DB tukaran → mode NORMAL → verdict penuh + root palsu ter-anchor selamanya, tanpa penantang.

### 17. Cap DITERBITKAN di kontrak, tetapi TIDAK ditegakkan di kontrak

Yang menolak job C adalah **agen Python off-chain**, bukan kontrak. Di
`contracts/src/EvaluatorVault.sol` kata `providerCap` muncul **tepat dua kali**: baris **142** (deklarasi
`mapping(address => uint256) public providerCap;`) dan baris **289** (penulisan di `setProviderCap`).
**Nol pembacaan** — tidak ada cabang di `postVerdict` atau `finalize` yang membandingkan budget job dengan
cap. Kontrak berfungsi sebagai **papan pengumuman yang bisa dibaca siapa pun**, dan itu tetap berguna
(angkanya publik, terikat waktu, dan bisa dibandingkan dengan verdict) — tetapi ia bukan penegak.

### 18. `pnpm -r test` kini menjalankan SATU proyek — dan `sim/` tetap nol tes

Versi README sebelumnya menyatakan suite ketiga `make test` hijau atas **nol proyek**. Itu **tidak lagi
benar**: `web/package.json:11` sekarang punya `"test": "node --test test/checks-parity.test.js"`, jadi
`pnpm -r test` menjalankan **satu** proyek dengan **lima** tes.

Isinya menutup celah yang dulu kami akui sendiri: klaim "port `web/src/lib/checks.js` menghasilkan array
`checks` yang identik dengan bundel bukti on-chain" dulu hanya **diperiksa sekali dengan tangan**, kini
**dijaga tes** (`web/test/checks-parity.test.js`). Yang dibandingkan bukan keluaran port dengan keluaran
port: teks dibaca dari `web/public/deliverables/<jobId>.json` dan harapannya dari
`web/public/verdicts/<jobId>.json`, dengan ikatan `sha_keccak` teks == `evaluation.deliverable` bundel
diperiksa lebih dulu (`:65-71`), lalu **seluruh objek cek** dibandingkan field demi field — `check`,
`criterion`, `depth`, `detail`, `pattern`, `proof`, `section`, `status` (`:77-93`) — plus `failed_checks`,
`unverified`, `category`, `depth`, `verdict` (`:95-99`) dan katalog kriteria deterministik (`:103-110`),
untuk job **418, 419, 421, 422**. Runner-nya `node:test` bawaan Node major line 24 (`docs/versions.md:9`,
aktual `v24.15.0`) — **nol dependensi baru**. `web/test/` sengaja di luar `tsconfig.lint.json` karena
impor `node:test`/`node:fs` menuntut `@types/node` yang tidak dipin.

**Yang TIDAK dijaganya** dan tidak boleh salah dibaca: paritas **port cek deterministik**, bukan bahwa
panel menjalankan gerbang cap atau membaca memori — panel memang tidak melakukan keduanya (butir 36),
dan kriteria kualitatif (`qualitative.0`) sengaja tidak diport karena rubric LLM dipotong (butir 33).

**Yang masih benar dari batasan lama:** `sim/` **tetap tanpa satu pun tes otomatis** —
`sim/package.json:6-10` memuat `job:min`, `sim:run`, `demo`, `mint:client`, `typecheck`, dan tidak satu
pun `test`. Jadi satu-satunya kode yang menyentuh SDK Virtuals masih dijaga hanya oleh rantai on-chain
yang dijalankan tangan. `forge test` dan `uv run pytest` nyata.

### 19. Tes destruktif: kedua varian kini diotomasi — yang belum adalah ARTEFAKNYA

Sebagian besar batasan ini sudah dicabut, dan versi README sebelumnya masih menyatakan sebaliknya. Keadaan
hari ini, apa adanya:

**Varian A — degradasi (commit `a03e294`).** `make demo` menjalankan §7 langkah 1-4 dari nol di Anvil lokal;
langkah 4-nya adalah varian destruktif pertama — vault segar + memori kosong, sehingga job C yang DITOLAK
saat memori ada menjadi **lolos** saat memori tidak ada, pada budget yang IDENTIK. Dua eksekusi berturut-turut
memberi ringkasan identik. Label modenya `normal`, bukan `naive` — baca butir 34 sebelum mengutipnya.

**"Cacat KASAR" pada varian A BUKAN tingkat keparahan yang dinilai.** Baris ringkasan varian A membedakan
"cacat halus LOLOS" dan "cacat kasar DITOLAK" (`sim/src/demo.ts:929-935`), dan itu mudah dibaca seolah
evaluator mengenal dua kelas keparahan. Ia tidak. Cacat "kasar" adalah **token `TODO` yang SAMA persis**,
hanya **dipindah ke bagian PERTAMA** dokumen: `sim/scenarios/coarse-defect.md:3` vs
`sim/scenarios/depth-demo.md:11` (bagian ketiga) — dua berkas dengan cacat identik pada posisi berbeda.
Karena `SAMPLING_SECTION_LIMIT = 2`, yang pertama duduk **di dalam** jendela `sampling` dan yang kedua di
luarnya. Jadi yang dibuktikan varian A adalah: **memori yang hilang menurunkan KEDALAMAN, bukan mematikan
evaluator — cacat di dalam jendela sampling tetap tertangkap** (`sim/src/demo.ts:110-116`, dan properti
kedua berkas itu diikat `agent/tests/test_criteria.py`). Tidak ada penilaian keparahan, dan tidak ada
kriteria kualitatif yang dinilai sama sekali (butir 33).

**Varian B — mode aman (commit `986fad6`).** Ia **juga sudah diotomasi**, di perintah yang sama: root
on-chain non-nol + `memory.db` dihapus → **mode aman**, nol `postVerdict`, job menggantung sampai
`expiredAt`. Ia tidak dipentaskan di chain buatan sendiri melainkan dijalankan atas **vault Sepolia yang
beku**, dan ia **menggugurkan seluruh run** bila salah satu buktinya tidak muncul — exit agen ≠ 0, baris
`MODE AMAN:` tidak tercetak, `gerbang memori: mode=safe` tidak tercetak, pemicunya bukan aturan (a) "file
hilang", ada `postVerdict`/`finalize`/`setProviderCap` yang terkirim, atau nonce wallet agen berubah
(`sim/src/demo.ts:672-685`, pesannya berbentuk `VARIAN B GUGUR: …`). Itu juga sebab `make demo` menuntut
internet (butir 34).

**Yang MASIH belum ada, dan itu artefaknya, bukan otomasinya.** `make demo` membuat direktori
`agent/data/demo/logs/` (`sim/src/demo.ts:71` dan `:618`) tetapi **tidak pernah menulis satu berkas pun ke
dalamnya** — tidak ada satu pun penulisan berkas di skrip itu. Seluruh bukti demo karena itu hanya **stdout
yang lewat**, dan `data/` ter-gitignore (butir 12). Tidak ada fixture, dan tidak ada berkas pendamping untuk
klaim "md5 identik sebelum/sesudah" pada tabel di bawah. Jadi tabel tes destruktif itu tetap **laporan** yang
tidak bisa Anda cocokkan dengan berkas mana pun di repo; yang bisa Anda lakukan adalah menjalankan
`make demo` sendiri dan membandingkannya dengan mata.

### 20. Pihak ketiga tidak bisa mengulang rantai A/B/C pada vault ini

Vault dibekukan (ADR-022) dan `agent` immutable milik tim (butir 3), jadi **orang lain tidak akan pernah
bisa membuat vault INI mengumumkan verdict atau cap**. Yang bisa dilakukan pihak ketiga: (a) **membaca
ulang** seluruh bukti on-chain di bawah dengan `cast`/BaseScan, dan (b) mendeploy vault sendiri dari HEAD —
yang bytecode-nya sudah berbeda dari yang terdeploy (butir 15). Reproduksi mandiri "dari nol sampai tx yang
sama" bukan sesuatu yang bisa kami tawarkan.

### 21. "Provider curang" di rantai demo adalah simulator kami sendiri, dan polanya satu kata

Job A dan B tidak berasal dari provider nyata: `demo/deliverables/418.json` dan `419.json` adalah stub tiga
baris yang ditulis `sim/`, dan **keduanya memuat kata "TODO"**. Detektornya satu regex,
`agent/agent/checks/format.py:47-50`:

```python
_PLACEHOLDER_RE: Final = re.compile(
    r"(?i)(?:\b(?:todo|tbd|fixme|wip|lorem ipsum|coming soon|placeholder|to be filled)\b"
    r"|<[a-z][a-z0-9 _-]{2,30}>)"
)
```

Jadi kalimat "pola SAMA dari job BERBEDA" yang memicu promosi memori berarti, secara harfiah: **kata "TODO"
diketik dua kali oleh skrip kami sendiri, pada dua jobId berbeda**. Mekanisme promosinya (≥ 2 job berbeda,
bukti wajib dari cek deterministik) memang yang diuji, dan itu berjalan — tetapi provider yang menghapus
satu kata itu **lolos** cek `format`. Cek `links` dan `chain` juga berjalan (butir 11), sedangkan sandbox
dan rubric LLM tidak. Kekuatan detektornya bukan bagian dari klaim proyek ini; yang diklaim adalah apa yang
dilakukan memori **sesudah** sebuah cek deterministik gagal.

---

### 22. `lastMemoryRoot()` vault SENGAJA tidak sama dengan `memory_export` atas DB hari ini

Ini pembalikan dari cara README versi sebelumnya menjual proyek ini, dan kami tulis eksplisit supaya Anda
tidak menemukannya sendiri di meja penilaian. Dua perintah di bawah **tidak** memberi nilai yang sama, dan
memang tidak seharusnya:

```
$ cd agent && uv run python -m agent.memory_export --db ./data/chain-abc/memory.db --out /tmp/mem.json
memory_root: 0x50750074c376526f2d86d7bc85234c10cabda21bcc31c9cabe69e50aeac90c3c

$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "lastMemoryRoot()(bytes32)" \
    --rpc-url https://sepolia.base.org
0x999a957070e0740b81f1142cd6a5173ff53f446ad1ea3e6e240a20abd2789b7d
```

Sebabnya **struktural, bukan angka basi**: `docs/spec.md` §5 langkah 5 menulis memori **sesudah**
`postVerdict`. Root `0x999a9570…9b7d` adalah keadaan memori **sebelum** job 422 menulis hasilnya; DB hari
ini sudah memuat tulisan itu, sehingga ia **satu langkah tulis di depan** chain. Nilai
`0x50750074…0c3c` belum pernah diumumkan on-chain — ia akan menjadi root yang diumumkan pada `postVerdict`
**berikutnya**. Vault dibekukan (ADR-022), jadi `postVerdict` berikutnya tidak akan pernah terjadi pada
vault ini, dan selisih satu langkah itu **permanen**.

**Pasangan yang benar-benar cocok hari ini** adalah root on-chain dengan **bundel bukti** job yang
mengumumkannya — dan ikatan itu lewat hash, bukan lewat kepercayaan:

```
# root yang diumumkan job 422 (topic1 MemoryRootUpdated, dan argumen memoryRoot VerdictPosted)
0x999a957070e0740b81f1142cd6a5173ff53f446ad1ea3e6e240a20abd2789b7d

# field memory_root di dalam bundel bukti job 422
$ cd agent && uv run python -c "import json;print(json.load(open('data/chain-abc/verdicts/422-0x2b0ca5747abea9c81c5f85741e8cdc92dab3b44f92bbbcbc03aec59ddcbc0704.json'))['memory_root'])"
0x999a957070e0740b81f1142cd6a5173ff53f446ad1ea3e6e240a20abd2789b7d

# dan bundel itu sendiri terikat ke reasonHash on-chain: keccak256(byte file) == nama file == reasonHash
0x2b0ca5747abea9c81c5f85741e8cdc92dab3b44f92bbbcbc03aec59ddcbc0704
```

Kelima bundel (418, 419, 420, 421, 422) memenuhi kecocokan `keccak256(isi file) == nama file` itu. Yang
dibuktikan pasangan ini: **root, verdict, dan alasan terikat dalam satu hash yang sudah diumumkan on-chain
sebelum eksekusi.** Yang **tidak** dibuktikannya: bahwa isi memori pada saat itu sah — untuk itu Anda butuh
file DB pada keadaan tersebut, dan keadaan itu sudah hilang (butir 7 dan 16). Batasan publikasi file
memori: butir 12.

### 23. Gerbang 402 ADA, tetapi registrasinya BELUM dikonsumsi jalur job

Versi README sebelumnya menulis bahwa gerbang pembayaran ini "tidak ada di repo". Itu **salah, dan salah ke
arah yang meremehkan**: berkasnya ada di `agent/agent/payment_402.py` (dengan tesnya di
`agent/tests/test_payment_402.py`). Yang benar adalah batasan yang lebih tepat:

- **Yang berjalan:** `POST /jobs/register` menjawab **402** beserta skema pembayarannya bila tidak ada
  header pembayaran, dan menjawab **200** hanya setelah server **membaca sendiri** kuitansinya on-chain —
  transfer harus berasal dari token escrow, mendarat di penerima yang benar, menutup jumlahnya, dan membawa
  hash transaksi yang belum pernah dipakai. Dalam `DEMO_MODE` header dummy diterima, tetapi jawabannya
  **menyatakan** itu sehingga 200 tidak pernah bisa disalahbaca sebagai pembayaran terverifikasi.
- **Yang BELUM:** registrasi yang dihasilkannya **tidak dikonsumsi oleh jalur job mana pun.** Tidak ada
  satu pun keputusan evaluasi hari ini yang berubah karena sebuah job "terdaftar". Jadi ini **demo mekanisme
  pembayaran**, bukan fitur produksi yang menghidupi antrean job.
- **Pembayarannya adalah kredensial bearer, dan itu bukan kiasan.** Yang diperiksa hanyalah **isi** transfer,
  bukan siapa yang menuntutnya: `nonce` di tantangan tidak pernah disimpan dan tidak pernah dibandingkan
  saat klaim (transfer ERC-20 polos tidak membawa memo), dan pengirimnya tidak pernah dibaca. Jadi siapa pun
  yang melihat transaksi itu di mempool/explorer bisa **mendahului** klien yang benar-benar membayar dengan
  mengutip hash yang sama lebih dulu. Ini ditulis di modulnya sendiri, bukan ditemukan auditor.
- **Ia TIDAK memperbaiki insentif fee.** Fee di muka ADR-004 yang membuat wasit dibayar sama besar entah ia
  meluluskan atau menolak (butir 14) **belum berlaku**: `evaluatorFeeBP` tetap hanya cair saat `Completed`.
- **Ini BUKAN protokol x402, dan menyebutnya begitu dilarang** oleh **ADR-010 keputusan 4**. Paket x402
  resmi memang ada (PyPI `x402` 2.22.0) dan **sengaja tidak dipakai**: skema `exact` EVM-nya berjalan di atas
  EIP-3009 `transferWithAuthorization`, sedangkan token escrow ACP tidak punya fungsi itu — pada bytecode
  terdeploy, selector `0xe3ee160e` muncul **nol** kali dengan kontrol positif `transfer` (`0xa9059cbb`) = 1.
  Angka `402` di sini adalah status HTTP yang benar-benar dikembalikan (RFC 9110 §15.5.3), bukan merek
  protokol; nama skema di `WWW-Authenticate` adalah `OnchainPayment`, dan larangan memakai nama `x402`
  di situ dijaga tes.

### 24. Wallet simulator TIDAK terdaftar di Service Registry Virtuals — dan itu menentukan multiplier

Fakta ini sebelumnya hanya hidup di komentar kode, padahal ia menentukan salah satu kriteria penilaian
hackathon. Kami naikkan ke permukaan:

```
POST https://api.acp.virtuals.io/auth/agent
→ 404  Agent not found with wallet address 0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2
```

Sumber: `sim/src/client_min.ts:510-512` (komentar hasil verifikasi 2026-09-04). Baris kode itu sendiri
menulis placeholder `<client>`, bukan alamatnya; alamat literalnya dikreditkan ke ADR-019
(`docs/decisions.md:385`), dan ia memang `jobs(417..422).client` on-chain. Artinya wallet
client simulator kami **belum pernah didaftarkan** sebagai agen di Service Registry Virtuals. Konsekuensinya
jujur-jujuran ada tiga:

1. **`session.submit()` SDK tidak bisa menaruh teks deliverable** ke API off-chain Virtuals — itu sebabnya
   teks dibaca dari artefak lokal `demo/deliverables/<jobId>.json` (butir 6), bukan dari API resmi.
2. **Multiplier "agen terdaftar di Virtuals" tidak boleh kami klaim.** Yang bisa kami klaim adalah bahwa
   seluruh transaksi ACP berjalan lewat SDK Virtuals sungguhan
   (`@virtuals-protocol/acp-node-v2@0.1.12`) dan bahwa `evaluatorAddress` diisi alamat vault kami — itu
   terlihat di jejak transaksi. Pendaftaran registry adalah hal yang **berbeda**, dan kami belum punya.
3. Pendaftaran itu butuh aksi manusia di sisi Virtuals; ia **tidak** diblokir oleh kode kami, dan kami
   tidak menyajikannya seolah sudah selesai.

### 25. Demo kedalaman (job 421 vs 422): teks IDENTIK, verdict BERBEDA — dan apa yang TIDAK dibuktikannya

Ini bukti terkuat yang kami punya untuk klaim "memori mengubah keputusan", jadi batasannya wajib ikut
tertulis. Dua job dijalankan dengan **teks deliverable yang sama byte demi byte**
(`keccak256(text)` = `0x246071b30c435f192b9ffcb064a11178bc2bd25a02819a1ad7c3b8ee24bf0a51` pada
`demo/deliverables/421.json` dan `422.json`), budget sama (250.000), evaluator sama (vault), tetapi dari
**provider yang berbeda**:

| job | provider | riwayat di memori | depth | hasil cek | verdict on-chain |
|---|---|---|---|---|---|
| **421** | `0xc3c6Bf20…aeff` (bersih) | nol insiden | `sampling` — hanya **2 bagian pertama** yang dibaca | `format.no-placeholder` **pass** ("tanpa penanda pekerjaan pada 2 bagian yang dibaca") | `VerdictPosted(kind=1)` → `Finalized` → **status 3 (Completed)** |
| **422** | `0x20212E4D…b321` (2 insiden: job 418, 419) | risk 2 | `full` | `format.no-placeholder` **fail** — `TODO` pada **bagian KETIGA** (bundel menulis `section: 2`, indeks 0-basis) | `VerdictPosted(kind=2)` → `Finalized` → **status 4 (Rejected)** |

Empat transaksi yang bisa Anda buka sendiri:

```
job 421  postVerdict  0x02356b079fa3bfcd32e62d7e2bb61d3f4eb8b66d29fac578cd6318b2028a1467  (blok 46455461)
job 421  finalize     0x371a4db2ed4c7975f3806f64392f92ecba2132feb9a1df78889c31af9bcaf020  (blok 46455526)
job 422  postVerdict  0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830  (blok 46455552)
job 422  finalize     0x502c8d944106914b15d95a38b2815187fa7b3d63965d95414ccd7f15835b5f08  (blok 46455616)
```

Yang dibuktikan: **kedalaman pemeriksaan diturunkan dari memori, dan kedalaman itu benar-benar mengubah
verdict** — cacatnya nyata (`TODO` di bagian ketiga) dan hanya terlihat pada `depth=full`. Rantai A/B/C
membuktikan gerbang cap; pasangan 421/422 membuktikan gerbang kedalaman, dan keduanya jalur kode yang
berbeda.

Yang **tidak** dibuktikannya, dan ini wajib dibaca bersamanya:

- **Kedua provider adalah simulator kami sendiri** (butir 21). Yang membedakan keduanya hanyalah riwayat
  yang kami tanam lewat job 418/419, bukan perilaku pihak ketiga yang independen.
- **Cacatnya satu kata.** `TODO` dikenali regex penanda pekerjaan (`agent/agent/checks/format.py:47-50`);
  ini bukan deteksi kecurangan yang canggih (butir 10). Berlaku juga untuk kata "kasar" vs "halus" di
  ringkasan `make demo`: itu **posisi** token yang sama di dalam/di luar jendela sampling, **bukan** dua
  tingkat keparahan yang dinilai — penjelasan penuhnya di butir 19.
- **`sampling` vs `full` hanya berbeda kalau dokumennya lebih panjang dari batas sampling.** Deliverable
  421/422 sengaja dibuat **TIGA bagian** (`# Summary`, `## Cara kerja`, `## Catatan lanjutan`) dengan
  `TODO` ditaruh di bagian **ketiga**, sementara `SAMPLING_SECTION_LIMIT = 2`
  (`agent/agent/checks/base.py:78`) — jadi `sampling` membaca dua bagian pertama dan **tidak pernah sampai**
  ke cacatnya, `full` membaca ketiganya dan menemukannya. Pada artefak demo lama (418/419) yang hanya satu
  bagian, `sampling` dan `full` membaca **persis** jumlah bagian yang sama sehingga kedalaman tidak bisa
  mengubah apa pun. Perhatikan dua konvensi indeks yang berbeda di tabel di atas: bundel bukti memakai
  indeks **0-basis** (`section: 2` = bagian ketiga), sedangkan prosa cek memakai **hitungan** bagian
  ("2 bagian yang dibaca").
- **Bundel `kind:"evaluation"` TIDAK memuat blok `gate`.** Hanya bentuk `gate-rejection` (job 420) yang
  punya. Akibatnya bundel 421/422 — justru dua artefak yang kami tawarkan sebagai bukti terkuat —
  **tidak bisa membuktikan sendiri** kepada auditor bahwa yang menolak job 422 adalah gerbang kedalaman
  dan bukan gerbang cap. Yang menutup celah itu hari ini hanyalah pembacaan kode (`criteria.py` hanya
  menerima `depth`, tidak pernah `risk`), bukan artefaknya. Ini utang yang diketahui, bukan yang baru
  ketahuan.
- **Job 421 yang lulus itulah yang membayar evaluator** 12.500 unit (butir 14) — bias insentif yang kami
  kritik tetap berlaku pada demo ini sendiri.

---

### 26. Verdict yang salah tidak bisa dibatalkan siapa pun — `CHALLENGE_WINDOW` adalah latensi, bukan perlindungan

Butir 2 sudah menyebut `challenge`/`resolve` sebagai stub. Yang ditambahkan di sini adalah **akibatnya
sampai habis**, karena reviewer keamanan menjalankan seluruh matriksnya sebagai tes musuh, bukan membacanya:

| Yang mencoba membatalkan verdict salah | Yang ia dapat | Bukti |
|---|---|---|
| agen sendiri (`postVerdict` ulang atas job yang sama) | `VerdictAlreadyPosted()` | `contracts/src/EvaluatorVault.sol:307`; `contracts/test/EvaluatorVault.t.sol:446` |
| penantang, membawa bond ETH | `NotImplemented()` — dan ETH-nya kembali utuh karena tx dibatalkan | `EvaluatorVault.sol:327-331`; `test_challenge_reverts` (`EvaluatorVault.t.sol:865-885`, keempat peran, dengan dan tanpa `msg.value`) |
| arbiter | `NotImplemented()` | `EvaluatorVault.sol:341-345`; `test_resolve_arbiter_reverts_notImplemented` (`:887`) |
| pihak asing yang ingin menjalankan verdictnya | **berhasil** — `finalize` permissionless, dan job benar-benar berpindah ke status 3 (`Completed`), yaitu **pembayaran nyata ke provider** | `EvaluatorVault.sol:363` (`finalize` tanpa modifier peran); `test_authMatrix_finalize_openToAllRoles` (`:987-997`, keempat peran, `assertEq(_status(jobId), 3)`) |

Jadi kalimat yang harus Anda bawa keluar dari bagian ini, tanpa pelunakan:

> **`CHALLENGE_WINDOW` = 120 detik pada kontrak submission adalah MURNI LATENSI. Ia memberi NOL
> perlindungan.** Selama dua menit itu tidak ada satu pun panggilan yang bisa menghentikan verdict; sesudah
> dua menit itu siapa pun boleh mengeksekusinya, dan uangnya berpindah.

Satu-satunya hal yang berdiri antara verdict salah dan pembayaran hari ini adalah **agen yang menahan diri
sebelum menandatangani**, bukan kontraknya. Itulah kenapa butir 16, 29, 30, dan 31 di bawah penting: seluruh
pertahanan nyata ada di sisi off-chain.

### 27. Guard `ArbiterEqualsAgent` ada di SKRIP DEPLOY, bukan di kontrak

Butir 3 menempel keluaran `cast` yang menunjukkan `arbiter() == agent()`. Yang belum tertulis: kontraknya
sendiri **tidak pernah** melarang keadaan itu. Yang melarangnya hanya skrip deploy —
`contracts/script/Deploy.s.sol:64` (`error ArbiterEqualsAgent();`) dan `:112`
(`if (arbiter == agent && !allowArbiterEqAgent) revert ArbiterEqualsAgent();`) — jadi guard itu bisa
dimatikan lewat `ALLOW_ARBITER_EQ_AGENT`, dan pada deploy submission memang dimatikan.

`EvaluatorVault.sol` sendiri tidak punya cabang itu di konstruktor mana pun. NatSpec `sweepToken` bahkan
menyandarkan alasan `onlyArbiter`-nya pada guard tersebut:

> `` `onlyArbiter`, bukan `onlyAgent`: agen adalah pihak yang mengumumkan verdict, jadi memberinya kunci ke
> hasil finansial dari verdictnya sendiri meniadakan pemisahan peran yang justru dijaga guard
> `ArbiterEqualsAgent` di skrip deploy. `` (`contracts/src/EvaluatorVault.sol:255-257`)

Pemisahan peran yang dijanjikan kalimat itu **tidak ada pada instans terdeploy**, dan tidak akan pernah ada:
kontraknya immutable dan ADR-022 keputusan 1 membekukannya sebagai kontrak submission. Baca NatSpec itu
sebagai niat rancangan, bukan sebagai gambaran vault `0x5c6EE45…f384`.

### 28. `BondTooLow` tidak pernah menyala — evaluator tidak mempertaruhkan apa pun, dan ETH pun terjebak

`postVerdict` memang memeriksa bond (`if (bond < MIN_BOND) revert BondTooLow();`,
`contracts/src/EvaluatorVault.sol:304`), tetapi `MIN_BOND` pada kontrak terdeploy = **0**
(`deployments/84532.json` → `"minBondWei": "0"`, butir 1). `bond` bertipe `uint256`, jadi `bond < 0`
mustahil: **pada vault submission cabang `BondTooLow` tidak bisa dijangkau sama sekali.** Jangan baca
keberadaan error itu di ABI sebagai perlindungan yang hidup.

Angkanya juga jangan dibaca sebagai "bond kecil": yang dipertaruhkan evaluator hari ini adalah **nol**.
Dan seandainya ia menyetor pun, ETH itu tidak bisa keluar — tidak ada satu pun jalur ETH keluar dari vault
(disengaja, ADR-013; NatSpec `sweepToken` menegaskan fungsi itu "tidak `payable`, tidak pernah menyentuh
`bond`", `EvaluatorVault.sol:243-247`). Untuk ERC-20 keadaannya sama buruknya lewat jalan lain:
`sweepToken` ADA di sumber tetapi **tidak ada di bytecode terdeploy**, sehingga 62.500 unit fee evaluator
hangus permanen (butir 4). **Dua-duanya, ETH maupun ERC-20, terjebak permanen di vault.**

### 29. Pihak yang bisa menulis `memory.db` bisa MELONGGARKAN cap sampai tanpa batas

Butir 10 menjelaskan apa yang terjadi kalau memori **hilang**. Ini kebalikannya: apa yang terjadi kalau
memori **ditulisi**. Modul memori menyatakannya sendiri, apa adanya
(`agent/agent/memory_policy.py:45-51`):

> `CAP BISA DILONGGARKAN SAMPAI TANPA BATAS. … penulis memory.db tidak hanya bisa mematikan agen, ia bisa
> MENIMPA body provider menjadi risk_level: 0 tanpa cap_usdc, sehingga derive_cap mengembalikan NO_CAP →
> cap_to_onchain = 0 → di kontrak berarti TANPA BATAS (ADR-001). Monoton tidak-naik tidak menolong:
> jangkarnya adalah cap_usdc yang tersimpan di body yang sama, dan penyerang menghapusnya bersamaan.`

Ia juga bisa menghapus `incident_jobs`, `confirmed_patterns`, dan seluruh entity provider sekaligus.

**Mitigasinya nyata tetapi berlubang, dan lubangnya harus disebut.** `gate_job` memakai `providerCap()`
on-chain sebagai **lantai** — cap dari memori yang lebih longgar daripada yang sedang ditegakkan vault tidak
dipakai (`agent/agent/memory_policy.py:1752-1758`), dan `setProviderCap` yang menaikkan cap ditolak
`_require_onchain_cap_floor` (`agent/agent/vault_client.py:1440`, dipanggil dari `_send()` :1484). Lubangnya
ada di baris berikutnya di kode yang sama: **`providerCap == 0` BUKAN lantai** — ia berarti TANPA BATAS
(ADR-001, `agent/agent/vault_client.py:1547`). Jadi pada provider yang belum pernah diberi cap, lantai itu
tidak ada, dan penulis memori bebas sepenuhnya.

### 30. `memory.db` yang DITUKAR dengan DB lain tidak terdeteksi

Ini penajaman butir 10, dan kami ulang di sini karena mudah terlewat di tengah daftar pemicu: mode aman
memeriksa **keadaan FILE** memori — hilang, tidak bisa dibaca, atau terkunci instans lain — dan **tidak
pernah memeriksa isinya** (`agent/agent/memory_policy.py:59-63`; ADR-024 konsekuensi menuliskan
`HILANG: deteksi "memory.db diganti DB LAIN", baik kosong maupun terisi`). DB tukaran yang terbaca membawa
agen ke **mode normal**, bukan mode aman.

### 31. `postVerdict` menerima `reasonHash` nol dan jobId apa pun; `UnknownMemoryRoot` tidak bisa dipicu

Dua hal yang membuat "perlindungan berbasis root di kontrak" menjadi salah baca:

- **`postVerdict` hampir tidak memvalidasi apa-apa.** Ia menolak `kind` di luar {1,2}, menolak `memoryRoot`
  nol, dan menolak verdict ganda — selesai (`contracts/src/EvaluatorVault.sol:301-320`). `reasonHash` **nol
  diterima**, dan `jobId` **tidak pernah dicek keberadaannya di ACP**. Artinya jangkar `lastMemoryRoot` bisa
  digerakkan atas job yang tidak pernah ada. Mitigasinya jujur: lewat kode kami hal itu tidak menggigit,
  karena `_require_derived_root` menolak menandatangani bila `memory_root` di calldata bukan turunan memori
  yang baru saja dibaca agen (`agent/agent/vault_client.py:1339`, dipanggil dari `_send()` :1473) — nol
  transaksi terkirim. Yang tidak tertutup adalah pemanggilan **langsung** ke kontrak dengan kunci agen,
  yang tidak melewati kode kami sama sekali.
- **`UnknownMemoryRoot` di `finalize` vestigial.** `finalize` menuntut `knownRoots[v.memoryRoot]`
  (`EvaluatorVault.sol:369`), tetapi `postVerdict` menulis `verdicts[jobId].memoryRoot` **dan**
  `knownRoots[memoryRoot] = true` dalam **satu transaksi yang sama** (`:312` dan `:315`). Tidak ada penghapus
  `knownRoots` (butir 7), jadi syarat itu selalu terpenuhi begitu verdictnya ada. **Penjaga itu tidak bisa
  dipicu pada kontrak ini.**

Kesimpulannya, dan ini yang tidak boleh salah dibaca dari diagram alur mana pun di README ini:
**fail-closed berbasis root sepenuhnya hidup di sisi agen, bukan di kontrak.** Kontraknya hanya menolak root
nol (butir 16).

### 32. Agen tidak punya batas waktu saat menunggu jendela challenge

Sesudah `postVerdict` mendarat, agen menunggu `readyAt` dengan loop tanpa batas atas:

```python
log.info("menunggu jendela challenge sampai readyAt=%d", ready_at)
while True:
    now = client.w3.eth.get_block("latest")["timestamp"]
    if now > ready_at:
        break
    ...
    time.sleep(min(20, max(2, ready_at - now + 1)))
```

(`agent/agent/vault_client.py:2586-2592`.) Tidak ada `deadline`, tidak ada jumlah percobaan maksimum. Bila
RPC macet atau `block.timestamp` berhenti maju, **prosesnya menggantung tanpa exit code dan tanpa satu baris
log yang menyatakan ia menyerah** — operator hanya melihat baris "sisa N detik" atau tidak ada apa-apa.
Verdictnya sendiri sudah aman on-chain dan `finalize` permissionless (butir 26), jadi pemulihannya adalah
memanggil `finalize` dari luar; tetapi otomasinya tidak menyediakan itu sendiri.

### 33. Kriteria kualitatif TIDAK DINILAI — tidak ada LLM di jalur mana pun

Butir 11 menyebut rubric LLM "dipotong". Yang perlu ditegaskan: pemotongan itu **tidak** membuat kriteria
kualitatif dianggap lolos, dan juga tidak diam-diam. Ia dicatat sebagai kategori tersendiri di setiap bundel
bukti — `unscored` beserta `unscored_reason` (`agent/agent/criteria.py:390-392` dan `:423-424`) dengan teks
konstan:

> `kriteria kualitatif TIDAK DINILAI di 2.3-min: rubric LLM dipotong (PM 5 Sep). Ia dicatat apa adanya,
> tidak pernah dianggap lolos.` (`agent/agent/criteria.py:121-124`, dikunci `agent/tests/test_criteria.py:336-337`)

Jadi **tidak ada satu pun panggilan LLM di jalur evaluasi hari ini.** Yang berjalan hanyalah cek
deterministik `format`, `links`, `chain` (butir 11). Bila README, video, atau post mana pun terbaca seolah
ada penilaian kualitatif, itu salah baca — bahasanya sengaja tidak menjanjikannya.

### 34. `make demo` BUTUH internet, dan label mode pada varian A adalah `normal`

Dua koreksi terhadap cara demo mudah disalahpahami.

**Internet.** Varian A berjalan sepenuhnya di Anvil lokal, tetapi varian destruktif B sengaja membaca
**vault Sepolia yang beku** supaya `lastMemoryRoot()` non-nol yang memicu mode aman adalah keadaan nyata,
bukan keadaan yang dipentaskan (`sim/src/demo.ts:125` `SEPOLIA_RPC = "https://sepolia.base.org"`; blok
varian B `:655-687`). Sifat sentuhan itu: **hanya baca — nol dana, nol transaksi**, dan itu diukur bukan
diucapkan, lewat nonce wallet agen sebelum vs sesudah (`txBaru`, `demo.ts:943`; baris `VARIAN B:` `:947`).
Konsekuensi praktisnya: **tanpa internet, `make demo` tidak selesai** — dan ia berhenti **PREFLIGHT di
detik pertama, sebelum Anvil menyala**, dengan exit 1 (`demo.ts:362` `preflight.ok`).

Satu koreksi terhadap versi README sebelumnya, yang mengkritik cacat yang **sudah tidak ada**: komentar
`Makefile` **tidak lagi** menulis "Tidak menyentuh jaringan apa pun" (`grep -rn "Tidak menyentuh jaringan"
Makefile` → kosong). Yang tertulis di sana sekarang justru sudah benar dan lebih tajam: "BUTUH INTERNET:
varian B membaca vault BEKU di Base Sepolia … NOL dana, NOL transaksi, NOL kunci privat, hanya dua
pembacaan view", beserta alasan kenapa kegagalannya keras (`Makefile:50-54`).

**Label mode.** Pada varian A, `plan.mode` yang dilaporkan agen adalah **`normal`, bukan `naive`** — sebab
invokasi pertama melahirkan `memory.db` lalu ditolak `MODE_DRIFT`, dan yang menghasilkan verdict adalah
invokasi kedua yang sudah punya DB (ADR-026; `sim/src/demo.ts:461-489`). Yang menunjukkan degradasinya
karena itu **bukan** label modenya, melainkan dua kolom lain di baris ringkasan: **`depth=sampling`** dan
**`cap=TANPA CAP`** (`demo.ts:826-841`). Jangan menyebut varian A "mode naif": kata itu hanya muncul sebagai
baris log invokasi pertama yang berakhir dengan nol transaksi, dan bukan mode yang pernah melahirkan verdict
lewat CLI.

### 35. Pembagian peran `sim/` dan `agent/` — `sim:run` memang tidak menghasilkan verdict

Ini bukan batasan melainkan pembacaan yang gampang salah, dan tempatnya paling berguna di sini.

`sim/` adalah **client ACP**: ia membuat, mendanai, dan menyerahkan job (`createJob → setBudget → fund →
submit`) lewat SDK `@virtuals-protocol/acp-node-v2`, dan berhenti tepat pada status yang dituntut naskah
demo — `SUBMITTED` untuk job A/B, `FUNDED` untuk job C — lalu mencetak `jobId`-nya. `sim/src/scenario.ts:34-39`
menyatakan batas itu sendiri:

> `BATAS: skrip ini menyiapkan JOB, bukan VERDICT. … Yang menghasilkan verdict adalah agent/; skrip ini
> berhenti tepat pada status yang dituntut tiap langkah … dan mencetak jobId-nya supaya agen bisa
> dijalankan atasnya.`

`agent/` adalah **evaluatornya**, dan ia dipanggil **per jobId** dengan
`uv run python -m agent.vault_client --job-id <N> --kind reject|complete` (butir 9) — **bukan** dipanggil
oleh `sim/`. Watcher event diturunkan dari jalur kritis oleh ADR-022 keputusan 3, jadi tidak ada proses yang
menjembatani keduanya secara otomatis di luar `make demo`, yang menjalankan kedua sisi itu berurutan sebagai
orkestrator demo (`sim/src/demo.ts`). Karena itu `pnpm sim:run` yang selesai **tanpa** verdict adalah
perilaku yang benar, bukan kegagalan; kolom `expectVerdict` di skenario adalah ekspektasi naskah, bukan
pengamatan. Batasan yang menyertainya: `sim/` belum punya satu pun tes otomatis (butir 18).

### 36. Permukaan hapus-memori di panel juri: GAGAL review keamanan, lalu ditutup — riwayatnya ditulis penuh

Panel juri (`/panel`) punya tombol hapus memori untuk mempertunjukkan tes destruktif di depan penonton.
Permukaan itu **sempat diberi verdict BLOKIR oleh review keamanan**, dengan **dua temuan TINGGI**, dan
kami menuliskannya di sini apa adanya alih-alih menghapus riwayatnya — bagian ini menceritakan apa yang
gagal, apa yang diperbaiki, dan apa yang **masih** kami terima sebagai risiko.

**Yang gagal.** (a) **CSRF** pada endpoint hapusnya: menghapus adalah **efek samping**, bukan bacaan,
sehingga CORS tidak pernah menjadi pertahanan — satu tab jahat cukup mengirim
`<form method=POST action="http://127.0.0.1:8010/demo/memory/reset">`, yang mengirim `text/plain`
(daftar aman CORS) sehingga tidak ada preflight yang menahannya, dan penyerang tidak perlu bisa membaca
jawabannya. (b) Proksi Next **mengekspos penghapus loopback ke LAN**, karena default Next adalah mengikat
`0.0.0.0`.

Pelajarannya ditulis di kodenya sendiri dan layak dibawa keluar dari repo ini:
**"loopback saja" BUKAN pertahanan terhadap browser, karena browser juri juga ada di loopback**
(`agent/agent/demo_reset.py:32-41`, batas 4 dan 5).

**Yang diperbaiki, dan bagaimana ia dibuktikan tertutup.** Reviewer **mengulang persis serangan yang dulu
berhasil**: form POST lintas-asal `text/plain` yang dulu menjawab `200 {"deleted": [3 berkas]}` kini
dijawab **403 `cross_origin_request`** dengan ketiga berkas utuh (`agent/agent/demo_reset.py:126`,
`check_same_origin` :394-417), dan `curl` dari IP LAN tertahan **dua lapis** — `serve()` menolak peer
non-loopback (`LOOPBACK_HOSTS`, :82) **dan** Next kini terikat `-H 127.0.0.1` (`web/package.json:7,9`).
POST kini juga menuntut `Content-Type: application/json` **persis** (memaksa preflight) serta `Host` yang
menyebut loopback + port server ini, sehingga DNS rebinding ikut tertutup (`_check_host` :420-438).
Satu temuan **SEDANG** — TOCTOU pada komponen leluhur path — ditutup lewat jalur **`dir_fd`**: penghapusan
tidak lagi memakai path string melainkan fd direktori akar, sehingga leluhur tidak pernah diresolve ulang
(`_open_root_fd`, `_remove` :301-336). **Review ulang: nol KRITIS, nol TINGGI, verdict LANJUT.**

**Yang MASIH diterima sebagai risiko, disebut supaya tidak perlu Anda temukan sendiri:**

- **RENDAH — `resetUrl()` membatasi HOST, bukan PORT.** Proksi Next menolak `NEXT_PUBLIC_AGENT_RESET_API`
  yang hostname-nya di luar loopback (`LOOPBACK_HOSTS`, `web/src/app/api/demo/memory/reset/route.js:47,59`)
  tetapi **tidak** membatasi portnya, jadi env yang salah ketik masih bisa mengarahkan POST ini ke port
  loopback lain. Diterima apa adanya.
- **Sisa balapan yang diakui docstringnya sendiri:** entri bernama sama masih bisa ditukar antara `open`
  dan `unlink`. Dampaknya terbatas pada **kejujuran laporan** — `unlink(dir_fd=…)` tidak mengikuti symlink
  pada komponen terakhir dan namanya **tidak bisa keluar** dari direktori yang dipegang fd, jadi berkas
  yang hilang lewat jalur ini selalu entri di dalam akar demo itu sendiri
  (`agent/agent/demo_reset.py:314-318`).

**Batas kerusakannya, dan ini yang paling penting**: tombol hanya dirender bila `DEMO_MODE=1` — dibaca
**di server** per permintaan (`web/src/app/panel/page.jsx:8,19`), jadi tidak ada penanda di HTML yang bisa
dibalik dari klien, dan tanpa env itu endpoint agennya **tidak terdaftar sama sekali** → 404, bukan 403
(`agent/agent/demo_reset.py:15-20`). Sasarannya **hanya memori demo** (`agent/data/demo/`, diturunkan dari
`agent_root()` dan **tidak pernah** dari permintaan): ia **tidak pernah** diberi kuasa atas
`agent/data/chain-abc/memory.db`, satu-satunya berkas yang bisa merekonstruksi root on-chain (butir 7
dan 12). Ketiga berkas SQLite (`memory.db`, `-wal`, `-shm`) disapu, karena WAL yang tertinggal bisa
memulihkan isinya dan "memori dihapus" yang menyisakan WAL adalah hijau palsu.

Tetap berlaku sebagai kebiasaan baik: jalankan `web/` lewat script yang sudah memin `-H 127.0.0.1`, dan
nyalakan `DEMO_MODE=1` hanya saat Anda memang sedang mempertunjukkan tes destruktifnya.

---

## Masalah → solusi

ERC-8183 menaruh seluruh kepercayaan pada evaluator dan tidak memberinya alasan untuk jujur: evaluator
adalah "fully trusted", `evaluatorFeeBP` hanya cair saat job **Completed** sehingga wasit dibayar kalau ia
meluluskan, tidak ada pembayaran parsial (Completed = 100% ke provider, Rejected/Expired = 100% refund), dan
evaluator standar bersifat stateless — provider yang sama bisa mengulang trik yang sama pada job berikutnya
tanpa jejak apa pun (`docs/spec.md` §1). The Evaluator memasang tiga hal di atas spek: **memori provider yang
di-anchor on-chain** (tiap `postVerdict` mengumumkan `memoryRoot`; root keadaan **sekarang** bisa dihitung
ulang dari file memori, root keadaan antara tidak — butir 7 dan 16),
**gating budget lewat hak `reject()` saat `Funded`** yang sudah ada di spek sehingga tidak butuh hook
ter-whitelist (ADR-001), dan **evaluator berupa kontrak** (`EvaluatorVault`) yang memegang verdict, jendela
waktu, dan jangkar memori (ADR-003).

Dari tiga cacat spek di atas, submission ini menyerang **satu**: kelupaan (stateless). Cacat insentif fee
tetap berlaku pada wasit ini sendiri (butir 14), dan "tidak ada pembayaran parsial" tidak kami sentuh sama
sekali — Rejected tetap berarti refund 100% ke client, bukan pembayaran sebagian ke provider.

### Siapa yang memakainya di hari pertama, dan kenapa ia mau membayar

Pertanyaan yang wajar: kalau saya sudah bisa menaruh alamat saya sendiri di `evaluatorAddress`, kenapa saya
butuh ini? Jawaban kami menunjuk satu konsumen konkret, bukan "agen pada umumnya":

**Konsumennya: operator yang menjalankan banyak job ACP ke provider yang sama berulang kali** — dalam repo
ini diperankan oleh `sim/` sebagai client, dan di luar repo ini bentuk nyatanya adalah tim yang mem-borong
pekerjaan berulang (riset, ringkasan, pengumpulan data) ke sekumpulan provider yang itu-itu juga. Ciri yang
membuatnya jadi konsumen hari pertama: **ia bertemu provider yang sama lebih dari sekali**, jadi kelupaan
evaluator langsung berubah jadi kerugian berulang.

**Kenapa `evaluatorAddress` = EOA sendiri TIDAK cukup untuk orang itu:**

1. **EOA tidak punya ingatan yang bisa ditunjukkan.** Ia bisa saja menolak job, tetapi ia tidak bisa
   membuktikan kepada provider (atau kepada siapa pun) **atas dasar riwayat apa** ia menolak. Di sini
   alasan penolakan terikat hash ke bundel bukti yang memuat `incident_jobs` dan cap, dan hash itu
   diumumkan on-chain sebelum eksekusi (butir 22).
2. **EOA adalah hakim yang menilai perkaranya sendiri.** Client yang menjadi evaluator atas job-nya sendiri
   punya insentif menolak supaya dapat refund 100%. Memindahkannya ke evaluator pihak ketiga yang
   ingatannya bisa diaudit memisahkan dua peran itu — dan bila ingatan itu **hilang**, agen berhenti
   bertransaksi alih-alih menebak (butir 22, "Tes destruktif").
3. **Kalibrasi tidak bisa disalin ke job berikutnya.** Yang membuat job 422 ditolak bukan aturan baru,
   melainkan kedalaman pemeriksaan yang **diturunkan dari dua job sebelumnya** — pada teks yang identik
   dengan job yang diluluskan (butir 25). EOA tanpa memori akan meluluskan keduanya.

**Berapa yang ia bayar, dan berapa yang ia hemat.** Angka yang bisa kami tunjukkan hari ini datang dari
demo, bukan dari riset pasar, jadi kami sebut apa adanya sebagai **ilustrasi bertanda**, bukan harga yang
tervalidasi. Tarif kontrak `evaluatorFeeBP` = **500** (5% dari budget). Pada job 422 (budget 250.000 unit
testnet) itu berarti **12.500 unit** — dan yang dihindarinya adalah membayar **250.000 unit penuh** untuk
deliverable yang memuat `TODO` yang belum selesai, karena Rejected berarti refund 100% ke client (tidak ada
pembayaran parsial di ERC-8183). **Rasionya 1:20**: bayar 5% untuk menghindari kehilangan 100% pada job yang
seharusnya tidak lulus. Ambang impasnya karena itu rendah — evaluator ini "membayar dirinya sendiri" bila ia
menangkap lebih dari satu job cacat dari setiap dua puluh.

Dua hal yang membuat angka itu belum boleh dibaca sebagai bukti permintaan: (1) 5% adalah tarif yang sudah
ada di kontrak ACP, **bukan** harga yang kami tetapkan atau uji; (2) hari ini fee itu hanya cair saat
`Completed`, jadi justru pada job 422 yang ditolak evaluator menerima **0** (butir 14) — struktur yang
membuat rasio 1:20 di atas menjadi argumen untuk fee di muka (ADR-004), bukan gambaran arus kas hari ini.

**Kejujuran yang menyertainya:** hari ini konsumen itu adalah simulator kami sendiri (butir 21), belum ada
pengguna pihak ketiga, gerbang pembayaran 402 yang akan menagihnya belum tersambung ke jalur job
(butir 23), dan wallet simulatornya belum terdaftar di Service Registry Virtuals (butir 24). Yang sudah nyata adalah mekanismenya di chain; yang belum adalah permintaannya.

## Alur

```
CLIENT ──createJob(evaluator = VAULT)──► ACP (Base Sepolia) ◄──setBudget / submit── PROVIDER
                                              │
                                              │ getJob + log JobFunded / JobSubmitted
                                              ▼
                                 Evaluator Agent (Python, dipanggil per job)
                                   • cek deterministik: format, links, chain
                                   • memori Sibyl: provider / pattern / suspicion(karantina)
                                   • derive_cap(memori) — hanya bisa mengetat
                                              │
                                              │ setProviderCap(provider, cap)
                                              │ postVerdict(jobId, kind, reasonHash, memoryRoot)
                                              ▼
                                 EvaluatorVault 0x5c6EE45…f384
                                   • emit MemoryRootUpdated(memoryRoot)
                                   • tunggu CHALLENGE_WINDOW = 120 detik
                                   • finalize() → acp.complete / acp.reject
                                              ▼
                                    JobCompleted / JobRejected
```

## Bukti on-chain: rantai A → B → C (Base Sepolia, 6 Sep 2026)

Tiga job dari **satu** provider `0x20212E4D95A75E6716575ED26e884cdeFf66b321`:

| Job | Budget | Hasil | Yang berubah di memori |
|---|---|---|---|
| **A = 418** | 1.000.000 | REJECT | cek `format` gagal (kata "TODO", butir 21) → pola `format.placeholder-text`, karantina count = 1, cap 0 → 1.000.000 |
| **B = 419** | 1.000.000 | REJECT | pola SAMA dari job BERBEDA → count = 2 → promosi ke `reference:pattern` + `provider.confirmed_patterns`, **risk = 2** → cap 1.000.000 → 250.000 |
| **C = 420** | 2.000.000 | **REJECT saat `Funded`** | budget > cap → ditolak sebelum provider sempat submit; status akhir job = 4 |

Baca kolom terakhir dengan dua batas yang sudah disebut di atas: yang dipelajari memori adalah **risk level
dan pola**, sedangkan **angka** cap 250.000 adalah konstanta tim dibagi 4 (`sample_size: 0`, butir 8); dan
"pola curang" di sini adalah kata "TODO" dari simulator kami sendiri (butir 21). Karantina (`suspicion`)
tidak pernah dibaca pengambil keputusan; promosi menuntut ≥ 2 job berbeda dengan bukti dari cek
deterministik (ADR-002, `docs/spec.md` §3 aturan 1-2).

**`JobRejected` job C** — field log yang dicocokkan (bukan dump mentah lengkap):

```
$ cast logs --address 0x0b93793923CD5De81850aF8604a233f3f24d461e \
    0xae7362b1af91f4492868987b9c73990d780060811551b58728fbe96fd1bab275 \
    0x00000000000000000000000000000000000000000000000000000000000001a4 \
    --from-block 46426499 --to-block 46436498 --rpc-url https://sepolia.base.org

blockNumber:     46436498
transactionHash: 0x78a3a65db3160f199bddf8eb6e703c000ab322e7fa49dea2058fd93ea794989e
topics[0]:       0xae7362b1af91f4492868987b9c73990d780060811551b58728fbe96fd1bab275   JobRejected(uint256,address,bytes32)
topics[1]:       0x00000000000000000000000000000000000000000000000000000000000001a4   jobId = 0x1a4 = 420
topics[2]:       0x0000000000000000000000005c6ee4586acabcb6326069c229e58091b21ef384   rejector = VAULT
data:            0x1618e7653959fcdbd11565a41e7688ce12e1a6abca3a12f1746ed5348262b5ed   reason
```

[Lihat transaksinya di
BaseScan](https://sepolia.basescan.org/tx/0x78a3a65db3160f199bddf8eb6e703c000ab322e7fa49dea2058fd93ea794989e).
Dua jebakan yang sudah kami tabrak, supaya Anda tidak: `rejector` adalah alamat **vault**, bukan EOA agen —
bukti yang mencari alamat agen akan gagal palsu; dan `cast logs "<signature>" <jobId>` **tidak** memfilter
(cast 1.7.1 mengabaikan argumen sesudah signature secara diam-diam). Yang memperbaikinya **bukan** sekadar
mem-pad topic-nya: selama signature masih ikut dikirim, topic-nya tetap diabaikan. Yang bekerja adalah
membuang signature-nya dan mengirim topic0 + topic1 bersama `--address`, persis bentuk blok di atas. Kontrol negatif dengan jobId `999999` pada rentang yang sama mengembalikan hasil KOSONG, jadi
filternya memang menggigit.

**Cap-nya DITERBITKAN di kontrak dan bisa dibaca siapa pun — yang MENOLAK job C adalah agen off-chain:**

```
$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 \
    "providerCap(address)(uint256)" 0x20212E4D95A75E6716575ED26e884cdeFf66b321 \
    --rpc-url https://sepolia.base.org
250000
```

250.000 < budget job C 2.000.000 → REJECT. Perbandingan itu terjadi di **proses Python**, bukan di
Solidity: `EvaluatorVault.sol` menulis `providerCap` (baris 289) dan **tidak pernah membacanya**
(butir 17). Nilai di atas adalah angka yang diumumkan agen sebelum menolak, bukan penegak penolakannya.

**Root memori yang diumumkan bisa dihitung ulang dari file memori — tetapi hanya pada keadaan yang
melahirkannya.** Root yang diumumkan job 420 adalah `0xcfdab1b0…5b26`:

```
$ cast logs --address 0x5c6EE4586ACABcb6326069c229E58091B21ef384 \
    0xc6028d32061c1f0b8f4f1370b6f1ab5105a96bfc6631a3840371ebbcb27c7923 \
    --from-block 46436434 --to-block 46436434 --rpc-url https://sepolia.base.org
blok 46436434  jobId 420  root(topic1) 0xcfdab1b0…5b26
```

**Peringatan yang wajib dibaca bersamanya, supaya Anda tidak menyalin blok ini dan mendapat MISMATCH:**
`memory_export.py` atas DB hari ini **tidak** mencetak nilai itu, dan `lastMemoryRoot()` vault juga tidak —
keduanya sudah maju melewati job 420 (job 421 dan 422 mendarat sesudahnya). Memori ditulis **sesudah**
`postVerdict` (`docs/spec.md` §5 langkah 5), jadi setiap root on-chain adalah keadaan **sebelum** job itu
menulis hasilnya, dan DB selalu **satu langkah tulis di depan** chain. Nilai kedua perintah itu hari ini,
beserta pasangan yang benar-benar cocok, ada di **butir 22**.

Nilai yang sama juga muncul sebagai `memory_root` di bundel bukti job 420 — dan **ikatan bundel↔chain itulah
yang bisa Anda verifikasi hari ini** (butir 22). Ekspor dan `postVerdict` memakai
**satu implementasi** yang sama, bukan salinan (`agent/agent/memory_policy.py` → `memory_root_for_onchain`),
dan encoding-nya dikunci vektor beku di `agent/tests/fixtures/memory_root_vector.json`. Perhitungan ulang
lintas bahasa ada di `agent/tools/memory_root_check.mjs`.

Yang **tidak** dibuktikan oleh kecocokan ini, supaya tidak ada yang salah baca: ia membuktikan agen
men-hash file yang ia baca, bukan bahwa file itu memori yang sah — perbandingannya melingkar dan on-chain
hanya root nol yang ditolak (butir 16). Batasan publikasi filenya: butir 12; batas audit mundur: butir 7.

**`reason` on-chain adalah hash bundel bukti, bukan angka acak.** Bundel job 420 memuat
`"cap": {"usdc": 250000}` dan `"incident_jobs": [418, 419]`; keccak256 atas byte file bundel itu identik
dengan `data` log di atas (`0x1618e765…b5ed`) — nama file bundelnya memang berisi hash tersebut. Bundel juga
menyimpan `mode: normal` dan `memory_root`, sehingga verdict, memori, dan alasan terikat dalam satu hash.

## Tes destruktif

Pertanyaan yang paling wajar dari juri: kalau memorinya dihapus, apakah ada yang berubah?
Dijalankan **6 Sep 2026 di Anvil lokal** (nol transaksi ke Base Sepolia; vault submission dan file memori
rantai A/B/C tidak berubah — md5 identik sebelum/sesudah).

> **Baca tabel ini sebagai laporan, bukan sebagai bukti.** Skripnya kini ADA — `make demo` menjalankan
> kedua varian destruktif (Batasan butir 19) — tetapi ia tidak meninggalkan satu berkas pun: tidak ada log,
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
gating cap (`docs/spec.md` §3 aturan 6).

Catatan jujur soal lingkungan: varian di atas berjalan pada vault **segar** (root on-chain = 0). Pada vault
submission yang sudah hidup, menghapus `memory.db` memicu **mode aman**, bukan degradasi — agen berhenti
total dan job menggantung sampai `expiredAt` (Batasan butir 10). **Kedua varian kini dijalankan oleh satu
perintah `make demo`**: varian A di Anvil lokal, varian B atas vault Sepolia yang beku — hanya baca, nol
dana, nol transaksi, dan run digugurkan bila buktinya tidak muncul (Batasan butir 19 dan 34). Yang belum
ada bukan otomasinya melainkan artefaknya: perintah itu tidak meninggalkan log atau fixture di repo.

## Di luar spek ERC-8183 — dan kenapa

| Tambahan | Alasan | ADR |
|---|---|---|
| **EvaluatorVault** sebagai alamat evaluator (bukan EOA) | spek tidak punya bond/challenge/timeout evaluator; spek mengizinkan evaluator berupa kontrak | ADR-003 |
| **Jangkar memori on-chain** (`MemoryRootUpdated`, `knownRoots`) | tiap eksekusi ke ACP terikat root yang sudah diumumkan SEBELUM eksekusi; batasnya: dari **delapan** root vault hanya **418** yang bisa dihitung ulang hari ini, sisanya keadaan antara yang hilang permanen (butir 7), dan jangkarnya melingkar (butir 16) | ADR-011 |
| **Gating cap lewat `reject()` saat `Funded`** | hook kustom butuh whitelist admin Virtuals yang tidak kami punya; hak reject saat Funded sudah ada di spek. Penegakannya off-chain; kontrak hanya menerbitkan cap (butir 17) | ADR-001 |
| **Karantina sebagai entity `suspicion`** | Sibyl hanya punya HOT/WARM/COLD/REFERENCE/ARCHIVE — tidak ada tier FLAGGED, jadi karantina dibangun sebagai konvensi, dan pengambil keputusan dilarang membacanya | ADR-002 |
| **Bond + jendela sengketa** | dirancang, tetapi hari ini `MIN_BOND` = 0 dan `challenge`/`resolve` stub — lihat Batasan butir 1-2 | ADR-013 |
| **Fee di muka via x402** | fee kontrak hanya cair saat Completed → insentif meluluskan, **termasuk pada wasit ini sendiri**. **Belum diimplementasikan** (Batasan butir 11 dan 14) | ADR-004 |

## Integrasi Base & Virtuals

| Komponen | Alamat / paket |
|---|---|
| EvaluatorVault (kontrak submission) | `0x5c6EE4586ACABcb6326069c229E58091B21ef384` |
| ACP (implementasi ERC-8183 Virtuals, Base Sepolia) | `0x0b93793923CD5De81850aF8604a233f3f24d461e` |
| ACP implementation di balik proxy | `0xc4E95dBc7E8C99c114FF9C8299A3E4851e1530fF` |
| Token escrow (`paymentToken()`) | `0xECc22a8F6fD62388498fBa19813E214605a2BDb3` |
| Wallet agen (menggerakkan vault) | `0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894` |
| Client simulator | `0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2` |
| Provider simulator | `0x20212E4D95A75E6716575ED26e884cdeFf66b321` |

Sumber: `deployments/84532.json` (jaringan `base-sepolia`, chainId 84532) dan
`deployments/pipeline-84532.md`. Vault dideploy di blok 46350667 dengan solc 0.8.36 (evm `osaka`,
optimizer runs 200), memakai 816.969 gas — semua angka itu ada di `deployments/84532.json`. Kontraknya
**terverifikasi di Sourcify dengan `exact_match`** (creation dan runtime), dari sumber commit `8d3e596`,
sehingga **Blockscout** mendekode event vault dengan nama; BaseScan tidak menariknya (Batasan butir 15):
`https://base-sepolia.blockscout.com/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384?tab=logs`

**SDK Virtuals dipakai sungguhan, bukan dekorasi.** Seluruh transaksi ACP di simulator lewat
`@virtuals-protocol/acp-node-v2@0.1.12` (`sim/package.json:12`); `sim/src/client_min.ts:11-14` menyatakan
dan menepati bahwa file itu tidak meng-encode satu pun calldata ACP sendiri — kalender panggilan, ABI, dan
urutan approve+fund datang dari SDK, dan yang kami sediakan hanya adapter penanda tangan viem
(`IEvmProviderAdapter`). `evaluatorAddress` diisi eksplisit dengan alamat vault: default SDK adalah alamat
nol = "skip evaluation", yang akan langsung membayar provider tanpa wasit. Batasnya, dan ini yang paling
lemah dari seluruh repo: **`sim/` tidak punya satu pun tes otomatis** (butir 18) — yang membuktikan jalur
SDK ini bekerja hanyalah transaksi Base Sepolia yang ditautkan di atas.

Pipa hidup pertama (job 417: `createJob → setBudget → fund → submit → postVerdict → finalize →
JobCompleted`) beserta enam hash transaksinya terdokumentasi di `deployments/pipeline-84532.md`.

## Reproduksi

```
make doctor    # cetak versi toolchain, exit 1 bila tidak cocok docs/versions.md
make test      # forge test + uv run pytest + pnpm -r test (yang ketiga = 5 tes paritas di web/;
               # sim/ masih tanpa tes — Batasan butir 18)
make demo      # rantai §7 langkah 1-4 dari NOL di Anvil lokal, ringkasan deterministik, lalu DUA
               # varian destruktif; varian B MEMBACA vault Sepolia beku — butuh internet
               # (hanya baca: nol dana, nol transaksi — Batasan butir 34)
               # RUNTIME TERUKUR: 3m23s dan 3m56s pada dua eksekusi. Angka "~2m20s" yang pernah
               # ditulis di sini berasal dari task 3.3, SEBELUM dua varian destruktif dan
               # preflight jaringan ditambahkan — jangan pakai untuk merencanakan rekaman.
```

`make doctor` membaca `node`/`forge` dari PATH yang hanya dimuat shell interaktif — jalankan dari terminal
biasa, bukan dari hook non-interaktif (pesan merahnya menjelaskan ini sendiri).

Rantai A/B/C dijalankan dengan perintah eksplisit, satu job per pemanggilan. Perintah ini menjalankan
rantai **baru** pada vault Anda sendiri; ia tidak mereproduksi job 418/419/420 pada vault submission, yang
`agent`-nya immutable milik kami (Batasan butir 20):

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
keamanannya ada di Batasan butir 36. Tes destruktif yang menjadi bukti submission dijalankan oleh
`make demo`, bukan oleh tombol ini.

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

Verdict tidak bisa dikalahkan flag: bila cek deterministik gagal (`Evaluation.passed == False`) atau gerbang
cap menolak, hasilnya REJECT apa pun isi `--kind`.

**Mereproduksi demo kedalaman (butir 25)** menuntut DUA provider, karena yang membedakan job 421 dan 422
hanyalah riwayat providernya. Pemilihnya `PROVIDER_SLOT` (`sim/src/client_min.ts:102,160-162`), dengan dua
nilai sah: `alpha` (default, kunci `PROVIDER_PRIVATE_KEY` — provider yang di rantai kami sudah punya dua
insiden) dan `beta` (`PROVIDER2_PRIVATE_KEY` — provider bersih):

```
# provider BERSIH → depth sampling → dua bagian pertama saja → LULUS
PROVIDER_SLOT=beta  BUDGET_RAW=250000 DELIVERABLE_FILE=sim/scenarios/depth-demo.md \
  pnpm --filter sim run job:min

# provider BERISIKO (2 insiden) → depth full → bagian ketiga terbaca → DITOLAK
PROVIDER_SLOT=alpha BUDGET_RAW=250000 DELIVERABLE_FILE=sim/scenarios/depth-demo.md \
  pnpm --filter sim run job:min
```

Sama seperti rantai A/B/C, ini menjalankan job **baru** pada vault Anda sendiri dan **tidak** mereproduksi
job 421/422 pada vault submission (Batasan butir 20). Yang menentukan hasilnya bukan flag mana pun,
melainkan apakah memori provider itu sudah memuat dua insiden — jadi urutan menjalankannya penting.

## Struktur repo

```
contracts/   EvaluatorVault.sol, IACP.sol, script/Deploy.s.sol, test/ (Foundry)
agent/       Python: memory_policy.py (skema memori, derive_cap, promosi), vault_client.py,
             memory_export.py (audit root), checks/{format,links,chain}.py, tools/memory_root_check.mjs
sim/         client simulator TypeScript di atas @virtuals-protocol/acp-node-v2 (tanpa tes — butir 18)
web/         Next.js: timeline job, halaman verdict+bukti, panel juri (port cek deterministik di
             src/lib/checks.js, paritasnya dijaga test/checks-parity.test.js); data dari JSON statis
             di web/public/, nol RPC dari browser (butir 18 dan 36)
demo/        deliverables/<jobId>.json (teks deliverable dari simulator, ADR-019 — butir 21)
deployments/ 84532.json (alamat + konstanta), pipeline-84532.md (pipa hidup job 417)
docs/        spec.md, decisions.md (ADR), api-facts.md (fakta API terverifikasi), versions.md
```

## Peta angka → sumber

| Angka | Sumber |
|---|---|
| `MIN_BOND` = 0 | `deployments/84532.json` → `minBondWei` |
| `CHALLENGE_WINDOW` = 120 detik | `deployments/84532.json` → `constants.CHALLENGE_WINDOW` |
| `MIN_ACP_GAS` = 300.000 | `deployments/84532.json` → `constants.MIN_ACP_GAS`; diturunkan dari pengukuran di ADR-015 keputusan 3 |
| `EVALUATOR_GRACE_PERIOD` = 900 detik | `docs/api-facts.md` §A KOREKSI 2026-09-03; ADR-014 |
| saldo vault = 62.500 unit (0,0625 USDC testnet) = 50.000 (job 417) + 12.500 (job 421); `evaluatorFeeBP` 500 = 5% | `cast call paymentToken "balanceOf(address)" <vault>` → `62500` (butir 4); `deployments/pipeline-84532.md:84` (tabel aliran dana); ADR-018 keputusan 2 |
| fee hanya cair saat `Completed` → fee evaluator untuk 418/419/420 = 0 | `docs/spec.md` §1 baris 19 (fakta ERC-8183) + status akhir 4 pada ketiga job, "Bukti on-chain" di atas |
| `BASELINE_CAP_USDC` 1.000.000; `MIN_CAP_USDC` 250.000 | ADR-020 keputusan 3 dan 5; ADR-021 keputusan 1 |
| cap job 420: `basis` "baseline-constant", `sample_size` 0, `usdc` 250.000 = ceil(1.000.000 / 4) | bundel bukti job 420; `agent/agent/memory_policy.py:1666` |
| `providerCap` ditulis di baris 289, dideklarasikan di baris 142, nol pembacaan | `contracts/src/EvaluatorVault.sol` (butir 17) |
| `postVerdict` hanya menolak root nol | `contracts/src/EvaluatorVault.sol:303` (`ZeroMemoryRoot`) |
| penjaga root off-chain membandingkan calldata dengan file yang dibaca agen sendiri | `agent/agent/vault_client.py:1339` (`_require_derived_root`, dipanggil :1473) (butir 16) |
| `agent`/`arbiter`/`MIN_BOND` immutable tanpa setter, tanpa pause | `contracts/src/EvaluatorVault.sol:14,106-114` |
| tiga pemicu mode aman; file hilang butuh root on-chain ≠ 0 | `agent/agent/memory_policy.py:1461-1500` |
| riwayat `MemoryRootUpdated` = **delapan** event; kedelapan root + jobId-nya | `cast logs` topic0 `0xc6028d32…7923`, blok 46350667→46455552 dalam jendela ≤ 9.999 blok (batas RPC publik, `docs/api-facts.md` §E); tabel lengkap di butir 7 |
| root job 418 `0x4e2a1ca1…ff5a` = root DB kosong (bisa direproduksi lewat `empty_memory_root()`, BUKAN lewat `memory_export.py` — alat itu menolak membuat DB); root 419/420/421/422 hilang permanen | `empty_memory_root()` di butir 7 vs `cast logs` di butir 7; `docs/spec.md` §5 langkah 5 (memori ditulis SESUDAH `postVerdict`) |
| Sourcify 84532/`0x5c6EE45…` → `exact_match` (creation + runtime), diverifikasi dari commit `8d3e596`; runtime 3518 byte, 174 byte berbeda seluruhnya di `immutableReferences`, hash metadata identik; broadcast tetap ter-gitignore | `deployments/84532.json:31-32` dan `:36-44` (`sourcify.check` memuat perintah `curl`-nya); `.gitignore:6` (butir 15) |
| `sim` tanpa script `test`; workspace = `sim`, `web` | `sim/package.json:5-8`; `pnpm-workspace.yaml` |
| regex penanda pekerjaan (satu kata memicu `format.placeholder-text`) | `agent/agent/checks/format.py:47-50`; `demo/deliverables/418.json`, `419.json` |
| job 418 / 419 / 420, budget 1.000.000 dan 2.000.000, status akhir 4 | keluaran `cast` di bagian "Bukti on-chain" |
| job 421 status 3 (Completed) / job 422 status 4 (Rejected), budget 250.000 keduanya | `cast call <ACP> "jobs(uint256)"` — ABI terverifikasi `docs/api-facts.md` §A, dipakai `agent/agent/vault_client.py:389-405` (butir 25) |
| `keccak256(text)` deliverable 421 == 422 == `0x246071b3…0a51` | `demo/deliverables/421.json`, `422.json` field `sha_keccak` (butir 25) |
| provider bersih job 421 = `0xc3c6Bf20…aeff`; provider berisiko job 422 = `0x20212E4D…b321` | `cast call <ACP> "jobs(uint256)"` (butir 25) |
| empat tx demo kedalaman (2× `postVerdict`, 2× `finalize`), blok 46455461-46455616 | daftar hash di butir 25 |
| gerbang 402 ada di `agent/agent/payment_402.py` (BUKAN `agent/x402_server.py`) | commit `a213cdd`, `3c5cafa`; tes `agent/tests/test_payment_402.py`; ADR-010 (butir 23) |
| wallet client simulator `0xbe2c447e…02C2` → 404 `/auth/agent` | `sim/src/client_min.ts:510-512` (komentar memakai placeholder `<client>`); alamat literal di ADR-019 `docs/decisions.md:385` + `jobs(417..422).client` on-chain (butir 24) |
| `providerCap` = 250.000 | `cast call providerCap(address)` di atas |
| blok 46436498, tx `0x78a3a65d…989e`, `reason` `0x1618e765…b5ed` | `cast logs JobRejected` di atas |
| `lastMemoryRoot()` = `0x999a9570…9b7d` (root job 422), sedangkan `memory_export` atas DB hari ini = `0x50750074…0c3c` — **sengaja berbeda satu langkah tulis** | `cast call lastMemoryRoot()` dan `memory_export.py` di butir 22; sebabnya `docs/spec.md` §5 langkah 5 |
| root warisan `0x1fa62c3d…7bf0` = `keccak("the-evaluator/live/memory-root/v1")` | `cast keccak` di Batasan butir 7; ADR-023 konteks |
| root selftest `0x5ff921fd…a19e` = `keccak("the-evaluator/selftest/memory-root/v1")` | `cast keccak` di Batasan butir 7; commit `26f11d6` (dicabut `190cb44`) |
| blok 46355036 / 46355080, jobId sintetis 9000000 / 9000001 (`0x895440` / `0x895441`) | `cast logs MemoryRootUpdated` di Batasan butir 7 |
| blok deploy 46350667, gas 816.969, solc 0.8.36, optimizer 200 | `deployments/84532.json` |
| chainId 84532 | `deployments/84532.json` |

## Lisensi

MIT — lihat [LICENSE](LICENSE).
