# The Evaluator

Wasit escrow ERC-8183 yang ingatannya tentang tiap provider bisa **dihitung ulang dari file**.

**Insentifnya BELUM diperbaiki.** Hari ini `evaluatorFeeBP` = 500 (5%) dan fee itu hanya cair saat job
berstatus `Completed` (`docs/spec.md` §1 baris 19, fakta ERC-8183 terverifikasi) — jadi wasit ini masih
dibayar hanya kalau ia **meluluskan**, persis bias yang menjadi alasan proyek ini ada. Di rantai demo
A/B/C (tiga REJECT) ia dibayar **0**, dan satu-satunya fee yang pernah ia terima — **50.000 unit dari job
417 yang ia LULUSKAN** — hangus permanen di vault yang tidak punya jalan keluar (Batasan butir 4 dan 14).
Fee di muka lewat x402, yang akan membuat kalimat "dibayar sama besar entah ia meluluskan atau menolak"
menjadi benar, adalah **rancangan (ADR-004), bukan fitur** (Batasan butir 11). Kalimat itu berasal dari
`docs/spec.md` §0, dan §0 berjudul "Pitch satu kalimat" — aspirasi, bukan catatan fakta; README ini tidak
mengutipnya lagi sebagai fakta.

Status: **proyek hackathon di Base Sepolia (testnet), belum pernah dijalankan di mainnet.** README ini
ditulis sebelum video demo direkam. Prosa berbahasa Indonesia; identifier, perintah, dan kutipan kode
berbahasa Inggris.

