# Bukti on-chain lengkap

Semua yang ada di sini bisa dibuka tanpa menjalankan repo ini. Jaringan: **Base Sepolia (chainId 84532)**.
Batasan yang menyertai tiap klaim ada di [`docs/limitations.md`](limitations.md) — nomor butir di halaman
ini merujuk ke sana.

## Alamat & integrasi

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
sehingga **Blockscout** mendekode event vault dengan nama; BaseScan tidak menariknya (butir 15):
`https://base-sepolia.blockscout.com/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384?tab=logs`

**SDK Virtuals dipakai sungguhan, bukan dekorasi.** Seluruh transaksi ACP di simulator lewat
`@virtuals-protocol/acp-node-v2@0.1.12` (`sim/package.json:12`); `sim/src/client_min.ts:11-14` menyatakan
dan menepati bahwa file itu tidak meng-encode satu pun calldata ACP sendiri — kalender panggilan, ABI, dan
urutan approve+fund datang dari SDK, dan yang kami sediakan hanya adapter penanda tangan viem
(`IEvmProviderAdapter`). `evaluatorAddress` diisi eksplisit dengan alamat vault: default SDK adalah alamat
nol = "skip evaluation", yang akan langsung membayar provider tanpa wasit. Batasnya, dan ini yang paling
lemah dari seluruh repo: **`sim/` tidak punya satu pun tes otomatis** (butir 18) — yang membuktikan jalur
SDK ini bekerja hanyalah transaksi Base Sepolia yang ditautkan di halaman ini.

Pipa hidup pertama (job 417: `createJob → setBudget → fund → submit → postVerdict → finalize →
JobCompleted`) beserta enam hash transaksinya terdokumentasi di `deployments/pipeline-84532.md`.

## Rantai A → B → C (6 Sep 2026): gerbang cap

Tiga job dari **satu** provider `0x20212E4D95A75E6716575ED26e884cdeFf66b321`:

| Job | Budget | Hasil | Yang berubah di memori |
|---|---|---|---|
| **A = 418** | 1.000.000 | REJECT | cek `format` gagal (kata "TODO", butir 21) → pola `format.placeholder-text`, karantina count = 1, cap 0 → 1.000.000 |
| **B = 419** | 1.000.000 | REJECT | pola SAMA dari job BERBEDA → count = 2 → promosi ke `reference:pattern` + `provider.confirmed_patterns`, **risk = 2** → cap 1.000.000 → 250.000 |
| **C = 420** | 2.000.000 | **REJECT saat `Funded`** | budget > cap → ditolak sebelum provider sempat submit; status akhir job = 4 |

Baca kolom terakhir dengan dua batas: yang dipelajari memori adalah **risk level dan pola**, sedangkan
**angka** cap 250.000 adalah konstanta tim dibagi 4 (`sample_size: 0`, butir 8); dan "pola curang" di sini
adalah kata "TODO" dari simulator kami sendiri (butir 21). Karantina (`suspicion`) tidak pernah dibaca
pengambil keputusan; promosi menuntut ≥ 2 job berbeda dengan bukti dari cek deterministik (ADR-002,
`docs/spec.md` §3 aturan 1-2).

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
membuang signature-nya dan mengirim topic0 + topic1 bersama `--address`, persis bentuk blok di atas.
Kontrol negatif dengan jobId `999999` pada rentang yang sama mengembalikan hasil KOSONG, jadi filternya
memang menggigit.

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

## Job 421 vs 422: gerbang kedalaman

Teks deliverable **identik byte demi byte** (`keccak256(text)` = `0x246071b3…0a51` pada
`demo/deliverables/421.json` dan `422.json`), budget sama (250.000), evaluator sama — provider berbeda,
verdict berlawanan. Tabel penuh, apa yang dibuktikan, dan **apa yang TIDAK dibuktikannya**: butir 25.

```
job 421  postVerdict  0x02356b079fa3bfcd32e62d7e2bb61d3f4eb8b66d29fac578cd6318b2028a1467  (blok 46455461)
job 421  finalize     0x371a4db2ed4c7975f3806f64392f92ecba2132feb9a1df78889c31af9bcaf020  (blok 46455526)
job 422  postVerdict  0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830  (blok 46455552)
job 422  finalize     0x502c8d944106914b15d95a38b2815187fa7b3d63965d95414ccd7f15835b5f08  (blok 46455616)
```

