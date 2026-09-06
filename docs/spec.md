# The Evaluator — Spesifikasi Build (v3, cocok dengan spek & SDK nyata)
Target: Sibyl Labs Hackathon (build 1–10 Sep 2026). Stack: Sibyl Memory + ERC-8183/ACP (Virtuals) + Base.
Disusun 24 Agu 2026 dari sumber primer: eips.ethereum.org/EIPS/eip-8183, repo Virtual-Protocol/acp-node-v2,
repo Sibyl-Labs/Sibyl-Memory, docs.sibyllabs.org/memory.

## 0. Pitch satu kalimat
Wasit escrow ERC-8183 yang ingatannya tentang tiap provider bisa diaudit siapa pun.

Versi 24 Agu menyambung kalimat itu dengan "— dan yang dibayar sama besar entah ia meluluskan atau menolak".
Frasa itu SALAH sebagai fakta dan sengaja TIDAK dihapus diam-diam, supaya ia tidak lahir kembali: ia adalah
RANCANGAN (ADR-004 — fee evaluasi dibayar di muka lewat x402), bukan perilaku sistem yang berjalan. Chain
membantahnya: `evaluatorFeeBP()` = 500 dan fee itu cair HANYA di jalur `complete`; saldo evaluator 50000
seluruhnya berasal dari job 417 yang DILULUSKAN, sementara rantai REJECT 418/419/420 membayar evaluator 0.
Baris di §1 pada file yang SAMA ("`evaluatorFeeBP` hanya dibayar saat Completed → insentif cacat") sudah
membantahnya sejak hari pertama. Frasa itu DILARANG dikutip sebagai fakta di `README.md`, `demo/`, dan
`docs/posts/*` (ADR-025 keputusan 3, yang TETAP berlaku).

## 1. Fakta terverifikasi yang mengikat desain

### ERC-8183 (Draft, 25 Feb 2026 — Crapis, Lim, Tay, Chooi)
- Status job: Open → Funded → Submitted → Completed | Rejected | Expired.
- Evaluator ditetapkan permanen di `createJob`, satu-satunya yang boleh `complete()`/`reject()` saat Submitted,
  dan BOLEH `reject()` saat Funded (sebelum provider submit).  ← dipakai untuk gating milestone.
- TIDAK ADA pembayaran parsial: Completed = 100% ke provider; Rejected/Expired = 100% refund ke client.
- TIDAK ADA bond/dispute/challenge/timeout evaluator. Spek: "use ERC-8004 reputation or staking for high-value jobs".
- `reason` = bytes32 (hash bukti off-chain), diemit di JobCompleted/JobRejected.
- Fee: `evaluatorFeeBP` hanya dibayar saat Completed → insentif cacat (wasit dibayar kalau meluluskan).
- Hook: `beforeAction/afterAction` dipanggil di setBudget/fund/submit/complete/reject; TIDAK di setProvider & claimRefund.
- Hook harus di-whitelist admin (`setHookWhitelist`, `whitelistedHooks`). Evaluator boleh berupa kontrak.

### Kontrak ACP Virtuals (implementasi ERC-8183 yang hidup)
- Base mainnet: 0x238E541BfefD82238730D00a2208E5497F1832E0
- Base Sepolia: 0x0b93793923CD5De81850aF8604a233f3f24d461e
- Token: USDC. API: https://api.acp.virtuals.io (prod), https://api-dev.acp.virtuals.io (testnet).
- ABI: createJob(provider, evaluator, expiredAt, description, hook) → jobId;
  setBudget(jobId, amount, optParams); fund(jobId, expectedBudget, optParams);   ← beda dari referensi (ada expectedBudget)
  submit(jobId, bytes32 deliverable, optParams); complete(jobId, bytes32 reason, optParams);
  reject(jobId, bytes32 reason, optParams); claimRefund(jobId); getJob(jobId); setProvider(jobId, provider).
- Sentinel "tanpa evaluator" = 0x000…000 (default SDK = skip evaluasi!).
- SDK: `npm i @virtuals-protocol/acp-node-v2` (peer: viem, @account-kit/infra).
  Evaluator: dengar event `job.submitted` → `session.complete(reason)` / `session.reject(reason)`.
  createJob(chainId, {providerAddress, evaluatorAddress, expiredAt, description, hookAddress?}).
  createJobFromOffering(chainId, offering, providerAddress, requirementData, {evaluatorAddress?, hookAddress?, packageId?}).
  MultiHookRouter memungkinkan >1 hook per selector — tapi tetap tunduk whitelist.

