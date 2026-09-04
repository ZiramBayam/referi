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


## ADR-013 `challenge`/`resolve` distub agar pipa hidup tembus 5 Sep
Konteks: aturan potong (3) pada blok TARGET KERAS Fase 1 aktif 3 Sep 23:59 — bila `EvaluatorVault`
belum hijau, mekanisme sengketa jadi stub. Pada 3 Sep 23:35 task 1.2 belum mulai, jadi pemotongan
dipicu jam, bukan rapat. Sengketa tidak muncul sama sekali di naskah demo spec §7 langkah 1-5 dan
tidak dinilai rubric; yang dinilai adalah pipa hidup 1.3d.

Keputusan: `challenge(uint256,bytes32)` dan `resolve(uint256,bool)` TETAP ada di ABI sesuai spec §4,
dengan badan `revert NotImplemented()`. `resolve` MEMPERTAHANKAN `onlyArbiter`, dan cek peran itu
dijalankan SEBELUM revert stub sehingga permukaan otorisasinya sudah terkunci tes sejak sekarang dan
v2 tinggal mengisi badan. `finalize` tidak punya cabang "challenge terbuka"; field `challenger` tetap
ada di struct tetapi tidak dibaca. Ketiga perilaku ini dikunci tes revert.

Konsekuensi: klaim "sengketa berbond" WAJIB ditulis sebagai v2 di README (task 4.3b), BUKAN sebagai
fitur hidup — menyebutnya fitur akan jadi klaim palsu di depan juri. Mengaktifkan kembali menuntut ADR
baru, bukan tambal diam-diam. Bond evaluator lewat `deposit()` tetap nyata dan tetap dipertaruhkan
secara sosial, tetapi hari ini tidak ada jalur on-chain yang menyitanya.

## ADR-014 CHALLENGE_WINDOW 2 menit, `expiredAt` demo 1 jam, griefing `claimRefund` diterima sebagai risiko
Konteks: spec §4 memakai CHALLENGE_WINDOW 10 menit. `docs/api-facts.md` §A KOREKSI 2026-09-03 (fork
bytecode asli + bisection, dikuatkan source terverifikasi Sourcify): `claimRefund` sah dari
Open/Funded/Submitted oleh SIAPA PUN, dengan `EVALUATOR_GRACE_PERIOD = 900` detik sesudah `expiredAt`
untuk status Submitted; sesudah refund itu `complete`/`reject` oleh evaluator revert `WrongStatus()`.
Laporan api-verifier terdahulu ("claimRefund hanya dari Funded") SALAH dan sudah diadili. Jendela vault
kasus terburuk = 901 detik; `complete`/`reject` sendiri tidak punya guard expiry. Jendela 10 menit juga
membuat naskah §7 langkah 4 mustahil direkam dalam video submission 2-5 menit.

Keputusan: `CHALLENGE_WINDOW = 2 minutes` sebagai `constant` (TIDAK settable); `expiredAt` client
simulator = `now + 3600`; kontrak TIDAK diubah untuk melawan griefing karena izin `claimRefund` ada di
ACP, bukan di vault. Mitigasi: pra-baca `jobs(jobId).status` sebelum `postVerdict` dan sebelum
`finalize` di sisi agen, plus pengakuan tertulis di README.

Konsekuensi: anggaran deteksi + LLM + 2 tx dibatasi <= 514 detik dan diuji di task 2.4 (hitungan PM:
watcher 15 + konfirmasi 12 + LLM 120 + postVerdict 60 + challenge 120 + finalize 60 = ~387 detik,
margin ~514). `test_A3` WAJIB varian Submitted pada `expiredAt+900`. Konstanta 900 DILARANG di-hardcode
di kode agen — baca `EVALUATOR_GRACE_PERIOD()` on-chain. Verdict yatim mungkin terjadi dan dinyatakan
terbuka di README (task 4.3b). Angka ini tidak dijamin sama di Base mainnet; mainnet di luar PRD §5.


