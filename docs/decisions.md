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

## ADR-010 Middleware 402 buatan sendiri; paket x402 resmi ADA tetapi sengaja TIDAK dipakai
Tanggal: 2026-09-06. Status: diterima. Mengunci lingkup task 2.6 dan mempersempit ADR-004 (tidak membalikkannya).
Pemicu: task 0.8 (timebox 60 menit) — "identifikasi paket x402 resmi ATAU tulis ADR-010".

Konteks — apa yang benar-benar dilihat hari ini (bukan ingatan):
(a) Paket resminya **ADA**, jadi ADR ini TIDAK boleh dibaca sebagai "tidak ada paket x402".
    - PyPI `x402` **2.22.0** (`curl -s https://pypi.org/pypi/x402/json`): author "x402 Foundation",
      Homepage `https://github.com/x402-foundation/x402`, lisensi MIT, `requires_python >=3.10`
      (classifier Python 3.13 ADA), rilis wheel 2026-09-04 — dua hari sebelum ADR ini.
      Classifier kematangannya: **"Development Status :: 3 - Alpha"**.
    - npm `x402` **1.2.0** dan npm `@coinbase/x402` **2.1.0** (`registry.npmjs.org/<pkg>/latest`).
(b) Middleware-nya HANYA untuk FastAPI dan Flask. Isi wheel `x402-2.22.0-py3-none-any.whl`
    (`x402/http/middleware/`) memuat TEPAT dua adapter framework — `fastapi.py` dan `flask.py`:
    - `x402.http.middleware.fastapi.payment_middleware(routes: RoutesConfig, server: x402ResourceServer,
      paywall_config: PaywallConfig | None = None, paywall_provider: PaywallProvider | None = None,
      sync_facilitator_on_start: bool = True)`
    - `x402.http.middleware.flask.payment_middleware(app: Flask, routes: RoutesConfig,
      server: x402ResourceServerSync, paywall_config=None, paywall_provider=None,
      sync_facilitator_on_start=True)`
    Extra-nya: `x402[fastapi]` → `fastapi[standard]>=0.115.0` + `starlette>=0.27.0`; `x402[flask]` → `flask>=3.0.0`.
    `grep -niE "fastapi|flask|starlette|uvicorn" docs/versions.md` → **NOL baris**. Jadi jalur resmi menuntut
    minimal DUA dependensi baru (x402 + satu framework web) di H-4 submission.
(c) Fasilitator default `https://x402.org/facilitator` (`x402/http/constants.py:16`) memang mendukung jaringan kita:
    `GET https://x402.org/facilitator/supported` → memuat `{"x402Version":2,"scheme":"exact","network":"eip155:84532"}`.
(d) **Tetapi skema `exact` EVM-nya berjalan di atas EIP-3009 `transferWithAuthorization`, dan token escrow kita
    tidak punya fungsi itu.** Aset default x402 untuk `eip155:84532` adalah USDC Circle
    `0x036CbD53842c5426634e7929541eC2318f3dCF7e` (`x402/mechanisms/evm/default_assets.py:39`), sedangkan
    token yang benar-benar dipakai ACP adalah `0xECc22a8F6fD62388498fBa19813E214605a2BDb3`
    (`paymentToken()`, `docs/versions.md`). Dibuktikan atas bytecode terdeploy token itu
    (`cast code 0xECc22a8F6fD62388498fBa19813E214605a2BDb3 --rpc-url https://sepolia.base.org`):
    selector `0xe3ee160e` (`transferWithAuthorization(...)`) → **0 kemunculan**; `0x3644e515` (`DOMAIN_SEPARATOR()`)
    → **0**; kontrol positif `0xa9059cbb` (`transfer(address,uint256)`) → **1**.
(e) Konsekuensi (d) yang menentukan jadwal: memakai x402 resmi berarti fee evaluasi dibayar dalam token yang
    BERBEDA dari token escrow, yaitu USDC Circle — persis token yang task **0.4b** buktikan terkunci di
    faucet ber-captcha dan sejak 4 Sep sengaja dikeluarkan dari jalur kritis. Jalur resmi menarik kembali satu
    blocker manusia yang sudah kita hindari.
(f) PRD §5 nomor 5 berbunyi "Endpoint x402 (fee evaluasi di muka) — **minimal: middleware 402 di endpoint
    `POST /jobs/register`**", dan TASKS.md baris 23 sudah menempatkan 2.6 sebagai kandidat potong nomor 2.

Keputusan:
1. Paket x402 resmi (PyPI `x402` 2.22.0, npm `x402`/`@coinbase/x402`) **TIDAK dipasang** dan **TIDAK ditambahkan**
   sebagai dependensi. `docs/versions.md` mencatatnya sebagai fakta terverifikasi + status TIDAK DIPAKAI, bukan
   sebagai pin. Memasangnya butuh ADR baru yang membalikkan ADR ini.
2. Task 2.6 dikerjakan sebagai **middleware 402 buatan sendiri** memakai pustaka standar Python + dependensi yang
   SUDAH dipin (`docs/versions.md`): `http.server` untuk servernya, `web3` 7.16.0 untuk verifikasi on-chain.
   Nol dependensi baru → tidak butuh ADR tambahan.
3. Bentuk kabelnya, dan ia mengikat 2.6:
   (i)  Tanpa pembayaran sah → **HTTP 402** + header `WWW-Authenticate` berisi skema dan parameternya
        (`realm`, `network=eip155:84532`, `asset=<alamat token escrow>`, `payTo`, `amount` dalam unit terkecil,
        `nonce`), plus badan JSON yang mengulang parameter yang sama agar terbaca manusia di demo.
   (ii) Klien membayar on-chain lalu mengulang permintaan dengan header `Authorization` yang membawa hash tx.
   (iii) Verifikasi = **membaca chain**, bukan mempercayai header: receipt `status == 1`, ada log `Transfer` pada
        alamat token escrow, `to == payTo`, `value >= amount`, dan hash tx BELUM pernah dipakai (penjaga replay
        milik kita sendiri — di jalur resmi ini tugas fasilitator).
   (iv) Nama skema di `WWW-Authenticate` **DILARANG** berupa `x402` atau turunannya, supaya klien x402 sungguhan
        tidak pernah menyangka endpoint ini bicara protokol x402.
   (v)  `DEMO_MODE` boleh menerima header dummy, tetapi respons 200-nya WAJIB menandai dirinya sebagai mode demo.
4. **Larangan klaim** (sejalan ADR-025 keputusan 3): `README.md`, naskah video, dan `docs/posts/*` DILARANG menulis
   bahwa proyek ini "mengimplementasikan x402" atau "kompatibel x402". Yang boleh: "middleware 402 buatan sendiri
   (ADR-010) — bukan protokol x402; paket resminya ada dan sengaja tidak dipakai, alasannya di ADR-010".
5. ADR ini dibuka ulang hanya bila: token escrow ACP berganti ke aset yang didukung fasilitator x402, ATAU
   ada waktu di luar jendela submission untuk memikul framework web + fasilitator.

Konsekuensi:
(+) 2.6 bisa selesai dengan nol dependensi baru, nol faucet manusia, dan nol layanan pihak ketiga di jalur demo.
(+) PRD §5 nomor 5 terpenuhi apa adanya: ia meminta "middleware 402", dan itulah yang mendarat.
(+) Verifikasinya justru lebih dekat ke tema proyek: bukti pembayaran dibaca dari chain oleh `web3.py`, sama
    seperti seluruh jalur verdict kita — bukan dari respons layanan yang harus dipercaya.
(-) **Interoperabilitas HILANG, dan ini kerugian yang sesungguhnya.** Klien x402 nyata mengirim otorisasi EIP-3009
    yang ditandatangani di header `X-PAYMENT`/`payment-signature` (`x402/http/constants.py:8`,
    `x402/http/middleware/fastapi.py:249`). Endpoint kita tidak akan memahaminya, dan tantangan 402 kita bukan
    tantangan berformat x402. Nol klien x402 di dunia bisa membayar endpoint ini tanpa kode khusus.
(-) Dompet, faucet, paywall UI, dan penemuan (bazaar) milik ekosistem x402 tidak berlaku untuk kita.
(-) Pembayaran kita TIDAK gasless: klien membayar gasnya sendiri, sedangkan fasilitator x402 menyelesaikan
    transfer atas nama klien. Untuk demo satu klien simulator, ini tidak terasa; untuk klien sungguhan, terasa.
(-) Penjaga replay, kedaluwarsa nonce, dan pembukuan pembayaran jadi kode kita sendiri — permukaan bug baru yang
    di jalur resmi sudah matang. Karena itu 2.6 wajib punya tes untuk tx yang dipakai dua kali.
