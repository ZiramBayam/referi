# API FACTS — satu-satunya sumber kebenaran untuk API eksternal
Aturan: kode HANYA boleh memanggil fungsi/metode yang tercantum di sini. Jika butuh sesuatu yang tidak ada di file ini,
BERHENTI, verifikasi dari sumber primer (URL di bawah), tambahkan ke file ini bersama URL-nya, baru pakai.
Diverifikasi 24 Agu 2026.

## A. Kontrak ACP (implementasi ERC-8183 milik Virtuals) — sumber: `dist/core/acpAbi.js` + `dist/core/constants.js`
## dari paket NYATA `@virtuals-protocol/acp-node-v2@0.1.12` (`npm pack`, shasum `c5342f3c…cb96`), DAN dikonfirmasi
## langsung ke kontrak Base Sepolia. Spek (hanya rujukan, bukan sumber): https://eips.ethereum.org/EIPS/eip-8183
## DIVERIFIKASI ON-CHAIN 2026-09-03. Metode: (1) `cast call/logs --rpc-url https://sepolia.base.org`;
## (2) fork Base Sepolia dengan `forge test` (`vm.createSelectFork("https://sepolia.base.org")` + `vm.prank`),
## yang mengeksekusi BYTECODE ASLI kontrak — semua "fakta perilaku" di bawah berasal dari eksekusi itu, bukan dari teks.
## (3) SUMBER BARU 2026-09-03: kode sumber TERVERIFIKASI `AgenticCommerceV3.sol` dari Sourcify, `match=exact_match`
##     (runtime DAN creation), `verifiedAt 2026-07-14`:
##     `curl -s "https://sourcify.dev/server/v2/contract/84532/0xc4e95dbc7e8c99c114ff9c8299a3e4851e1530ff?fields=sources,abi"`
##     (alamat WAJIB huruf kecil; endpoint v1 `/files/any/...` menolak dengan 403). Pakai ini untuk menentukan
##     URUTAN CEK dan konstanta, lalu buktikan lagi lewat fork sebelum ditulis di sini.
##     Paket itu memuat 28 file; hanya DUA yang milik Virtuals: `contracts/AgenticCommerceV3.sol` (631 baris,
##     sha256 `3b47cdbcf6397583510c35a1c9783880d6d3443e5d2c12a70dbe82d3a508cddb`) dan `contracts/interfaces/IACPHook.sol`
##     (36 baris, sha256 `4491e3abb21def6af6f9cd3123f4a408adcfb419cb6d3e5ad151cb5b614377d3`); sisanya OpenZeppelin.
##     **Semua rujukan `:<baris>` di §A menunjuk ke file ber-sha256 itu** (ambil ulang & cocokkan sha sebelum percaya).
##     `BaseACPHook` TIDAK ada di paket — jangan mengutip atau mewarisinya.
## PERINGATAN SUMBER: ABI di paket SDK `acp-node-v2@0.1.12` adalah SUBSET BASI dari kontrak nyata — ia kehilangan
## error `ClientIsProvider`, `EvaluatorIsProvider`, `EnforcedPause`, `ExpectedPause` DAN view `EVALUATOR_GRACE_PERIOD()`
## (dihitung: ABI SDK punya 21 error, ABI terverifikasi punya 25). "Tidak ada di ABI SDK" TIDAK berarti "tidak ada di kontrak".
Alamat:
- Base Sepolia (84532): `0x0b93793923CD5De81850aF8604a233f3f24d461e` — ERC-1967 proxy.
  Implementasi (slot `0x360894…2bbc`) = `0xc4E95dBc7E8C99c114FF9C8299A3E4851e1530fF`, nama kontrak `AgenticCommerceV3`.
- Base mainnet (8453):  `0x238E541BfefD82238730D00a2208E5497F1832E0`
- Sentinel "tanpa evaluator" (EVM): `0x0000000000000000000000000000000000000000`
- API: prod `https://api.acp.virtuals.io`, testnet `https://api-dev.acp.virtuals.io`
- **Token escrow Base Sepolia = `0xECc22a8F6fD62388498fBa19813E214605a2BDb3`** (`cast call <ACP> "paymentToken()(address)"`;
  `symbol()` = `"USDC"`, `name()` = `"USD Coin"`, `decimals()` = 6). Ini **BUKAN** USDC Circle `0x036CbD53…dCF7e`.
  **`symbol()` TIDAK BISA membedakan keduanya — jangan pernah dipakai sebagai bukti identitas token.** Dibaca ulang
  2026-09-04 (`cast call <token> "symbol()(string)"|"name()(string)"|"decimals()(uint8)" --rpc-url https://sepolia.base.org`):
  escrow → `"USDC"` / `"USD Coin"` / 6; Circle `0x036CbD53…dCF7e` → `"USDC"` / `"USDC"` / 6. Simbol IDENTIK, desimal identik;
  hanya `name()` berbeda (pembeda lemah) dan **ALAMAT** yang mengikat. Satu-satunya cek yang sah:
  `cast call 0x0b93793923CD5De81850aF8604a233f3f24d461e "paymentToken()(address)" --rpc-url https://sepolia.base.org`
  lalu bandingkan hasilnya (case-insensitive) dengan `USDC_ADDRESS`. Setiap AC/skrip yang "membuktikan alamat token
  dengan `symbol()`" adalah CACAT dan lolos untuk token yang salah.
  ACP hanya menarik token ini di `fund`; saldo USDC Circle TIDAK bisa dipakai. Token ini punya
  `mint(address,uint256)` TANPA kontrol akses (selector `0x40c10f19` ada di bytecode; dibuktikan di fork: pemanggil
  acak berhasil mint 100 USDC) → tidak butuh faucet Circle. Sama untuk bscTestnet; Base mainnet = USDC Circle asli.
- `platformTreasury()` Base Sepolia = `0xb3bdEdda2050a3615B73bB9a2684946eC38B5375`. `jobCounter()` = 408 (3 Sep 2026).

Fungsi (ABI paket + dikonfirmasi ke chain — PERHATIKAN `fund` punya `expectedBudget`, berbeda dari teks EIP):
```
createJob(address provider, address evaluator, uint256 expiredAt, string description, address hook) returns (uint256 jobId)
setProvider(uint256 jobId, address provider_)                // client, HANYA saat Open + now < expiredAt + provider == 0
setBudget(uint256 jobId, uint256 amount, bytes optParams)    // provider, saat Open; boleh dipanggil BERULANG (menimpa)
fund(uint256 jobId, uint256 expectedBudget, bytes optParams) // client, Open→Funded; expectedBudget HARUS == job.budget;
                                                             // DITOLAK bila now >= expiredAt (guard expiry ADA — lihat urutan cek)
submit(uint256 jobId, bytes32 deliverable, bytes optParams)  // provider, Funded→Submitted; DITOLAK bila now >= expiredAt
                                                             // JUGA menerima status Open bila budget == 0 (hasil tergantung evaluator)
complete(uint256 jobId, bytes32 reason, bytes optParams)     // evaluator, Submitted→Completed; TIDAK ada guard expiry
reject(uint256 jobId, bytes32 reason, bytes optParams)       // client/provider saat Open; evaluator saat Funded/Submitted
                                                             // (client/provider bila evaluator==0); TIDAK ada guard expiry
claimRefund(uint256 jobId)                                   // siapa pun; Open/Funded → Expired saat now >= expiredAt;
                                                             // Submitted → Expired saat now >= expiredAt + 900 (lihat tabel di bawah)
getJob(uint256 jobId) returns (Job)                          // TIDAK revert untuk id tak dikenal → struct nol
jobs(uint256) returns (client, status, provider, expiredAt, evaluator, hook, budget, description)  // getter mapping publik
evaluatorFeeBP() / platformFeeBP() / platformTreasury() / paymentToken() / jobCounter() / whitelistedHooks(address) — view
EVALUATOR_GRACE_PERIOD() returns (uint256)                   // konstanta publik = 900 (15 menit). TIDAK ada di ABI SDK;
                                                             // dibaca langsung: cast call <ACP> "EVALUATOR_GRACE_PERIOD()(uint256)" → 900
paused() returns (bool)                                      // kontrak Pausable; saat ini false (3 Sep 2026)
setHookWhitelist / setEvaluatorFee / setPlatformFee / grantRole / upgradeToAndCall / pause / unpause /
emergencyWithdraw / batchDetachHook — admin Virtuals (BUKAN kita). Signature + topic0 lengkap di §A.1.
```
Struct `Job` (urutan field APA ADANYA dari ABI — TIDAK ada field `id`, `expiredAt` = **uint48**, `status` = uint8):
```
struct Job { address client; uint8 status; address provider; uint48 expiredAt; address evaluator; address hook; uint256 budget; string description; }
// tuple ABI: (address,uint8,address,uint48,address,address,uint256,string)
```
Status enum: Open=0, Funded=1, Submitted=2, Completed=3, Rejected=4, Expired=5. `setBudget` TIDAK mengubah status (tetap Open).

Fee (`cast call … --rpc-url https://sepolia.base.org`, 2026-09-03): **`platformFeeBP()` = 100 (1%)**, `evaluatorFeeBP()` = 500 (5%).
Aritmetika `complete` dibuktikan di fork dengan budget 10.000.000 (10 USDC): provider **9.400.000**, evaluator **500.000**,
treasury **100.000** — kedua fee dipotong dari budget. `reject` mengembalikan **100%** budget ke client, fee evaluator 0.
Bila `evaluator == address(0)`: `submit` LANGSUNG menyelesaikan job (status → Completed) dan membayar provider
budget − platformFee saja (9.900.000); `JobCompleted.reason` = nilai `deliverable`; `complete()` sesudahnya revert `WrongStatus`.

**`submit` dari status Open — DUA HAL TERPISAH, jangan digabung (mock kita pernah menyimpang persis di sini).**
Source `:456-459`: `if (job.status != Funded && (job.status != Open || job.budget > 0)) revert WrongStatus();`
— syarat MASUK adalah `status == Funded` **ATAU** (`status == Open` **DAN** `budget == 0`). Status masuk sama sekali TIDAK
melihat `evaluator`. Yang menentukan status KELUAR hanyalah cabang `evaluator` sesudahnya (`:466`, `:497-498`):

  | status masuk | budget | evaluator | hasil |
  |---|---|---|---|
  | Open (0)   | `== 0` | `!= 0` | **Submitted (2)** — bukan Completed; evaluator masih bisa `complete()` → Completed (3) |
  | Open (0)   | `== 0` | `== 0` | **Completed (3)** (jalur auto-complete, tanpa transfer karena budget nol) |
  | Open (0)   | `> 0`  | apa pun| revert `WrongStatus()` `0x8e78f0cb` (harus `fund` dulu) |
  | Funded (1) | apa pun| `!= 0` | Submitted (2) |
  | Funded (1) | apa pun| `== 0` | Completed (3) |

Keempat baris pertama dibuktikan di fork Base Sepolia 2026-09-03 atas bytecode asli. Catatan lama "juga menerima
Open→Completed bila budget == 0 & evaluator == 0" TIDAK LENGKAP: ia melewatkan jalur Open+budget0+evaluator!=0 → Submitted.
Awas: docstring kontrak sendiri (`:445`) juga menulis versi sempit "Also accepts Open -> Completed for zero-budget jobs
without an evaluator" — **kode lebih longgar dari docstring-nya**; ikuti kode. Pada jalur Open+budget0+evaluator!=0 satu-satunya
event yang diemit adalah `JobSubmitted` (fork: 1 log, topic0 `0x80c17d…538e`).

