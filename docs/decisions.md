# ADR — Keputusan Desain (kenapa, bukan cuma apa)
Format: Konteks → Keputusan → Konsekuensi. Jangan buka ulang keputusan ini tanpa bukti baru; tambahkan ADR baru bila berubah.

## ADR-001 Gating memori lewat `reject()` saat Funded, bukan hook
Konteks: kontrak ACP Virtuals mewajibkan hook di-whitelist admin (`setHookWhitelist`). Kita tidak punya akses admin.
Keputusan: EvaluatorVault menyimpan `providerCap`; saat `JobFunded` dengan budget > cap, agen post verdict REJECT
(hak evaluator saat Funded menurut spek). `MemoryGateHook.sol` tetap ditulis sebagai bonus, di luar jalur kritis.
Konsekuensi: client mengalami satu refund + harus memecah job → tampilkan pesan yang jelas di UI dan di `reason`.

## ADR-002 Karantina sebagai entity `suspicion`, bukan tier
Konteks: Sibyl hanya punya HOT/WARM/COLD/REFERENCE/ARCHIVE. Konsekuensi: pengambil keputusan dilarang membaca `suspicion`;
promosi hanya bila ≥2 job berbeda dengan bukti deterministik. Ditegakkan di `memory_policy.py` + tes unit.

## ADR-003 Evaluator = kontrak (EvaluatorVault), bukan EOA
Konteks: spek tidak punya bond/challenge; spek mengizinkan evaluator berupa kontrak. Keputusan: vault memegang bond,
commit verdict, jendela challenge, lalu memanggil complete/reject. Konsekuensi: job harus dibuat dengan
`evaluatorAddress = VAULT`; agen tidak pernah memanggil ACP langsung.

## ADR-004 Fee evaluasi dibayar di muka via x402, `evaluatorFeeBP` diabaikan
Konteks: fee di kontrak hanya cair saat Completed → insentif meluluskan. Keputusan: `POST /jobs/register` di balik
middleware x402; bayaran sama untuk complete/reject. Konsekuensi: butuh facilitator x402 testnet; bila gagal, mode demo
menerima header dummy tapi UI tetap menunjukkan alur 402.

## ADR-005 Agen membaca event langsung dari chain, bukan dari API ACP
Konteks: belum terverifikasi apakah API ACP mengirim event ke evaluator yang tidak terdaftar di Service Registry.
Keputusan: web3.py `get_logs` polling pada kontrak ACP dengan filter `evaluator == VAULT`. API ACP hanya untuk mengambil
konten deliverable jika deliverable adalah referensi off-chain.

## ADR-006 Agen dalam Python, client simulator & web dalam TypeScript
Konteks: SDK Sibyl hanya Python; SDK ACP hanya TypeScript. Keputusan: batas jelas — Python = evaluator + memori + vault
client; TS = simulator client/provider (acp-node-v2) + web. Kontrak dipanggil dari Python via web3.py dengan ABI dari SDK.

## ADR-007 Fail-closed saat memori hilang tapi root onchain ada
Lihat `docs/spec.md` §3 aturan 5. Demo memakai skenario database bersih (root di-reset) agar degradasi terlihat.

## ADR-008 Tidak ada pembayaran parsial → milestone = job berantai
Konteks: ERC-8183 all-or-nothing. Keputusan: `derive_cap` memaksa job besar dipecah. Konsekuensi: UI harus punya
tombol "pecah jadi N job" di simulator client.

## ADR-011 Cek root di `finalize` memakai himpunan root yang pernah diumumkan, bukan `lastMemoryRoot`
Konteks: `docs/spec.md` §4 baris 134 membuat `postVerdict` meng-update root GLOBAL, dan baris 138 membuat
`finalize(jobId)` revert bila `verdict.memoryRoot != lastMemoryRoot`. Memori berubah tiap job (statistik provider,
event COLD), jadi root berubah tiap `postVerdict`. Dengan CHALLENGE_WINDOW 10 menit, verdict yang tumpang tindih
dijamin terjadi: postVerdict(A,R1) → postVerdict(B,R2) → `finalize(A)` revert SELAMANYA. Uang client terkunci di
escrow ACP sampai `expiredAt`, dan naskah demo §7 langkah 3 (client memecah jadi 3 job berantai) mustahil selesai.
Ditemukan @agent-hackathon-judge (F1, laporan fase-0) dan diverifikasi ulang di spec §4.

Keputusan: `postVerdict` mencatat `verdict.memoryRoot` per job DAN menandai `knownRoots[memoryRoot] = true`
(revert bila `memoryRoot == 0`). `finalize` mensyaratkan `knownRoots[v.memoryRoot] == true`, BUKAN kesamaan dengan
`lastMemoryRoot`. `lastMemoryRoot` tetap disimpan dan `MemoryRootUpdated` tetap di-emit untuk auditor/UI, tetapi
tidak lagi menjadi syarat eksekusi. Tidak ada fungsi penghapusan root (menghapus = mengembalikan deadlock).

Konsekuensi:
- (+) Verdict lama tetap bisa difinalisasi; §7 langkah 3 jalan; dana client tidak terkunci sampai `expiredAt`.
- (+) Properti audit yang sebenarnya ingin dijaga tetap utuh: setiap eksekusi ke ACP terikat pada root memori yang
  sudah diumumkan on-chain SEBELUM eksekusi, sehingga siapa pun bisa merekonstruksinya (task 2.1b).
- (−) Hilang: jaminan "verdict mencerminkan memori TERBARU". Jaminan itu memang tidak bisa ditegakkan on-chain
  tanpa menyerialkan job, dan menyerialkan job bertentangan langsung dengan §7 langkah 3. Diterima sadar.
- (−) Fail-closed sekarang murni dijaga di sisi agen (spec §3 aturan 5): dalam mode aman agen tidak memanggil
  `postVerdict`, jadi tidak ada root baru yang diumumkan dan tidak ada verdict baru yang bisa difinalisasi.
  Perilaku ini WAJIB ditunjukkan sebagai varian B tes destruktif (task 3.3b), bukan sekadar diklaim di README.
- (−) `knownRoots` menumpuk satu slot per root; biaya gas kecil dan dianggap wajar untuk hackathon.
- Menggantikan kalimat "revert jika `verdict.memoryRoot != lastMemoryRoot`" di `docs/spec.md` §4 baris 138;
  pembaruan baris itu adalah bagian dari AC task 0.8b. Ditegakkan oleh tes di task 1.2a.

## Amandemen ADR-007 (memperluas, tidak membalikkan)
Demo menjalankan DUA varian: (A) database bersih + root di-reset agar degradasi terlihat, dan (B) root onchain
dipertahankan + memori dihapus agar mode aman benar-benar dieksekusi. Menyebut mode aman hanya di README tidak
cukup — lihat task 3.3b. Dasar: temuan juri F4, naskah lama hanya menjalankan varian yang dijamin menang.
