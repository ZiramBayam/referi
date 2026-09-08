# Masalah, solusi, dan apa yang di luar spek ERC-8183

Nomor butir merujuk ke [`docs/limitations.md`](limitations.md). Diagram alur ada di
[`README.md`](../README.md).

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

Satu kalimat yang sering dikutip salah: "dibayar sama besar entah ia meluluskan atau menolak". Fee di muka
lewat x402 yang akan membuat kalimat itu benar adalah **rancangan (ADR-004), bukan fitur** (butir 11).
Kalimat itu berasal dari `docs/spec.md` §0, dan §0 berjudul "Pitch satu kalimat" — aspirasi, bukan catatan
fakta; README tidak mengutipnya lagi sebagai fakta.

## Siapa yang memakainya di hari pertama, dan kenapa ia mau membayar

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
   bertransaksi alih-alih menebak (butir 22, dan tes destruktif di `docs/reproduce.md`).
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
(butir 23), dan wallet simulatornya belum terdaftar di Service Registry Virtuals (butir 24). Yang sudah
nyata adalah mekanismenya di chain; yang belum adalah permintaannya.

## Di luar spek ERC-8183 — dan kenapa

| Tambahan | Alasan | ADR |
|---|---|---|
| **EvaluatorVault** sebagai alamat evaluator (bukan EOA) | spek tidak punya bond/challenge/timeout evaluator; spek mengizinkan evaluator berupa kontrak | ADR-003 |
| **Jangkar memori on-chain** (`MemoryRootUpdated`, `knownRoots`) | tiap eksekusi ke ACP terikat root yang sudah diumumkan SEBELUM eksekusi; batasnya: dari **delapan** root vault hanya **418** yang bisa dihitung ulang hari ini, sisanya keadaan antara yang hilang permanen (butir 7), dan jangkarnya melingkar (butir 16) | ADR-011 |
| **Gating cap lewat `reject()` saat `Funded`** | hook kustom butuh whitelist admin Virtuals yang tidak kami punya; hak reject saat Funded sudah ada di spek. Penegakannya off-chain; kontrak hanya menerbitkan cap (butir 17) | ADR-001 |
| **Karantina sebagai entity `suspicion`** | Sibyl hanya punya HOT/WARM/COLD/REFERENCE/ARCHIVE — tidak ada tier FLAGGED, jadi karantina dibangun sebagai konvensi, dan pengambil keputusan dilarang membacanya | ADR-002 |
| **Bond + jendela sengketa** | dirancang, tetapi hari ini `MIN_BOND` = 0 dan `challenge`/`resolve` stub — lihat butir 1-2 | ADR-013 |
| **Fee di muka via x402** | fee kontrak hanya cair saat Completed → insentif meluluskan, **termasuk pada wasit ini sendiri**. **Belum diimplementasikan** (butir 11 dan 14) | ADR-004 |