### Sibyl Memory
- `pip install sibyl-memory-client` (repo: Sibyl-Labs/Sibyl-Memory, MIT). Python ≥3.10. SQLite + FTS5, local-first,
  "free, unactivated use makes no network calls" → berjalan headless tanpa `sibyl init`.
- API: **jangan menyalin signature dari file ini.** Sumber tunggal = `docs/api-facts.md` §C (ditambah §C.1 untuk
  enumerasi REFERENCE lewat `search`, §C.2 untuk `Storage.transaction`, §C.3 untuk tier & cap), yang disalin dari
  `inspect.signature` pada paket TERPASANG, bukan dari README. Dua kesalahan versi 24 Agu yang pernah berdiri di
  sini, dicabut: parameter pertama entity bernama **`category`**, BUKAN `kind` (`kind=…` → `TypeError`); dan
  `search_entities` HANYA menjangkau tier WARM — pencarian yang mencakup keempat tier adalah
  `search(query, *, limit=20, prefix=False, tiers=None)` dengan tier sah `("entity","state","reference","journal")`.
- Tier resmi: HOT / WARM / COLD / REFERENCE / ARCHIVE. Tidak ada tier FLAGGED yang bisa dipakai: `schema.sql` 0.7.0
  MEMANG memuat tabel `flagged_actors`, tetapi `client.py`/`storage.py` nol kemunculan → tidak diekspos SDK
  (`docs/api-facts.md` §C). Karantina karena itu tetap konvensi: entity `category="suspicion"` (ADR-002).
- Rubric: memori load-bearing 40 | inovasi 25 | teknis 20 | pitch 15 | PMF +10. Multiplier ×1.15 (1 stack) / ×1.25 (Base+Virtuals),
  hanya jika juri konfirmasi integrasi "doing real work". Submission: repo publik MIT/Apache, video 2–5 mnt fresh-session recall,
  README, 2 post build-in-public.

## 2. Arsitektur v3

```
Client ──createJob(evaluator=VAULT)──► ACP (Base) ◄──submit── Provider
                                        │ events: JobFunded / JobSubmitted
                                        ▼
                               ┌─────────────────────┐
                               │ Evaluator Agent (py) │  runtime: Virtuals/ACP + Sibyl Memory
                               │  • watcher (viem/web3)│
                               │  • criteria builder   │
                               │  • checks (det + LLM) │
                               │  • memory policy      │
                               └──────────┬───────────┘
                                          │ postVerdict / postCap
                                          ▼
                               ┌─────────────────────┐
                               │ EvaluatorVault (sol) │  = alamat evaluator di tiap job
                               │  • bond              │
                               │  • commit verdict    │
                               │  • challenge window  │
                               │  • finalize → ACP    │
                               │  • MemoryRoot anchor │
                               └─────────────────────┘
```

### Kenapa tidak pakai hook (dan apa gantinya)
Hook kustom butuh whitelist admin Virtuals. Gantinya, gating memori dilakukan oleh evaluator lewat hak yang sudah
ada di spek: **reject saat Funded**.
- Vault menyimpan `providerCap[provider]` (USDC) yang diturunkan agen dari memori.
- Saat `JobFunded` masuk dan `budget > providerCap[provider]` → agen memanggil `postVerdict(jobId, REJECT, reasonHash)`
  dengan alasan "melebihi cap milestone provider ini (riwayat: N insiden)". Refund penuh; client memecah jadi job kecil.
- Jika Virtuals bersedia whitelist saat workshop 5–7 Sep, MemoryGateHook (beforeAction di `fund`) menjadi bonus:
  gating terjadi sebelum uang masuk. Kode hook disiapkan tapi bukan jalur kritis.

### Perbaikan insentif fee
`evaluatorFeeBP` dikendalikan Virtuals (bukan kita). Kita tidak bergantung padanya: client membayar jasa evaluasi
**di muka via x402** ke endpoint vault-agent saat mendaftarkan job. Bayaran identik untuk complete maupun reject.

## 3. Skema memori (pemetaan ke API Sibyl)

