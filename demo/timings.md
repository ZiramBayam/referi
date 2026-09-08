# Runtime `make demo` — pengukuran nyata

Angka ini ada supaya klaim durasi di README dan di naskah rekaman bisa ditelusuri,
bukan diingat. `make demo` sengaja TIDAK menulis berkas log apa pun (lihat
`docs/limitations.md` butir 19), jadi berkas inilah satu-satunya jejak waktunya.

Semua pengukuran di mesin yang sama, 8 September 2026, dengan jaringan aktif
(preflight menghubungi `https://sepolia.base.org` — dua pembacaan view, nol dana,
nol transaksi).

| # | Pengukur | Perintah | `real` | Exit |
|---|---|---|---|---|
| 1 | gerbang juri 4.2 | `make demo` | **3m56s** | 0 |
| 2 | gerbang juri 4.2 | `make demo` | **3m23s** | 0 |
| 3 | verifikasi lanjutan | `time make demo` | **3m40.850s** | 0 |

`user 1m21.225s`, `sys 0m19.132s` pada pengukuran ke-3 — sebagian besar waktu dinding
adalah menunggu blok Anvil dan jendela challenge, bukan CPU.

## Kenapa angka lama `~2m20s` salah

`~2m20s` diukur saat task 3.3, SEBELUM dua hal ditambahkan:
1. preflight jaringan ke Base Sepolia (task 3.3b turunan, gagal keras bila tidak terjangkau);
2. DUA varian destruktif berurutan — varian A di Anvil lokal dengan vault segar, varian B
   terhadap vault Sepolia yang beku.

Keduanya menambah waktu dinding. Angka lama sudah dicabut dari README.

## Akibatnya untuk perekaman

Naskah (`demo/video-script.md`, `demo/video-script.en.md`) memicu tata letak layar panjang
bila runtime melewati ± 3 menit. Dengan ketiga pengukuran di atas, tata letak itu adalah
**jalur normal, bukan rencana darurat** — mulailah dengan asumsi tersebut, dan jalankan
dry-run berwaktu di mesin perekam sebelum TAKE-1.

## Cara mengukur ulang

```
cd <repo> && time make demo
```

Butuh internet. Bagian deterministik dua eksekusi berturut-turut harus IDENTIK; hanya
baris `[demo] onchain` yang boleh berbeda antar-run.