Event — daftar `indexed` APA ADANYA dari ABI, dikonfirmasi ke log nyata (`cast logs`, job #403, blok 46173980-46173987):
```
JobCreated(uint256 indexed jobId, address indexed client, address indexed provider, address evaluator, uint256 expiredAt, address hook)
ProviderSet(uint256 indexed jobId, address indexed provider)
BudgetSet(uint256 indexed jobId, uint256 amount)
JobFunded(uint256 indexed jobId, address indexed client, uint256 amount)
JobSubmitted(uint256 indexed jobId, address indexed provider, bytes32 deliverable)
JobCompleted(uint256 indexed jobId, address indexed evaluator, bytes32 reason)
JobRejected(uint256 indexed jobId, address indexed rejector, bytes32 reason)
JobExpired(uint256 indexed jobId)
PaymentReleased(uint256 indexed jobId, address indexed provider, uint256 amount)
EvaluatorFeePaid(uint256 indexed jobId, address indexed evaluator, uint256 amount)
Refunded(uint256 indexed jobId, address indexed client, uint256 amount)
```
**`evaluator` TIDAK indexed di `JobCreated`** (ia ada di `data`) → watcher (task 2.2) TIDAK bisa memfilter job milik vault
lewat topic saat `JobCreated`; penyaringan `evaluator == VAULT` harus dilakukan di sisi client atau lewat `JobCompleted`
(di sana `evaluator` = topic 2). topic0 (`cast sig-event`, 2026-09-03):
```
JobCreated      0xb0f0239bfdd96453e24733e18bfc24b70d8fadf123dd977473518dd577ee79b9
JobFunded       0xe3fbcc1ea1bdc559ec7f0347efde7655e58b5f45a30b0e4470a583c3ef5496b3
JobSubmitted    0x80c17db79857f338a6a6df68a6883ecc0ce78e2202fe61ed979733573f40538e
JobCompleted    0x0fd54bd364fa9e67f17b091aefe930932c09fe7651cf5ad02c71a418f3341444   <- (uint256,address,bytes32)
JobRejected     0xae7362b1af91f4492868987b9c73990d780060811551b58728fbe96fd1bab275
JobExpired      0x97237956f8810192811e2c3f273fd02c5d6295206fdd9c62e6fe2bfc19ba9232
PaymentReleased 0x21d71db5be59bb9fa133895586b7404307dd33fb93b16db09dc6f1d9d7d231b0
EvaluatorFeePaid 0x253dd534010ac976fa263caa123bae79b9c50292adf7ce67bdc5ec309f784e61
Refunded        0x7ca5472b7ea78c2c0141c5a12ee6d170cf4ce8ed06be3d22c8252ddfc7a6a2c4
BudgetSet       0x869e2577b006bf47ee981cf6fec2e25583548081c14b98deab587f77b5068038
ProviderSet     0x9a87df076ea1725aba8ba29d32517ce37c9597d88cbf16ec6707892cc330ab69
```
Bentuk `JobRejected` (3 argumen, `rejector` = topic 2) DIKONFIRMASI ULANG 2026-09-06 dari ABI paket + source terverifikasi
+ log nyata + eksekusi fork — rinciannya dan jebakan `cast logs` ada di **§G** (baca sebelum menulis AC berbasis log).
**Bentuk 2-argumen `JobCompleted(uint256,bytes32)` TIDAK ADA.** topic0-nya `0x45c386dc6524a2d9fe630455323c6a39f557c52ab01e886deee20a0b538147ac`
dan `cast logs --address <ACP> <topic0 itu> --from-block 46173040 --to-block 46183039` mengembalikan KOSONG pada rentang
yang justru memuat `JobCompleted` bentuk 3-argumen. Jangan pernah memakai bentuk 2-argumen di AC/skrip/indexer.
Urutan emit dalam satu tx (dibuktikan `vm.recordLogs` di fork): `complete` → EvaluatorFeePaid, JobCompleted, PaymentReleased.
`claimRefund` — **DAFTAR EVENT PERSIS PER JALUR** (task 2.2 memfilter per event, jadi ini mengikat). Diuji di fork
Base Sepolia 2026-09-03 atas bytecode asli `0x0b93…4d461e`, pemanggil = stranger `0xBADBEEF`, isi `vm.getRecordedLogs()`
apa adanya, urutan sesuai indeks log:

  | status sebelum refund | budget | event yang diemit, BERURUTAN |
  |---|---|---|
  | Open (0)      | 0 **atau** != 0 (hanya `setBudget`, belum `fund`) | **HANYA `JobExpired(jobId)`** — TIDAK ada `Refunded` |
  | Funded (1)    | > 0  | ERC20 `Transfer(ACP→client)` (emitter = paymentToken, BUKAN ACP), lalu `Refunded(jobId, client, budget)`, lalu `JobExpired(jobId)` |
  | Funded (1)    | == 0 | **HANYA `JobExpired`** |
  | Submitted (2) | > 0  | ERC20 `Transfer`, `Refunded`, `JobExpired` — identik dengan jalur Funded |
  | Submitted (2) | == 0 | **HANYA `JobExpired`** |

  Sumber (badan `claimRefund` di source terverifikasi Sourcify `exact_match`): `if (job.budget > 0 && (prev == Funded ||
  prev == Submitted)) { safeTransfer; emit Refunded; } emit JobExpired;` — syaratnya BUKAN status saja melainkan
  **`budget > 0` DAN status ∈ {Funded, Submitted}**. **`Refunded` beramount NOL TIDAK PERNAH DIEMIT.**
  Konsekuensi watcher: `JobExpired` satu-satunya event yang PASTI ada di semua jalur refund → pakai ia sebagai pemicu,
  perlakukan `Refunded` sebagai opsional. "Tidak ada `Refunded`" TIDAK berarti dana tertahan: pada Open memang belum
  pernah ada escrow, pada Funded/Submitted berbudget nol tidak ada yang dipindahkan.

Custom error (ABI + selector `cast sig`) — kontrak asli TIDAK punya `PastExpiry`/`NotYetExpired`/`UnknownJob`/`NotClient`/`NotProvider`/`NotEvaluator`:
```
WrongStatus()        0x8e78f0cb   ExpiryTooShort()  0xf7a0748c   BudgetMismatch()      0x99b0fc87  (TANPA argumen)
InvalidJob()         0x71c8f460   Unauthorized()    0x82b42900   ProviderNotSet()      0xa9456d43
HookNotWhitelisted() 0xa04b28ec   ZeroAddress()     0xd92e233d   FeesTooHigh()         0xc9034e18
ClientIsProvider()   0x332ff0f9   EvaluatorIsProvider() 0xc7b4e9eb   <- DUA INI TIDAK ADA DI ABI SDK, tapi ADA & dipakai
+ error OpenZeppelin: AccessControl*, ERC1967*, UUPS*, ReentrancyGuardReentrantCall (0x3ee5aeb5),
  EnforcedPause/ExpectedPause (Pausable), SafeERC20FailedOperation, FailedCall
```
Fakta perilaku — SEMUA dibuktikan dengan eksekusi bytecode asli di fork Base Sepolia 2026-09-03:
- `expiredAt` harus **> now + 300 detik**, bukan `>=`: `now+300` → revert `ExpiryTooShort()`, `now+301` → sukses.
- Batas waktu diuji tepat di titiknya: `submit` pada `now == expiredAt` → revert `WrongStatus()` (jadi submit DILARANG
  saat `now >= expiredAt`); `claimRefund` pada `now == expiredAt` → SUKSES **hanya dari status Open/Funded** — untuk
  status Submitted lihat tenggang 900 detik di bawah.
- **`complete` dan `reject` TIDAK punya guard expiry**: keduanya SUKSES pada `expiredAt + 1`. Verdict vault yang telat
  tetap bisa dieksekusi selama status masih Submitted.
- **KOREKSI 2026-09-03 — baris lama "`claimRefund` HANYA dari status Funded; dari Submitted → `WrongStatus()`" SALAH.**
  Yang benar: `claimRefund` bisa dari **Open, Funded, DAN Submitted**; khusus Submitted ada tenggang
  `EVALUATOR_GRACE_PERIOD` = **900 detik** setelah `expiredAt`. Tabel lengkap (semua diuji ulang di fork 2026-09-03,
  bytecode asli, pemanggil = alamat acak `0xBADBEEF`, evaluator = KONTRAK, budget 10 USDC, `expiredAt = now + 3600`):

  | status saat dipanggil | syarat waktu | hasil | transfer |
  |---|---|---|---|
  | Open (0)      | `now >= expiredAt`         | SUKSES → Expired(5) | tidak ada (belum ada escrow) |
  | Funded (1)    | `now >= expiredAt`         | SUKSES → Expired(5) | 100% budget ke client |
  | Submitted (2) | `now >= expiredAt + 900`   | SUKSES → Expired(5) | 100% budget ke client, provider NOL |
  | Completed (3) | — | selalu `WrongStatus()` `0x8e78f0cb` | — |
  | Rejected (4)  | — | selalu `WrongStatus()` `0x8e78f0cb` | — |
  | Expired (5)   | — | selalu `WrongStatus()` `0x8e78f0cb` (tidak ada refund ganda) | — |

  Bisection eksplisit dari status Submitted, offset terhadap `expiredAt` (returndata apa adanya):
  `-1, 0, +1, +100, +600, +898, +899` → revert `0x8e78f0cb` (`WrongStatus()`); `+900, +901, +902, +1800, +3600, +100000`
  → SUKSES, status 5, saldo client +10.000.000. Jadi ambangnya **tepat `expiredAt + 900`, inklusif**.
  Anchor = `expiredAt`, BUKAN waktu submit: submit di `expiredAt-1` tetap gagal di `expiredAt+899` dan sukses di
  `expiredAt+900`; sebaliknya submit sangat awal lalu refund di `submitTime+900` (masih < `expiredAt`) → `WrongStatus()`.
  Dari Open/Funded TIDAK ada tenggang: `expiredAt-1` revert, `expiredAt+0/+1/+899/+900` sukses.
  Sesudah refund dari Submitted, `complete()` DAN `reject()` oleh evaluator sama-sama revert `WrongStatus()` `0x8e78f0cb`.
  Konstanta ini BISA dibaca on-chain: `cast call <ACP> "EVALUATOR_GRACE_PERIOD()(uint256)" --rpc-url https://sepolia.base.org`
  → `900`. Jangan hardcode 900 di kode tanpa membacanya, dan jangan berasumsi angkanya sama di Base mainnet.
  **Konsekuensi model ancaman:** griefing `claimRefund` setelah `submit` BUKAN mustahil, hanya tertunda 900 detik. Siapa pun
  boleh membatalkan job yang sudah Submitted begitu `expiredAt + 900` lewat, dan itu MEMBUNUH verdict vault yang belum
  dieksekusi (`complete`/`reject` sesudahnya revert). Anggaran waktu vault kasus terburuk = `expiredAt + 900` sejak job dibuat.
  METODE YANG MENYEBABKAN KESALAHAN LAMA (jangan diulang): (1) `claimRefund` dari Submitted hanya diuji DI/DEKAT `expiredAt`
  lalu digeneralisasi jadi aturan status; (2) daftar error/fungsi diambil dari ABI SDK yang basi sehingga
  `EVALUATOR_GRACE_PERIOD()` tak pernah terlihat. Aturan sekarang: untuk setiap guard waktu, uji minimal
  `t-1 / t / t+1` DI SETIAP STATUS yang mungkin, dan cek daftar konstanta publik di sumber terverifikasi.
- `fund`: hanya client (`Unauthorized()` untuk pihak lain); `expectedBudget != job.budget` → `BudgetMismatch()` (pengaman
  selip harga, interpretasi "harus sama persis" TERBUKTI); fund kedua kali → `WrongStatus()`; tanpa provider → `ProviderNotSet()`.
  `fund(jobId, 0, "")` pada job yang belum pernah `setBudget` DITERIMA (budget 0 sah, status → Funded).
- `setBudget`: hanya provider (`Unauthorized()`); `amount == 0` diterima; boleh dipanggil berulang selagi Open
  **dan `now < expiredAt`** — pada `now == expiredAt` revert `WrongStatus()` (dibuktikan di fork 2026-09-03).
- **URUTAN CEK `setBudget` / `fund` / `submit` — APA ADANYA dari source terverifikasi, tiap kombinasi dieksekusi di fork
  Base Sepolia 2026-09-03 (returndata mentah). `fund` BERBEDA dari dua lainnya; jangan digeneralisasi.**
```
setBudget :396-399  InvalidJob → status!=Open WrongStatus → now>=expiredAt WrongStatus → bukan provider Unauthorized
submit    :455-461  InvalidJob → status WrongStatus → now>=expiredAt WrongStatus → bukan provider Unauthorized
fund      :420-425  InvalidJob → status!=Open WrongStatus → bukan client Unauthorized → provider==0 ProviderNotSet
                    → now>=expiredAt WrongStatus → budget!=expectedBudget BudgetMismatch
```
  Jadi di `setBudget`/`submit` otorisasi dicek TERAKHIR, tetapi di `fund` otorisasi dicek SEBELUM `ProviderNotSet` dan
  SEBELUM guard expiry. Selector pemenang untuk kombinasi (fork 2026-09-03):

  | fungsi | pelanggaran gabungan | selector pemenang |
  |---|---|---|
  | `fund`      | caller salah **DAN** status salah      | `WrongStatus()` `0x8e78f0cb` |
  | `fund`      | caller salah **DAN** `now >= expiredAt`| **`Unauthorized()` `0x82b42900`** (auth menang atas expiry) |
  | `fund`      | caller salah **DAN** provider belum diset | `Unauthorized()` `0x82b42900` |
  | `fund`      | client benar **DAN** provider belum diset **DAN** expiry lewat | `ProviderNotSet()` `0xa9456d43` |
  | `fund`      | client benar **DAN** `now >= expiredAt` **DAN** expectedBudget salah | `WrongStatus()` `0x8e78f0cb` |
  | `setBudget` | caller salah **DAN** status salah      | `WrongStatus()` `0x8e78f0cb` |
  | `setBudget` | caller salah **DAN** `now >= expiredAt`| `WrongStatus()` `0x8e78f0cb` (expiry menang atas auth) |
  | `submit`    | caller salah **DAN** status salah      | `WrongStatus()` `0x8e78f0cb` |
  | `submit`    | caller salah **DAN** `now >= expiredAt`| `WrongStatus()` `0x8e78f0cb` (expiry menang atas auth) |

  Kontrol satu-cabang (semua di fork): caller salah SAJA di `setBudget`/`submit` → `Unauthorized()` `0x82b42900`.
- **`fund` PUNYA guard expiry** (source `:424` `if (block.timestamp >= job.expiredAt) revert WrongStatus();`) — fakta ini
  dulu tidak tercatat. Dibuktikan di fork: client memanggil `fund` tepat pada `now == expiredAt` → `WrongStatus()`
  `0x8e78f0cb`; pada `expiredAt - 1` → SUKSES, status → Funded(1). Jadi jendela pendanaan client tertutup di `expiredAt`,
  sama seperti `setBudget` dan `submit`. Hanya `complete` dan `reject` yang tanpa guard expiry.
- `setProvider` (satu-satunya fungsi ALUR JOB yang tidak `nonReentrant`). Urutan cek APA ADANYA:
  `InvalidJob` → `status != Open` `WrongStatus()` → `now >= expiredAt` `WrongStatus()` → bukan client `Unauthorized()`
  → `provider != 0` `WrongStatus()` → `provider_ == 0` `ZeroAddress()` → `provider_ == client` `ClientIsProvider()` `0x332ff0f9`
  → `provider_ == evaluator` `EvaluatorIsProvider()` `0xc7b4e9eb`. Dibuktikan di fork 2026-09-03: job Open berprovider nol
  yang sudah di-`reject` (status 4) → `setProvider` revert `WrongStatus()` `0x8e78f0cb`; `setProvider` pada `now == expiredAt`
  (masih Open) → `WrongStatus()`. Catatan lama "tidak ada cek status" SALAH.
  Prioritas itu kini DIKUATKAN EKSEKUSI per-cabang (fork 2026-09-03, dua guard dilanggar dalam satu panggilan, returndata
  apa adanya): `provider_ == 0` DAN `provider_ == job.evaluator` (job berevaluator nol) → **`ZeroAddress()` `0xd92e233d`**
  (jadi `ZeroAddress` menang atas `EvaluatorIsProvider`); `provider_ == client` DAN `client == job.evaluator` →
  **`ClientIsProvider()` `0x332ff0f9`** (menang atas `EvaluatorIsProvider`); `now >= expiredAt` DAN `provider_ == 0` →
  **`WrongStatus()` `0x8e78f0cb`**; pemanggil bukan client DAN `provider_ == 0` (job juga lewat expiry) → `WrongStatus()`.
  Kontrol satu-cabang: ZeroAddress saja `0xd92e233d`, ClientIsProvider saja `0x332ff0f9`, EvaluatorIsProvider saja
  `0xc7b4e9eb`. Kombinasi `ZeroAddress`+`ClientIsProvider` TIDAK BISA dicapai (butuh client = `address(0)`, dan job
  seperti itu tak bisa dibuat) — urutan keduanya hanya diketahui dari source, bukan eksekusi.
- `complete` mengecek **STATUS DULU, baru otorisasi**: `complete(non-evaluator, status=Funded)` → `WrongStatus()` `0x8e78f0cb`
  (BUKAN `Unauthorized()`); `complete(evaluator, status=Funded)` → `WrongStatus()`; `complete(non-evaluator, status=Submitted)`
  → `Unauthorized()` `0x82b42900`. Dibuktikan di fork 2026-09-03. Mock yang mengecek auth lebih dulu akan menyimpang di sini.
- `reject` — matriks otorisasi lengkap (dibuktikan di fork 2026-09-03; catatan lama "saat Open hanya client" SALAH):
  status Open → **client ATAU provider** (provider berhasil reject job Open, status → 4); Funded/Submitted dengan
  `evaluator != 0` → HANYA evaluator (client/stranger → `Unauthorized()`); Funded/Submitted dengan `evaluator == 0` →
  **client ATAU provider** (stranger → `Unauthorized()`); status lain → `WrongStatus()`.
- **`reject` melewati `Refunded` saat `budget == 0` — ATURAN SERAGAM dengan `claimRefund`.** Source `:584-590`:
  `if ((prev == Funded || prev == Submitted) && job.budget > 0) { safeTransfer(client, budget); emit Refunded; }`
  lalu `emit JobRejected` selalu. Syaratnya identik dengan `claimRefund`: **`budget > 0` DAN status sebelumnya ∈
  {Funded, Submitted}**. Berlaku untuk KEDUA fungsi: **`Refunded` diemit HANYA bila `budget > 0`; `Refunded` beramount NOL
  TIDAK PERNAH DIEMIT di mana pun di kontrak ini.** Daftar event persis (fork 2026-09-03, `vm.getRecordedLogs()` apa adanya):

  | status sebelum `reject` | budget | event yang diemit, BERURUTAN |
  |---|---|---|
  | Funded/Submitted | > 0  | ERC20 `Transfer(ACP→client)` (emitter = paymentToken), `Refunded(jobId, client, budget)`, `JobRejected(jobId, rejector, reason)` |
  | Funded/Submitted | == 0 | **HANYA `JobRejected`** (1 log) |
  | Open             | apa pun (termasuk `setBudget` besar yang belum di-`fund`) | **HANYA `JobRejected`** (1 log) |

  Baris Open penting: job Open berbudget 10 USDC yang belum pernah di-`fund` tetap TIDAK memicu `Refunded` (tidak ada escrow).
  Konsekuensi watcher (2.2): pemicu yang PASTI ada di jalur reject = `JobRejected`; `Refunded` bersifat OPSIONAL — sama
  seperti di jalur `claimRefund` yang pemicunya `JobExpired`. Jangan menunggu `Refunded` untuk menutup job.
- `getJob(<id tak dikenal>)` **tidak revert**, mengembalikan struct nol. Fungsi yang MENGUBAH state (`fund`, `claimRefund`, …)
  pada id tak dikenal → `InvalidJob()`. Jangan pakai revert sebagai deteksi "job tidak ada"; bandingkan `job.evaluator`.
- `createJob` dengan `hook` yang tidak di-whitelist → `HookNotWhitelisted()` (dicek sudah di createJob, bukan nanti).
  `hook = address(0)` dan `evaluator = address(0)` keduanya sah; `provider = address(0)` juga sah (diisi belakangan
  lewat `setProvider`).
- `createJob` — batas atas `expiredAt` NYATA (dibuktikan di fork 2026-09-03): `expiredAt > type(uint48).max` → revert
  **`ExpiryTooShort()` `0xf7a0748c`** (bukan truncation!). Tepat `type(uint48).max` (281474976710655) SUKSES, `2**48` revert,
  `type(uint256).max` revert. Guard yang sama juga menolak `expiredAt <= now + 300`.
- `createJob` punya guard identitas: `msg.sender == provider` → `ClientIsProvider()` `0x332ff0f9`;
  `evaluator != 0 && evaluator == provider` → `EvaluatorIsProvider()` `0xc7b4e9eb`. Keduanya dibuktikan di fork 2026-09-03.
- `createJob` — URUTAN CEK APA ADANYA (source terverifikasi, dikuatkan per-cabang di fork 2026-09-03):
  `ExpiryTooShort` → `ClientIsProvider` → `EvaluatorIsProvider` → `HookNotWhitelisted` → (bila hook != 0) ERC165 `InvalidJob`.
  **Guard expiry MENANG** bila dilanggar bersamaan dengan guard identitas: `expiredAt = now+100` DAN `msg.sender == provider`
  → revert **`ExpiryTooShort()` `0xf7a0748c`** (BUKAN `0x332ff0f9`). Sama untuk expiry pendek + `evaluator == provider`
  (`0xf7a0748c`), untuk `expiredAt = 2**48` + `msg.sender == provider` (`0xf7a0748c`), dan untuk tiga pelanggaran sekaligus
  expiry+clientIsProvider+hook tak-whitelist (`0xf7a0748c`). Kontrol satu-cabang: expiry saja `0xf7a0748c`, clientIsProvider
  saja `0x332ff0f9`, evaluatorIsProvider saja `0xc7b4e9eb`; clientIsProvider + hook tak-whitelist → `0x332ff0f9`
  (identitas menang atas hook).
- (dari sumber terverifikasi + bytecode, BUKAN dari eksekusi — tidak ada jalur reentrancy tanpa hook untuk diuji)
  kontrak asli mewarisi **`ReentrancyGuardTransient` OpenZeppelin**; `createJob`, `setBudget`, `fund`, `submit`,
  `complete`, `reject`, `claimRefund` semuanya `nonReentrant` (satu slot transient bersama → guard berlaku LINTAS fungsi
  dalam satu tx). Selector `ReentrancyGuardReentrantCall()` `0x3ee5aeb5` memang ada di bytecode implementasi:
  `cast code 0xc4E95dBc7E8C99c114FF9C8299A3E4851e1530fF | grep -o 3ee5aeb5` → 1 kecocokan. Konsekuensi: vault kita tidak
  boleh memanggil balik ACP dari dalam callback yang berasal dari ACP.
- Kontrak `Pausable` oleh admin Virtuals: `cast call <ACP> "paused()(bool)"` → `false` (3 Sep 2026). Menurut sumber
  terverifikasi semua fungsi alur job memakai `whenNotPaused`, jadi saat dipause `complete`/`claimRefund` pun revert
  `EnforcedPause()`. Risiko liveness di luar kendali kita. **Kini DIUJI di fork** (ADMIN_ROLE dipalsukan lewat `vm.store`,
  lihat §A.1): `complete` DAN `claimRefund` memang keduanya revert saat paused. `setProvider` juga `whenNotPaused`;
  `claimRefund` TIDAK hookable (docstring `:599`) tapi tetap `whenNotPaused`.
- Tidak ada pembayaran parsial. Tidak ada dispute/bond/timeout evaluator.

### A.1 Permukaan ADMIN (bukan kita) — model ancaman "operator jahat", watcher 2.2 harus melihatnya
Semua dari source terverifikasi Sourcify; keempat selector dikonfirmasi ADA di bytecode implementasi
(`grep -o <selector>` atas `cast code 0xc4E95dBc…30fF` → 1 kecocokan masing-masing); perilaku dibuktikan di fork
Base Sepolia 2026-09-03 dengan ADMIN_ROLE dipalsukan lewat `vm.store` ke slot ERC-7201 AccessControl
(`keccak(account, keccak(role, 0x02dd7bc7…6800))`) — kontraknya sendiri bytecode ASLI.
```
emergencyWithdraw(address token, address to, uint256 amount)  0xe63ea408  ADMIN_ROLE + whenPaused
batchDetachHook(uint256[] jobIds)                             0x4c4911c4  ADMIN_ROLE, TANPA whenPaused
pause()                                                       0x8456cb59  ADMIN_ROLE
unpause()                                                     0x3f4ba83a  ADMIN_ROLE
setHookWhitelist(address,bool) / setPlatformFee(uint256,address) / setEvaluatorFee(uint256)  ADMIN_ROLE
upgradeToAndCall(address,bytes)                                          DEFAULT_ADMIN_ROLE (`_authorizeUpgrade` :203)
ADMIN_ROLE = keccak256("ADMIN_ROLE") = 0xa49807205ce4d355092ef5a8a18f56e8913cf4a201fbe287825b095693c21775
  (dikonfirmasi live: cast call <ACP> "ADMIN_ROLE()(bytes32)" --rpc-url https://sepolia.base.org)
```
topic0 event admin (`cast sig-event`, 2026-09-03; `EmergencyWithdraw` + `HookDetached` juga TERLIHAT di log nyata pada fork):
```
EmergencyWithdraw(address indexed token, address indexed to, uint256 amount)
                     0xf24ef89f38eadc1bde50701ad6e4d6d11a2dc24f7cf834a486991f3883328504
HookDetached(uint256 indexed jobId, address indexed hook)
                     0xcde6a24b3e1e5d23bc4d45609905c64b3516b23478ba2f7fdada3ab2bae3812d
HookWhitelistUpdated(address indexed hook, bool status)
                     0x7ee54953080e392a475a25b6acacb85417ca4e1953293c90934233ca13612510
PlatformFeeUpdated(uint256 feeBP, address indexed treasury)   <- feeBP TIDAK indexed, treasury indexed
                     0xf0c09f5238364083d828870e877edaebb364d9f19f4093fdbf24e486bbdca484
EvaluatorFeeUpdated(uint256 feeBP)                            <- tanpa argumen indexed
                     0x24fe03678743d8fe5f3d39d760da9fc7a5f3feea46847d91688ba8ef9e400d14
```
Fakta ancaman yang DIEKSEKUSI di fork (bukan dibaca saja):
- **`emergencyWithdraw` benar-benar bisa menyedot escrow job yang sedang hidup.** Skenario: job Submitted berescrow
  10 USDC → admin `pause()` → `emergencyWithdraw(paymentToken, penyerang, 10e6)` → saldo ACP **0**, saldo penyerang
  **10.000.000**. Fungsi ini TIDAK memeriksa pembukuan job sama sekali; `token = address(0)` berarti ETH native.
  Kontrol: `pause()` oleh non-admin ditolak, dan `emergencyWithdraw` tanpa `pause` ditolak (`ExpectedPause`).
- **Saat paused, jalur pemulihan kita mati**: `complete()` DAN `claimRefund()` sama-sama revert (`EnforcedPause`).
  Sesudah `unpause`, `complete()` tetap gagal karena escrow sudah kosong (transfer gagal). Jadi pause+withdraw = kerugian
  permanen untuk client, dan vault kita tidak punya mitigasi on-chain. Risiko diterima, harus disebut di README/pitch.
- **`batchDetachHook` TIDAK butuh `paused`** dan berlaku ke job yang sedang berjalan: hook yang aktif memblokir `setBudget`
  dilepas oleh admin (event `HookDetached`, `job.hook` → `address(0)`), lalu `setBudget` yang sama LOLOS. Artinya setiap
  jaminan yang kita gantungkan pada `MemoryGateHook` bisa dimatikan sepihak kapan saja tanpa sinyal `Paused`.
  Watcher 2.2 WAJIB memantau `HookDetached` bila kita pernah memasang hook.

### A.2 `IACPHook` — TERVERIFIKASI (menggantikan baris "BELUM diverifikasi" yang lama)
Sumber: `contracts/interfaces/IACPHook.sol` di paket Sourcify `exact_match` yang sama. Signature APA ADANYA:
```solidity
interface IACPHook is IERC165 {
    function beforeAction(uint256 jobId, bytes4 selector, bytes calldata data) external;  // 0xdc08fb1d
    function afterAction(uint256 jobId, bytes4 selector, bytes calldata data) external;   // 0xa3fe4783
}
// type(IACPHook).interfaceId = 0x7ff6bc9e  (dihitung compiler solc 0.8.36, BUKAN tulisan tangan:
//   = 0xdc08fb1d ^ 0xa3fe4783; TIDAK menyertakan supportsInterface 0x01ffc9a7 milik IERC165 yang diwarisi)
```
Dibuktikan lewat EKSEKUSI di fork (bytecode ACP asli, hook di-whitelist dengan `vm.store` ke `whitelistedHooks`
= slot mapping **6**, layout dikonfirmasi live: slot0 `paymentToken`, 1 `platformFeeBP`, 2 `platformTreasury`,
3 `evaluatorFeeBP`, 4 `jobs`, 5 `jobCounter`, 6 `whitelistedHooks`):
- `createJob` dengan hook non-nol menuntut ERC-165 (source `:335-343`): hook yang tidak mendukungnya → revert
  **`InvalidJob()` `0x71c8f460`** (bukan `HookNotWhitelisted`). Urutannya: whitelist DULU — hook ber-ERC165 benar tapi
  belum di-whitelist → `HookNotWhitelisted()` `0xa04b28ec`; sesudah di-whitelist, hook tanpa ERC165 → `InvalidJob()`.
- Cek itu memakai `ERC165Checker.supportsInterface` (OZ), yang menuntut TIGA hal sekaligus:
  `supportsInterface(0x01ffc9a7) == true` **DAN** `supportsInterface(0xffffffff) == false` **DAN**
  `supportsInterface(0x7ff6bc9e) == true`. Hook yang mengembalikan `true` untuk semua id akan DITOLAK.
- `_beforeHook`/`_afterHook` (`:293-301` / `:305-314`) no-op saat `hook == address(0)`, selain itu memanggil
  `IACPHook(hook).beforeAction/afterAction(jobId, msg.sig, data)` TANPA try/catch → **hook yang revert membatalkan
  seluruh transaksi ACP** (dibuktikan: hook yang revert di `beforeAction` membuat `setBudget` gagal).
- Urutan log satu `setBudget` berhook (fork, `vm.getRecordedLogs()`): event hook `beforeAction`, lalu `BudgetSet`
  dari ACP, lalu event hook `afterAction`. `data` = `abi.encode(...)` khas per fungsi (mis. `setBudget` →
  `abi.encode(msg.sender, amount, optParams)`, `fund` → `abi.encode(msg.sender, optParams)`).
- `submit` tanpa evaluator memanggil `_afterHook` DUA KALI: sekali dengan `msg.sig` = `submit` (`:485`), lalu sekali lagi
  dengan `this.complete.selector` dan `abi.encode(address(0), deliverable, optParams)` (`:491-496`) — sentinel `address(0)`
  menandai auto-complete. Hook yang menghitung penyelesaian harus menangani pemanggilan ganda ini.
- `whitelistedHooks[address(0)] = true` diset di `initialize` (`:199`) dan DIKONFIRMASI LIVE:
  `cast call <ACP> "whitelistedHooks(address)(bool)" 0x00…00 --rpc-url https://sepolia.base.org` → `true`.
  Itulah sebabnya `hook = address(0)` lolos guard whitelist.
- **`complete` MEMANG hookable — DIVERIFIKASI 2026-09-04 (menutup tiga "BELUM DIVERIFIKASI" task 1.2d).**
  Sumber: source terverifikasi Sourcify `exact_match` yang sama, diambil ulang & sha256 dicocokkan hari ini
  (`curl -s "https://sourcify.dev/server/v2/contract/84532/0xc4e95dbc7e8c99c114ff9c8299a3e4851e1530ff?fields=sources"`
  → `contracts/AgenticCommerceV3.sol` sha256 `3b47cdbc…8cddb`, 631 baris — identik dengan yang dicatat di kepala §A).
  Badan `complete` APA ADANYA (`:510-545`), dikutip verbatim:
```solidity
function complete(uint256 jobId, bytes32 reason, bytes calldata optParams)
    external whenNotPaused nonReentrant {
    Job storage job = jobs[jobId];
    if (jobId == 0 || jobId > jobCounter) revert InvalidJob();   // :515
    if (job.status != JobStatus.Submitted) revert WrongStatus(); // :516
    if (msg.sender != job.evaluator) revert Unauthorized();      // :517

    bytes memory data = abi.encode(msg.sender, reason, optParams); // :520
    _beforeHook(job.hook, jobId, msg.sig, data);                   // :521
    ...
    _afterHook(job.hook, jobId, msg.sig, data);                    // :544
}
```
  Tiga fakta yang mengikat:
  (1) **`complete` termasuk fungsi hookable.** Daftar LENGKAP titik hook di kontrak (`grep -n "_beforeHook\|_afterHook"`,
      2026-09-04): definisi `:293`/`:305`; pemanggilan `:402`,`:407` (`setBudget`), `:428`,`:440` (`fund`),
      `:464`,`:485`,`:491`,`:501` (`submit`, termasuk jalur auto-complete), **`:521`,`:544` (`complete`)**,
      `:579`,`:594` (`reject`). Jadi lima fungsi alur job hookable; hanya `createJob` dan `claimRefund` yang tidak.
  (2) **`data` untuk `complete` = `abi.encode(msg.sender, reason, optParams)`** — ini BUKAN analogi dari `setBudget`,
      melainkan teks `:520` apa adanya. `reject` (`:578`) memakai encoding yang persis sama. `msg.sender` di sini
      SELALU `job.evaluator` (auth sudah lolos di `:517`); satu-satunya tempat `data` `complete`-selector membawa
      `address(0)` di posisi pertama adalah jalur auto-complete `submit` (`:491-496`).
  (3) **`_beforeHook` dipanggil SESUDAH ketiga cek** (`InvalidJob` → `WrongStatus` → `Unauthorized`) dan SEBELUM
      `job.status = Completed` serta sebelum transfer apa pun. Jadi panggilan `complete` yang ditolak TIDAK PERNAH
      menyentuh hook, dan hook `beforeAction` melihat status yang MASIH `Submitted(2)`. `_afterHook` (`:544`) dipanggil
      paling akhir, sesudah semua transfer dan sesudah `JobCompleted`+`PaymentReleased`.
  Selector dikonfirmasi ulang 2026-09-04 dengan `cast sig`: `beforeAction(uint256,bytes4,bytes)` → `0xdc08fb1d`,
  `afterAction(uint256,bytes4,bytes)` → `0xa3fe4783`, dan `msg.sig` yang diteruskan =
  `complete(uint256,bytes32,bytes)` → **`0xd75bbdf3`**. Hook yang merutekan per-selector harus memakai `0xd75bbdf3`.
  Catatan pembanding untuk mock: source menjaga SETIAP transfer di `complete` (`:527-537`) —
  `if (platformFee > 0)`, `if (evalFee > 0)` (transfer + `EvaluatorFeePaid` di guard yang SAMA), `if (net > 0)`.
  Ketiganya, bukan hanya fee evaluator. Pada job berbudget nol `complete` TIDAK mengemit satu pun ERC-20 `Transfer`.
- **PERINGATAN dari docstring `setHookWhitelist` (source `:255-262`, kutipan): whitelist punya DUA arti —**
  (1) alamat itu boleh dipasang sebagai hook di job baru, dan (2) *"They can call beforeAction/afterAction on OTHER
  whitelisted hooks (checked in BaseACPHook.onlyACP) … every whitelisted address gains cross-invocation power over all
  other hooks. Only whitelist contracts you fully trust and have audited."* Ini ancaman LANGSUNG bagi `MemoryGateHook`
  (task 1.4): setiap hook lain yang di-whitelist Virtuals bisa memanggil `beforeAction`/`afterAction` milik kita dengan
  `jobId`/`selector`/`data` karangan. `MemoryGateHook` TIDAK boleh mempercayai `msg.sender` hanya karena ia whitelisted —
  batasi ke alamat ACP saja, dan jangan menulis memori dari data yang tidak diverifikasi ulang ke `jobs(jobId)`.
  Catatan: `BaseACPHook` TIDAK termasuk dalam paket Sourcify (hanya `AgenticCommerceV3.sol` + `interfaces/IACPHook.sol`),
  jadi klaim `onlyACP` di atas berasal dari docstring, BELUM dari kode `BaseACPHook` — jangan mewarisi kelas itu.

## B. SDK `@virtuals-protocol/acp-node-v2` — sumber: README repo di atas
```ts
import { AcpAgent, AssetToken } from "@virtuals-protocol/acp-node-v2";   // peer deps: viem, @account-kit/infra
const agent = await AcpAgent.create({ /* CreateAcpClientInput + transport?, api? */ });
agent.getAddress(); agent.getSession(chainId, jobId);
agent.createJob(chainId, { providerAddress, evaluatorAddress, expiredAt /*unix s*/, description, hookAddress? }) // → bigint jobId
agent.createJobFromOffering(chainId, offering, providerAddress, requirementData, { evaluatorAddress?, hookAddress?, packageId? })
session.setBudget(assetToken); session.fund(assetToken?); session.submit(deliverable /*string*/, transferAmount?);
session.complete(reason /*string*/); session.reject(reason /*string*/); session.sendMessage(content, contentType?)
AssetToken.usdc(0.1, base.id); AssetToken.usdcFromRaw(100000n, base.id)
agent.on("entry", async (session, entry) => { if (entry.kind === "system") switch (entry.event.type) { case "job.created": case "budget.set": case "job.funded": case "job.submitted": case "job.completed": case "job.rejected": } })
session.availableTools(); session.toMessages(); session.executeTool(name, args)   // untuk agen LLM
```
### B.1 Konversi `reason`/`deliverable` string → bytes32 — DIVERIFIKASI 2026-09-02 (menutup lubang verifikasi terakhir §B)
Diperiksa pada paket NYATA `@virtuals-protocol/acp-node-v2@0.1.12` (registry: `dist.shasum c5342f3c…cb96`), diekstrak &
dipasang di direktori sementara DI LUAR repo dengan `npm pack @virtuals-protocol/acp-node-v2@0.1.12` + `npm i` pada
Node v24.15.0 / viem 2.55.19. Yang dikutip = artefak `dist/` yang benar-benar dieksekusi (sourcemap memetakannya ke
`src/clients/evmAcpClient.ts`). ABI dikonfirmasi ulang lewat `import { ACP_ABI }`: `submit(uint256,bytes32 deliverable,bytes)`,
`complete(uint256,bytes32 reason,bytes)`, `reject(uint256,bytes32 reason,bytes)`, event `JobSubmitted/JobCompleted/JobRejected`
membawa `bytes32` non-indexed → §A benar.

**TIDAK ada satu aturan tunggal: `deliverable` dan `reason` diperlakukan BERBEDA. Jangan disamakan.**

`deliverable` (submit) — SELALU keccak, tanpa cabang, tanpa batas panjang. `dist/clients/evmAcpClient.js:75-81`:
```js
async submit(chainId, params) {
    return this.wrap(chainId, this.buildContractCall(chainId, "submit", [
        BigInt(params.jobId), keccak256(toHex(params.deliverable)), params.optParams ?? "0x", ]));
}
```
`reason` (complete/reject) — 3 cabang, `dist/clients/evmAcpClient.js:152-159` (`private static toBytes32`; `private` hanya
TS, saat runtime ia static biasa dan bisa dipanggil):
```js
static toBytes32(value) {
    if (value.startsWith("0x") && value.length === 66) return value;    // 1. hex 32-byte → DITERUSKAN APA ADANYA
    const hex = toHex(value);                                           //    (utf8 → hex)
    if (hex.length <= 66) return pad(hex, { size: 32, dir: "right" });  // 2. utf8 ≤ 32 B → padding NOL DI KANAN
    return keccak256(hex);                                              // 3. utf8 > 32 B → keccak256
}
```
Alasan asimetri itu ditulis sendiri oleh SDK di `dist/core/solana/encoding.js:12-21` (encoder Solana yang sengaja
"mirror the EVM client"): *"Unlike the deliverable (which is always hashed because the full text is kept off-chain via
postDeliverable), the reason has no off-chain copy, so short reasons must remain readable rather than being hashed and lost."*