## Riwayat `MemoryRootUpdated` (delapan event)

Tabel kedelapan root beserta jobId, apa artinya, dan mana yang masih bisa dihitung ulang hari ini:
**butir 7**. Ikatan root ↔ bundel bukti (satu-satunya pasangan yang cocok hari ini): **butir 22**.

## Peta angka → sumber

| Angka | Sumber |
|---|---|
| `MIN_BOND` = 0 | `deployments/84532.json` → `minBondWei` |
| `CHALLENGE_WINDOW` = 120 detik | `deployments/84532.json` → `constants.CHALLENGE_WINDOW` |
| `MIN_ACP_GAS` = 300.000 | `deployments/84532.json` → `constants.MIN_ACP_GAS`; diturunkan dari pengukuran di ADR-015 keputusan 3 |
| `EVALUATOR_GRACE_PERIOD` = 900 detik | `docs/api-facts.md` §A KOREKSI 2026-09-03; ADR-014 |
| saldo vault = 62.500 unit (0,0625 USDC testnet) = 50.000 (job 417) + 12.500 (job 421); `evaluatorFeeBP` 500 = 5% | `cast call paymentToken "balanceOf(address)" <vault>` → `62500` (butir 4); `deployments/pipeline-84532.md:84` (tabel aliran dana); ADR-018 keputusan 2 |
| fee hanya cair saat `Completed` → fee evaluator untuk 418/419/420 = 0 | `docs/spec.md` §1 baris 19 (fakta ERC-8183) + status akhir 4 pada ketiga job, rantai A/B/C di atas |
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
| job 418 / 419 / 420, budget 1.000.000 dan 2.000.000, status akhir 4 | keluaran `cast` di rantai A/B/C di atas |
| job 421 status 3 (Completed) / job 422 status 4 (Rejected), budget 250.000 keduanya | `cast call <ACP> "jobs(uint256)"` — ABI terverifikasi `docs/api-facts.md` §A, dipakai `agent/agent/vault_client.py:389-405` (butir 25) |
| `keccak256(text)` deliverable 421 == 422 == `0x246071b3…0a51` | `demo/deliverables/421.json`, `422.json` field `sha_keccak` (butir 25) |
| provider bersih job 421 = `0xc3c6Bf20…aeff`; provider berisiko job 422 = `0x20212E4D…b321` | `cast call <ACP> "jobs(uint256)"` (butir 25) |
| empat tx demo kedalaman (2× `postVerdict`, 2× `finalize`), blok 46455461-46455616 | daftar hash di atas dan di butir 25 |
| gerbang 402 ada di `agent/agent/payment_402.py` (BUKAN `agent/x402_server.py`) | commit `a213cdd`, `3c5cafa`; tes `agent/tests/test_payment_402.py`; ADR-010 (butir 23) |
| wallet client simulator `0xbe2c447e…02C2` → 404 `/auth/agent` | `sim/src/client_min.ts:510-512` (komentar memakai placeholder `<client>`); alamat literal di ADR-019 `docs/decisions.md:385` + `jobs(417..422).client` on-chain (butir 24) |
| `providerCap` = 250.000 | `cast call providerCap(address)` di atas |
| blok 46436498, tx `0x78a3a65d…989e`, `reason` `0x1618e765…b5ed` | `cast logs JobRejected` di atas |
| `lastMemoryRoot()` = `0x999a9570…9b7d` (root job 422), sedangkan `memory_export` atas DB hari ini = `0x50750074…0c3c` — **sengaja berbeda satu langkah tulis** | `cast call lastMemoryRoot()` dan `memory_export.py` di butir 22; sebabnya `docs/spec.md` §5 langkah 5 |
| root warisan `0x1fa62c3d…7bf0` = `keccak("the-evaluator/live/memory-root/v1")` | `cast keccak` di butir 7; ADR-023 konteks |
| root selftest `0x5ff921fd…a19e` = `keccak("the-evaluator/selftest/memory-root/v1")` | `cast keccak` di butir 7; commit `26f11d6` (dicabut `190cb44`) |
| blok 46355036 / 46355080, jobId sintetis 9000000 / 9000001 (`0x895440` / `0x895441`) | `cast logs MemoryRootUpdated` di butir 7 |
| blok deploy 46350667, gas 816.969, solc 0.8.36, optimizer 200 | `deployments/84532.json` |
| chainId 84532 | `deployments/84532.json` |