| Konsep | Tier | Panggilan | Isi |
|---|---|---|---|
| Job aktif | HOT | `set_state("job:{id}", {...})` | kriteria, deliverable hash, hasil cek sementara, mode pemeriksaan |
| Profil provider | WARM | `set_entity("provider", addr, {...})` | risk_level, cap_usdc, stats{jobs, pass, reject}, confirmed_patterns[], last_seen |
| Profil client | WARM | `set_entity("client", addr, {...})` | kualitas kriteria, riwayat sengketa yang ternyata salah |
| **Karantina** (pengganti FLAGGED) | WARM | `set_entity("suspicion", f"{addr}:{pattern}", {...})` | count, evidence[{job, check, proof}], status: pending |
| Verdict & cek | COLD | `write_event(acted=[...])` | tiap verdict, tiap cek deterministik, tiap promosi memori |
| Rubric per kategori | REFERENCE | `set_reference("rubric:{cat}", ...)` | kriteria template yang terbukti |
| Pola curang terkonfirmasi | REFERENCE | `set_reference("pattern:{id}", ...)` | deskripsi, detektor, contoh |
| Job final | ARCHIVE | `archive_entity("job", id)` | — |

Aturan yang membuat memori tidak bisa diracuni lewat input:
1. Entity `suspicion` TIDAK PERNAH dibaca oleh pengambil keputusan. Hanya `provider` + `reference:pattern`.
2. `suspicion` → promosi ke `provider.confirmed_patterns` + `reference:pattern` hanya jika `count ≥ 2` dari **job berbeda**
   dan setiap evidence berasal dari cek deterministik (bukan klaim pihak).
3. Semua tulisan memori berasal dari hasil cek agen sendiri; teks deliverable/pesan pihak = data, tidak pernah instruksi.
4. Fungsi `derive_cap(provider)`. Rumus 24 Agu ("risk 1 → median budget lolos; risk ≥2 → 25% median") DICABUT oleh
   **ADR-020** dan diperketat **ADR-021**: median-atas-budget menyerahkan cap ke tangan provider, yang mendanai job
   raksasa sendiri agar ditolak lalu melihat capnya naik. Yang BERLAKU sekarang — budget yang dikendalikan provider
   DILARANG masuk rumus dalam bentuk apa pun; hanya job `Completed` masuk `passed_budgets` dan kontribusinya
   diplafon `min(budget, BASELINE_CAP_USDC)` (ADR-021 kep. 1); `record_job_outcome` membuang budget bila
   `client == provider` (ADR-021 kep. 2) dan wajib idempoten per `job_id`; himpunan budget lolos kosong → cap dari
   KONSTANTA, bukan statistik: `BASELINE_CAP_USDC = 1_000_000` untuk risk 1 dan `BASELINE_CAP_USDC // 4` = 250.000
   untuk risk ≥2; cap monoton TIDAK-NAIK per provider; lantai `MIN_CAP_USDC = 250_000`; dan "blokir total" BUKAN
   keluaran sah `derive_cap` (penghentian hanya lewat mode aman, aturan 5). Sifatnya satu arah: memori hanya bisa
   MENGECILKAN cap, tidak pernah membesarkannya — jadi "provider membangun kepercayaan lewat riwayat baik"
   DILARANG diklaim. Cap juga bukan deteksi; ia hanya membatasi UKURAN kerugian per job (ADR-021 kep. 4).
5. **Fail-closed.** Perbandingan `memory_root` lokal dengan root di vault MATI sebagai pemicu: **ADR-023** keputusan 1
   mengeluarkan `lastMemoryRoot`/`knownRoots` dari jalur keputusan tx (root lokal selalu maju satu tulisan di depan
   root yang diumumkan, jadi perbandingan itu mem-brick agen sesudah job pertama). Pemicu mode aman adalah
   **memori lokal hilang atau tidak bisa dibaca**. Presedensi PERSIS-nya adalah **ADR-024 keputusan 2**, dievaluasi
   berurutan:
   1. kunci single-instance gagal, ATAU `load_snapshot`/`memory_root` melempar → **AMAN**;
   2. `memory.db` (atau `-wal`/`-shm`) hilang: `lastMemoryRoot() == 0` → **NAIF**, selain itu → **AMAN**;
   3. selebihnya → **NORMAL**, termasuk memori kosong dengan nol job outcome.
   `lastMemoryRoot()` dibaca HANYA di cabang 2, dan hanya untuk membedakan "hari pertama" dari "vault yang sudah
   hidup"; di cabang lain ia log/UI saja. Dalam mode aman agen menahan `postVerdict`, `finalize`, DAN
   `setProviderCap` (ADR-020 kep. 8): agen berhenti total, job menggantung sampai `expiredAt`, lalu siapa pun boleh
   `claimRefund` dan client menerima refund penuh — jalur pemulihannya adalah memulihkan `memory.db` dari backup.
   Yang HILANG dan wajib diucapkan apa adanya: deteksi "memori diganti DB LAIN" (ADR-023/ADR-024) tidak ada di v1.
   Mode aman tetap "tidak melakukan yang diklaim" (kalibrasi hilang) → tetap lolos gate destruktif juri.