Contoh KONKRET (output apa adanya dari menjalankan `EvmAcpClient.toBytes32` milik SDK sendiri, bukan reimplementasi):
| Input | utf8 | Cabang | Hasil bytes32 |
|---|---|---|---|
| `reason` = `"quality below rubric"` | 20 B | 2 pad-kanan | `0x7175616c6974792062656c6f7720727562726963000000000000000000000000` (= teks itu sendiri, bisa dibaca balik) |
| `reason` = `"0123456789abcdef0123456789abcdef"` | 32 B | 2 pad-kanan (batas MASIH lolos) | `0x3031323334353637383961626364656630313233343536373839616263646566` |
| `reason` = `"0123456789abcdef0123456789abcdefg"` | 33 B | 3 keccak | `0xc4d96194ea8ab65ed426578ad730558133cd44216c70dd4d83505ba51942e674` |
| `reason` = `"0x9c22ff5f21f0b81b113e63f7db6da94fedef11b2119b4088b89664fb9a3cb658"` | 66 B | 1 passthrough | nilai yang sama persis, tidak di-hash |
| `reason` = `""` | 0 B | 2 pad-kanan | `0x0000…0000` (bytes32 nol — tidak dilarang SDK) |
| `deliverable` = `"ipfs://bafkreiabc123"` | 20 B | selalu keccak | `0xc08fd6cd378f3bf0b1474acb8c35171dbde09e82d09074a574fcb6c9db20d3bd` |
| `deliverable` = string 66-char `0x…` di atas | 66 B | selalu keccak (TIDAK passthrough) | `0x4c56cd21e4213617574aa7cf2009104176f4d4ff5463b4a90ee854da95420e31` |