(-) Kita kehilangan hak mengucapkan "x402 beneran" di materi juri. Keputusan 4 membuat kehilangan itu eksplisit
    alih-alih membiarkannya menjadi klaim yang nanti dicabut — pola yang sudah terjadi sekali (ADR-025).

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

KOREKSI 4 Sep: versi pertama ADR ini menyatakan "client dan provider boleh satu EOA". Itu SALAH dan
terbukti mustahil di kontrak (`ClientIsProvider()` `0x332ff0f9`, api-facts §A:276-279); poin 3-5 di
bawah menggantikannya.

Keputusan:
1. Buat `CLIENT_PRIVATE_KEY` baru. Kunci HANYA di `.env`; di `.env.example` ia baris KOSONG berkomentar.
   DILARANG dicetak, di-log, atau di-commit.
2. Danai wallet itu ETH secukupnya dari wallet agen, lalu 2 USDC lewat `mint` terbuka (task 0.4b-min).
   0.4b tetap milik user HANYA untuk top-up 100 USDC yang dibutuhkan skenario 3.1.
3. TIGA EOA terpisah WAJIB, bukan pilihan gaya: api-facts §A:276-279 (fork 2026-09-03) membuktikan
   `createJob` merevert `ClientIsProvider()` `0x332ff0f9` bila `msg.sender == provider`, dan
   `EvaluatorIsProvider()` `0xc7b4e9eb` bila `evaluator != 0 && evaluator == provider`; guard yang sama
   ada di `setProvider`. Karena `setBudget` dan `submit` juga provider-only (§A:207-210), provider WAJIB
   memegang kunci privat + ETH gas sendiri. Peran: CLIENT `0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2`
   (pemegang token escrow), PROVIDER = `PROVIDER_PRIVATE_KEY` baru (ETH saja, tanpa token), EVALUATOR =
   alamat VAULT `0x5c6EE4586ACABcb6326069c229E58091B21ef384` yang digerakkan wallet agen
   `0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894`. Wallet agen DILARANG jadi provider walau kontrak
   mengizinkannya (evaluator on-chain adalah vault, bukan EOA agen): pada `complete` ia akan menerima
   payout provider sementara vault menerima `evaluatorFeeBP` 500 dan `arbiter()` masih mungkin == `agent()`.
4. `submit(jobId, deliverable, optParams)` dieksekusi `sim/client_min.ts` memakai `PROVIDER_PRIVATE_KEY`
   di 1.3c, dalam run yang sama dengan createJob/setBudget/fund — bukan 1.3d: tanpa status Submitted,
   `complete()` di 1.3d pasti revert `WrongStatus()` (api-facts §A).
5. Fallback "satu EOA merangkap" TIDAK TERSEDIA untuk pasangan client/provider — kontrak yang menolaknya,
   bukan keputusan produk. Fallback hanya berlaku untuk hal lain yang tidak diblokir kontrak, dan tetap
   menuntut pengakuan tertulis di `deployments/pipeline-84532.md` + README (4.3b).

Konsekuensi:
(+) Klaim "wasit pihak ketiga" (PRD §5, spec §7 langkah 5) bertahan di panel juri: client, provider,
    dan evaluator bukan satu alamat.
(+) 0.4b lepas dari jalur kritis Fase 1, sehingga tenggat 5 Sep tidak bergantung pada aksi user.
(-) Satu rahasia baru di `.env` yang tidak pernah boleh di-commit atau tercetak.
(-) Dua transaksi tambahan (danai ETH, mint) dan satu alamat lagi untuk dilacak di artefak demo.
(-) `arbiter() == agent()` tetap utang pengakuan terpisah (1.2c/4.3b); ADR ini tidak menutupnya.

## ADR-018 Redeploy vault: arbiter terpisah, 50.000 token vault v1 dilepas sadar, dan jalur mundur
Tanggal: 2026-09-04. Status: diterima.

Konteks: vault immutable, jadi redeploy = alamat baru. Vault v1
`0x5c6EE4586ACABcb6326069c229E58091B21ef384` MEMEGANG 50.000 token escrow hasil job 417
(evaluatorFee 5% dari budget 1.000.000) dan tidak akan pernah punya `sweepToken` — dibuktikan
langsung: `cast call` ke selector `sweepToken(address,address)` di v1 → `execution reverted`.
`deployments/pipeline-84532.md` adalah bahan video/README dan menunjuk v1. ADR-016 tahap 2
memindahkan kunci keluar dari jalur DEPLOY saja; `AGENT_PRIVATE_KEY` tetap di `.env` untuk
`agent/vault_client.py`, jadi ini pengurangan permukaan, BUKAN penghapusan kunci dari repo —
README wajib mengklaim persis itu, tidak lebih.

Keputusan:
1. Redeploy dilakukan SEBELUM perekaman demo §7, karena biaya membatalkan artefak naik monoton
   terhadap waktu: hari ini satu file, pekan depan video + README + artefak demo.
