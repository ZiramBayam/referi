---
title: "Kenapa wasit escrow butuh memori, bukan sekadar penilai satu job"
date: 2026-09-08
proyek: The Evaluator (hackathon Sibyl, Base Sepolia)
repo: EvaluatorVault 0x5c6EE4586ACABcb6326069c229E58091B21ef384
---

# Kenapa wasit escrow butuh memori, bukan sekadar penilai satu job

ERC-8183 menaruh seluruh kepercayaan pada satu pihak: evaluator. Ia "fully trusted", pembayarannya
all-or-nothing (Completed = 100% ke provider, Rejected = 100% refund ke client, tidak ada pembayaran
parsial), dan — ini yang kami serang — ia **stateless**. Setiap job dinilai seolah provider itu baru
lahir hari ini. Provider yang menyerahkan pekerjaan setengah jadi pada job A bertemu evaluator yang
sama pada job B dengan catatan bersih.

Kami membangun evaluator yang **mengingat**, dan yang ingatannya bisa dihitung ulang orang lain dari
file, bukan dipercaya begitu saja.

## Keputusan hari ini dibentuk oleh riwayat, dan itu ada tx-nya

Bukti terkuat yang kami punya bukan diagram, melainkan dua job di Base Sepolia dengan **teks
deliverable yang identik byte demi byte** (`keccak256(text)` = `0x246071b3…0a51` pada
`demo/deliverables/421.json` dan `422.json`), budget sama (250.000), evaluator sama — tetapi provider
berbeda:

- **Job 421**, provider tanpa riwayat insiden → kedalaman pemeriksaan `sampling` (hanya 2 bagian
  pertama yang dibaca; `SAMPLING_SECTION_LIMIT = 2` di `agent/agent/checks/base.py:78`) → **lulus**.
  `postVerdict` `0x02356b079fa3bfcd32e62d7e2bb61d3f4eb8b66d29fac578cd6318b2028a1467`.
- **Job 422**, provider dengan dua insiden tercatat (job 418 dan 419) → risk 2 → kedalaman `full` →
  cacat `TODO` di **bagian ketiga** terbaca → **ditolak**.
  `postVerdict` `0xe95910d28ac4b5182220b9ea7c31519fb006b99b2edb0ed453f18556fa295830`.

Teks yang sama, verdict yang berbeda, dan yang membedakannya hanya riwayat. Itu klaim yang bisa Anda
buka sendiri di explorer.

Batas jujurnya, karena tanpa ini kalimat di atas terdengar lebih hebat dari kenyataan: kedua provider
itu **simulator kami sendiri**, cacatnya adalah **satu kata** yang ditangkap satu regex
(`agent/agent/checks/format.py:47-50`), dan tidak ada satu pun LLM di jalur evaluasi — yang berjalan
hanya cek deterministik `format`, `links`, `chain`. Kriteria kualitatif dicatat `unscored` di setiap
bundel bukti dan **tidak pernah** dianggap lolos (`agent/agent/criteria.py:121-124`).

## Memori yang tidak bisa diaudit hanyalah tebakan yang percaya diri

Memori yang hanya hidup di proses kami sendiri tidak berhak mengubah keputusan finansial. Jadi setiap
`postVerdict` mengumumkan `memoryRoot` — hash kanonik atas keadaan memori — dan kontrak meng-emit
`MemoryRootUpdated`. Fungsi yang menghitungnya adalah **satu implementasi yang sama** dengan yang
dipakai alat ekspor (`agent/agent/memory_policy.py` → `memory_root_for_onchain`), encodingnya dikunci
vektor beku (`agent/tests/fixtures/memory_root_vector.json`), dan ada perhitungan ulang lintas bahasa
di `agent/tools/memory_root_check.mjs`.

Dua hal yang harus disebut bersamaan, dan kami menolak menyembunyikannya:

1. **Jangkarnya melingkar.** Root membuktikan "agen men-hash sebuah file", bukan "file itu memori yang
   sah". On-chain, `postVerdict` hanya menolak root **nol**
   (`contracts/src/EvaluatorVault.sol:303`). Yang menahan root karangan ada di sisi agen
   (`_require_derived_root`, `agent/agent/vault_client.py:1339`), bukan di kontrak.
2. **Hanya satu dari delapan root vault yang bisa dihitung ulang hari ini**, yaitu root job 418 — dan
   justru karena saat itu memorinya masih kosong. Memori ditulis **sesudah** `postVerdict`, jadi
   setiap root on-chain adalah keadaan sebelum job itu menulis hasilnya, dan keadaan antara hilang
   permanen begitu memori maju. Log root per job untuk audit mundur adalah v2 (ADR-023).

Yang **bisa** diverifikasi hari ini adalah ikatan root ↔ bundel bukti: nama file bundel = `reasonHash`
on-chain = `keccak256` isi file, dan di dalam file itu ada `memory_root` yang sama dengan yang
diumumkan. Kelima bundel (418-422) memenuhinya. Verdict, alasan, dan root terikat dalam satu hash yang
diumumkan **sebelum** eksekusi.

## Karantina dipisah dari jalur keputusan — dan kenapa itu tidak biasa

Bagian rancangan yang paling sering ditanyakan: memori kami punya entity `suspicion` (karantina) yang
**dilarang dibaca oleh pengambil keputusan**. Kenapa menyimpan sesuatu yang tidak boleh dipakai?

Asalnya batasan nyata: Sibyl hanya punya tier HOT/WARM/COLD/REFERENCE/ARCHIVE — **tidak ada tier
FLAGGED**. Jadi karantina kami bangun sebagai konvensi, bukan sebagai fitur DB (ADR-002). Dan begitu
karantina hanya konvensi, satu-satunya cara ia tidak berubah jadi "tuduhan yang diam-diam menghukum"
adalah melarangnya menyentuh keputusan sama sekali. Kecurigaan baru boleh mengubah apa pun setelah
**dipromosikan**: minimal 2 job berbeda, dengan bukti dari cek deterministik.

Larangan itu bukan komentar di kode. Tiga tes menjaganya, dan ketiganya diperlukan
(`agent/tests/test_memory_policy.py`):

- pemindaian **AST** atas sumber jalur keputusan — karena nama kategori bisa disamarkan, pemindai
  substring saja tidak cukup;
- tes **properti**: dua DB kembar dengan riwayat tulis identik, satu diracuni karantina, lalu 240
  masukan acak (alamat dikenal & asing, budget ganjil & genap, sampai `2**200 + 1`, semua mode) harus
  memberi keluaran **identik** — inilah yang membunuh mutan yang bersyarat pada input tertentu;
- **klien mata-mata** yang memeriksa pembacaan yang benar-benar terjadi saat jalan, sehingga bentuk
  pemanggilan tidak relevan.

Tes itu punya kontrol negatifnya sendiri (DB teracun memang berisi ≥ 13 baris karantina), jadi
hijaunya bukan hijau palsu.

## Yang belum, disebut di muka

Insentifnya belum diperbaiki: `evaluatorFeeBP` = 5% dan fee hanya cair saat `Completed`, jadi wasit ini
masih dibayar hanya kalau ia meluluskan — persis bias yang kami kritik. Evaluator tidak mempertaruhkan
apa pun (`MIN_BOND` = 0), dan `challenge`/`resolve` adalah stub, sehingga jendela 120 detik itu murni
latensi: verdict salah tidak bisa dibatalkan siapa pun. Semuanya tertulis lengkap di bagian "Batasan &
asumsi kepercayaan" di README, di atas pitch mana pun.

Repo, kontrak, dan seluruh tx-nya publik. Post berikutnya: apa yang patah saat membangunnya.
