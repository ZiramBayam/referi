# The Evaluator

Wasit escrow ERC-8183 yang ingatannya tentang tiap provider bisa **dihitung ulang dari file**. Evaluator
standar ERC-8183 bersifat stateless dan "fully trusted": provider yang sama bisa mengulang trik yang sama
pada job berikutnya tanpa jejak. Di sini tiap `postVerdict` mengumumkan `memoryRoot` on-chain, dan memori
itulah yang menentukan kedalaman pemeriksaan serta cap budget per provider.

- Status: **proyek hackathon di Base Sepolia (testnet), belum pernah dijalankan di mainnet.**
- Kontrak submission (BEKU, ADR-022): [`0x5c6EE4586ACABcb6326069c229E58091B21ef384`](https://sepolia.basescan.org/address/0x5c6EE4586ACABcb6326069c229E58091B21ef384)
- **Insentifnya BELUM diperbaiki**: `evaluatorFeeBP` = 500 (5%) hanya cair saat job `Completed`, jadi wasit
  ini masih dibayar hanya kalau ia meluluskan. Fee di muka via x402 adalah rancangan (ADR-004), bukan
  fitur. Detail: [`docs/limitations.md`](docs/limitations.md) butir 14.
- Prosa berbahasa Indonesia; identifier, perintah, dan kutipan kode berbahasa Inggris. Lisensi: MIT.

## Kalau Anda cuma punya 3 menit

Tiga hal ini yang paling kami ingin Anda periksa — semuanya bisa dibuka tanpa menjalankan apa pun:

1. **Verdict yang dibentuk riwayat, di chain.** Job 421 dan 422 memakai deliverable yang identik byte demi
   byte; 421 lulus, 422 ditolak. `postVerdict` job 422:
   [`0xe95910d2…295830`](https://base-sepolia.blockscout.com/tx/0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830)
   (Blockscout mendekode nama eventnya — butir 15). Duduk perkaranya: **butir 25**.
2. **Bundel bukti job 422**, yang hash-nya sudah diumumkan on-chain sebelum eksekusi:
   [`web/public/verdicts/422.json`](web/public/verdicts/422.json) — memuat `memory_root`, `checks`,
   `incident_jobs`, dan kriteria yang **tidak** dinilai. Cara mencocokkannya dengan chain: **butir 22**.
3. **Baris `claim step=C-vs-D`** yang dicetak `make demo` (`sim/src/demo.ts:902-907`): gerbang cap yang
   sama, dengan memori vs tanpa memori, pada budget identik. Konteks dan batasnya: **butir 19**.

Kalau Anda hanya ingin tahu apa yang TIDAK bekerja: [`docs/limitations.md`](docs/limitations.md).

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

Kenapa tiga hal ini ada di luar spek ERC-8183, dan ADR mana yang memutuskannya:
[`docs/design.md`](docs/design.md).

## Cara menjalankan

```
make doctor    # cetak versi toolchain, exit 1 bila tidak cocok docs/versions.md
make test      # forge test + uv run pytest + pnpm -r test
make demo      # §7 langkah 1-4 dari NOL di Anvil lokal + DUA varian destruktif
               # BUTUH INTERNET (varian B membaca vault Sepolia beku: nol dana, nol transaksi)
               # runtime terukur: 3m23s dan 3m56s pada dua eksekusi
```

UI (opsional, di luar `make demo`):

```
DEMO_MODE=1 pnpm --filter web start          # http://127.0.0.1:3000/panel
cd agent && DEMO_MODE=1 uv run python -m agent.demo_reset --host 127.0.0.1 --port 8010
```

Perintah per-job, reproduksi rantai A/B/C, reproduksi demo kedalaman, dan troubleshooting exit code 4:
[`docs/reproduce.md`](docs/reproduce.md).

## Tes destruktif

`make demo` menjalankan kedua varian; keduanya menghapus `memory.db`, dan yang berubah adalah lingkungannya:

| Varian | Kondisi | Yang berubah |
|---|---|---|
| **A — degradasi** (Anvil lokal) | vault segar, `lastMemoryRoot()` = 0, `SIBYL_DB_PATH` ke path yang belum pernah ada | job C yang DITOLAK saat memori ada menjadi **lolos** pada budget IDENTIK: `depth=sampling`, `cap=TANPA CAP`. Label modenya `normal`, bukan `naive` (butir 34) |
| **B — mode aman** (baca vault Sepolia beku) | root on-chain non-nol + `memory.db` dihapus | **mode aman**: nol `postVerdict`, nol `finalize`, nol `setProviderCap`; job menggantung sampai `expiredAt`. Run digugurkan bila buktinya tidak muncul (`sim/src/demo.ts:672-685`) |

```
# varian A, dijalankan tangan (bentuk yang sama dipakai make demo)
cd agent && uv run python -m agent.vault_client --job-id <job C> --kind reject
```

Pada vault segar perintah itu butuh **dua** invokasi: yang pertama melahirkan `memory.db` lalu ditolak
penjaga `MODE_DRIFT` dengan **exit code 4 dan nol transaksi** (ADR-026). Tabel hasil lengkap dan
troubleshooting: [`docs/reproduce.md`](docs/reproduce.md). Yang belum ada adalah **artefaknya** — perintah
itu tidak meninggalkan log atau fixture di repo (butir 19).

> **Hapus memori kami, dan kamu dapat evaluator stateless biasa — persis pesaing kami.**

Yang **tidak** berubah saat memori hilang: cek deterministik tetap berjalan, jadi cacat kasar tetap ditolak.
Yang hilang hanyalah kalibrasi — kedalaman cek, pola yang sudah dipelajari, dan gating cap. Catatan penting:
"cacat kasar" adalah **posisi** token `TODO` di dalam jendela sampling, bukan tingkat keparahan yang dinilai
(butir 19).

## Bukti on-chain (yang paling kuat)

| Fakta | Nilai / bukti |
|---|---|
| EvaluatorVault (submission, beku) | `0x5c6EE4586ACABcb6326069c229E58091B21ef384` |
| ACP (ERC-8183 Virtuals, Base Sepolia) | `0x0b93793923CD5De81850aF8604a233f3f24d461e` |
| Verifikasi sumber | Sourcify `exact_match` (creation + runtime), dari commit `8d3e596` — `deployments/84532.json:36-44`; Blockscout mendekode event vault dengan nama; BaseScan tidak menariknya (butir 15) |
| `postVerdict` job 422 (`VerdictPosted`, kind=2) | [`0xe95910d2…295830`](https://base-sepolia.blockscout.com/tx/0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830) — blok 46455552 |
| SDK yang dipakai | `@virtuals-protocol/acp-node-v2@0.1.12` (`sim/package.json:12`); `evaluatorAddress` diisi alamat vault (default SDK = 0x0 = skip evaluasi) |

**Teks identik, verdict berlawanan.** Dua job, deliverable sama byte demi byte
(`keccak256(text)` = `0x246071b3…0a51` di `demo/deliverables/421.json` dan `422.json`), budget sama
(250.000), evaluator sama — yang berbeda hanya riwayat providernya di memori:

| job | provider | riwayat | depth | verdict on-chain |
|---|---|---|---|---|
| 421 | `0xc3c6Bf20…aeff` | nol insiden | `sampling` (2 bagian pertama) | `kind=1` → status 3 (Completed) |
| 422 | `0x20212E4D…b321` | 2 insiden (418, 419) | `full` | `kind=2` → status 4 (Rejected) — `TODO` di bagian ketiga |

`SAMPLING_SECTION_LIMIT = 2` (`agent/agent/checks/base.py:78`); regex penanda pekerjaan di
`agent/agent/checks/format.py:47-50`. Apa yang pasangan ini **tidak** buktikan: butir 25.

Alamat lengkap, rantai A/B/C beserta `cast logs` `JobRejected`, riwayat delapan `MemoryRootUpdated`, empat
hash tx demo kedalaman, dan peta angka → sumber: [`docs/evidence.md`](docs/evidence.md).

## Batasan & asumsi kepercayaan

Daftar lengkap 36 butir ada di [`docs/limitations.md`](docs/limitations.md) — penomorannya tidak berubah,
dan naskah video merujuknya dengan nomor yang sama. Delapan yang paling menentukan:

1. **Verdict yang salah tidak bisa dibatalkan siapa pun.** `challenge`/`resolve` adalah stub
   (`revert NotImplemented()`), jadi `CHALLENGE_WINDOW` = 120 detik adalah **murni latensi, nol
   perlindungan**; sesudah jendela itu `finalize` permissionless dan uangnya berpindah
   (`EvaluatorVault.sol:327-331`, `:363`; butir 2 dan 26).
2. **Bond evaluator = nol.** `MIN_BOND` pada kontrak terdeploy = 0 (`deployments/84532.json` →
   `minBondWei`), jadi cabang `BondTooLow` tidak bisa dijangkau (butir 1 dan 28).
3. **`arbiter()` == `agent()`, permanen.** Satu EOA merangkap deployer, agen, arbiter, dan satu-satunya
   penanda tangan; kontraknya immutable, tanpa rotasi dan tanpa pause (butir 3 dan 27).
4. **Dana yang masuk vault terjebak.** `sweepToken` ada di sumber tetapi **tidak ada di bytecode
   terdeploy**, dan tidak ada jalur ETH keluar — 62.500 unit fee hangus permanen (butir 4 dan 28).
5. **Kriteria kualitatif TIDAK dinilai.** Rubric LLM dipotong; tidak ada satu pun panggilan LLM di jalur
   evaluasi. Kriteria itu dicatat `unscored` di tiap bundel, tidak pernah dianggap lolos
   (`agent/agent/criteria.py:121-124`; butir 33).
6. **Cap awal adalah parameter tim, bukan hasil belajar.** `BASELINE_CAP_USDC` = 1.000.000 dipilih tim;
   bundel job 420 sendiri menulis `sample_size: 0`. Memori hanya bisa **mengetatkan** cap (butir 8).
7. **Cap diterbitkan di kontrak, tetapi ditegakkan di agen off-chain.** `providerCap` ditulis
   (`EvaluatorVault.sol:289`) dan **tidak pernah dibaca** kontrak (butir 17).
8. **Jangkar root melingkar, dan agen tidak otonom.** On-chain hanya root nol yang ditolak
   (`EvaluatorVault.sol:303`); `memory.db` yang **ditukar** DB lain tidak terdeteksi (butir 16, 29, 30).
   Agen dijalankan per job dengan `--job-id` — bukan watcher (butir 9).

Lainnya di daftar itu, antara lain: teks deliverable tidak datang dari API ACP resmi (butir 6), tiga dari
delapan root vault bukan turunan memori (butir 7), `sim/` tanpa tes otomatis (butir 18), tes destruktif
belum meninggalkan artefak (butir 19), gerbang 402 belum dikonsumsi jalur job (butir 23), wallet simulator
belum terdaftar di Service Registry Virtuals (butir 24), dan riwayat review keamanan permukaan hapus-memori
(butir 36).

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
docs/        spec.md, decisions.md (ADR), api-facts.md, versions.md,
             limitations.md, evidence.md, reproduce.md, design.md
```

## Dokumen

| Berkas | Isi |
|---|---|
| [`docs/limitations.md`](docs/limitations.md) | 36 butir batasan & asumsi kepercayaan, lengkap |
| [`docs/evidence.md`](docs/evidence.md) | bukti on-chain lengkap, tabel tx, peta angka → sumber |
| [`docs/reproduce.md`](docs/reproduce.md) | perintah reproduksi, varian destruktif, troubleshooting |
| [`docs/design.md`](docs/design.md) | masalah → solusi, konsumen hari pertama, di luar spek ERC-8183 |
| [`docs/decisions.md`](docs/decisions.md) | ADR — bila spec dan ADR berbeda, ADR yang berlaku (ADR-025) |
| [`demo/video-script.md`](demo/video-script.md) | naskah video demo (dan `video-script.en.md`) |

## Lisensi

MIT — lihat [LICENSE](LICENSE).