6. Tanpa memori, lapis 1 (kriteria) dan lapis 2 (cek deterministik + rubric) tetap berjalan. Yang hilang hanya kalibrasi
   kedalaman cek, pola curang yang dipelajari, dan gating milestone. Kalimat pitch: *"hapus memori kami, dan kamu dapat
   evaluator stateless biasa — persis pesaing kami."*

Jangkar memori (**ADR-020** keputusan 6-7, menggantikan rumus 24 Agu `keccak(sorted(provider entities) ||
sorted(reference patterns))`): `memory_root` menjangkar PERSIS himpunan yang boleh dibaca pengambil keputusan,
yaitu ketiga prefiks — semua entity `provider`, semua `reference:pattern:*`, dan semua `reference:rubric:*` —
**termasuk pattern yatim** yang tidak dirujuk provider mana pun, BUKAN irisan yang dirujuk. Aturan itu otomatis
mengecualikan `suspicion` (ADR-002) dan membuat keadaan "saya membacanya tapi tidak menjangkarnya" mustahil.
Encoding preimage WAJIB kanonik sebelum root boleh diumumkan on-chain: dihitung dari body MENTAH yang tersimpan
(bukan proyeksi lossy), tiap int di-encode sebagai string desimal, dan kunci entity dengan pemisah yang tidak bisa
ditabrak — sehingga siapa pun bisa merekonstruksi root, di TypeScript maupun Python, dari file memori yang
dipublikasikan/diaudit. Dikirim ke vault tiap `postVerdict`.

## 4. EvaluatorVault.sol (ekstensi di luar spek — kontribusi orisinal)

```solidity
// pragma ^0.8.28 ; evaluator = address(this) di tiap job
struct Verdict { uint8 kind; /*1=complete,2=reject*/ bytes32 reasonHash; bytes32 memoryRoot; uint64 readyAt; bool finalized; address challenger; }
function deposit() external payable;                                   // bond evaluator
function setProviderCap(address provider, uint256 capUsdc) external onlyAgent;
function postVerdict(uint256 jobId, uint8 kind, bytes32 reasonHash, bytes32 memoryRoot) external onlyAgent;
        // readyAt = now + CHALLENGE_WINDOW; emit VerdictPosted; emit MemoryRootUpdated(memoryRoot)
        // ADR-011: TAMBAH knownRoots[memoryRoot] = true; revert bila memoryRoot == 0
function challenge(uint256 jobId, bytes32 counterEvidenceHash) external payable;   // bond penantang; hanya sebelum readyAt
function resolve(uint256 jobId, bool evaluatorWasRight) external onlyArbiter;      // MVP: arbiter = multisig/juri; v2: ERC-8004 validation
function finalize(uint256 jobId) external;   // siapa pun, setelah readyAt & tanpa challenge terbuka;
        // ADR-011 MENGGANTI syarat "verdict.memoryRoot != lastMemoryRoot" (yang mengunci verdict tumpang tindih
        // SELAMANYA): syaratnya knownRoots[v.memoryRoot] == true — root yang PERNAH diumumkan, bukan yang TERAKHIR.
        // Varian lastMemoryRoot-sebagai-syarat DILARANG. lastMemoryRoot tetap disimpan & di-emit untuk auditor/UI saja;
        // fail-closed dijaga di sisi agen (§3 aturan 5): dalam mode aman tidak ada verdict yang di-post sama sekali.
        // kind==1 → acp.complete(jobId, reasonHash, "") ; kind==2 → acp.reject(jobId, reasonHash, "")
function providerCap(address) external view returns (uint256);
```
Catatan: `finalize` mengeksekusi `complete/reject` atas nama vault (msg.sender = vault = evaluator job). Pastikan job
dibuat dengan `evaluatorAddress = vault` (jangan biarkan default SDK = sentinel 0x0 = skip evaluasi).
CHALLENGE_WINDOW: 10 menit untuk demo, konfigurable.