Batas yang menggigit:
- Batas padding = **32 byte, bukan 31**. Ini BUKAN `formatBytes32String` ethers v5 (yang maks 31 B karena menyimpan panjang).
- Diukur dalam **byte UTF-8, bukan karakter**: `"putusan: ditolak — bukti kurang"` = 31 karakter tapi 33 byte (em-dash 3 B)
  → jatuh ke cabang keccak, bukan padding. Jangan pakai panjang string JS/Python sebagai penentu.
- **Tidak pernah throw dan tidak pernah memotong.** String panjang diam-diam berubah jadi hash — konsekuensinya
  `JobCompleted.reason` kadang teks terbaca, kadang komitmen hash, tergantung panjang input. UI/indexer harus menangani KEDUANYA.
- Cabang 1 hanya memeriksa prefix `0x` + panjang 66; **isinya tidak divalidasi hex**. `"0x" + "z"*64` diteruskan apa adanya
  dan viem `encodeFunctionData` TIDAK menolaknya. Jadi jangan menyuapkan string arbitrer sepanjang 66 karakter.
- Network call: `session.submit()` → `AcpAgent.internalSubmit` (`dist/acpAgent.js:601-604`, juga `:863-865` untuk varian
  transfer) menjalankan `await this.api.postDeliverable(chainId, jobId, deliverable)` **SEBELUM** tx on-chain →
  `POST <serverUrl>/jobs/<chainId>/<jobId>/deliverable` body `{"deliverable": "<teks penuh>"}` (`dist/events/acpApiClient.js:20-30`),
  melempar bila `!res.ok` sehingga submit gagal total. **Tetapi yang di-hash adalah string LOKAL, bukan id/URL/payload balasan API.**
  `complete`/`reject` TIDAK memposting `reason` ke API sama sekali (tidak ada salinan off-chain).