## ADR-015 Penjaga gas ABSOLUT sebelum `try`, dan kegagalan `finalize` tidak menggugurkan verdict
Konteks: `finalize` memakai `try/catch` atas `acp.complete/reject` (ADR-014/R1) supaya verdict tidak
terkunci selamanya saat job sudah Expired. Perlindungan pertama terhadap penyalahgunaan `catch` adalah
penjaga RASIO `gasleft() < gasBefore / 32`. Penjaga itu SALAH, dan salahnya hanya terlihat lewat
pengukuran. Sisa gas setelah OOG menumpuk per kedalaman panggilan (aturan 63/64 EIP-150 diterapkan
berulang): 15 permil di kedalaman 1, 30 permil di kedalaman 2, **46 permil di kedalaman 3**. ACP nyata
SELALU kedalaman >= 3 dari sudut vault — `vault -> proxy ERC-1967 (CALL) -> implementasi (DELEGATECALL)
-> paymentToken.safeTransfer (CALL)` — sehingga ambang 31,25 permil ditembus.

Akibatnya terbukti dua kali secara independen, dengan mock ACP di belakang `ERC1967Proxy`: sapuan 51
nilai gas pada 74.500-86.500 menggugurkan verdict SEHAT (security-reviewer: 25/51; solidity-engineer
memasang ulang penjaga lama dan mendapat 33/51 — parameter mock berbeda, kesimpulan sama). Efeknya:
provider dibayar NOL, job beku di `Submitted`, `postVerdict` ulang ditolak `VerdictAlreadyPosted`,
`finalize` ulang ditolak `AlreadyFinalized`. Tidak ada pemulihan. Itu persis pencurian-jasa yang
penjaga tersebut dimaksudkan mencegah. Kontrol: sapuan yang SAMA pada mock kedalaman-1 menggugurkan
NOL verdict — harness kedalaman-1 buta total terhadap kelas bug ini, dan itulah sebabnya mutan
`gasBefore/16` dan `gasBefore/64` sama-sama LOLOS 106 tes.

Akar yang sama membuat sinyal SEMENTARA menghasilkan kehilangan PERMANEN: `pause` ACP satu blok
(kontrak asli punya `whenNotPaused` pada `complete`/`reject`), hook ter-whitelist yang revert, atau
`Unauthorized` karena jobId salah — semuanya menutup verdict selamanya.

Keputusan:
1. Penjaga rasio DIHAPUS seluruhnya (`gasBefore` tidak lagi ada di kontrak).
2. `require(gasleft() >= MIN_ACP_GAS)` DI LUAR/SEBELUM `try`, sehingga OOG tidak mungkin terjadi.
3. `MIN_ACP_GAS = 300_000`, diturunkan dari PENGUKURAN, bukan dari margin karangan:
   `ceil25k( max(89_628 ; 92_578) x 3 ) = ceil25k(277_734) = 300_000`.
   - Sumber 1, tx `complete` NYATA on-chain Base Sepolia = **89.628 gas** (budget 2 USDC, 3 transfer
     ERC-20). Contoh: `0xa258c85c4cfb021fb0fea0f9538c6ccc05593ac64f44df1ccf16c313fcf3b849`. Pemindaian
     log penuh blok 42.500.000-46.343.804 hanya menemukan 6 `JobCompleted`; 4 di antaranya 89.628, satu
     55.231 (budget 0, tanpa transfer).
   - Sumber 2, mock salinan-setia DI BELAKANG `ERC1967Proxy`, diukur dari posisi vault dengan slot
     penerima dingin = **92.578 gas** (diukur ulang tiap run oleh `test_minAcpGas_isAtLeastThreeTimesMeasuredCost`).
   - Pembanding (bukan input rumus): bytecode ASLI di fork, budget 10 USDC = 76.480 gas.
   - Faktor 3 menutup aturan 63/64, cold slot, dan hook masa depan.
4. `catch` TIDAK lagi menggugurkan: `finalized` tetap `false`, `emit FinalizeFailed(uint256 indexed
   jobId)`, dan `finalize` boleh diulang siapa pun kapan pun. Event `VerdictVoided` DIHAPUS.
5. TIDAK ada `void(uint256)` dan tidak ada tenggat gugur (ditolak PM sebagai scope creep): membiarkan
   verdict hidup tidak menimbulkan deadlock, karena dananya ada di escrow ACP, bukan di vault.
