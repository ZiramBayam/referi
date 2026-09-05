# Pipa hidup Base Sepolia (84532) — job ACP 417

Satu job nyata menembus seluruh pipa pada 2026-09-04: **createJob → setBudget → fund → submit →
postVerdict → finalize → `JobCompleted`**. Evaluator job ini adalah kontrak `EvaluatorVault`, bukan
sebuah EOA, jadi pembayaran provider benar-benar diputuskan oleh vault.

Verdict di-hardcode dan memori masih kosong pada run ini — yang dibuktikan di sini HANYA pipanya.

## Peran (tiga alamat berbeda, dipaksa kontrak)

| Peran | Alamat |
|---|---|
| Client | `0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2` |
| Provider | `0x20212E4D95A75E6716575ED26e884cdeFf66b321` |
| Evaluator (kontrak) | `0x5c6EE4586ACABcb6326069c229E58091B21ef384` |
| Wallet agen (menggerakkan vault) | `0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894` |
| ACP | `0x0b93793923CD5De81850aF8604a233f3f24d461e` |
| Token escrow | `0xECc22a8F6fD62388498fBa19813E214605a2BDb3` |

`createJob` merevert `ClientIsProvider()` `0x332ff0f9` bila client == provider, jadi tiga alamat ini
bukan pilihan gaya. Wallet agen sengaja BUKAN provider (ADR-017 poin 3).

## Empat transaksi kunci

1. **createJob** — [`0x20bc0e46…be70a`](https://sepolia.basescan.org/tx/0x20bc0e469d86316089ab1868d396819804419168ff256300ae7c7f821bfbe70a)
2. **fund** — [`0xa5b5ea60…81f370`](https://sepolia.basescan.org/tx/0xa5b5ea60a35cfb2d253144772fee6016cb67441c5ec441e6ae4d4357cd81f370)
3. **postVerdict** — [`0x54a72152…b86dfb`](https://sepolia.basescan.org/tx/0x54a72152a922f02f62ca18d71d781ea7bc833b6df70e415ce84a9888f7b86dfb) (blok 46378567)
4. **finalize** — [`0x808d63be…db9f33`](https://sepolia.basescan.org/tx/0x808d63be45a506ef13a9cc047194f9bb5d3f3eb875ad513b1c08b09836db9f33) (blok 46378631)

Dua transaksi provider yang melengkapi alur:
`setBudget` [`0x969b0e54…c014153`](https://sepolia.basescan.org/tx/0x969b0e54d82e5e0da3c157dc19ca404d22e58e22142924067dc2c2303c014153),
`submit` [`0x607f88b3…9f53eb`](https://sepolia.basescan.org/tx/0x607f88b3fcbc5141fe6dad9d805bca7fbc55c7a14d2a199a570ff7cbba9f53eb).

Tautan basescan di atas adalah artefak untuk MANUSIA, bukan bukti mesin: basescan menolak akses
otomatis dengan HTTP 403. Bukti mesinnya ada di bawah.

## `JobCompleted` di chain

```
$ cast logs --address 0x0b93793923CD5De81850aF8604a233f3f24d461e \
    "JobCompleted(uint256,address,bytes32)" 417 \
    --from-block 46368632 --to-block 46378631 --rpc-url https://sepolia.base.org
- address: 0x0b93793923CD5De81850aF8604a233f3f24d461e
  blockHash: 0xb3a1b93c27dd7bcd7dfdd07bda32cef9ff704a829b2b8d5bd04da6312de37345
  blockNumber: 46378631
  data: 0x6478e788a7953cf990091291d8d1b4f3f046567a915e5158d4dcf57d9fd845b0
  logIndex: 127
  removed: false
  topics: [
  	0x0fd54bd364fa9e67f17b091aefe930932c09fe7651cf5ad02c71a418f3341444
  	0x00000000000000000000000000000000000000000000000000000000000001a1
  	0x0000000000000000000000005c6ee4586acabcb6326069c229e58091b21ef384
  ]
  transactionHash: 0x808d63be45a506ef13a9cc047194f9bb5d3f3eb875ad513b1c08b09836db9f33
  transactionIndex: 10
```

Topic 1 = `0x1a1` = jobId 417. Topic 2 = alamat vault: **evaluator yang meluluskan job ini adalah
kontrak kita**. `data` = `reasonHash` yang diumumkan vault saat `postVerdict`.

Rentang blok WAJIB <= 10.000; lebih dari itu RPC publik menjawab HTTP 413 (`-32614`), bukan hasil kosong.

## Status akhir & aliran dana

```
$ cast call 0x0b93793923CD5De81850aF8604a233f3f24d461e \
    "jobs(uint256)(address,uint8,address,uint48,address,address,uint256,string)" 417 \
    --rpc-url https://sepolia.base.org
0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2
3
0x20212E4D95A75E6716575ED26e884cdeFf66b321
1788527304
0x5c6EE4586ACABcb6326069c229E58091B21ef384
0x0000000000000000000000000000000000000000
1000000
"the-evaluator smoke job: provider menyerahkan satu deliverable, EvaluatorVault yang menilai."
```

status = 3 (Completed). Budget 1 USDC terbelah persis:

| Penerima | Jumlah | Catatan |
|---|---|---|
| Provider | 940.000 | payout |
| Vault (evaluator fee) | 50.000 | `evaluatorFeeBP()` = 500 = 5% |
| Platform | 10.000 | 1% |

Angka 940.000 + 50.000 + 10.000 = 1.000.000 diukur dari `balanceOf` sesudah `finalize`, bukan dihitung
di atas kertas.

**Utang yang terlihat dari sini, dan TIDAK ditutup:** vault memegang 50.000 token dan tidak punya jalan
keluar. `sweepToken(address,address) onlyArbiter` mendarat di sumber (commit `e675234`) sebagai kode + tes
SAJA; ADR-022 membekukan alamat di atas sebagai kontrak submission dan membatalkan redeploy, jadi fungsi itu
TIDAK ADA di bytecode terdeploy — dibuktikan langsung: `cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384
"sweepToken(address,address)" ...` → `execution reverted`. 50.000 unit (0,05 USDC testnet) hangus permanen;
ini dilepas secara sadar oleh ADR-018 keputusan 2, bukan kelalaian.

## Cara memutar ulang

```
pnpm --filter sim run job:min          # createJob + setBudget + fund + submit → jobId baru
cd agent && uv run python -m agent.vault_client --job-id <jobId>   # postVerdict → tunggu 120 dtk → finalize
```

Anggaran waktu: verdict WAJIB di-`finalize` sebelum `expiredAt + 900`. Sesudah ambang itu siapa pun
boleh `claimRefund` job Submitted dan verdict jadi yatim — `complete()` sesudahnya revert
`WrongStatus()`. Run ini selesai 2.655 detik sebelum ambang tersebut.