Kontrak submission (BEKU, ADR-022): [`0x5c6EE4586ACABcb6326069c229E58091B21ef384`](https://sepolia.basescan.org/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384)

---

## Batasan & asumsi kepercayaan

Bagian ini sengaja ditaruh **paling atas** dan ditulis lebih dulu daripada bagian pitch mana pun. Butir
1-13 dipindahkan apa adanya dari ADR dan artefak deploy; butir 14-21 ditambahkan sesudah audit "klaim vs
kenyataan" dan sumbernya adalah kode serta chain yang bisa Anda buka sendiri. Angkanya tidak dilunakkan.

Kalau waktu Anda hanya cukup untuk tiga: **butir 14** (insentif fee belum diperbaiki — pembalikan terbesar),
**butir 16** (jangkar root melingkar dan tanpa konsekuensi), **butir 19** (tes destruktif belum berartefak).

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

### 4. Kontrak terdeploy TIDAK punya `sweepToken`; 50.000 unit token hangus permanen

```
$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "sweepToken(address,address)" \
    0xECc22a8F6fD62388498fBa19813E214605a2BDb3 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894 \
    --rpc-url https://sepolia.base.org
execution reverted
```

`sweepToken(address,address) onlyArbiter` mendarat di **sumber** (commit `e675234`) sebagai kode + tes saja;
ADR-022 membekukan alamat di atas sebagai kontrak submission dan membatalkan redeploy, jadi fungsi itu
tidak ada di bytecode terdeploy.

Vault memegang **50.000 unit** token escrow, dan itu saldo yang masih bisa Anda baca sendiri sekarang:

```
$ cast call 0xECc22a8F6fD62388498fBa19813E214605a2BDb3 "balanceOf(address)(uint256)" \
    0x5c6EE4586ACABcb6326069c229E58091B21ef384 --rpc-url https://sepolia.base.org
50000
```

Angka itu = `evaluatorFeeBP()` 500 = 5% dari budget 1.000.000 job 417 (`deployments/pipeline-84532.md:84`,
tabel aliran dana) — satu-satunya job yang pernah `Completed`, dan job yang evaluator **luluskan**
(butir 14). Kalimat artefak itu apa adanya:

> `50.000 unit (0,05 USDC testnet) hangus permanen; ini dilepas secara sadar oleh ADR-018 keputusan 2,
> bukan kelalaian.`

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

### 7. Tiga dari enam root vault BUKAN turunan memori — dan satu root lagi hilang permanen

Jalur mundur ADR-018 aktif (ADR-022 membekukan v1), jadi riwayat root vault memuat sisa dari pipa awal.
Dua **nilai** root berikut adalah **konstanta berlabel**, bukan turunan memori (dan keduanya mengisi
**tiga** dari enam event `MemoryRootUpdated` — tabel lengkapnya di bawah). **Keduanya tidak bisa
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

blok 46355036  jobId 0x895440 = 8999488  root(topic1) 0x5ff921fd…a19e
blok 46355080  jobId 0x895441 = 8999489  root(topic1) 0x5ff921fd…a19e
```

(`MemoryRootUpdated` kedua argumennya `indexed`, jadi root ada di **topic1** dan `data` kosong — skrip yang
men-decode `data` akan mendapat hasil kosong.)

Keduanya sudah **DICABUT dari jalur produksi** oleh task 2.4b (commit `190cb44`): satu-satunya sumber
`memory_root` yang boleh dikirim ke `postVerdict` adalah `memory_policy.memory_root()`, fungsi yang sama yang
dipakai `agent/memory_export.py`, dan `_send()` **menolak menandatangani** bila root di calldata tidak cocok
dengan memori saat itu — penegakannya di `_send()`, bukan di pemanggil (`agent/agent/vault_client.py:186-201`).

Tetapi `postVerdict` menulis setiap root ke `knownRoots` **tanpa penghapus** (ADR-011), jadi kedua konstanta
itu tetap menjadi root sah selamanya di vault yang dibekukan. Bingkainya apa adanya: **vault submission
menyimpan jejak permanen dari fase sebelum aturan itu ada.** Itu fakta yang kami akui, bukan yang kami
sembunyikan.

**Seluruh riwayat root vault ini, keenamnya, supaya tidak ada yang tersisa untuk ditemukan sendiri.**
`MemoryRootUpdated` diemit **enam kali** sepanjang umur vault (`cast logs` atas topic0
`0xc6028d32…7923`, blok 46350667→46436600, dipecah sembilan jendela ≤ 9.999 blok karena batas RPC publik —
`docs/api-facts.md` §E). Root ada di topic1, jobId di topic2:

| # | root | jobId | apa itu | bisa dihitung ulang hari ini? |
|---|---|---|---|---|
| 1 | `0x5ff921fd…a19e` | 8999488 (sintetis) | konstanta selftest | tidak — konstanta berlabel, preimage di atas |
| 2 | `0x5ff921fd…a19e` | 8999489 (sintetis) | konstanta selftest | tidak — sama |
| 3 | `0x1fa62c3d…7bf0` | **417** | konstanta warisan pipa awal | tidak — konstanta berlabel, preimage di atas |
| 4 | `0x4e2a1ca1697b2a287fcfc8158fd5c460298aa69af8d5bec2d35671d71c4dff5a` | **418** | root memori **kosong** | **ya** — siapa pun bisa, dari DB baru |
| 5 | `0x3f506e52977407d8a4a1eb88179773f66679c992e6c74ac3cf20adcd7b9eecc2` | **419** | keadaan antara | **tidak — HILANG PERMANEN** |
| 6 | `0xcfdab1b0…5b26` | **420** | keadaan memori sekarang | **ya** — cocok dengan `memory_export.py` |

Baris 4 perlu dijelaskan supaya tidak terbaca lebih hebat dari yang sebenarnya: root job 418 **identik
dengan root DB kosong**, dan itu **kebetulan mekanis**, bukan properti yang kami rancang. Sebabnya ada di
`docs/spec.md` §5 langkah 5 — memori ditulis **sesudah** `postVerdict`, jadi saat verdict job A diumumkan,
memorinya memang masih kosong. Ia bisa direproduksi siapa pun: `memory_export.py` atas DB alas rantai
(keadaan sebelum job A) mencetak nilai yang sama persis, dan begitu pula DB baru mana pun. Justru karena
itu, root ini **tidak membuktikan apa-apa tentang isi memori** — ia hanya membuktikan memorinya kosong.

Jadi klaim yang benar bukan "hanya root terakhir yang bisa diaudit", melainkan: **root yang bisa diaudit
hari ini adalah 420 (keadaan sekarang) dan 418 (karena memorinya masih kosong saat itu); root 419 hilang
permanen.** DB Sibyl menyimpan keadaan **sekarang** — tidak ada tabel versi, tidak ada snapshot per job —
sehingga keadaan antara seperti 419 tidak bisa dibangun ulang begitu memori maju. Kesimpulannya tetap yang
paling penting: **jangkar ini kedaluwarsa setiap kali memori berubah.** Log root per job untuk audit mundur
adalah v2 (ADR-023 keputusan 5).

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
(`agent/agent/memory_policy.py:1645-1654`, cabang `basis = "baseline-constant"`). Yang **memang** datang
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
| `make demo` | `Makefile:43-44` mencetak `Belum tersedia.` — rantai demo dijalankan lewat perintah eksplisit (lihat "Reproduksi") |
| x402 fee di muka (ADR-004) | `agent/x402_server.py` tidak ada di repo |
| `MemoryGateHook` | tidak ada di `contracts/src/` (hanya `EvaluatorVault.sol`, `IACP.sol`); hook butuh whitelist admin Virtuals (ADR-001) |
| Rubric LLM | dipotong; hanya cek deterministik yang jalan (`agent/agent/checks/`: `format`, `links`, `chain`) |
| `checks/sandbox` | tidak diimplementasikan dan tidak diklaim hidup |
| UI web / panel juri | direktori `web/` belum ada |
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

- job **417** (satu-satunya `Completed`, dan job yang evaluator **LULUSKAN**) → vault menerima **50.000**
  unit, dan 50.000 itu **hangus permanen** karena `sweepToken` tidak ada di bytecode (butir 4);
- job **418, 419, 420** (seluruh rantai demo, tiga-tiganya **REJECT**) → vault menerima **0**.

Jadi pada submission ini fee memang mengalir persis mengikuti bias yang dikritik ERC-8183: bayaran datang
hanya bersama kelulusan. Perbaikannya — client membayar di muka lewat x402 dengan tarif identik untuk
`complete` maupun `reject` — dirancang di ADR-004 dan **tidak berjalan**: `agent/x402_server.py` tidak ada
di repo (butir 11). Yang mencegah bias itu berlaku hari ini bukan struktur insentif, melainkan hal yang
jauh lebih lemah: fee-nya terkunci di vault sehingga tidak ada pihak yang bisa menikmatinya.

### 15. Kontrak submission BELUM terverifikasi di Sourcify/BaseScan

README ini mengajak Anda "cek sendiri" ke explorer, jadi batas ajakan itu harus jelas. Kueri Sourcify
`v2/contract/84532/0x5c6EE45…` mengembalikan `{"match":null,"creationMatch":null,"runtimeMatch":null}`, dan
tidak ada `forge verify-contract` di `Makefile`, di `contracts/foundry.toml`, maupun di `docs/`. Di BaseScan
Anda bisa membaca **transaksi, event, dan hasil `cast call`** — itu semua nyata dan itulah yang dijadikan
bukti di README ini — tetapi **bukan** source yang cocok dengan bytecode.

Lebih jauh: bukti provenance terkuat menurut `deployments/84532.json` → `notes` adalah
`contracts/broadcast/Deploy.s.sol/84532/run-1788469622537.json`, sedangkan `contracts/broadcast/` dibuang
oleh `.gitignore:6` — **artefak itu tidak ada di repo publik**. Dan bytecode HEAD ≠ bytecode terdeploy
(sejak commit `e675234` menambahkan `sweepToken`; catatan yang sama menjelaskan diff-nya). Kesimpulan yang
jujur: kaitan **sumber ↔ bytecode terdeploy** hari ini hanya bisa dicek oleh orang yang kami serahi artefak
broadcast-nya, atau oleh orang yang mem-build ulang commit `8d3e596` sendiri.

### 16. Jangkar root itu melingkar, dan tidak ada konsekuensi bagi root karangan

Dua fakta yang harus dibaca berdampingan:

- **Off-chain:** `_require_derived_root` membandingkan root di calldata dengan root yang **baru saja
  dihitung agen dari file yang ia baca sendiri** (`agent/agent/vault_client.py:1292-1302`).
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

### 18. `pnpm -r test` tidak cocok dengan proyek mana pun → exit 0

`make test` menjalankan tiga suite, dan yang ketiga kosong: `pnpm-workspace.yaml` mendaftarkan `sim` dan
`web` (dan `web/` belum ada, butir 11), sementara `sim/package.json:5-8` hanya punya script `job:min` dan
`mint:client` — **nol tes**. Jadi satu-satunya kode yang menyentuh SDK Virtuals punya **nol tes otomatis**;
yang menjaganya hanyalah rantai on-chain yang dijalankan tangan. `forge test` dan `uv run pytest` nyata.

### 19. Tes destruktif belum punya artefak di repo

Tabel tes destruktif di bawah adalah bagian yang paling menentukan penilaian, dan **buktinya belum ada di
repo publik**: tidak ada skrip yang menjalankannya (`make demo` mencetak `Belum tersedia.`,
`Makefile:43-44`), tidak ada direktori `logs/`, tidak ada fixture, dan klaim "md5 identik sebelum/sesudah"
tidak disertai berkas pendamping. Yang belum ada bukan sekadar otomasinya — **bukti tertulisnya juga belum
ada**. Yang bisa diperiksa pihak ketiga hari ini adalah bagian on-chain-nya (butir 20), bukan varian Anvil.

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
(cast 1.7.1 mengabaikan argumen sesudah signature secara diam-diam), jadi pakai topic literal ter-pad seperti
di atas. Kontrol negatif dengan jobId `999999` pada rentang yang sama mengembalikan hasil KOSONG, jadi
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

**Root memori yang berlaku sekarang bisa dihitung ulang dari file memori** (klaim headline proyek ini —
"sekarang", karena DB Sibyl hanya menyimpan keadaan terkini: butir 7):

```
$ cd agent && uv run python -m agent.memory_export --db ./data/chain-abc/memory.db --out /tmp/mem.json
memory_root: 0xcfdab1b06d6cb9e8349d1171da197b998945f6e6433abe3d4bd5e7a26a3c5b26

$ cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "lastMemoryRoot()(bytes32)" \
    --rpc-url https://sepolia.base.org
0xcfdab1b06d6cb9e8349d1171da197b998945f6e6433abe3d4bd5e7a26a3c5b26
```

Nilai yang sama juga muncul sebagai `memory_root` di bundel bukti job 420. Ekspor dan `postVerdict` memakai
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

> **Baca bagian ini sebagai laporan, bukan sebagai bukti.** Berbeda dengan bagian on-chain di atas, tidak
> ada skrip, log, atau fixture di repo yang mendukung tabel ini, dan md5 di atas tidak punya berkas
> pendamping (Batasan butir 19). Yang bisa Anda verifikasi sendiri hari ini adalah rantai A/B/C on-chain.

```
# vault SEGAR di Anvil: lastMemoryRoot() = 0, providerCap(provider) = 0
# SIBYL_DB_PATH diarahkan ke path yang belum pernah ada; agent/data/ TIDAK dihapus
cd agent && uv run python -m agent.vault_client --job-id <job C> --kind reject
```

| Kondisi | Hasil |
|---|---|
| **Tanpa file memori** | agen melapor `mode=naive … cap=TANPA CAP gate=lolos`, **nol `postVerdict`**, `cast logs JobRejected` KOSONG |
| **File memori dikembalikan** (chain yang sama, perintah yang sama) | `cap=250000 gate=DITOLAK` → `postVerdict(REJECT)` → `Finalized(kind=2)`, `JobRejected` MUNCUL, job jadi status 4, client refund penuh |

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

Catatan jujur soal lingkungan: varian di atas berjalan pada vault **segar** (root on-chain = 0 → mode naif).
Pada vault submission yang sudah hidup, menghapus `memory.db` memicu **mode aman**, bukan degradasi — agen
berhenti total dan job menggantung sampai `expiredAt` (Batasan butir 10). Kedua varian dipentaskan terpisah;
otomasinya lewat `make demo` belum ada (Batasan butir 11).

## Di luar spek ERC-8183 — dan kenapa

| Tambahan | Alasan | ADR |
|---|---|---|
| **EvaluatorVault** sebagai alamat evaluator (bukan EOA) | spek tidak punya bond/challenge/timeout evaluator; spek mengizinkan evaluator berupa kontrak | ADR-003 |
| **Jangkar memori on-chain** (`MemoryRootUpdated`, `knownRoots`) | tiap eksekusi ke ACP terikat root yang sudah diumumkan SEBELUM eksekusi; batasnya: dari enam root vault hanya 420 dan 418 yang bisa dihitung ulang, 419 hilang permanen (butir 7), dan jangkarnya melingkar (butir 16) | ADR-011 |
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
**belum terverifikasi** di Sourcify/BaseScan, jadi di explorer Anda melihat transaksi dan event, bukan
source yang tercocokkan (Batasan butir 15).

**SDK Virtuals dipakai sungguhan, bukan dekorasi.** Seluruh transaksi ACP di simulator lewat
`@virtuals-protocol/acp-node-v2@0.1.12` (`sim/package.json:10`); `sim/src/client_min.ts:11-14` menyatakan
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
make test      # forge test + uv run pytest + pnpm -r test (yang ketiga kosong — Batasan butir 18)
make demo      # BELUM TERSEDIA (Makefile:43-44)
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
```

Verdict tidak bisa dikalahkan flag: bila cek deterministik gagal (`Evaluation.passed == False`) atau gerbang
cap menolak, hasilnya REJECT apa pun isi `--kind`.

## Struktur repo

```
contracts/   EvaluatorVault.sol, IACP.sol, script/Deploy.s.sol, test/ (Foundry)
agent/       Python: memory_policy.py (skema memori, derive_cap, promosi), vault_client.py,
             memory_export.py (audit root), checks/{format,links,chain}.py, tools/memory_root_check.mjs
sim/         client simulator TypeScript di atas @virtuals-protocol/acp-node-v2 (tanpa tes — butir 18)
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
| saldo vault = 50.000 unit (0,05 USDC testnet); `evaluatorFeeBP` 500 = 5% | `cast call paymentToken "balanceOf(address)" <vault>` → `50000` (butir 4); `deployments/pipeline-84532.md:84` (tabel aliran dana); ADR-018 keputusan 2 |
| fee hanya cair saat `Completed` → fee evaluator untuk 418/419/420 = 0 | `docs/spec.md` §1 baris 19 (fakta ERC-8183) + status akhir 4 pada ketiga job, "Bukti on-chain" di atas |
| `BASELINE_CAP_USDC` 1.000.000; `MIN_CAP_USDC` 250.000 | ADR-020 keputusan 3 dan 5; ADR-021 keputusan 1 |
| cap job 420: `basis` "baseline-constant", `sample_size` 0, `usdc` 250.000 = ceil(1.000.000 / 4) | bundel bukti job 420; `agent/agent/memory_policy.py:1645-1654,1669` |
| `providerCap` ditulis di baris 289, dideklarasikan di baris 142, nol pembacaan | `contracts/src/EvaluatorVault.sol` (butir 17) |
| `postVerdict` hanya menolak root nol | `contracts/src/EvaluatorVault.sol:303` (`ZeroMemoryRoot`) |
| penjaga root off-chain membandingkan calldata dengan file yang dibaca agen sendiri | `agent/agent/vault_client.py:1292-1302` (butir 16) |
| `agent`/`arbiter`/`MIN_BOND` immutable tanpa setter, tanpa pause | `contracts/src/EvaluatorVault.sol:14,106-114` |
| tiga pemicu mode aman; file hilang butuh root on-chain ≠ 0 | `agent/agent/memory_policy.py:1461-1500` |
| riwayat `MemoryRootUpdated` = **enam** event; keenam root + jobId-nya | `cast logs` topic0 `0xc6028d32…7923`, blok 46350667→46436600 dalam sembilan jendela ≤ 9.999 blok (batas RPC publik, `docs/api-facts.md` §E); tabel lengkap di butir 7 |
| root job 418 `0x4e2a1ca1…ff5a` = root DB kosong (bisa direproduksi); root job 419 `0x3f506e52…eecc2` hilang permanen | `memory_export.py` atas DB alas rantai vs `cast logs` di butir 7; `docs/spec.md` §5 langkah 5 (memori ditulis SESUDAH `postVerdict`) |
| Sourcify 84532/`0x5c6EE45…` → `{"match":null,...}`; broadcast ter-gitignore | kueri Sourcify v2; `.gitignore:6`; `deployments/84532.json` → `notes` (butir 15) |
| `sim` tanpa script `test`; workspace = `sim`, `web` | `sim/package.json:5-8`; `pnpm-workspace.yaml` |
| regex penanda pekerjaan (satu kata memicu `format.placeholder-text`) | `agent/agent/checks/format.py:47-50`; `demo/deliverables/418.json`, `419.json` |
| job 418 / 419 / 420, budget 1.000.000 dan 2.000.000, status akhir 4 | keluaran `cast` di bagian "Bukti on-chain" |
| `providerCap` = 250.000 | `cast call providerCap(address)` di atas |
| blok 46436498, tx `0x78a3a65d…989e`, `reason` `0x1618e765…b5ed` | `cast logs JobRejected` di atas |
| `lastMemoryRoot` = `0xcfdab1b0…5b26` | `cast call lastMemoryRoot()` + `memory_export.py` di atas |
| root warisan `0x1fa62c3d…7bf0` = `keccak("the-evaluator/live/memory-root/v1")` | `cast keccak` di Batasan butir 7; ADR-023 konteks |
| root selftest `0x5ff921fd…a19e` = `keccak("the-evaluator/selftest/memory-root/v1")` | `cast keccak` di Batasan butir 7; commit `26f11d6` (dicabut `190cb44`) |
| blok 46355036 / 46355080, jobId sintetis 8999488 / 8999489 | `cast logs MemoryRootUpdated` di Batasan butir 7 |
| blok deploy 46350667, gas 816.969, solc 0.8.36, optimizer 200 | `deployments/84532.json` |
| chainId 84532 | `deployments/84532.json` |

## Lisensi

MIT — lihat [LICENSE](LICENSE).