6. `deposit()` menjadi `onlyAgent`. Ini MENYIMPANG dari `docs/spec.md` §4 yang menulisnya tanpa
   modifier; penyimpangan disengaja dan dicatat di natspec kontrak. Alasan: vault tidak punya jalur ETH
   keluar sama sekali selama ADR-013, dan reviewer membuktikan 5 ETH dari alamat acak terkunci permanen.

Angka yang DITOLAK, dicatat agar bisa ditinjau ulang: satu tx yang memuat `complete` memakai 192.163
gas, tetapi `to`-nya EntryPoint ERC-4337 (`0x0000000071727De2…7da032`) — angka itu mengukur bundler,
validasi smart account, dan paymaster, jalur yang tidak pernah dilewati vault karena vault memanggil
ACP LANGSUNG. Memasukkannya memberi `ceil25k(576_489) = 600_000`. Bila kelak vault dipanggil lewat
ERC-4337, tinjau ulang angka ini.

Konsekuensi:
(+) OOG mustahil; kegagalan sementara (pause, hook revert) pulih cukup dengan mengulang tx.
(+) Konsekuensi ambang yang meleset turun dari "provider dibayar nol permanen" menjadi "coba lagi" —
    ambang gas bukan lagi satu-satunya pertahanan.
(+) ETH nyasar dari pihak ketiga tertutup.
(-) `finalize` menuntut gas lebih besar dari pemanggil; WAJIB disebut di 1.3b/2.4.
(-) Verdict yatim (job sudah `claimRefund`) hidup selamanya tanpa penanda on-chain. Tidak ada dana
    terkunci di vault; mitigasi ada di sisi agen (pra-baca status, ADR-014) + pengakuan README 4.3b.
(-) `FinalizeFailed` BUKAN terminal: watcher 2.2 dan UI DILARANG memperlakukannya sebagai selesai, dan
    siapa pun bisa menyemprotnya pada job mati dengan biaya gasnya sendiri.
Mengaktifkan kembali penggugur eksplisit menuntut ADR baru dengan bukti deadlock konkret.


## ADR-016 Kunci deploy pindah dari `AGENT_PRIVATE_KEY` (.env) ke keystore terenkripsi Foundry
Konteks: `contracts/script/Deploy.s.sol` menyerahkan kunci sebagai ARGUMEN cheatcode — `vm.addr(pk)`
dan `vm.startBroadcast(pk)`. Foundry menyensor trace TEKS (`VM::addr(<pk>)`, `VM::envString(...) ->
<env var value>`) tetapi TIDAK menyensor `forge script --json`, yang mendump calldata mentah:
`"data":"0xffa18649<kunci>"` dan `"data":"0xce817d47<kunci>"` — kunci privat UTUH, 2x per run, di
stdout, pada jalur SUKSES, di verbositas DEFAULT. `--json` bukan flag eksotis: ia cara kanonik
mengambil alamat vault secara terprogram untuk mengisi `deployments/84532.json`.
@agent-security-reviewer membuktikan ini BUKAN batas Foundry: di sandbox, skrip dengan
`vm.startBroadcast()` TANPA argumen menghasilkan nol kemunculan kunci pada `--json`.
Belum ada kebocoran nyata: nol `--json` di Makefile/scripts/docs, artefak `broadcast/84532` bersih,
kunci asli tidak pernah tercetak. Rotasi kunci TIDAK diperlukan.

Opsi `--private-key <nilai>` di CLI DITOLAK: ia memindahkan kunci ke `argv` proses (terlihat lewat
`ps`) dan memaksa shell membaca `.env` yang justru diblokir `scripts/guard.sh` dengan sengaja —
menukar satu kebocoran dengan kebocoran lain.

Keputusan, dua tahap:
1. **Jangka pendek (task 1.3a, sekarang):** tutup KANAL dan MOTIF secara mekanis, tanpa menyentuh
   logika deploy — `make deploy` menolak `--json`, `scripts/guard.sh` memblokir `forge script --json`,
   alamat vault diambil dari `broadcast/.../run-latest.json` memakai `python3` (artefak itu sudah ada
   dan terbukti bersih), dan NatSpec dikoreksi karena sempat mengklaim kunci tidak pernah terekspos.