Konsekuensi untuk `agent/vault_client.py` + `EvaluatorVault.sol` (mengoreksi catatan lama yang menduga "simpan ke API lalu hash"):
- `reason = keccak256(bundel bukti)` kita **kompatibel, tidak perlu diubah**. Nilai itu berupa hex 66 karakter, jadi kalaupun
  suatu saat melewati SDK ia kena cabang 1 (passthrough) dan menghasilkan bytes32 yang identik dengan panggilan langsung web3.py.
- Untuk memverifikasi deliverable provider: ambil teks penuh dari API ACP, lalu bandingkan dengan slot on-chain memakai
  `Web3.keccak(text=<teks>)` — sudah dibuktikan cocok byte-per-byte dengan `keccak256(toHex(s))` SDK
  (`"ipfs://bafkreiabc123"` → `c08fd6cd…d3bd` di kedua sisi; `uv run --no-project --with 'web3==7.16.0'`, web3 7.16.0/py3.13.15).
  Awas: di web3 7.x `HexBytes.hex()` mengembalikan hex **tanpa** prefix `0x` → tambahkan sendiri saat membandingkan string.
- Karena `reason` kita selalu hash 32 byte, ia TIDAK akan terbaca sebagai teks di explorer — berbeda dari `reason` pendek
  buatan SDK. Kalau demo butuh alasan yang terbaca on-chain, pakai label ≤32 byte UTF-8; bila tidak, tetap hash + tampilkan
  bundel bukti dari memori.

## C. Sibyl Memory — paket `sibyl-memory-client 0.7.0` (satu-satunya paket Sibyl yang dipakai; pin di docs/versions.md)
## Diverifikasi 2026-09-02 dengan `inspect.signature` di venv sekali-pakai DI LUAR repo:
## `uv run --no-project --with 'sibyl-memory-client==0.7.0' python probe.py` → Python 3.13.15,
## `importlib.metadata.version("sibyl_memory_client")` → `0.7.0`. Repo sekunder: https://github.com/Sibyl-Labs/Sibyl-Memory ;
## https://docs.sibyllabs.org/memory/concepts
## DIVERIFIKASI ULANG 2026-09-06 pada paket TERPASANG di `agent/.venv` (bukan venv sekali-pakai):
## `agent/.venv/bin/python -c "import inspect, importlib.metadata as m, sibyl_memory_client as s; ..."` → versi `0.7.0`;
## `set_entity(self, category, name, body, *, status=None)`, `search_entities(self, query, *, limit=20, prefix=False,
## category=None)`, `search(self, query, *, limit=20, prefix=False, tiers=None)` — identik dengan yang tercatat di bawah.
## `flagged_actors` masih 0 kemunculan di `client.py` DAN `storage.py` (hanya `schema.sql` + `lint.py`) → FLAGGED tetap
## tidak bisa dipakai dari SDK. Dirujuk oleh ADR-025 butir (iv).
## SAPU BERSIH 2026-09-06: SELURUH signature + bentuk baris + jebakan §C/§C.1 di bawah DIJALANKAN ULANG pada paket
## terpasang (daftar 27 metode publik, `hasattr(MemoryClient,"list_references")` → False, `get_state` → pembungkus
## `{'body','updated_at'}`, `get_entity` → `NotFoundError` vs `get_reference` → `None`, `get_reference()["body"]` → `str`,
## `kind=` → `TypeError`, `write_event` posisional → `TypeError`, `tiers=("bogus",)` → `ValueError`, `search("")` → 0 baris,
## kebocoran prefiks-token + body (`rubric:defi` ikut terbawa), urutan `search` = urutan INSERT bukan urut-kunci,
## potong senyap 100/20, kunci `..` → `ValidationError`, `delete_entity` True→False, `requires_python >=3.10`, tier `free`)
## — semua COCOK dengan yang tertulis. DIPERCAYA-TAPI-TIDAK-DIUJI-ULANG hari ini: klaim offline/netns di bawah
## (terakhir dijalankan 2026-09-02). Cap 5 MB free tier BUKAN LAGI "dipercaya": `CapExceededError` DIPICU sungguhan
## 2026-09-06, lihat §C.3. **§C.2 membatalkan klaim "0.7.0 tanpa transaksi".**
Signature NYATA (salinan `inspect.signature`, `self` dibuang; `*` = keyword-only). Bukan tulisan tangan dari README:
```python
from sibyl_memory_client import MemoryClient, NotFoundError
MemoryClient.local(path: str|Path = '~/.sibyl-memory/memory.db', *, tenant_id: str = '00000000-0000-0000-0000-000000000001',
    tier: str = 'free', account_id: str|None = None, session_token: str|None = None,
    credentials_claim: dict|None = None, credentials_signature: str|None = None) -> MemoryClient   # classmethod
                                       # offline, tanpa `sibyl init` — diverifikasi offline 2026-09-02, bukti di bawah
# HOT
set_state(key: str, body: dict|list) -> None
get_state(key: str) -> dict|None                  # → {'body':…, 'updated_at':…} atau None — BUKAN body mentah
# WARM
set_entity(category: str, name: str, body: dict|list, *, status: str|None = None) -> dict
get_entity(category: str, name: str) -> dict      # MELEMPAR NotFoundError bila tidak ada (bukan None)
list_entities(category: str|None = None, *, status: str|None = None, limit: int = 100) -> list[dict]
search_entities(query: str, *, limit: int = 20, prefix: bool = False, category: str|None = None) -> list[dict]
# COLD (journal, append-only)
write_event(*, evaluated=None, acted=None, forward=None, extra=None, ts: str|None = None) -> str   # → event id; SEMUA keyword-only
read_events(*, limit: int = 50, since: str|None = None, until: str|None = None) -> list[dict]
# REFERENCE
set_reference(key: str, body: str|dict|list, *, metadata: dict|None = None) -> None
get_reference(key: str) -> dict|None
# TIDAK ADA `list_references` di 0.7.0 (`hasattr(MemoryClient,"list_references")` → False).
# Enumerasi reference HANYA lewat `search` di bawah — baca §C.1 sebelum memakainya.
# LINTAS TIER (TERVERIFIKASI 2026-09-05, lihat §C.1)
search(query: str, *, limit: int = 20, prefix: bool = False, tiers: tuple[str, ...]|None = None) -> list[dict]
# ARCHIVE / hapus permanen
archive_entity(category: str, name: str, reason: str|None = None) -> dict   # → {'archived_id','original_id'}; MELEMPAR NotFoundError
delete_entity(category: str, name: str) -> bool   # True bila terhapus, False bila tidak ada (idempoten, tidak melempar)
```
Bentuk baris: entity = `{id, tenant_id, category, name, status, body, created_at, updated_at}` (`body` sudah di-deserialize);
event = `{id, ts, evaluated, acted, forward, extra}`.

KOREKSI vs deskripsi lama (semua dibuktikan `inspect.signature` + smoke test pada DB sementara):
- Parameter pertama entity bernama **`category`**, BUKAN `kind`. Pemanggilan posisional aman; `kind=…` → `TypeError`.
- `get_entity`/`archive_entity` MELEMPAR `NotFoundError`; `get_state`/`get_reference` mengembalikan `None`. Jangan disamakan.
- `get_state` mengembalikan pembungkus → pakai `["body"]`. `set_state`/`set_reference` mengembalikan `None`, `set_entity` → row.
- `set_reference` menyimpan dict/list sebagai **string JSON kanonik**; `get_reference(k)["body"]` bertipe `str` → perlu `json.loads`.
- `search_entities` **hanya tier WARM**, BUKAN "lintas tier". Lintas tier = `search(query, *, limit=20, prefix=False,
  tiers: tuple|None)` dengan tier sah `("entity","state","reference","journal")` (`ValueError` bila nama lain).
- `list_entities` default `limit=100` → diam-diam memotong; set eksplisit saat menghitung statistik provider.
- `read_events` TIDAK punya filter per-job/aktor, hanya `limit/since/until` → penyaringan dilakukan di sisi kita.
- `set_entity(..., status=…)` + `list_entities(status=…)` ADA → dipakai untuk `suspicion` berstatus `pending` (spec §3).