2. 50.000 token di v1 DILEPAS. Tanpa upaya pemulihan, tanpa proxy/upgradeable (PRD §5 "tidak
   dikerjakan"). Nilainya 0,05 USDC testnet. Dicatat terbuka di `deployments/pipeline-84532.md`
   dan README, bukan disembunyikan.
3. `arbiter` diisi EOA BARU `0xC9CF30c8aB471fD22536B955b5CFb79D26672cF1`, dan
   `ALLOW_ARBITER_EQ_AGENT` WAJIB kosong. Alasannya berubah sejak `sweepToken` ada: sebelumnya
   arbiter tidak punya wewenang on-chain apa pun (`resolve` stub, ADR-013) sehingga
   `arbiter == agent` tidak berbahaya; sekarang arbiter adalah pemegang TUNGGAL seluruh saldo
   ERC-20 vault, tanpa timelock, two-step, maupun allowlist penerima (temuan SEDANG
   @agent-security-reviewer).
4. Pipa 1.3d DIPUTAR ULANG di dalam task `1.2c-deploy`, bukan dengan membuka ulang 1.3d. 1.3d
   tetap `[x]` sebagai bukti pipa hidup PERTAMA; yang diganti hanya artefak yang menunjuk alamat.
   Aturannya: siapa yang membuat alamat baru, dia yang membereskan seluruh jejak alamat lama —
   dalam satu task, supaya tidak pernah ada jendela di mana artefak juri menunjuk kontrak yang
   bukan kontrak submission.
5. Timebox internal 6 Sep 18:00 (angka internal, BUKAN tenggat hackathon). Lewat itu berlaku
   JALUR MUNDUR: redeploy dibatalkan, vault v1 dipertahankan untuk submission, `sweepToken`
   mendarat sebagai kode + tes saja, dan README (4.3b) menyatakan eksplisit "kontrak yang
   terdeploy belum punya `sweepToken`".

Konsekuensi:
(+) Kontrak submission punya jalan keluar dana, dan kunci deploy bukan lagi argumen cheatcode.
(+) Satu alamat vault konsisten di seluruh artefak juri.
(+) Peran terpisah penuh: client, provider, agent, arbiter adalah empat EOA berbeda.
(-) 0,05 USDC testnet hangus permanen dan WAJIB disebut di README — juri yang bertanya harus
    mendapat jawaban yang sudah siap, bukan improvisasi.
(-) Alamat vault muncul di `sim/`, `agent/`, `deployments/`, `docs/`; AC (h) task 1.2c-deploy
    (`grep` alamat lama nol hit di jalur eksekusi) adalah satu-satunya penjaga mekanisnya.
(-) Bergantung pada satu aksi user yang tidak bisa diotomasi (`cast wallet import`).

## ADR-019 Sumber teks deliverable, dan `derive_cap` saat himpunan "budget lolos" kosong
Tanggal: 2026-09-04. Status: diterima. Pemicu: gerbang fase 1 (T8/T1) + lubang spec yang ditemukan
product-manager saat menyusun rantai 2.5.

Konteks:
(a) `session.submit()` SDK memanggil `api.postDeliverable` ke API off-chain Virtuals, dan API itu
    menolak wallet simulator kita — `POST https://api.acp.virtuals.io/auth/agent` → 404
    `Agent not found with wallet address 0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2` (terbukti
    4 Sep). Jadi on-chain HANYA ada `keccak256` deliverable, bukan teksnya. Tanpa teks, task 2.3
    (checks deterministik) tidak punya input, dan tanpa 2.3 gate rubric 40 poin tidak bisa dijawab.
(b) spec §3 aturan 4 mendefinisikan cap untuk risk >= 1 sebagai fungsi "median budget LOLOS". Pada
    provider yang seluruh jobnya DITOLAK — persis skenario §7 langkah 1-2 — himpunan itu KOSONG dan
    `derive_cap` tidak terdefinisi. Rantai §7 langkah 3 akan berhenti di sana.

Keputusan:
1. `sim/` MENULIS teks deliverable ke `demo/deliverables/<jobId>.json` berisi
   `{"jobId", "text", "sha_keccak"}`, dan `deliverable` yang dikirim on-chain adalah
   `keccak256` dari byte UTF-8 field `text` yang PERSIS sama.
2. `agent/` membaca teks HANYA dari direktori itu (`DELIVERABLE_DIR`, default `demo/deliverables`)
   dan WAJIB memverifikasi ulang bahwa `keccak256(text)` sama dengan nilai deliverable on-chain
   sebelum menilai. Tidak cocok / file hilang → REFUSE: nol `postVerdict`, nol `finalize`, cetak
   `DELIVERABLE TIDAK TERVERIFIKASI`. Perlakuannya sekelas mode aman (task 2.4a).
3. Teks deliverable dan input panel juri §7 langkah 5 adalah DATA, TIDAK PERNAH instruksi
   (spec §3 aturan 3).
4. `derive_cap`: bila himpunan budget LOLOS kosong, median diambil dari budget SELURUH job yang
   pernah diamati untuk provider itu; risk 1 → median itu, risk >= 2 → 25% dari median itu. Cap
   DILARANG nol — nol berarti menolak segalanya, yaitu blacklist yang tidak ada di spec (dan di
   kontrak, cap 0 justru berarti TANPA BATAS, ADR-001).

Konsekuensi:
(+) 2.3 punya input; §7 langkah 1/4/5 bisa dieksekusi.
(+) Artefak lokal TERIKAT ke chain: juri bisa mengambil `demo/deliverables/<jobId>.json`, meng-keccak
    sendiri, dan mencocokkannya dengan `getJob`. Properti audit yang sama dengan klaim memori, gratis.
(+) §7 langkah 3 ("client memecah jadi job kecil → lolos bertahap") jadi mungkin, karena cap non-nol.
(-) Sumber teks BUKAN API ACP resmi. WAJIB dinyatakan di README sebagai batasan beserta alasan 404
    yang terukur — bukan didiamkan.
(-) Cap turunan "seluruh job yang diamati" lebih longgar dari niat spec §3 aturan 4. Diterima sadar
    untuk hackathon; pembaruan baris spec-nya masuk AC task 0.8b.

## ADR-020 Cap tidak boleh diturunkan dari budget yang dikendalikan provider; root menjangkar seluruh memori yang dibaca
Tanggal: 2026-09-05. Status: diterima. Menggantikan ADR-019 keputusan 4 (cabang "median-all-observed").
Pemicu: @agent-security-reviewer memblokir task 2.1 dengan 2 KRITIS + 4 TINGGI; dua di antaranya
menyentuh ADR-019 dan definisi root, jadi keduanya butuh putusan produk, bukan tambalan engineer.

Konteks:
(a) ADR-019 keputusan 4 memberi cap dari median SELURUH budget yang pernah diamati saat himpunan budget
    LOLOS kosong. `record_job_outcome` memasukkan budget job yang DITOLAK ke himpunan itu, sehingga tiap
    penolakan MENAIKKAN cap yang menyebabkan penolakan itu. Reviewer mengeksekusi rantainya:
    cap 500.000 -> 750.000 -> 12.750.000 -> 24.750.000, tiga ronde, dan job 20 JUTA akhirnya LOLOS.
    Biaya penyerang NOL: `reject` mengembalikan 100% budget ke client dan fee evaluator 0 (api-facts §A),
    dan token escrow Base Sepolia punya `mint()` tanpa kontrol akses (ADR-017, 0.4b-min). Provider
    mendanai job raksasa sendiri, ditolak, uangnya utuh, capnya naik 50x. Ini membatalkan spec §7
    langkah 3 justru pada provider paling jahat — satu-satunya artefak yang menjawab gate rubric 40 poin.
(b) `MIN_CAP_USDC = 1` (1 unit = 0,000001 USDC) aman hasilnya tetapi menyamarkan "blokir segalanya"
    sebagai angka. Spec §3 tidak punya blacklist dan ADR-019 melarang cap nol.
(c) Root saat ini TIDAK mengikat isi memori: field asing di body tidak mengubah root; dua entity provider
    berbeda bisa runtuh jadi satu kunci sehingga satu entity hilang dari audit tanpa mengubah root; dan
    preimage-nya memakai int presisi-arbitrer Python sehingga TIDAK bisa direkonstruksi di TS/JS
    (budget > 2^53 pecah diam-diam) — padahal 2.1b dan `web/` justru alat audit publiknya. Juri fase-1
    sudah menghancurkan klaim root sekali dengan satu `cast keccak`.
(d) Mode aman (spec §3 aturan 5) menahan `finalize`; ADR-011 membuat `finalize` bergantung `knownRoots`
    dan `postVerdict`-lah yang mendaftarkan root. Mengumumkan root dari memori rusak = persis yang
    ADR-011 klaim dicegah.

Keputusan:
1. Cabang "median-all-observed" (ADR-019 keputusan 4) DICABUT. Budget yang dikendalikan provider DILARANG
   masuk rumus cap dalam bentuk apa pun. `all_budgets` sebagai input `derive_cap` DIHAPUS, bukan disaring.
2. `record_job_outcome` hanya memasukkan budget ke `passed_budgets` bila job berakhir Completed. Job
   Rejected/Expired hanya menaikkan `stats.reject`. Fungsi itu WAJIB idempoten per `job_id`.
3. Himpunan budget LOLOS kosong -> cap dari KONSTANTA, bukan statistik:
   `BASELINE_CAP_USDC = 1_000_000` (1 USDC, 6 desimal); risk 1 -> `BASELINE_CAP_USDC`;
   risk >= 2 -> `BASELINE_CAP_USDC // 4` = 250.000. Angka dipilih agar §7 langkah 3 muat di 2 USDC yang
   sudah dimiliki wallet client (0.4b-min): job C 2 USDC > cap 0,25 USDC -> REJECT; pecahan 0,2 USDC lolos.
   Jadi 0.4b (top-up 100 USDC) TETAP di luar jalur kritis.
4. `derive_cap` monoton TIDAK-NAIK per provider: `cap = min(kandidat, provider.cap_usdc sebelumnya)` bila
   field itu sudah ada. Pertahanan berlapis; §7 tidak pernah menuntut cap naik.
5. "Blokir total" BUKAN keluaran sah `derive_cap`. Tidak ada `CapDecision.block`, tidak ada cap 0
   (di kontrak cap 0 justru berarti TANPA BATAS, ADR-001). `MIN_CAP_USDC = 1` diganti lantai bermakna
   `MIN_CAP_USDC = 250_000` (0,25 USDC). Jalur "agen berhenti total" hanya ada satu dan sudah benar:
   mode aman (task 2.4a) yang menahan transaksi, bukan cap yang menyamar jadi angka.
6. Encoding `memory_root` BELUM DIBEKUKAN. Ia baru boleh dibekukan (dan baru boleh dipakai di jalur
   produksi `postVerdict`) setelah: preimage dihitung dari body MENTAH yang tersimpan (bukan proyeksi
   lossy), setiap int di-encode sebagai string desimal, dan kunci entity di-encode dengan pemisah yang
   tidak bisa ditabrak (panjang-berprefiks atau escaping), sehingga dua kunci berbeda mustahil runtuh
   jadi satu. Sampai itu mendarat, DILARANG ada root turunan-memori yang diumumkan on-chain.
7. Cakupan root: `memory_root` menjangkar SELURUH memori yang BOLEH dibaca pengambil keputusan — semua
   entity `provider`, semua `reference:pattern:*`, dan semua `reference:rubric:*` — termasuk pattern
   YATIM yang tidak dirujuk provider mana pun. BUKAN irisan yang dirujuk. Aturannya satu kalimat:
   root menjangkar persis himpunan yang boleh dibaca pengambil keputusan. Itu otomatis mengecualikan
   `suspicion` (ADR-002) dan membuat keadaan "saya membacanya tapi tidak menjangkarnya" mustahil.
8. Mode aman menahan `postVerdict` DAN `finalize` DAN `setProviderCap`. Konsekuensinya dinyatakan apa
   adanya: agen berhenti total, job MENGGANTUNG sampai `expiredAt`, lalu siapa pun boleh `claimRefund`
   (ADR-014) dan client menerima refund penuh. Itu perilaku yang diinginkan, bukan kegagalan yang
   disembunyikan, dan WAJIB diucapkan begitu di §7 langkah 4 varian B, di 3.3b, dan di README 4.3c.

Konsekuensi:
(+) Cap berhenti menjadi permukaan serang: satu-satunya masukan yang tersisa adalah hasil cek deterministik
    agen sendiri (spec §3 aturan 3) dan konstanta.
(+) §7 langkah 3 tetap bisa dieksekusi pada provider yang SEMUA jobnya ditolak — masalah yang melahirkan
    ADR-019 keputusan 4 tetap tertutup, tanpa memberi provider kendali atas capnya.
(+) Klaim "siapa pun bisa merekonstruksi root" (spec §3 baris 124) menjadi benar di TS maupun Python.
(+) Penghapusan pattern yatim tidak bisa lolos audit tanpa mengubah root.
(-) Cap awal kini angka pilihan tim, bukan turunan data; WAJIB disebut di README sebagai parameter, bukan
    disamarkan sebagai hasil pembelajaran. Kalibrasi dari riwayat baru hidup setelah ada job LOLOS.
(-) Monoton-tidak-naik berarti provider yang membaik tidak pernah memulihkan capnya dalam satu garis
    memori. Diterima sadar untuk hackathon; pemulihan reputasi adalah v2 dan DILARANG diklaim hidup.
(-) 2.1b dan 2.4b diblokir sampai 2.1r (encoding kanonik) hijau. Urutannya tidak boleh dibalik.
(-) Spec §3 baris 113 (rumus `derive_cap`) dan baris 123 (definisi root) berubah; pembaruannya masuk AC
    task 0.8b. Baris 123 WAJIB menyebut ketiga prefiks dan kata "termasuk pattern yatim".

## ADR-021 Plafon pertumbuhan cap per job, dan penolakan budget saat client == provider
Tanggal: 2026-09-05. Status: diterima. Memperketat ADR-020 keputusan 1-3 (tidak membalikkannya).
Pemicu: review ulang @agent-security-reviewer atas task 2.1 sesudah ADR-020 mendarat.

Konteks: ADR-020 keputusan 1 melarang budget yang dikendalikan provider masuk rumus cap, tetapi
`passed_budgets` — satu-satunya sumber median yang tersisa — MASIH dikendalikan provider. Sebabnya
struktural, bukan bug: tidak ada apa pun di ERC-8183/ACP yang mengikat client != provider secara
ekonomis (yang ada hanya `ClientIsProvider()` yang melarang ALAMAT yang sama, api-facts §A:276-279),
dan token escrow Base Sepolia punya `mint()` tanpa kontrol akses (ADR-017, dibuktikan 0.4b-min).
Reviewer menjalankan rantainya: provider mendanai jobnya sendiri lewat EOA kedua sebesar 100 USDC
dengan deliverable sepele yang LOLOS empat cek deterministik; risk masih 0 sehingga tidak ada cap
tersimpan dan monoton ADR-020 keputusan 4 tidak punya jangkar; sesudah insiden pertama pada client
SUNGGUHAN, risk 1 memberi cap = median-passed = 100.000.000, dan job 20 USDC LOLOS padahal cap yang
benar 1.000.000. Ini kegagalan §7 langkah 3 yang SAMA dengan ADR-020, lewat pintu berbeda.

Keputusan:
1. PLAFON PERTUMBUHAN: kontribusi tiap job LOLOS ke perhitungan median dibatasi
   `min(budget, BASELINE_CAP_USDC)`. Konsekuensinya matematis dan disengaja — cap turunan riwayat
   TIDAK PERNAH melampaui `BASELINE_CAP_USDC` (1 USDC), dan untuk risk >= 2 tidak pernah melampaui
   250.000. Riwayat baik tidak bisa MENAIKKAN cap; ia hanya bisa gagal menurunkannya.
2. `record_job_outcome` menerima `client` sebagai ARGUMEN dan MENOLAK merekam budget bila
   `client == provider` (kesamaan alamat PERSIS, case-insensitive/checksum-normalized). Filter ini
   ada di titik MASUK, bukan di state: tidak ada field baru di body provider, sehingga preimage
   `memory_root` (ADR-020 keputusan 6-7, task 2.1r) TIDAK berubah dan tidak perlu diputar ulang.
   Job seperti itu tetap menaikkan `stats.jobs`; hanya budgetnya yang dibuang.
3. Definisi "sekerabat" BERHENTI di kesamaan alamat persis. Analisis Sybil (alamat yang saling
   mendanai gas, umur wallet, pendanaan bersama) DITOLAK sebagai scope creep: ACP sudah memaksa
   penyerang memakai EOA kedua (`ClientIsProvider()`), jadi deteksi EOA kedua adalah masalah Sybil
   terbuka yang tidak akan selesai sebelum 10 Sep. Kita memagarinya dengan keputusan 1, bukan
   berpura-pura menyelesaikannya.
4. Cap BUKAN pertahanan tunggal terhadap provider curang; ia hanya membatasi UKURAN kerugian per job.
   Pertahanan terhadap deliverable curang tetap cek deterministik (task 2.3) dan mode aman (2.4a).
   Kalimat ini WAJIB ada di README agar tidak ada yang mengira cap adalah deteksi.

Konsekuensi:
(+) Rantai eksploit reviewer mati di dua tempat sekaligus, dan keduanya diuji dengan angka.
(+) Sifat sistem menjadi satu arah dan bisa diucapkan dalam satu kalimat: memori hanya bisa
    MENGECILKAN cap, tidak pernah membesarkannya. Klaim itu tidak bisa dipatahkan dengan `cast`.
(+) Nol perubahan pada encoding root; 2.1r dan 2.1b tidak terganggu; mendarat hari ini.
(-) "Provider membangun kepercayaan lewat riwayat baik" DILARANG diklaim di README, video, dan post.
    Yang boleh diklaim: kalibrasi memori mengetatkan cap dan memperdalam cek, tidak pernah melonggarkan.
(-) Provider jujur berbudget besar akan terkena cap 1 USDC begitu ia menyentuh risk >= 1. Diterima
    sadar: pemulihan reputasi dan cap yang tumbuh adalah v2 (sejalan ADR-020 konsekuensi ke-2).
(-) Median-passed kini hampir selalu tersaturasi di plafon, sehingga cap praktis berperilaku seperti
    konstanta berjenjang risiko. Itu tidak apa-apa untuk hackathon dan HARUS ditulis apa adanya —
    jangan sajikan sebagai statistik yang seolah belajar.

## ADR-022 Vault v1 dibekukan sebagai kontrak submission; otonomi diturunkan jadi invokasi per-job
Tanggal: 2026-09-05. Status: diterima. Menggantikan ADR-018 keputusan 1 dan 5 (timebox 6 Sep 18:00).

Konteks: ambang keras "7 Sep 23:59 tx `JobRejected` belum ada → Fase 3 dihentikan". Rantai tersisa
2.4a-inti → 2.3-min → 2.4-min → 2.5 memproduksi artefak yang TERIKAT ALAMAT VAULT (`JobRejected`,
`providerCap`, `knownRoots`, `MemoryRootUpdated`). Redeploy sesudah artefak itu lahir memaksa 2.5
diputar ulang, dan 2.5 adalah satu-satunya task yang menentukan skor. Argumen ADR-018 keputusan 1
("biaya membatalkan artefak naik monoton terhadap waktu") karena itu MEMBALIK arahnya: produksi
artefak dimulai hari ini, jadi titik termurah membekukan alamat adalah SEKARANG, bukan 6 Sep 18:00.
Selain itu 1.2c-deploy BLOCKED pada satu aksi user yang tidak bisa diotomasi, dan 1.2e menyatakan
sendiri nilainya nol setelah vault beku.

Keputusan:
1. Vault v1 `0x5c6EE4586ACABcb6326069c229E58091B21ef384` adalah kontrak submission. Redeploy
   DIBATALKAN; `sweepToken` mendarat sebagai kode + tes saja (1.2c-kode, sudah `[x]`).
2. 1.2e DICABUT; validasi "job ini milik kita" hanya off-chain di `vault_client` (task 2.4-min).
3. Watcher (2.2) diturunkan dari jalur kritis; agen dipanggil per job. `client_address` dan cek
   `getJob(jobId).evaluator == VAULT` PINDAH ke 2.4-min supaya ADR-021 keputusan 2 tidak mati diam-diam.
4. Review wajib kembali ke CLAUDE.md apa adanya: `contracts/` + `agent/memory_policy.py`.

Konsekuensi:
(+) Nol kemungkinan 2.5 diputar ulang; alamat vault konsisten di seluruh artefak juri sejak sekarang.
(+) Dua task blocked (1.2c-deploy, 1.2e) keluar dari jalur menuju tx; tidak ada lagi aksi user yang
    memblokir skor.
(-) Kontrak terdeploy TIDAK punya `sweepToken`; 0,05 USDC testnet di v1 hangus permanen (ADR-018 kep. 2).
(-) `arbiter()` == `agent()` pada v1 apa adanya — README 4.3b/4.3c WAJIB menempel keluaran keduanya.
(-) Klaim "agen otonom" DILARANG muncul di README/video/post; ganti "agen dipanggil per job".

## ADR-023 Mode aman dipicu asal-usul memori lokal, bukan perbandingan root
Tanggal: 2026-09-05. Status: diterima. Memperbaiki penerapan spec §3 aturan 5; TIDAK membalikkan
ADR-011/ADR-022. Pemicu: temuan KRITIS @agent-security-reviewer atas task 2.4a-inti.

Konteks: gerbang 2.4a membandingkan `memory_root` lokal dengan `lastMemoryRoot()`. Dua kegagalan.
(1) Warisan: vault submission yang dibekukan ADR-022 menyimpan
    `lastMemoryRoot` = `keccak("the-evaluator/live/memory-root/v1")` — konstanta pipa 1.3d job 417,
    tidak bisa diturunkan dari `memory.db` mana pun, dan `postVerdict` adalah satu-satunya penulisnya
    → mode aman PERMANEN. Dibuktikan live: `cast call <vault> "lastMemoryRoot()(bytes32)"` →
    `0x1fa62c3db5c16f4c831ee1d9ee4c083745b8c8bae86bda3587b8b02ba52f7bf0`.
(2) Desain: spec §5 langkah 5 menulis memori SESUDAH `postVerdict`, jadi root lokal selalu satu
    langkah di depan. Bahkan pada vault BARU agen berhenti sesudah job pertama; rantai tiga job
    §7 langkah 3 mustahil. Dibuktikan: `decide_mode(0,R1)=naive` → `record_job_outcome` →
    `decide_mode(R1,R2)=safe`.
Gerbang ini bertentangan dengan ADR-011 dan `EvaluatorVault.sol:300` yang menyatakan `lastMemoryRoot`
BUKAN syarat eksekusi.

Keputusan:
1. `lastMemoryRoot` dan `knownRoots` KELUAR dari jalur keputusan tx. `lastMemoryRoot()` tetap dibaca
   dan dicetak sebagai konteks log/UI saja.
2. Aturan 5 dibaca: mode aman bila memori lokal tidak bisa membuktikan ASAL-USULNYA, yaitu
   (a) `memory.db` hilang, atau `load_snapshot`/`memory_root` melempar, atau kunci single-instance
   tidak didapat; atau (b) DB ada tetapi NOL job outcome SEMENTARA `lastMemoryRoot() != 0`.
   Selain itu mode normal. Root onchain nol → naif (tidak berubah).
   Usul `knownRoots(rootLokal)` DITOLAK: root lokal selalu maju satu tulisan di depan yang
   diumumkan, jadi ia tetap self-brick sesudah job A.
3. `decide_mode` tetap fungsi murni yang mengembalikan NILAI; penegakan tetap hanya di `_send()`.
4. Root bukan-turunan-memori yang permanen di vault dicatat apa adanya: 1.3d
   `keccak("the-evaluator/live/memory-root/v1")` dan `SELFTEST_MEMORY_ROOT`. Tidak ada upaya
   membersihkannya, dan sesudah keputusan 1 keduanya tidak bisa melemahkan apa pun.
5. Penguatan berbasis `knownRoots(root-lampau)` butuh log root lokal yang belum ada → v2, di luar
   scope 10 Sep.

Konsekuensi:
(+) §7 langkah 2/3/5 dan task 2.5 kembali mungkin; 3.3b varian A punya kontrol "agen bekerja".
(+) Ancaman asli (memori hilang/diganti) tetap fail-closed dan tetap bisa dipentaskan.
(-) HILANG: deteksi "memori lokal diganti memori LAIN yang tidak kosong". Diterima sadar; tidak
    terdeteksi on-chain tanpa log root lokal (v2). WAJIB disebut di README §Batasan.
(-) 3.3b varian A dijalankan di Anvil lokal (vault segar, root nol → naif → degradasi terlihat);
    varian B di vault Sepolia beku (DB dihapus, root non-nol → mode aman). Amandemen ADR-007 tetap
    berlaku, hanya lokasinya kini ditetapkan.

## ADR-024 Aturan (b) dicabut; pemicu mode aman = memori lokal tidak terbaca
Tanggal: 2026-09-05. Status: diterima. Mencabut ADR-023 keputusan 2 huruf (b); menegakkan ADR-023
keputusan 1. Pemicu: BLOKIR @agent-security-reviewer atas 2.4a-fix.

Konteks: ADR-023 aturan (b) ("DB ada tapi NOL job outcome SEMENTARA `lastMemoryRoot() != 0` → AMAN")
memindahkan self-brick, tidak membunuhnya. Pada vault submission beku ADR-022,
`lastMemoryRoot` = `keccak("the-evaluator/live/memory-root/v1")` = `0x1fa62c3d…` permanen non-nol dan
tidak bisa dinolkan (`postVerdict` satu-satunya penulis), jadi (b) SELALU aktif. Job A adalah job
pertama → `job_outcomes = 0` saat `postVerdict`-nya → ditahan → outcome pertama tidak pernah lahir.
Dieksekusi pada DB bersih: rantai 2.5 menghasilkan `tx = []`. Kontrol: DB sama + satu outcome
karangan → `tx = ['postVerdict']`.
Dua cacat tambahan: (i) (b) membaca `lastMemoryRoot` di cabang keputusan tx, yang justru dilarang
ADR-023 keputusan 1 — ADR-023 kontradiktif dengan dirinya sendiri; (ii) (b) dipenuhi oleh DB 3 baris
buatan tangan, jadi ia menegakkan "DB tidak kosong", bukan "memori bisa membuktikan asal-usulnya";
terhadap penyerang yang bisa menulis `memory.db` nilainya NOL, sementara biayanya seluruh §7.

Keputusan:
1. Aturan (b) DICABUT. Tidak ada penggantinya di v1.
2. `decide_mode` final, urutan presedensi TEPAT ini:
   (1) kunci single-instance gagal, ATAU `load_snapshot`/`memory_root` melempar → AMAN;
   (2) `memory.db` (atau `-wal`/`-shm`) hilang: `lastMemoryRoot() == 0` → NAIF; selain itu → AMAN;
   (3) selebihnya → NORMAL, termasuk memori kosong nol job outcome.
   `lastMemoryRoot()` dibaca HANYA di cabang (2) dan hanya untuk membedakan "hari pertama" dari
   "vault yang sudah hidup"; di semua cabang lain ia log/UI saja (ADR-023 keputusan 1).
3. Bootstrap job A TIDAK punya jalur khusus: memori kosong = mode normal tanpa kalibrasi, yang
   perilakunya sama dengan evaluator stateless (spec §3 aturan 6). DITOLAK: pengecualian "postVerdict
   pertama", entity `origin`, dan langkah seeding di `make demo` — dua yang pertama melubangi aturan
   atau mati bersama `rm -rf data/`, yang ketiga menulis outcome yang tidak lahir dari verdict.
4. `proves_origin` DIGANTI NAMA jadi `local_memory_readable`. Nama/docstring yang mengklaim
   pembuktian asal-usul DILARANG sampai ada log root lokal (v2).
5. Residu `agent/data/memory.db` (provider fiktif `0xa1a1…`, `incident_jobs=(11,12)`, tidak pernah
   lewat `record_job_outcome`) DILARANG jadi alas rantai 2.5. Rantai A/B/C dijalankan pada DB yang
   TERBUKTI kosong; kekosongan dibuktikan dengan `agent/memory_export.py` sebelum job A.

Konsekuensi:
(+) Rantai 2.5 dan §7 langkah 1-3/5 mungkin pada vault beku; gate destruktif §7 langkah 4 tetap utuh
    lewat aturan (a) di kedua varian 3.3b.
(+) Satu-satunya pembacaan chain yang tersisa di jalur keputusan hanya bisa melonggarkan pada vault
    yang belum pernah mem-post verdict — pada vault itu tidak ada memori untuk dilewati.
(-) HILANG: deteksi "`memory.db` diganti DB LAIN", baik kosong maupun terisi. Diperluas dari ADR-023
    konsekuensi ke-3. WAJIB disebut di README §Batasan dengan kalimat ini apa adanya.
(-) `rm -rf agent/data` pada vault beku tetap = mode aman permanen sampai memori dipulihkan dari
    backup. Itu perilaku yang DIINGINKAN (3.3b varian B), jadi baris keluarannya WAJIB menyebut jalur
    pemulihan, bukan hanya akibatnya.

## ADR-025 `docs/spec.md` v3 berstatus historis; ADR menang atas spec
Tanggal: 2026-09-06. Status: diterima. Pengganti task 0.8b selama larangan `loop.md` poin 5 berlaku.
TIDAK membalikkan ADR mana pun; ia hanya menyatakan presedensi dan mendaftar divergensi yang sudah terbukti.

Konteks: task 0.8b memerintahkan menyunting `docs/spec.md` agar cocok dengan ADR + `docs/api-facts.md`.
`loop.md` poin 5 — aturan yang ditulis USER — melarangnya apa adanya ("Jangan ubah docs/spec.md atau
PRD.md"). @agent-product-manager (6 Sep) memutuskan larangan MENANG: `TASKS.md` dan `CLAUDE.md`
sama-sama ditulis loop, jadi keduanya tidak bisa memberi izin yang sudah dicabut user. 0.8b karena itu
`[!]` BLOCKED PADA USER. Akibatnya `docs/spec.md` v3 (24 Agu) kini memuat kalimat yang sudah DIBANTAH
oleh chain dan DICABUT oleh ADR, tetapi tetap dibaca sebagai dokumen desain — dan sekali sudah terbukti
kalimat itu menular ke artefak juri (lihat butir (i)). ADR ini menutup lubang itu di file yang TIDAK
dilarang, tanpa menyentuh spec.

Keputusan:
1. `docs/spec.md` DIBEKUKAN sebagai **dokumen historis**: catatan niat desain 24 Agu, BUKAN sumber
   kebenaran. Bila spec dan ADR berbeda, **ADR yang berlaku**. Untuk API eksternal, `docs/api-facts.md`
   tetap satu-satunya sumber (CLAUDE.md), dan spec tidak pernah mengalahkannya.
2. Tabel divergensi di bawah adalah daftar yang MENGIKAT. Setiap ADR baru yang mencabut kalimat spec
   WAJIB menambahkan barisnya di sini dalam ADR yang sama — kalau tidak, pencabutannya tidak berlaku
   terhadap pembaca spec.
3. Kalimat §0 baris 7-8 ("dibayar sama besar entah ia meluluskan atau menolak") **DILARANG DIKUTIP**
   sebagai fakta di `README.md`, `demo/video-script.md`, dan `docs/posts/*` (mengikat task 4.3).
   Yang boleh: menyebutnya sebagai RANCANGAN (ADR-004, fee di muka lewat x402) beserta angka chain yang
   membantahnya. **§7 (naskah demo) TIDAK terpengaruh** dan tetap sumber naskah.
4. Bila USER mencabut larangan (task 0.8f), 0.8b dijalankan dengan AC lamanya dan ADR-025 disusutkan
   menjadi catatan sejarah — bukan dihapus, karena ia merekam kenapa spec sempat divergen.

Tabel divergensi yang DIKETAHUI (tiap baris diverifikasi ulang @agent-api-verifier 2026-09-06):

| # | Baris spec | Kalimat spec | Yang BERLAKU | Bukti / pencabut |
|---|---|---|---|---|
| (i)   | §0 baris 7-8 | "…dan yang **dibayar sama besar entah ia meluluskan atau menolak**" | Wasit dibayar HANYA saat `Completed`; pada REJECT ia dibayar 0. Fee sama-besar adalah rancangan (ADR-004), bukan fitur. | Dibantah oleh **§1 baris 19 di file yang SAMA** ("`evaluatorFeeBP` hanya dibayar saat Completed → insentif cacat") DAN oleh chain (di bawah). §0 berjudul "Pitch satu kalimat" — aspirasi, bukan catatan fakta. |
| (ii)  | §3 baris 116 | "root onchain ada tapi memori lokal **hilang/tidak cocok** → mode aman" | Pemicu mode aman = **memori lokal tidak terbaca**, BUKAN perbandingan root. Presedensi PERSIS ada di **ADR-024 keputusan 2**: (1) kunci single-instance gagal ATAU `load_snapshot`/`memory_root` melempar → AMAN; (2) `memory.db`/`-wal`/`-shm` hilang: `lastMemoryRoot() == 0` → NAIF, selain itu → AMAN; (3) selebihnya → NORMAL, termasuk memori kosong nol job outcome. | ADR-023 (mencabut perbandingan root; `lastMemoryRoot`/`knownRoots` KELUAR dari jalur keputusan tx) + ADR-024 (mencabut aturan (b) ADR-023; `proves_origin` → `local_memory_readable`). Frasa "tidak cocok" tidak punya penegak mana pun hari ini. |
| (iii) | §4 baris 138 (dan baris 134 yang memberinya konteks) | "revert jika `verdict.memoryRoot != lastMemoryRoot`" | **ADR-011**: `postVerdict` menandai `knownRoots[memoryRoot] = true` (revert bila `memoryRoot == 0`); `finalize` mensyaratkan `knownRoots[v.memoryRoot] == true`. Varian **`lastMemoryRoot`-sebagai-syarat DILARANG** — ia mengunci verdict yang tumpang tindih selamanya. `lastMemoryRoot` tetap disimpan & di-emit untuk auditor/UI saja. | ADR-011 (temuan @agent-hackathon-judge F1) + ADR-023 keputusan 1. Baris §4 ini harus dibaca menurut ADR-011, bukan apa adanya. |
| (iv)  | §2 baris 46 & 50 | `m.set_entity(kind, name, body)` ; `m.search_entities(query)  # FTS5 lintas tier` | Parameter pertama bernama **`category`** (`kind=…` → `TypeError`). `search_entities(query, *, limit=20, prefix=False, category=None)` **hanya tier WARM**; lintas tier adalah **`search(query, *, limit=20, prefix=False, tiers=None)`** dengan tier sah `("entity","state","reference","journal")`. | `docs/api-facts.md` §C:523, §C:545, §C:549 dan §C.1. Diverifikasi ulang 2026-09-06 dengan `inspect.signature` pada paket TERPASANG di `agent/.venv` (`sibyl-memory-client` 0.7.0). §2 baris 52 ("TIDAK ADA tier FLAGGED") tetap **BENAR**: `schema.sql` 0.7.0 memuat tabel `flagged_actors`, tetapi `client.py`/`storage.py` nol kemunculan → tidak diekspos SDK; karantina tetap entity `category="suspicion"` (ADR-002). |

Bukti chain untuk baris (i), diukur ulang 2026-09-06 (`cast call … --rpc-url https://sepolia.base.org`):
- `evaluatorFeeBP()` pada ACP `0x0b93793923CD5De81850aF8604a233f3f24d461e` → **500** (5%), dan fee itu
  cair HANYA di jalur `complete`; `reject` mengembalikan 100% budget ke client dengan fee evaluator 0
  (`docs/api-facts.md` §A).
- `balanceOf(vault)` pada token escrow `0xECc22a8F6fD62388498fBa19813E214605a2BDb3` → **50000**, yaitu
  PERSIS 500 bp dari budget `1000000` job **417** yang berstatus **3 = Completed** — satu-satunya job
  yang DILULUSKAN. Rantai demo A/B/C = job **418/419/420**, ketiganya berstatus **4 = Rejected**, dan
  tidak menambah saldo itu satu unit pun → evaluator dibayar **0** untuk seluruh rantai REJECT.
- 50000 itu hangus permanen: selector `sweepToken(address,address)` `0x258836fe` **nol kemunculan** di
  `cast code 0x5c6EE4586ACABcb6326069c229E58091B21ef384` (kontrol positif: `lastMemoryRoot()` `0xdf103897`
  → 1 kemunculan), dan `cast call` ke selector itu → `execution reverted`. Sejalan ADR-018 kep. 2 + ADR-022.
- **Bukan risiko teoretis:** kalimat §0 itu pernah menjadi kalimat PEMBUKA `README.md` lengkap dengan
  sitasi "(`docs/spec.md` §0)" — commit `e029faa`, dikoreksi baru di commit `54c6573`. Dicatat sebagai
  kejutan terberat S1 (`docs/judge-reports/BLOCKED.md`).

Konsekuensi:
(+) Pembaca spec punya satu tempat untuk mengetahui baris mana yang sudah mati, tanpa menyentuh file
    yang dilarang user. 0.8b tidak lagi memblokir apa pun.
(+) Larangan kutip (keputusan 3) membuat regresi README/video/post terdeteksi lewat `grep`, bukan lewat
    juri. Ini pertahanan yang sama untuk kelas kesalahan yang SUDAH terjadi sekali.
(-) Divergensi kini hidup di DUA file: pembaca yang hanya membuka `docs/spec.md` masih bisa tersesat.
    Itu harga yang dibayar untuk menghormati aturan user, dan hanya hilang bila 0.8f dijawab.
(-) Tabel ini bisa basi diam-diam bila ADR baru lupa menambah barisnya. Keputusan 2 adalah satu-satunya
    penjaganya, dan penjaga itu manusia/agen — bukan mesin.
(-) §7 sengaja dikecualikan, jadi naskah demo tetap dibaca dari file yang dinyatakan historis. Diterima
    sadar: tidak ada satu pun divergensi terbukti di §7 hari ini; begitu ada, ia masuk tabel di atas.

## ADR-026 Mode NAIF dibiarkan tak terjangkau dari `--job-id`; hari pertama butuh dua invokasi
Tanggal: 2026-09-06. Status: diterima. TIDAK membalikkan ADR-024 (cabang NAIF tetap ada dan tetap
load-bearing); ia hanya menyatakan JANGKAUAN cabang itu apa adanya dan memilih untuk tidak menutup
selisihnya. Pemicu: temuan @agent-agent-engineer saat menjalankan task 2.5 AC (e), diangkat jadi task 2.5a.

Konteks — yang diukur hari ini, bukan diingat (harness RPC palsu `agent/tests/test_verdict_pipeline.py`,
vault segar `lastMemoryRoot() == 0`, `memory.db` belum ada, job Submitted yang deliverablenya LOLOS cek):
(a) Gerbang saat start membaca `naive` (ADR-024 keputusan 2 cabang 2) dan run diteruskan — benar.
(b) `plan_job` (`agent/agent/vault_client.py`) membuka `MemoryClient.local(str(client.db_path))` untuk
    membangun `DecisionMemoryView`, dan panggilan itu **MEMBUAT** filenya. Sifat ini bukan baru: AC task
    3.3b sudah memuat peringatan "URUTAN WAJIB … `MemoryClient.local(path)` MEMBUAT file".
(c) `run_live` membaca ULANG gerbang sebelum tx (memang wajib, ADR-023/2.4a-fix), kini melihat file itu
    ADA → mode `normal`, sementara `plan.mode` masih `naive` → penjaga MODE_DRIFT menolak.
    Hasil terukur invokasi PERTAMA: `EXIT_REFUSED` (4), `sent_transactions == []`, nonce tidak dibaca.
(d) Invokasi KEDUA atas job yang sama berjalan sampai selesai: mode `normal`, depth `sampling`,
    `cap=TANPA CAP`, `postVerdict` + `finalize` mendarat, exit 0.
(e) Yang membuat (c)+(d) tidak merugikan apa pun: `empty_memory_root()` dan `memory_root` atas DB kosong
    yang baru dibuat adalah **nilai yang SAMA PERSIS** —
    `0x4e2a1ca1697b2a287fcfc8158fd5c460298aa69af8d5bec2d35671d71c4dff5a` pada kedua jalur. Depth dan cap
    juga identik (`DEPTH_SAMPLING`, risk 0 → `TANPA CAP`), karena ADR-024 keputusan 3 memang menyamakan
    "memori kosong" dengan evaluator stateless. Satu-satunya beda yang tersisa adalah label `mode` di
    dalam bundel bukti (dan karenanya `reasonHash`), plus jumlah invokasi.
(f) Akibatnya cabang NAIF di `derived_memory_root()` dan `empty_memory_root()` TAK TERJANGKAU dari CLI;
    keduanya hidup hanya untuk pemanggil pustaka yang memanggil `post_verdict()` langsung.
(g) Mode AMAN tidak tersentuh: pada "DB hilang + root non-nol" `main()` keluar 0 di gerbang start, jauh
    SEBELUM `plan_job`, jadi tidak ada yang membuat file dan 3.3b varian B tetap utuh.

Keputusan:
1. Selisih ini **DIBIARKAN**, bukan ditutup. Perilakunya fail-closed (nol tx, nol verdict palsu) dan
   sembuh sendiri pada invokasi berikutnya.
2. Alasan menolak "menutupnya": menutup berarti membuat NAIF benar-benar terjangkau dari CLI, yaitu
   memberi jalur produksi izin mengumumkan `empty_memory_root()` pada vault segar. Itu MENAMBAH permukaan
   pada jalur yang baru saja dikunci 2.4b (root wajib turunan memori) demi keuntungan yang, menurut (e),
   NOL byte on-chain: root, depth, dan cap yang diumumkan sama saja. Harganya satu invokasi ekstra pada
   hari pertama — jelek, tetapi jujur dan terukur.
3. Cabang NAIF di `decide_mode` **TIDAK boleh dihapus** walau tak terjangkau dari CLI: ia yang membuat
   "DB hilang + root nol" TIDAK jatuh ke mode aman. Tanpa cabang itu invokasi pertama keluar 0 di gerbang
   start tanpa pernah menyentuh path DB, `memory.db` tidak pernah lahir, dan agen tidak pernah bootstrap.
4. Komentar yang mengklaim jangkauan lebih besar dari (f) DILARANG. Yang dikoreksi hari ini:
   `vault_client.py` (latch `observed_readable_memory` yang mengklaim "BERLAKU di Anvil / vault segar
   yang dipakai TASKS 2.5 AC (e)" — SALAH, AC (e) berakhir di MODE_DRIFT), komentar cabang NAIF di
   `derived_memory_root()`, docstring modul `vault_client`, komentar cabang (2) `decide_mode`, dan
   docstring `empty_memory_root()`.
5. Perilaku ini DIKUNCI TES supaya tidak berubah diam-diam: invokasi pertama = exit 4 + nol tx +
   `memory.db` LAHIR; invokasi kedua = 2 tx + mode `normal`; root yang diumumkan == `empty_memory_root()`;
   dan kontrol mode aman = file TIDAK pernah dibuat. Membalik keputusan 1 berarti tes-tes itu MERAH.
6. Operator WAJIB diberi tahu di README (task 4.3c): pada vault segar, jalankan `--job-id` sekali untuk
   melahirkan `memory.db` (atau lahirkan lewat `python -m agent.memory_export`), baru jalankan yang
   menghasilkan verdict. Menyembunyikan ini akan membuat exit 4 pertama terbaca sebagai kerusakan.

Konsekuensi:
(+) Nol perubahan pada jalur tx; penjaga 2.4b/2.5 (gerbang `_send`, latch refusal, lantai cap, empat
    syarat `bundle_reproduces_onchain`, toko bukti sekali-tulis) tidak disentuh sama sekali.
(+) Klaim di komentar kembali sama besar dengan perilaku yang bisa diperagakan — kelas cacat yang sudah
    dua kali menggigit proyek ini ("tidak ada jalur teks pihak ke memori", sitasi "api-facts §C").
(-) Hari pertama pada vault SEGAR menuntut DUA invokasi `--job-id`, dan yang pertama keluar 4. Itu jelek
    di depan operator dan WAJIB tertulis, bukan ditemukan sendiri.
(-) `MODE NAIF` praktis hanya muncul sebagai baris log invokasi pertama; ia TIDAK PERNAH menjadi mode
    yang melahirkan verdict lewat CLI. README/video/post DILARANG menyajikannya seperti itu.
(-) Cabang NAIF di `derived_memory_root()`/`empty_memory_root()` adalah kode yang tidak dilewati jalur
    produksi mana pun. Ia tetap diuji, tetapi setiap perubahan di sana tidak akan pernah tertangkap oleh
    pipa nyata — hanya oleh tesnya.
Tidak ada baris `docs/spec.md` yang dicabut ADR ini, jadi tabel divergensi ADR-025 tidak bertambah:
mode aman/naif sudah diwakili baris (ii) apa adanya.

## ADR-027 `@types/node` 26.4.1 dipasang tipe-saja di `sim/`; typecheck BUKAN pengganti tes
Tanggal: 2026-09-06. Status: diterima. Aditif; TIDAK membuka ulang ADR-010 dan tidak mengubah ADR mana pun.
Pemicu: task 0.9d — `sim/` adalah SATU-SATUNYA kode yang menyentuh jalur uang nyata (mint/approve/fund,
`docs/spec.md` §7 langkah 1-2) dan punya NOL tes otomatis, sehingga kesalahan tipe di sana muncul pertama kali
sebagai transaksi gagal di testnet, bukan sebagai tes merah.

Konteks — yang benar-benar diukur (2026-09-06, bukan ingatan):
(a) `sim/src/{client_min,mint_min}.ts` mengimpor `node:fs`, `node:path`, `node:url` dan memakai `process.env`.
    Dengan `--typeRoots <dir kosong>` (simulasi tanpa paket ini) `tsc --strict` berhenti pada **6× TS2591**
    "Cannot find name 'node:fs'" — enam error itu SEMUANYA modul node, nol error logika. Jadi satu paket tipe
    adalah selisih antara "typecheck tidak bisa jalan" dan "typecheck hijau".
(b) `cd sim && pnpm exec tsc --noEmit` → exit 0, 0 error.
(c) Paketnya tipe-saja: isinya hanya `.d.ts` (+ LICENSE/README/package.json), `sim/` tetap dijalankan `tsx`,
    dan `sim/tsconfig.json` `noEmit: true` — tidak ada satu byte pun yang masuk bundel atau proses berjalan.
(d) Lockfile tidak menggerakkan versi apa pun: 26.4.1 SUDAH resolved transitif sebelumnya; diff `679724a`
    hanya menambah entri importer `sim` dan melepas `optional: true` dari `@types/node@26.4.1` serta
    `undici-types@8.3.0`. Itu konsekuensi mekanis promosi ke devDependency keras, BUKAN paket lain berpindah.

Keputusan:
1. `@types/node` dipin **EXACT 26.4.1** (bukan `^`), sebagai **devDependency `sim/` saja**, **tipe-saja**.
   Ia dicatat di `docs/versions.md` tabel TypeScript lengkap dengan perintah + tanggal verifikasi.
2. `types: ["node"]` di `sim/tsconfig.json` dipertahankan sebagai penjaga preventif: lockfile MASIH memuat
   `@types/node@12.20.55` transitif (via `@types/connect`, `@types/uuid`, `@types/ws`) dan salinan basi itu
   duduk di `node_modules/.pnpm/node_modules/@types/node`. Setelan itu mengunci himpunan tipe ambient jadi
   TEPAT satu paket, sehingga layout hoisted/flat tidak bisa menyeretnya masuk. Kejujuran ukurannya:
   pada layout pnpm hari ini menghapus setelan itu TETAP menghasilkan 0 error — ia belum menahan apa pun
   hari ini, dan klaim "39 error" tidak tereproduksi. Tetap dipertahankan karena murah dan preventif.
3. **Ini TIDAK membuka ulang ADR-010.** Batas ADR-010 adalah nol dependensi **RUNTIME** baru (di sana:
   x402 + satu framework web yang ikut jalan di proses). `@types/node` tidak pernah dieksekusi, jadi ia
   ada di luar batas itu. ADR-010 tetap berlaku utuh.

Konsekuensi:
(+) Ada satu jaring statis untuk jalur mint/approve/fund — satu-satunya jaring yang dimiliki `sim/`.
(-) Satu entri baru di `docs/versions.md` pada H-4 submission; permukaan versi yang harus dijaga bertambah.
(-) **Typecheck BUKAN tes.** Ia tidak pernah mengirim transaksi, tidak menyentuh RPC, dan tidak membuktikan
    satu pun perilaku on-chain. Butir "Batasan" di `README.md` yang menyatakan `sim/` punya NOL tes otomatis
    TETAP BERLAKU dan **DILARANG** diturunkan jadi "sudah tercakup typecheck" di README, naskah video,
    maupun `docs/posts/*` (sejalan larangan klaim ADR-010 keputusan 4 dan ADR-025 keputusan 3).

## Catatan: izin user atas `docs/spec.md` (task 0.8f), 2026-09-06
User ditanya satu baris: *"boleh aku edit `docs/spec.md`?"* — jawabannya **"iya"**.

Larangan `loop.md` poin 5 karena itu DICABUT untuk `docs/spec.md` saja. **`PRD.md` TETAP
TERLARANG** — user tidak menyebutnya, dan izin yang tidak diminta tidak boleh diperluas
sendiri. Task 0.8b yang sebelumnya `[!]` BLOCKED PADA USER dibuka kembali; ADR-025 (spec
berstatus historis, ADR menang bila berbeda) TETAP BERLAKU sebagai aturan resolusi, dan
0.8b menyelaraskan spec supaya divergensinya berkurang, bukan menggantikan ADR-025.

Jawaban user atas pertanyaan kedua (task 0.8e) pada tanggal yang sama: pemeriksaan
`ALLOW_ARBITER_EQ_AGENT=true` pada berkas environment lokal mengembalikan **0**, jadi
escape hatch itu memang KOSONG di mesin build. Temuan RENDAH @agent-security-reviewer soal
itu ditutup tanpa perubahan kode.

## Catatan lintas-ADR: `lastMemoryRoot()` adalah nilai BERGERAK, jangan pernah di-hardcode
Ditambahkan 2026-09-06 (task 0.8g, temuan samping @agent-api-verifier saat 0.8b-note).

ADR-023 (`:572`) dan ADR-024 (`:611`) merekam `lastMemoryRoot()` vault sebagai
`0x1fa62c3db5c16f4c831ee1d9ee4c083745b8c8bae86bda3587b8b02ba52f7bf0`. Nilai itu BENAR pada
tanggal ADR-nya, dan **ADR-nya TIDAK diubah** — penalaran keduanya bergantung pada "root
non-nol", bukan pada nilai spesifik, jadi tidak ada yang perlu dikoreksi di sana.

Yang perlu diketahui pembaca berikutnya: **setiap `postVerdict` yang berhasil menulis ulang
`lastMemoryRoot`**. Rantai A/B/C (task 2.5) sudah menggesernya sekali, dan setiap job baru
akan menggesernya lagi. Karena itu:

- **JANGAN pernah menulis nilai `lastMemoryRoot` sebagai literal di AC, skrip verifikasi,
  README, atau naskah demo.** AC yang melakukannya akan GAGAL tanpa sebab yang jelas
  beberapa job kemudian — kelas cacat yang sama dengan AC 0.2(a) yang sudah ditulis ulang
  oleh task 0.9b karena lulus karena alasan yang salah.
- Bacalah nilainya saat itu juga:
  `cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "lastMemoryRoot()(bytes32)" --rpc-url https://sepolia.base.org`
- Klaim yang BOLEH dipegang adalah klaim RELASIONAL, bukan nilai: *root yang diumumkan
  on-chain sama dengan keluaran `agent/memory_export.py` atas DB yang menjangkarnya pada
  saat itu*. Itulah bentuk yang dipakai AC (d) task 2.4b, dan ia tetap benar berapa kali pun
  rootnya bergeser.

## ADR-028 Ambang 85/110 gerbang 4.2 tidak boleh menunda perekaman video
Tanggal: 2026-09-06. Status: diterima. Aditif; TIDAK mengubah ADR mana pun dan tidak mengubah scope.
Pemicu: gerbang fase 2 (task 2.9, laporan `docs/judge-reports/fase-2.md`, 6 Sep 2026) memberi skor dasar
**82/110** (94/137,5 setelah multiplier ×1.15) — di bawah ambang `TASKS.md` 4.2 "skor >= 85/110 sebelum
rekam video". Dibaca HARFIAH, aturan itu bisa menahan perekaman sampai skor naik.

Konteks: PRD §5 "Submission lengkap" = repo MIT + **video 2-5 mnt** + README + 2 post. Submission tanpa
video bernilai **NOL**, bukan 82. Jadi membaca 4.2 sebagai penahan video menukar kehilangan 3 poin dengan
kehilangan seluruh nilai.

Keputusan:
1. Ambang **85/110 TETAP** syarat untuk menyatakan "siap rekam", dan skornya tetap dilaporkan APA ADANYA
   di `docs/judge-reports/fase-4.md`. Ambang tidak diturunkan dan tidak "dipoles" agar hijau.
2. Bila **9 Sep 2026 18:00** tiba dengan skor < 85, video **TETAP direkam hari itu** memakai state terbaik
   yang ada, dan laporan 4.2 mencatat skor apa adanya — bukan skor yang dipoles.
3. **Tidak ada task lain yang boleh menunda 4.3** (video + 2 post build-in-public) dengan alasan skor.

Konsekuensi:
(+) Kita bisa mengirim submission yang skornya jujur di bawah target; skor rendah tetap terlihat di laporan.
(-) Sebaliknya, mustahil kehilangan SELURUH nilai karena mengejar tiga poin.
(=) Nol scope bertambah maupun berkurang — ini aturan proses, bukan fitur. Rekomendasi 1-3 juri
    (`docs/judge-reports/fase-2.md`, proyeksi ~91/110) tetap dikejar sampai tenggat, tapi tidak menyandera 4.3.
(!) Checklist submission di hack.sibyllabs.org TIDAK diverifikasi di sesi ini; klaim "video 2-5 mnt"
    bersumber pada `PRD.md:30` yang terverifikasi, bukan pada situs itu.