## 5. Alur event (agen)
1. `watch JobCreated where evaluator == VAULT` → `set_state("job:{id}")`, bangun kriteria dari `description`
   (+ pesan requirement via ACP API), simpan `criteriaHash`.
2. `watch JobFunded` → baca `provider` entity → `derive_cap`; jika budget > cap → `postVerdict(REJECT)` (gating milestone).
   Jika lolos → tentukan `mode` (sampling / penuh / penuh+milestone) dan simpan di HOT.
3. `watch JobSubmitted(deliverable)` → ambil konten deliverable (ACP API / IPFS) → jalankan cek deterministik
   (angka vs chain, link hidup, format, sandbox kode) + rubric LLM → skor per-kriteria + bukti.
4. Bundel bukti {criteria, checks, scores, memory_root, mode} → IPFS → `reasonHash = keccak(bundle)`.
5. `postVerdict(jobId, kind, reasonHash, memory_root)` → tulis memori: event ke COLD; pola gagal deterministik →
   `suspicion` (atau promosi); update `provider`; `archive_entity("job", id)` setelah finalize.
6. Setelah window: `finalize(jobId)` (dipanggil agen atau siapa pun) → ACP `complete/reject`.
7. Notifikasi kedua pihak (ACP `session.sendMessage` atau Ping onchain Sibyl — opsional).

## 6. Struktur repo
```
evaluator/
  contracts/         EvaluatorVault.sol, MemoryGateHook.sol (opsional), script/Deploy.s.sol, test/
  agent/             python: watcher.py, criteria.py, checks/{chain,links,format,sandbox}.py, judge_llm.py,
                     memory_policy.py (skema §3, derive_cap, promosi), vault_client.py, x402_server.py, main.py
  sim/               provider_honest.py, provider_neat_but_wrong.py, provider_half_done.py, client_demo.ts (acp-node-v2)
  web/               Next.js: timeline job, verdict+bukti, panel "coba jadi provider" untuk juri, tombol "hapus memori"
  demo/              skenario.md, video-script.md
  README.md          arsitektur, tes destruktif, pemetaan tier, kontribusi di luar spek (vault, fee, karantina)
```

## 7. Naskah demo (2–5 menit, sesuai rubric)
1. Job 1 (Alpha, rapi tapi angka supply salah) → cek deterministik gagal → REJECT, refund penuh. `suspicion` count=1.
2. Job 2 (Alpha, pola sama, job berbeda) → count=2 → promosi ke `reference:pattern` + `provider.confirmed_patterns`;
   risk=2 → `setProviderCap(Alpha, kecil)`; `MemoryRootUpdated` tampil di Base explorer.
3. **Proses dimatikan, sesi baru.** Client fund job 3 dengan Alpha, budget besar → agen membaca memori →
   REJECT saat Funded: "melebihi cap milestone; 2 insiden terkonfirmasi" → client memecah jadi 3 job kecil → lolos bertahap.
4. **Tes destruktif:** hapus `memory.db` (skenario database bersih, root onchain di-reset untuk demo) → job 3 diulang →
   tidak ada cap (job besar diterima), mode sampling. Deliverable Alpha dibuat dengan **cacat halus di bagian yang tidak
   tersampling** — yang di langkah 2 tertangkap karena Alpha masuk mode penuh — kini LOLOS. Cacat kasar tetap ditolak;
   tunjukkan itu juga sekilas agar juri melihat memori mengubah *kalibrasi*, bukan menggantikan seluruh evaluator.
   Sebut di README: di produksi, memori hilang saat root onchain ada → mode aman (§3 aturan 5), bukan degradasi.
5. Panel juri: unggah deliverable sendiri (cacat halus) → verdict + bukti per-kriteria + hash di explorer.

## 8. Yang masih harus diverifikasi saat build (tidak memblokir desain)
- Apakah API ACP mensyaratkan evaluator terdaftar di Service Registry untuk menerima event via SDK
  (fallback: baca event langsung dari chain — sudah jadi default desain).
- Faucet USDC Base Sepolia + apakah kontrak Sepolia ACP mengizinkan evaluator berupa kontrak (spek: ya).
- Definisi "integrasi Virtuals terverifikasi" untuk multiplier: memakai kontrak ACP + SDK Virtuals seharusnya memenuhi;
  konfirmasi di workshop 5–7 Sep. Tanyakan sekalian whitelist hook.
- `fund()` di ACP butuh `expectedBudget` (beda dari referensi) — pakai ABI dari `src/core/acpAbi.ts`, bukan dari EIP.