Tier FLAGGED: `schema.sql` 0.7.0 memang memuat tabel `flagged_actors` (komentar "FLAGGED tier", rule 13/14/15), TAPI
`client.py`/`storage.py` tidak mengekspos satu pun metode baca/tulis untuknya (hanya `lint.py` membacanya read-only)
→ tidak bisa dipakai dari SDK. Karantina TETAP entity `category="suspicion"`.
Perintah: `grep -rn "flagged_actors" <site-packages>/sibyl_memory_client/client.py <…>/storage.py` → kosong.
Metode publik lain yang ADA di 0.7.0 tapi di luar cakupan verifikasi ini (jangan dipanggil sebelum diverifikasi):
`learn, learner, lint, get/set_tenant, get/set_tier, schema_version,
accept_skill_proposal, reject_skill_proposal, list_skill_proposals`. (`search` DIKELUARKAN dari daftar ini
2026-09-05: sudah terverifikasi di §C.1. `storage` DIKELUARKAN 2026-09-06: sudah terverifikasi di §C.2.
`free_tier_status` DIKELUARKAN 2026-09-06: terverifikasi di §C.3 untuk pemakaian read-only — ingat `tier` yang
dilaporkannya = argumen `local(tier=…)` sisi kita, BUKAN jawaban server.) Daftar LENGKAP metode publik `MemoryClient` 0.7.0
(`sorted(a for a in dir(MemoryClient) if not a.startswith("_"))`, dijalankan 2026-09-05) — apa pun di luar daftar ini
TIDAK ADA: `accept_skill_proposal, archive_entity, delete_entity, free_tier_status, get_entity, get_reference,
get_state, get_tenant, get_tier, learn, learner, lint, list_entities, list_skill_proposals, local, read_events,
reject_skill_proposal, schema_version, search, search_entities, set_entity, set_reference, set_state, set_tenant,
set_tier, storage, write_event`.
Python ≥ 3.10 (`requires_python` di https://pypi.org/pypi/sibyl-memory-client/json). Tier plugin default `local()` = `free`
→ cap lokal 5 MB, `set_entity`/`archive_entity` bisa melempar `CapExceededError`. Cap itu DIBUKTIKAN dipicu, dan
klaim panitia "Pro tier active for the hackathon" TIDAK menjangkau jalur kita: §C.3.

### C.1 Enumerasi REFERENCE lewat `search` — TERVERIFIKASI 2026-09-05 (menutup blocker 2.1r / ADR-020 kep. 7)
Sumber: paket TERPASANG di `agent/.venv` (`importlib.metadata.version("sibyl_memory_client")` → `0.7.0`),
`inspect.signature`, plus probe perilaku pada DB temp SEKALI-PAKAI di luar repo (`MemoryClient.local(<tmpdir>/memory.db)`,
offline). Signature PERSIS (salinan `inspect.signature`, `self` dibuang):
```python
search(query: 'str', *, limit: 'int' = 20, prefix: 'bool' = False,
       tiers: 'tuple[str, ...] | None' = None) -> 'list[dict[str, Any]]'
list_entities(category: 'str | None' = None, *, status: 'str | None' = None,
              limit: 'int' = 100) -> 'list[dict[str, Any]]'
```
YA — `search("pattern:", limit=<N>, prefix=True, tiers=("reference",))` BISA mengenumerasi reference, DENGAN syarat di bawah.
Bentuk baris: kolom PERSIS `['body','category','key','rank','snippet','tier','ts']`; `category` selalu `None` untuk tier
reference. **`body` bertipe `str` JSON** (mis. `'{"i":1}'`) → WAJIB `json.loads`, konsisten dengan `get_reference` di §C.

TERVERIFIKASI (tiap baris = hasil probe yang dijalankan, bukan bacaan kode):
- `search("", limit=100, tiers=("reference",))` → **0 baris**. Query KOSONG BUKAN wildcard-semua; tidak ada "ambil semua".
- `prefix=True` menemukan SEMUA kunci `pattern:*` — **nol false-negative** atas 14 kunci patologis yang berhasil disimpan:
  `pattern:` (kosong), `pattern:x`, `pattern:---`, `pattern:🎯`, `pattern:日本語`, `pattern:` + `"L"*300`, `pattern:a b`,
  `pattern:'quote`, `pattern:NEAR`, `pattern:AND`, `pattern:OR`, `pattern:*`, `pattern:0x9aF3`, `pattern:  `
  → `stored: 14 returned: 14` / `FALSE NEGATIVES (0): []`. Inilah yang menutup blocker: `memory_root` bisa menjangkar
  SELURUH `reference:pattern:*` + `reference:rubric:*`, termasuk pattern yatim.
- Filter `tiers` RAPAT: dengan kunci senama di 4 tier, `tiers=("reference",)` → `set(row["tier"])` = `{"reference"}`
  (2 baris); query sama TANPA `tiers` → `['entity','journal','reference','state']` (5 baris). Tier sah tetap
  `("entity","state","reference","journal")`.

BAHAYA — TIGA jebakan; pemanggil WAJIB menangani ketiganya, kalau tidak `memory_root` SALAH secara senyap:
1. **`prefix=True` BUKAN prefiks-kunci, melainkan prefiks-TOKEN FTS atas kunci DAN body.** Hasilnya SUPERSET yang bocor
   lintas prefiks. Probe: kunci `pattern:real`, `rubric:pattern:trap`, `other:pattern-trap` → `search("pattern:",
   prefix=True, tiers=("reference",))` mengembalikan KETIGANYA. Body pun terindeks: `rubric:defi` berbody
   `{"note":"this rubric mentions pattern matching"}` JUGA dikembalikan (`BODY-ONLY MATCH LEAKED: True`).
   (`metadata=` TIDAK terindeks: `qqq:viameta` dengan `metadata={"tag":"pattern"}` tidak muncul.)
   → Pemanggil WAJIB menyaring sendiri `row["key"].startswith("pattern:")` SESUDAH `search`. Jangan pakai hasil mentah.
2. **URUTAN TIDAK TERURUT-KUNCI — jangan pernah dipakai apa adanya untuk preimage hash.** Urutannya `ORDER BY rank`
   (bm25: makin negatif makin dulu → dokumen makin PENDEK makin dulu), seri dipecah rowid = urutan INSERT.
   Bukti bantahan: (a) body beda panjang, insert urut kunci a,b,c → keluar `b(-1.64e-06)`, `c(-1.19e-06)`, `a(-6.46e-07)`,
   `got == sorted: False`; (b) 10 kunci `pattern:pNNN` body seragam, insert TERBALIK → keluar p009…p000,
   `got == sorted: False`, `got == insertion order: True`; (c) kunci aneh (`pattern:B`, `pattern:a-b`, `pattern:a_b`,
   `pattern:á`, `pattern:zz-ü`, …) → `got == sorted(got): False`. Kasus "kelihatan sorted" (25 kunci `pattern:pNNN`
   body seragam di-insert urut) HANYA KEBETULAN rank seri + rowid menaik (`ranks distinct: 1`) — jangan jadi dasar.
   Urutan STABIL antar panggilan pada DB yang tidak berubah, tapi stabil ≠ kanonik: berubah bila body diedit atau
   urutan tulis berbeda. → Implementasi WAJIB `sorted()` sendiri atas kunci sebelum menghitung hash/`memory_root`.
3. **POTONG SENYAP — tanpa error, tanpa flag "masih ada sisa".** `search` default `limit=20`; `list_entities` default
   `limit=100`. Probe 25 pattern: `limit=10 → 10`, `limit=20 → 20`, `limit=25 → 25`, `limit=100 → 25`, tanpa `limit` → 20.
   `list_entities` atas 120 entity: default → 100, `limit=10` → 10, `limit=100` → 100, `limit=200` → 120.
   → Pemanggil WAJIB (a) memberi `limit` EKSPLISIT dan (b) MENDETEKSI saat `len(hasil) == limit` lalu MELEMPAR, bukan
   mendiamkan. Pola wajib kita: helper `_list_all` yang MELEMPAR bila hasil menyentuh batas.

Catatan samping (kunci reference divalidasi saat tulis): `set_reference` MELEMPAR `ValidationError` untuk kunci berisi
`..` (`"key contains a forbidden path sequence"`), `"`, atau karakter kontrol — 3 dari 17 kunci uji ditolak di probe ini.

### C.2 TRANSAKSI — KOREKSI 2026-09-06: klaim "0.7.0 TANPA transaksi" SALAH, DAN ia sitasi hantu
Klaim "`sibyl-memory-client` 0.7.0 tidak punya transaksi (api-facts §C)" dikutip di `agent/agent/memory_lock.py`,
`memory_export.py`, `memory_policy.py`, `vault_client.py`. **§C TIDAK PERNAH menulis itu** (`sed -n '501,662p'
docs/api-facts.md | grep -niE "transak|atomi"` 2026-09-06 → nol baris): fakta yang dikutip tidak ada di sumber
yang dikutip, dan isinya keliru. Yang NYATA ada, dari paket TERPASANG `agent/.venv` (versi `0.7.0`):

```
agent/.venv/bin/python -c "import inspect; from sibyl_memory_client import storage as st;
  print(inspect.signature(st.Storage.transaction)); print(inspect.getsource(st.Storage.transaction))"
→ transaction(self) -> 'Iterator[sqlite3.Connection]'      # @contextmanager
→ badan: with self.connection() as conn: BEGIN IMMEDIATE / yield / except → ROLLBACK+re-raise / else → COMMIT
  (docstring paket: "Atomic transaction. Rolls back on exception, commits on clean exit.")
```
`MemoryClient.storage` adalah **`property` → `Storage`** (`isinstance(inspect.getattr_static(MemoryClient,"storage"),
property)` → True), jadi `client.storage.transaction()` TERJANGKAU pemakai SDK — tidak terkubur.
PRAGMA sambungan (storage.py `_connect`): `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`.

PERILAKU — semua baris di bawah = hasil probe yang DIJALANKAN 2026-09-06 pada DB temp sekali-pakai di luar repo,
bukan bacaan kode:
- **Atomik: YA.** `UPDATE` di dalam blok yang melempar → nilai kembali ke semula (`{'n':0}` → tampak `{"n":999}`
  di dalam txn → `{'n':0}` sesudahnya); blok yang selesai bersih → COMMIT (`{'n':7}`).
- **Sambungan per-thread yang SAMA dipakai ulang** (`with connection() as a` / `as b` → `a is b` → True,
  `isolation_level` = `None`/autocommit di luar txn).
- **Metode BACA klien BOLEH bersarang di dalam `storage.transaction()`** — `list_entities`, `get_entity`, `search`
  semuanya pakai `storage.connection()`, jadi ikut sambungan yang sama dan ikut snapshot txn. Dibuktikan lintas
  PROSES: penulis di proses lain menembak `set_entity` di tengah blok, dua pembacaan di dalam blok tetap
  `{'n':0}`/`{'n':0}` (`TORN: False`); penulis itu TERTAHAN 1,03 s lalu sukses sesudah COMMIT (`{'n':5}`).
  Baseline tanpa txn pada urutan yang sama: `{'n':0}` → `{'n':1}` (`TORN: True`) — balapannya nyata.
- **Metode TULIS klien TIDAK BOLEH bersarang.** `set_entity/set_reference/set_state/write_event/delete_entity/
  archive_entity` membuka `storage.transaction()`-nya SENDIRI di sambungan yang sama →
  `StorageError: SQLite error: OperationalError`, `__cause__ = OperationalError('cannot start a transaction within
  a transaction')`, dan **tulisannya HILANG** (probe: entity `p1` `NotFoundError` sesudahnya).
  Akibatnya read-modify-write lewat API publik (baca versi lalu `set_entity`) TIDAK BISA dijadikan satu transaksi.
- **Menahan txn lebih lama dari `busy_timeout` MEMBUNUH penulis lain**, bukan mengantrekannya: txn ditahan 7 s →
  proses penulis lain gagal pada 5,01 s dengan `StorageError` / `OperationalError('database is locked')` dan
  tulisannya hilang. Thread lain di proses yang sama: gagal serupa. `MemoryClient.local()` pada DB yang sedang
  terkunci bahkan gagal lebih awal di `_ensure_schema` (`SchemaError: Failed to apply schema: database is locked`).

KONSEKUENSI untuk kunci kooperatif kita (`agent/agent/memory_lock.py`) — **TETAP PERLU**, dan yang ditutupnya
BERBEDA (lebih luas) dari yang ditutup `Storage.transaction()`:
1. Kelas BACA-KONSISTEN (`load_snapshot`: `list_entities` + 2x `search` + N x `get_reference`) — `transaction()`
   MEMANG bisa menutupnya (bukti `TORN: False` di atas). Di kelas ini kunci bukan satu-satunya penutup.
2. Kelas BACA-UBAH-TULIS (`_save_provider_cas`: baca versi → `set_entity`; dedup `recorded_jobs`) —
   `transaction()` TIDAK bisa menutupnya sama sekali lewat API publik (galat "transaction within a transaction").
   Menutupnya dengan transaksi berarti turun ke SQL mentah, melewati validasi/pemicu FTS+shadow/akuntansi cap SDK.
   Kunci adalah satu-satunya penutup yang tersedia.
3. Kelas RENTANG-DI-LUAR-DB — kunci membentang melewati kerja yang bukan SQLite: hitung `memory_root`, tulis file
   ekspor, banding ke `lastMemoryRoot()` on-chain, kirim tx. `BEGIN IMMEDIATE` tidak bisa membentang RPC; dan bila
   dipaksa, ia justru MERUSAK proses agen kedua (gagal pada 5 s, tulisan hilang) alih-alih menolaknya bersih.
4. MODE GAGAL — kunci menolak instans kedua SEBELUM ia bekerja (`MemoryLockError`, fail-closed). `transaction()`
   menjatuhkan instans kedua DI TENGAH JALAN dengan `StorageError` sesudah ia mungkin sudah bekerja di luar DB.
Yang harus berhenti ditulis: "SDK tidak punya transaksi". Yang benar: **transaksi ADA dan atomik, tetapi tidak bisa
membungkus panggilan TULIS SDK, dan tidak bisa membentang di luar SQLite** — itulah celah yang ditutup kunci.

### C.3 TIER & CAP — dicatat 2026-09-06, memisahkan yang TERVERIFIKASI dari yang KLAIM PANITIA
Pemicu: user mengirim tangkapan layar halaman panitia `https://hack.sibyllabs.org/team/referi-bd41` ("Set up Sibyl
Memory") yang berbunyi *"Pro tier active for the hackathon — Every plugin account is on the Pro tier through the end
of the event. Storage cap lifted, nothing to pay, nothing to claim."* Baris di bawah dipisah TEGAS: apa yang bisa
kita eksekusi sendiri, versus apa yang hanya klaim pihak lain.

**A. TERVERIFIKASI — cap 5 MB NYATA dan MENGIKAT jalur kita** (menutup butir "DIPERCAYA, bukan dibuktikan" di
kepala §C). Probe dijalankan pada DB temp sekali-pakai DI LUAR repo, `HOME` kosong baru, interpreter
`agent/.venv/bin/python` (paket TERPASANG, versi `0.7.0`): tulis entity 64 KB berulang lewat `set_entity`.
```
version: 0.7.0
CapExceededError RAISED at n = 24
  msg: You're at the 5 MB free-tier cap and your account isn't activated. Run `sibyl init` to activate,
       or stay under the cap.
  current_size: 5316608  cap: 5242880  proposed_delta: 64218
  upgrade_url: https://docs.sibyllabs.org/memory/tiers
```
Jadi cap itu ditegakkan SECARA LOKAL, tanpa jaringan, pada akun yang TIDAK diaktivasi — persis konfigurasi kita.
Jalur kodenya dibaca di `_capcheck.py`: `_refresh_and_check` cabang pertama, `if not self.account_id or not
self.session_token:` → bandingkan ke `self._cap` → `raise CapExceededError`. Tidak ada panggilan keluar.

**B. TERVERIFIKASI — pembacaan tier dari sisi kita: `free_tier_status()`** (metode ini sebelumnya ada di daftar
"jangan dipanggil sebelum diverifikasi"; sekarang terverifikasi untuk pemakaian read-only ini). Keluaran apa adanya:
```
{'tier': 'free', 'db_size_bytes': 266240, 'soft_cap_bytes': 5242880, 'pct_used': 0.0508,
 'uncapped': False, 'at_or_above_warning': False, 'at_or_above_cap': False,
 'upgrade_url': 'https://sibyllabs.org/plugin#tier'}          # sesudah lewat cap: pct_used 1.014, at_or_above_cap True
```
`tier` yang dilaporkannya adalah `self._tier` — argumen `MemoryClient.local(tier=…)`, default `'free'` — BUKAN
jawaban server. Ia tidak bisa dipakai untuk membuktikan grant Pro.

**C. TERVERIFIKASI — cap dihitung PER AKUN dan AGREGAT lintas store, bukan per file.** `_capcheck.aggregate_db_size`
menjumlahkan (docstring + kode): `primary_db`, `~/.sibyl-memory/memory.db`, `$HERMES_HOME/sibyl/memory.db` +
tiap `profiles/<p>/memory.db`, dan `$SIBYL_MEMORY_DB`. Konsekuensi operasional: kalau seseorang menjalankan
`sibyl setup` sehingga Claude Code/Codex menulis ke `~/.sibyl-memory/memory.db`, byte itu IKUT dihitung terhadap
cap `agent/data/memory.db` kita. Ukuran kita hari ini: `agent/data/memory.db` 286.720 B + `agent/data/chain-abc`
331.671 B ≈ 12% dari 5.242.880 B → cap bukan risiko nyata bagi submission.

**D. TERVERIFIKASI dari docs resmi — tidak ada tier bernama "Pro".** `curl -sL https://docs.sibyllabs.org/memory/tiers`
(diambil 2026-09-06, halaman bertanda "Last updated 2026-06-29") menyebut TIGA tier: **Free** (default sesudah
`sibyl init`), **Staker** (tahan ambang $SIBYL di Base), **Subscription** (bayar USDC di Base). Sejalan dengan kode
0.7.0: `PAID_TIERS = frozenset({"sync","team","lifetime","stake","enterprise"})` (`_capcheck.py:69`) — **"pro" TIDAK
ada di himpunan itu**. TAPI jangan disimpulkan berlebihan: pada `_refresh_and_check` server boleh mengirim
`cap_bytes` EKSPLISIT, dan hanya bila field itu absen kode jatuh ke `None if tier in PAID_TIERS else self._cap`.
Artinya grant sisi-server tetap bisa melepas cap tanpa nama tier dikenal klien — untuk akun yang DIAKTIVASI.
Catatan ketidakcocokan dokumen: tabel di halaman yang sama menulis "2 MB local cap", sedangkan bagian "The 5 MB cap,
precisely" di halaman itu juga menulis 5.242.880 byte. Kode yang kita jalankan yang menang: `FREE_TIER_CAP_BYTES =
5 * 1024 * 1024`, dengan komentar "Raised 2026-08-06 … from 2 MiB → 5 MiB". Docs 2 MB itu BASI.

**E. KLAIM PANITIA — TIDAK bisa kita verifikasi, dan tidak perlu.** Halaman `hack.sibyllabs.org/team/referi-bd41`
membalas **HTTP 404 tanpa autentikasi** (`curl -sL -o /dev/null -w "%{http_code}" …` → `404`, 2026-09-06), jadi
satu-satunya bukti klaim "Pro tier active" adalah tangkapan layar user. Memverifikasinya menuntut `sibyl init`
(sign-in browser milik user) + `sibyl status` — dua hal yang tidak boleh dijalankan di sini. **Yang lebih penting:
klaim itu TIDAK MENYENTUH jalur kita.** Agen memanggil `MemoryClient.local(str(db))` (`vault_client.py:1098` dkk.)
tanpa `account_id`/`session_token`/`credentials_*`, sehingga default `tier='free'`, `account_id=None`. Grant tier
apa pun pada "plugin account" hanya berlaku untuk akun yang teraktivasi lewat `~/.sibyl-memory/credentials.json`;
tanpa itu satu-satunya cabang yang bisa dijangkau adalah cap free lokal (bukti A). Jadi: **jangan tulis di
README/video/post bahwa cap kita terangkat.** Yang benar dan bisa dipertahankan: kita berjalan di bawah cap free
5 MB, tidak teraktivasi, tanpa panggilan jaringan, dan pemakaian ~12% dari cap.

**F. `sibyl-memory-cli[mcp]` — VONIS: perkakas BUILDER, BUKAN jalur submission. JANGAN dipasang.**
Bukti, semuanya primer:
- Registry PyPI (`https://pypi.org/pypi/<pkg>/json`, dibaca 2026-09-06): `sibyl-memory-cli` **0.4.0**,
  `sibyl-memory-mcp` **0.2.0**, `sibyl-memory-langgraph` **0.2.0**, `sibyl-memory-client` **0.8.0** (semua MIT,
  `requires_python >=3.10`, diunggah 2026-08-31).
- **BLOKIR VERSI:** `sibyl-memory-cli` 0.4.0 `requires_dist` = `['sibyl-memory-client>=0.8.0',
  'sibyl-memory-hermes>=0.4.0', 'pyyaml>=6.0,<7', "sibyl-memory-mcp>=0.2.0; extra == 'mcp'", …]`. Memasangnya
  MEMAKSA `sibyl-memory-client` naik dari pin **0.7.0** ke ≥ **0.8.0** — ganti minor line pada satu-satunya paket
  yang menopang SELURUH §C/§C.1/§C.2 → wajib ADR + verifikasi ulang semua signature. `sibyl-memory-mcp` 0.2.0 dan
  `sibyl-memory-langgraph` 0.2.0 menuntut hal yang sama.
- Docs resmi memisahkan jalurnya secara eksplisit. `https://docs.sibyllabs.org/memory/integrations`, tabel
  "Which package do I install?": *"Claude Code / Codex / Cursor / Continue → `sibyl-memory-cli` → `sibyl setup`"*;
  *"**Your own Python → `sibyl-memory-client` → `import MemoryClient`**"*. `sibyl setup` "auto-detects Hermes,
  Claude Code, and Codex and wires Sibyl as the memory provider" — ia mengubah lingkungan CODING kita, bukan
  runtime agen yang disubmit.
- Syarat submission TIDAK menyebut akun plugin. `https://hack.sibyllabs.org/rules` §08 "What to submit": repo
  publik MIT/Apache-2.0 + video 2–5 mnt dengan momen fresh-session recall + README + 2 post build-in-public;
  §03 gerbangnya adalah "delete the Sibyl Memory layer… does the project still do what it claims?". Tidak ada
  kata "plugin account", "`sibyl init`", "activated", atau "CLI" di gerbang maupun daftar submission
  (`https://hack.sibyllabs.org/submissions` juga hanya menyebut 4 item yang sama).
Kesimpulan: memasang `sibyl-memory-cli[mcp]` empat hari sebelum submit membeli NOL poin rubric dan menaruh pin
0.7.0 dalam risiko. Bila suatu saat ia dipakai, ia dipasang di lingkungan builder (venv terpisah), BUKAN di
`agent/pyproject.toml`. Catatan silang: task 0.2 dulu menghapus penyebutan paket-paket ini dengan alasan "tidak
dipakai di kode mana pun" — itu tetap BENAR untuk kode, dan blok F ini tidak membalikkannya; ia mencatat kenapa
paket itu SENGAJA tidak dipakai, sehingga pertanyaan yang sama tidak perlu diriset ulang. AC 0.2 butir (b)
(`grep -nE "sibyl-memory-(cli|mcp|langgraph)([^a-z]|$)" docs/api-facts.md` → kosong) karena itu TIDAK LAGI
terpenuhi apa adanya, dan alat ukurnya perlu diganti seperti AC 0.2 (a) dulu diganti 0.9b: bentuk yang tetap
bermakna adalah "tidak ada baris yang menyatakan paket itu DIPAKAI/DIPASANG", mis.
`grep -nE "sibyl-memory-(cli|mcp|langgraph)([^a-z]|$)" agent/pyproject.toml agent/uv.lock` → kosong (dijalankan
2026-09-06: nol baris). Akhiran `([^a-z]|$)` WAJIB dipertahankan — tanpa itu `cli` ikut mencocokkan `client`,
jebakan yang sama yang sudah tercatat di AC 0.2 (b).

### Klaim "offline, tanpa `sibyl init`" — diverifikasi offline 2026-09-02
Yang diuji: `MemoryClient.local(<path baru>)` membuat DB dari nol tanpa `sibyl init` dan tanpa jaringan, lalu
`set_entity → get_entity → delete_entity → get_entity` (alur tes destruktif spec §7 langkah 3) berhasil. Dua fase sengaja
dipisah: instalasi paket JELAS butuh jaringan; yang diklaim offline hanya runtime SDK-nya. `$SP` = direktori kerja
sementara DI LUAR repo.

Fase 1 — INSTALASI (boleh jaringan, DI LUAR netns; BUKAN bagian dari klaim):
```
uv venv --python 3.13 $SP/venv-offline
uv pip install --python $SP/venv-offline/bin/python 'sibyl-memory-client==0.7.0'
$SP/venv-offline/bin/python -c "import importlib.metadata as m; print(m.version('sibyl_memory_client'))"
# → Installed 1 package: + sibyl-memory-client==0.7.0 ; Python 3.13.15 ; versi 0.7.0
```
Fase 2 — KLAIM (tanpa jaringan sama sekali; HANYA interpreter venv yang dijalankan, tidak ada resolusi/unduh paket.
`env -i` + HOME kosong baru → dipastikan tidak ada state `~/.sibyl-memory` atau kredensial sisa):
```
unshare -rn env -i HOME=$SP/fresh-home PATH=/usr/bin:/bin TMPDIR=$SP/tmp \
  $SP/venv-offline/bin/python $SP/probe_offline.py
```
Output apa adanya (exit 0):
```
HOME/.sibyl-memory exists = False
db exists before = False
db exists after local() = True | size = 4096
set_entity keys  = ['body', 'category', 'created_at', 'id', 'name', 'status', 'tenant_id', 'updated_at']
get_entity body  = {"evidence": ["a", "b"], "job_id": 42, "verdict": "reject"} | status = pending
delete_entity    = True bool
get_entity after delete -> NotFoundError: entity provider/0xdead not found for tenant 00000000-0000-0000-0000-000000000001
delete_entity (ulang, idempoten) = False
network events captured = []
RESULT: OK — offline, no `sibyl init`, no outbound socket
EXIT=0
```
Bonus "tidak ada usaha koneksi keluar": `sys.addaudithook` merekam event `socket.connect` / `socket.getaddrinfo` /
`socket.gethostbyname` / `urllib.Request` selama SELURUH probe termasuk `import sibyl_memory_client` → daftar kosong,
jadi bukan exception jaringan yang ditelan diam-diam. Kontrol bahwa netns memang mati: di dalam `unshare -rn`,
`socket.create_connection(("151.101.0.223", 443))` (IP langsung, tanpa DNS) → `OSError [Errno 101] Network is unreachable`,
dan `ip -o addr` tidak mencetak apa pun.
Konsekuensi operasional: `local()` membuat direktori induk bila belum ada, dan menghasilkan `memory.db` (header
`SQLite format 3`) + `memory.db-wal` + `memory.db-shm` → tes destruktif "hapus memori" harus menghapus KETIGA file,
bukan `memory.db` saja.

## D. Hackathon Sibyl — sumber: https://hack.sibyllabs.org
Build 1–10 Sep; rubric: memori load-bearing 40 / inovasi 25 / teknis 20 / pitch 15 / PMF +10; multiplier ×1.15 (1 stack)
/ ×1.25 (Base+Virtuals) hanya jika integrasi "doing real work"; submission: repo MIT/Apache-2.0, video 2–5 mnt
fresh-session recall, README, 2 post build-in-public. Gate: "Delete the memory layer. If your project still does what it
claims, it is a wrapper and does not qualify."

## E. Jaringan
Base Sepolia chainId 84532, RPC publik `https://sepolia.base.org`. Explorer: https://sepolia.basescan.org
RPC publik itu membatasi `eth_getLogs` ke rentang **10.000 blok** (`{"code":-32614,"message":"eth_getLogs is limited to a
10,000 range"}`, diuji 2026-09-03) → watcher (2.2) dan setiap `cast logs` WAJIB memecah rentang; pemindaian 100k blok
sekaligus akan gagal HTTP 413, bukan mengembalikan hasil kosong.
**BATAS PERSIS — diukur ulang 2026-09-05 dengan bisection, bukan diperkirakan.** Yang dibatasi adalah SELISIH
`toBlock - fromBlock`, bukan jumlah blok: selisih **<= 10.000 DITERIMA** (yaitu 10.001 blok inklusif), selisih
**>= 10.001 DITOLAK**. Perintah (JSON-RPC polos, `User-Agent: curl/8.5.0` — lihat catatan 403 di §E.1):
`POST https://sepolia.base.org` `{"method":"eth_getLogs","params":[{"address":"0x0b93…4d461e","topics":["0x80c17db7…538e"],
"fromBlock":"<latest-D>","toBlock":"<latest>"}]}`, latest = 46426579. Hasil apa adanya:
`D=9998/9999/10000` → HTTP 200; `D=10001/19999/49999/50000/99999` → **HTTP 413 + body `{"code":-32614,"message":"eth_getLogs
is limited to a 10,000 range"}`**. Jadi "50.000 blok gagal" benar, tapi bukan angka batasnya; batasnya 10.000.
**Lewat web3.py errornya BUKAN error JSON-RPC.** `HTTPProvider` memanggil `raise_for_status()` lebih dulu, jadi kode
`-32614` tidak pernah sampai ke pemanggil; yang dilempar adalah
`requests.exceptions.HTTPError: 413 Client Error: Payload Too Large for url: https://sepolia.base.org/`
(diuji 2026-09-05: `contract.events.JobSubmitted().get_logs(..., from_block=hi-10000, to_block=hi)` → sukses;
`hi-10001` → HTTPError di atas). Penanganan galat yang menunggu `ValueError`/`Web3RPCError` akan MELEWATKANNYA.
Token: **escrow ACP Base Sepolia memakai `0xECc22a8F6fD62388498fBa19813E214605a2BDb3`, BUKAN USDC Circle
`0x036CbD53842c5426634e7929541eC2318f3dCF7e`** (keduanya `symbol() == "USDC"`, 6 desimal — mudah tertukar). Lihat §A.
USDC Circle tetap dicatat di `docs/versions.md` untuk rujukan, tetapi TIDAK dipakai jalur escrow kita.

### E.1 RPC publik TIDAK menjamin read-your-writes — dicatat 2026-09-04 setelah 4 kegagalan berbayar gas
`https://sepolia.base.org` adalah endpoint publik gratis. https://docs.base.org/chain/network-information (dibaca
2026-09-04) HANYA mencantumkan URL-nya dan **tidak menjanjikan konsistensi apa pun** — tidak ada jaminan read-your-writes
di sana, jadi jangan berasumsi ada. (Kalimat "rate-limited / not suitable for production" yang beredar TIDAK berhasil
ditemukan verbatim di halaman mana pun yang kami baca; jangan mengutipnya.) Endpoint ini menjawab
`web3_clientVersion` → `reth/v2.5.1-2fa11e6/x86_64-unknown-linux-gnu/base/v1.3.0` (6 panggilan, identik), dan **`eth_call` bisa
dilayani node yang TERTINGGAL di belakang receipt yang baru saja endpoint yang sama kembalikan.** Akibatnya: baca-sesudah-tulis
mengembalikan nilai LAMA (nol), kode menyimpulkan tx gagal padahal sukses, lalu mengirim tx lanjutan yang REVERT.
Empat kejadian terukur 2026-09-04 (semua di endpoint ini):
1. `verdicts(jobId).readyAt` = `0` tepat sesudah receipt `postVerdict` sukses → `finalize` dikirim terlalu dini dan
   **revert on-chain**: tx `0x12673d199582081656747caba9c5316f0d642fb6aae1e7a9663db9fd289247ba`, blok 46355038,
   **status 0 (failed)**, `to` = vault `0x5c6EE4586ACABcb6326069c229E58091B21ef384` (dicek ulang `cast receipt`).
2. `balanceOf` = `0` sesudah `mint` sukses: tx `0x17c15c0264a3141c980f9aeaa6e3656582f522ca883656817f50a9891e48774c`,
   blok 46375962, **status 1**, log `Transfer(0x0 → 0xbe2c…02c2)` bernilai `0x1e8480` = **2000000** dari token escrow
   `0xECc22a8F…2BDb3` (dicek ulang `cast receipt --json`). Nilai on-chain nyata ada; pembacaannya yang salah.
3. `balanceOf` ETH terbaca `0` sesudah transfer sukses (pola identik, tanpa hash tercatat).
4. `fund` job 415 revert saat **SIMULASI** dengan returndata **KOSONG** (bukan custom error!) karena node simulasi belum
   melihat receipt `approve` yang baru dikembalikannya; `cast call` beberapa detik kemudian SUKSES. Job 415 sampai kini
   masih `status 0 (Open)`, budget 1000000, evaluator = vault (`cast call <ACP> "getJob(uint256)(...)" 415`).
**Status bukti:** keempat receipt/state di atas diverifikasi ulang langsung ke chain 2026-09-04 dan cocok dengan laporan;
mekanismenya (load balancer ke node yang lag) adalah INFERENSI dari gejala + arsitektur multi-node — pembacaan mundur
tidak berhasil direproduksi dalam jendela pengamatan singkat (20 sampel `eth_blockNumber` berurutan monoton naik).
Perlakukan sebagai fakta OPERASIONAL, bukan fakta protokol.
**Aturan mengikat untuk semua kode kita (agent, skrip deploy, demo):**
- JANGAN pernah menyimpulkan hasil sebuah tx dari `eth_call` sesudahnya. Sumber kebenaran = **event di receipt tx itu**
  (`Transfer`, `JobFunded`, `VerdictPosted`, …). Receipt bersifat self-contained dan tidak bisa "tertinggal".
- Bila sebuah nilai HARUS dibaca lewat `eth_call` sesudah tulis (mis. `readyAt` sebelum `finalize`), bungkus dengan
  **retry + backoff sampai nilainya masuk akal**, jangan sekali baca. Nol/kosong = "belum terlihat", BUKAN "tidak ada".
- `eth_call` yang revert dengan **returndata kosong** sesudah tx tulis yang baru saja sukses hampir selalu artefak lag,
  bukan bug kontrak — retry dulu sebelum mengubah kode.
- Jangan mengirim tx yang bergantung pada prasyarat on-chain tanpa simulasi yang LULUS pada percobaan ulang; simulasi
  gagal satu kali bukan alasan mengirim, dan bukan alasan menyerah.
Catatan alat: `urllib`/`requests` polos ke endpoint ini bisa dijawab **HTTP 403** sementara `cast` di detik yang sama
lolos (diamati 2026-09-04) → jangan menafsirkan 403 sebagai "node down" atau sebagai bukti rate limit kita sendiri.

## F. web3.py 7.16.0 — HANYA yang dipakai `agent/`. Sumber: `inspect.signature` pada paket TERPASANG di
## `agent/.venv` (BUKAN venv sekali-pakai, BUKAN ingatan) + satu panggilan NYATA ke Base Sepolia.
## Diverifikasi 2026-09-05: `agent/.venv/bin/python -c "import web3; print(web3.__version__)"` → `7.16.0`,
## Python 3.13.15, `eth-abi` 6.0.0. Cocok dengan pin `docs/versions.md`.
```python
# web3/contract/contract.py — salinan inspect.signature apa adanya (`self` dibuang, tipe diringkas):
ContractEvent.get_logs(argument_filters: dict|None = None,
                       from_block: BlockIdentifier|None = None,
                       to_block: BlockIdentifier|None = None,
                       block_hash: HexBytes|None = None) -> Iterable[web3.types.EventData]
# semuanya POSITIONAL-OR-KEYWORD (tidak ada `*`), snake_case. Bandingkan `create_filter` yang
# keyword-only dan berdefault `to_block='latest'` — `get_logs` TIDAK punya default itu.
Eth.block_number   # PROPERTY, bukan method: inspect.getattr_static(Eth,"block_number") -> <class 'property'>.
                   # `w3.eth.block_number()` = TypeError. Nilai bertipe int.
```
`argument_filters` atas argumen **indexed** menjadi TOPIC (bukan pemindaian sisi-klien). Dibuktikan lewat
`web3._utils.filters.construct_event_filter_params(...)` dengan fragmen ABI `JobSubmitted` kita dan `{"jobId": 403}` →
`topics = ['0x80c17db7…538e', '0x…0193']`, `data_filters = [[]]`. Untuk argumen **non-indexed** (`deliverable`)
tidak ada topic yang terbentuk — filternya jatuh ke `data_filters` dan disaring di sisi klien setelah semua log ditarik.
Jadi memfilter `deliverable` TIDAK menghemat apa pun di RPC; filter yang sah untuk mempersempit rentang hanya `jobId`
dan `provider`.

Bentuk `EventData` yang dikembalikan (kunci PERSIS, `sorted(web3.types.EventData.__annotations__)`):
`['address','args','blockHash','blockNumber','event','logIndex','transactionHash','transactionIndex']`.
**Tidak ada kunci `topics`** — jangan membacanya dari hasil `get_logs`. `blockNumber` bertipe `int`.

Bukti END-TO-END terhadap chain (2026-09-05, `agent/.venv/bin/python`, `Web3(HTTPProvider("https://sepolia.base.org"))`,
fragmen ABI tulisan tangan `ACP_ABI` di `agent/agent/vault_client.py` apa adanya):
```
c.events.JobSubmitted().get_logs(argument_filters={"jobId": 403}, from_block=46170000, to_block=46179999)
→ 1 log, blockNumber 46173983 (int),
  args = {'jobId': 403, 'provider': '0x40552F2daC6bE37c831536B703743a3f701Da8E5',
          'deliverable': b'\x0ba\x1fv…\xe2\x05'}   # bytes32 → Python `bytes`, len 32, BUKAN HexBytes/str
c.functions.jobs(403).call()
→ 8 nilai: ['0x6F75…440e', 3, '0x4055…a8E5', 1788118042, '0x6F75…440e', '0x00…00', 0, '{"product":"TRACE",…}']
```
Dua konsekuensi yang MENGIKAT (menutup pertanyaan task 2.4-min):
1. **Struct `Job` TIDAK punya field `deliverable`.** Dikonfirmasi di DUA sumber: ABI paket
   `node_modules/.pnpm/@virtuals-protocol+acp-node-v2@0.1.12/…/dist/core/acpAbi.js` — satu-satunya entri ABI yang
   menyebut `deliverable` adalah `event JobSubmitted` dan `function submit`, TIDAK ada di `getJob`/`jobs`; dan panggilan
   live `jobs(403)` di atas yang mengembalikan tepat 8 nilai sesuai §A. Karena itu **log `JobSubmitted` adalah
   SATU-SATUNYA sumber hash deliverable on-chain** — tidak ada getter yang bisa menggantikannya.
2. Fragmen ABI `JobSubmitted` tulisan tangan di `vault_client.py` COCOK FIELD-PER-FIELD dengan ABI acp-node-v2:
   `jobId uint256 indexed=true`, `provider address indexed=true`, `deliverable bytes32 indexed=false`, `anonymous=false`.
   topic0 yang dihasilkannya = `Web3.keccak(text="JobSubmitted(uint256,address,bytes32)")` =
   `0x80c17db79857f338a6a6df68a6883ecc0ce78e2202fe61ed979733573f40538e` — identik dengan nilai §A.
   Perintah pembanding: `node -e "const {ACP_ABI}=require('<…>/dist/core/acpAbi.js'); console.log(JSON.stringify(
   ACP_ABI.filter(x=>x.name==='JobSubmitted')))"`.

## G. Verifikasi log lewat `cast logs` — ALAT, bukan protokol. Diverifikasi 2026-09-06 (prasyarat AC (a) task 2.5)
### G.1 `JobRejected` — bentuk DIKONFIRMASI ULANG dari tiga sumber independen (2026-09-06)
`JobRejected(uint256 indexed jobId, address indexed rejector, bytes32 reason)` — **BENAR**, aritas 3, dua argumen indexed,
`reason` di `data`. Sumber yang dilihat hari ini, bukan ingatan:
1. ABI paket terpasang: `node -e "const {ACP_ABI}=require('<node_modules/.pnpm/@virtuals-protocol+acp-node-v2@0.1.12/…>/dist/core/acpAbi.js');
   console.log(JSON.stringify(ACP_ABI.filter(x=>x.name==='JobRejected')))"` → `indexed:true jobId uint256`, `indexed:true rejector address`,
   `indexed:false reason bytes32`, `anonymous:false`.
2. Source terverifikasi Sourcify `exact_match` (`AgenticCommerceV3.sol` `:121-125`, sha256 `3b47cdbc…8cddb` diambil ulang & cocok).
3. Log NYATA Base Sepolia: blok 45755763, tx `0x301d71c947bd06afbc8016093a5f9e5c09bbd1175ece2ee56775ab916090c551`,
   3 topics + `data` 32 byte (job 367, rejector = client karena `evaluator == 0`).
topic0 = `cast sig-event "JobRejected(uint256,address,bytes32)"` = `0xae7362b1af91f4492868987b9c73990d780060811551b58728fbe96fd1bab275`
— identik dengan §A dan dengan topic0 log nyata di atas. `reject(uint256,bytes32,bytes)` selector `0x41dd26f5` (terlihat di calldata tx itu).

### G.2 Rantai job C (`reject` saat **Funded** oleh vault-sebagai-evaluator) — DIEKSEKUSI di fork, bukan dibaca
`forge test` di fork Base Sepolia 2026-09-06 memakai kontrak ASLI (ACP `0x0b93…4d461e`, vault terdeploy `0x5c6E…f384`,
`vm.prank(agent)`): createJob(evaluator = VAULT) → setBudget 2 USDC → fund → status **1 (Funded)** →
`postVerdict(jobId, 2, reasonHash, root)` → warp 200 s → `finalize(jobId)` **SUKSES**. `vm.getRecordedLogs()` dari tx
`finalize` (job 418), apa adanya:
```
1 ERC20 Transfer  emitter 0xECc2…BDb3  (ACP → client, 0x1e8480 = 2.000.000)
2 Refunded        emitter ACP  topic0 0x7ca5472b…a2c4
3 JobRejected     emitter ACP  topic0 0xae7362b1…b275  topic1 jobId  topic2 = 0x5c6E…f384 (VAULT)  data = reasonHash
4 Finalized       emitter VAULT topic0 0x642e932534104f1bb949c7593c10c039babcf12b89d90da5c889ca1e833f87b5
```
status sesudahnya = **4 (Rejected)**, client menerima 100% budget. Tiga konsekuensi yang MENGIKAT AC (a):
- **`reject` dari status Funded SAH untuk evaluator** (source `:563-575`, `emit JobRejected` `:592`: Funded ATAU
  Submitted, `evaluator != 0` → HANYA evaluator). Gerbang cap saat Funded memang mungkin; tidak perlu menunggu Submitted.
- **`rejector` (topic 2) = alamat VAULT `0x5c6EE4586ACABcb6326069c229E58091B21ef384`, BUKAN EOA agent.** Bukti AC (a) yang
  mencari alamat agent akan gagal palsu.
- `JobRejected` selalu diemit; `Refunded` hanya bila `budget > 0` (§A) — jangan jadikan `Refunded` penanda.

### G.3 JEBAKAN `cast logs` 1.7.1: filter argumen indexed DIABAIKAN DIAM-DIAM saat memakai signature
Diuji 2026-09-06 pada rentang 45750000-45759999 yang memuat TEPAT SATU `JobRejected` (job 367):
```
cast logs --address <ACP> "JobRejected(uint256,address,bytes32)" 367      → log job 367 keluar
cast logs --address <ACP> "JobRejected(uint256,address,bytes32)" 999999   → log job 367 TETAP keluar  (!!)
cast logs --address <ACP> "JobRejected(uint256,address,bytes32)" 367 <alamat rejector SALAH> → TETAP keluar (!!)
```
Bentuk hex 32-byte juga diabaikan. Jadi **argumen sesudah signature TIDAK memfilter apa pun**; perintah "berfilter jobId"
memberi LULUS PALSU untuk sembarang reject di rentang itu. Yang benar-benar memfilter hanyalah bentuk TOPIC MENTAH:
```
cast logs --address <ACP> 0xae7362b1af91f4492868987b9c73990d780060811551b58728fbe96fd1bab275 \
  0x<jobId di-pad 32 byte> --from-block <N-9999> --to-block <N> --rpc-url https://sepolia.base.org
```
kontrol: jobId salah (`0x…0f423f`) → keluaran KOSONG; jobId benar → 1 log. (`cast --to-uint256 <jobId>` untuk padding.)
**Bahaya kedua: keluaran KOSONG + exit 0 adalah hasil yang SAMA untuk "tidak ada event" dan untuk "signature salah"** —
persis kegagalan `JobCompleted(uint256,bytes32)` di 1.3d. Perintah AC (a) apa adanya (tanpa filter jobId) BEKERJA dan
mengembalikan semua `JobRejected` di rentang; ia sah HANYA bila keluarannya dicocokkan sendiri ke `topic1 == jobId C`
dan `topic2 == VAULT`. Rentang tetap tunduk batas §E: `toBlock - fromBlock <= 10000` (`N-9999`..`N` = 9999, aman).

### G.4 Sisi vault (AC (b) & (d)) — dibaca dari bytecode TERDEPLOY `0x5c6E…f384`, 2026-09-06
```
providerCap(address)(uint256)  selector 0x99893d92   → 1 kecocokan di `cast code`; `cast call <VAULT>
  "providerCap(address)(uint256)" <provider> --rpc-url https://sepolia.base.org` → 0 (belum ada cap). Signature AC (b) BENAR.
MemoryRootUpdated(bytes32 indexed memoryRoot, uint256 indexed jobId)
  topic0 0xc6028d32061c1f0b8f4f1370b6f1ab5105a96bfc6631a3840371ebbcb27c7923  (ada di bytecode terdeploy)
VerdictPosted(uint256 indexed jobId, uint8 kind, bytes32 reasonHash, bytes32 memoryRoot, uint64 readyAt)
  topic0 0x6744a0f4fac82e60e8b7fdcca821ce8a15f365465f8c2ad497249e023511eb7e
```
**KEDUA argumen `MemoryRootUpdated` indexed → `data` kosong (`0x`)**; `memoryRoot` = topic 1, `jobId` = topic 2. Dikonfirmasi
pada log nyata blok 46355036 & 46355080 (`cast logs --address <VAULT> "MemoryRootUpdated(bytes32,uint256)" --from-block
46350000 --to-block 46359999`): `data: 0x`. Skrip AC (d) yang men-decode `memoryRoot` dari `data` akan mendapat kosong.
Sumber Solidity = commit **8d3e596** (revisi yang benar-benar dideploy, `deployments/84532.json`), bukan HEAD:
`git show 8d3e596:contracts/src/EvaluatorVault.sol` baris 130/140/248. Selector `sweepToken` `0x258836fe` milik HEAD
**0 kecocokan** di bytecode terdeploy — jangan pakai fungsi itu di AC.