2. **Jangka menengah (task 1.2c, deploy berikutnya):** WAJIB keystore terenkripsi. `cast wallet import
   agent --interactive` sekali oleh user, `forge script --account agent --sender $AGENT_ADDRESS`,
   `vm.startBroadcast()` tanpa argumen, `deployer` dari `msg.sender`. Parser kunci
   (`_envPrivateKey`/`_parsePrivateKey`, ~120 baris + tesnya) DIHAPUS. `AGENT_PRIVATE_KEY` tetap di
   `.env` HANYA untuk `agent/vault_client.py` (web3.py), tidak lagi untuk deploy.

Konsekuensi:
(+) Kunci berhenti menjadi argumen cheatcode, sehingga seluruh kelas kanal ini tertutup di akarnya,
    bukan per-flag.
(+) Utang tes yang diketahui (mutan D1-D7: menghapus seluruh panggilan `_validate` dari `run()`, dan
    mengganti tiap `vm.envOr` dengan nilai default, SEMUANYA lolos 137/137 hari ini) diselesaikan
    sekali terhadap bentuk final, bukan dua kali.
(-) Satu aksi manual USER sebelum 1.2c — bukan sebelum 1.3d, jadi rantai pipa tidak tertahan.
(-) `.env.example`, README (4.3b), dan `Makefile` berubah.
Selama tahap 1 berlaku, `--json` DILARANG dipakai dengan skrip deploy, dan larangan itu ditegakkan
mesin (Makefile + guard), bukan sekadar komentar.

## ADR-017 Wallet client simulator terpisah dari wallet agen; `submit()` milik `sim/client_min.ts`
Tanggal: 2026-09-04. Status: diterima.

Konteks: task 1.3c/1.3d butuh EOA yang memegang token escrow
`0xECc22a8F6fD62388498fBa19813E214605a2BDb3`, sementara satu-satunya kunci privat yang dipegang
otomasi adalah `AGENT_PRIVATE_KEY` — yang juga `agent` DAN `arbiter` immutable di vault. Saldo token
alamat itu nol, dan task 0.4b (danai wallet client) blocked pada user sejak 3 Sep, sedangkan 1.3d
bertenggat keras 5 Sep. `mint(address,uint256)` pada token escrow terbukti TANPA kontrol akses
(api-facts §A, selector `0x40c10f19`) tetapi baru diuji di fork, belum lewat tx nyata.

Keputusan:
1. Buat `CLIENT_PRIVATE_KEY` baru. Kunci HANYA di `.env`; di `.env.example` ia baris KOSONG berkomentar.
   DILARANG dicetak, di-log, atau di-commit.
2. Danai wallet itu ETH secukupnya dari wallet agen, lalu 2 USDC lewat `mint` terbuka (task 0.4b-min).
   0.4b tetap milik user HANYA untuk top-up 100 USDC yang dibutuhkan skenario 3.1.
3. Client dan provider BOLEH satu EOA; evaluator TIDAK PERNAH. Yang harus independen adalah wasitnya,
   bukan client-vs-provider. Task 3.1 tetap wajib memisahkan tiga provider.
4. `submit(jobId, deliverable, optParams)` dieksekusi `sim/client_min.ts` di 1.3c, bukan 1.3d: tanpa
   status Submitted, `complete()` di 1.3d pasti revert `WrongStatus()` (api-facts §A).
5. Bila (1) gagal, fallback client == wallet agen HANYA dengan pengakuan tertulis di
   `deployments/pipeline-84532.md` dan README (4.3b), dan artefak fallback DILARANG masuk video.

Konsekuensi:
(+) Klaim "wasit pihak ketiga" (PRD §5, spec §7 langkah 5) bertahan di panel juri: client, provider,
    dan evaluator bukan satu alamat.
(+) 0.4b lepas dari jalur kritis Fase 1, sehingga tenggat 5 Sep tidak bergantung pada aksi user.
(-) Satu rahasia baru di `.env` yang tidak pernah boleh di-commit atau tercetak.
(-) Dua transaksi tambahan (danai ETH, mint) dan satu alamat lagi untuk dilacak di artefak demo.
(-) `arbiter() == agent()` tetap utang pengakuan terpisah (1.2c/4.3b); ADR ini tidak menutupnya.
