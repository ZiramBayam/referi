# VERSIONS — versi yang dipakai (diverifikasi 24 Agu 2026 dari registry/repo resmi)
Aturan: pin persis versi di bawah. Jangan upgrade/downgrade tanpa ADR. Kolom "Catatan" memuat risiko yang sudah diketahui.

## Runtime
Kolom **Dipin** = versi yang disepakati (pin; hanya berubah lewat ADR). Kolom **Aktual** = yang benar-benar terpasang di mesin build, diverifikasi 2026-09-02 (perintah di bawah tabel). Drift dicatat, pin TIDAK ikut berubah.

| Alat | Dipin | Aktual (2026-09-02) | Drift | Status | Catatan |
|---|---|---|---|---|---|
| Node.js | **24.19.0** | `v24.15.0` | patch/minor di major line 24 → OK tanpa ADR | Active LTS (Maintenance mulai 2026-10-20) | v26 baru LTS 2026-10-28 — jangan pakai dulu. `.nvmrc` = 24. nvm di mesin ini hanya menyediakan versi tsb; toolchain sengaja TIDAK di-upgrade |
| pnpm | latest via `corepack enable` | `11.25.0` (shim corepack 0.34.6) | — (pin memang "latest") | — | sebelumnya "tidak diverifikasi", kini tercatat. Kunci ulang di field `packageManager` + lockfile saat `package.json` dibuat |
| Python | **3.13** (`.python-version`) | `3.13.15` (uv-managed) | patch di major line 3.13 → OK tanpa ADR | bugfix (security-only ~Okt 2026) | 3.14.x = ganti major line → WAJIB ADR. Awas: `/usr/bin/python3` sistem = 3.12.3, jadi selalu jalankan lewat `uv run` |
| uv | 0.12.5 | `0.12.7` | patch di major line 0.12 → OK tanpa ADR | stabil | pengelola env & lock Python |
| Foundry | **v1.7.1** (`foundryup` stable) | `forge 1.7.1` (commit 4072e487, build 2026-05-08) | cocok | stabil | default `evm_version` = osaka (cocok Base pasca-Azul) |
| Solidity | **0.8.36** | `0.8.36+commit.8a079791.Linux.g++` | cocok | stabil | diverifikasi 2026-09-03: `~/.svm/0.8.36/solc-0.8.36 --version` (svm mengunduhnya saat `forge build` pertama di `contracts/`, `foundry.toml` baris 9 `solc = "0.8.36"`). Repo resmi kini github.com/argotorg/solidity; implementasi ACP Base Sepolia sendiri dikompilasi dengan **0.8.28** (metadata CBOR di ekor bytecode proxy DAN implementasi: `…736f6c634300081c0033` = solc 0.8.28) — beda compiler dari mock kita, jadi jangan bandingkan bytecode, bandingkan ABI |

### Ambang ADR untuk perubahan versi
- **Drift patch/minor di dalam major line yang sudah dipin** (mis. Node tetap di major line 24, uv tetap di 0.12.x): TIDAK butuh ADR. Cukup `@agent-api-verifier` memperbarui kolom "Aktual" di tabel ini + tanggal + perintah verifikasi.
- **Ganti major line: WAJIB ADR di `docs/decisions.md` SEBELUM instalasi.** Termasuk: Node 26, Python 3.14, TypeScript 5.x (turun dari 7.x), Foundry 1.8+, solc ≠ 0.8.36, viem 3.x.
- Kolom "Dipin" hanya boleh diubah oleh ADR. Kolom "Aktual" boleh diperbarui api-verifier kapan saja, asalkan disertai perintah + tanggal.

### Perintah verifikasi kolom "Aktual" (dijalankan 2026-09-02, shell INTERAKTIF `bash -ic`)
```
node --version; pnpm --version; uv --version; forge --version; corepack --version
uv python find; uv run --no-project python --version   # python proyek, bukan /usr/bin/python3
```
WAJIB shell interaktif: `~/.bashrc` mesin ini punya guard `case $- in *i*) ;; *) return;; esac` (baris 8),
sedangkan nvm (baris 119-121) dan `PATH` foundry (baris 127) dimuat SESUDAH guard itu. Di `bash -lc` maupun
proses non-interaktif (hook, cron, CI) hasilnya beda: node = `/usr/bin/node` v18.19.1, `pnpm` & `forge` tidak
ditemukan; hanya `uv` yang selamat (lewat `~/.profile`). Diverifikasi 2026-09-02 dengan
`env -i HOME=$HOME /bin/bash -lc 'command -v node pnpm uv forge'`.

## Kontrak (Foundry)
| Paket | Versi | Catatan |
|---|---|---|
| openzeppelin-contracts | v5.7.0 | `forge install OpenZeppelin/openzeppelin-contracts@v5.7.0` |
| openzeppelin-contracts-upgradeable | v5.7.0 | hanya jika mock ACP referensi (UUPS) dibutuhkan |
| forge-std | ikut foundryup | — |
`foundry.toml`: `solc = "0.8.36"`, `evm_version = "osaka"`, `optimizer = true`, `optimizer_runs = 200`.

## TypeScript (sim/ & web/)
| Paket | Versi | Catatan |
|---|---|---|
| typescript | **7.0.2** | major baru. Jika Next/ESLint bermasalah → fallback ke 5.x terakhir dan tulis ADR |
| next | 16.3.2 | App Router |
| react / react-dom | 19.2.8 | — |
| viem | 2.55.19 | **bukan** 3.0.0-next (prerelease) |
| wagmi | 3.7.6 | butuh @tanstack/react-query |
| @tanstack/react-query | 5.102.2 | — |
| @virtuals-protocol/acp-node-v2 | 0.1.12 | peer deps: viem, @account-kit/infra (4.88.5) |
| vitest | 4.1.11 | bukan 5.0.0-rc |
| tailwindcss | latest 4.x | versi persis tidak diverifikasi → cek `pnpm view tailwindcss version` saat install |

## Python (agent/)
| Paket | Versi | Catatan |
|---|---|---|
| sibyl-memory-client | **0.7.0** | python ≥3.10; verifikasi signature metode dengan `inspect.signature` sebelum dipakai |
| web3 | 7.16.0 | python ≥3.8,<4 |
| anthropic | **1.0.0** | major baru (0.x→1.x) — baca changelog sebelum pakai; model default `claude-sonnet-5` |
| pydantic | 2.13.4 | skema kriteria/verdict |
| httpx | 0.28.1 | ambil deliverable off-chain |
| pytest | 9.1.1 | — |
| ruff | latest | versi persis tidak diverifikasi |
| x402 (server/facilitator lib) | **BELUM DIVERIFIKASI** | cari paket resmi Coinbase x402 untuk Python/Node, verifikasi terhadap registry resmi sebelum server x402 dibuat |

## Jaringan & alamat (diverifikasi on-chain + docs.base.org + circlefin/skills)
Baris token & fee diverifikasi ulang 2026-09-03 dengan `cast call <ACP> "paymentToken()(address)"`, `"platformFeeBP()(uint256)"`, `"evaluatorFeeBP()(uint256)"`, `"platformTreasury()(address)"` (RPC https://sepolia.base.org). Rincian perilaku: `docs/api-facts.md` §A.
Baris alamat & token diverifikasi ULANG 2026-09-04 langsung ke chain. **`symbol()` BUKAN alat identifikasi token di jaringan ini** — dua alamat berbeda sama-sama menjawab `"USDC"`; satu-satunya pembeda yang mengikat adalah ALAMAT hasil `paymentToken()`. Lihat `docs/api-facts.md` §A.
| Item | Nilai |
|---|---|
| Base Sepolia | chainId 84532 (0x14a34), RPC https://sepolia.base.org, explorer https://sepolia.basescan.org |
| Base mainnet | chainId 8453, RPC https://mainnet.base.org |
| EVM version Base | osaka (Azul: Sepolia 2026-04-20, mainnet 2026-05-28); gas cap per-tx 16,777,216 (EIP-7825) |
| USDC Circle Base Sepolia | 0x036CbD53842c5426634e7929541eC2318f3dCF7e — **TIDAK dipakai escrow ACP**, lihat baris berikutnya. Dibaca 2026-09-04: `symbol()` = "USDC", `name()` = **"USDC"**, `decimals()` = 6 |
| **Token escrow ACP Base Sepolia** | **0xECc22a8F6fD62388498fBa19813E214605a2BDb3** — nilai `paymentToken()` kontrak ACP; `mint(address,uint256)` terbuka untuk siapa pun → tidak butuh faucet Circle. Dibaca 2026-09-04: `symbol()` = "USDC" (IDENTIK dengan USDC Circle → tidak bisa membedakan), `name()` = "USD Coin", `decimals()` = 6 |
| **Cara membedakan dua "USDC" itu** | `cast call 0x0b93793923CD5De81850aF8604a233f3f24d461e "paymentToken()(address)" --rpc-url https://sepolia.base.org` → `0xECc22a8F6fD62388498fBa19813E214605a2BDb3` (2026-09-04). Bandingkan **alamat**, jangan `symbol()`. Pembeda lemah tambahan: `name()` "USD Coin" (escrow) vs "USDC" (Circle) |
| USDC Base mainnet | 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 (6 desimal) — di mainnet ACP memang memakai USDC Circle |
| ACP Base Sepolia | 0x0b93793923CD5De81850aF8604a233f3f24d461e (proxy ERC-1967; implementasi 0xc4E95dBc7E8C99c114FF9C8299A3E4851e1530fF — slot `0x360894…2bbc` dibaca ulang 2026-09-04, tidak berubah) |
| **EvaluatorVault (kontrak KITA) Base Sepolia** | **0x5c6EE4586ACABcb6326069c229E58091B21ef384**. Deploy tx `0xfcf339e2732f60809bd8c86232ccc386e9cb5285edb285e355fb2ca1fe98b601`, blok 46350667, status 1, gasUsed 816969, `effectiveGasPrice` 6.000.000 wei, deployer/`from` = 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894 (`cast receipt … --rpc-url https://sepolia.base.org`, 2026-09-04). Immutable on-chain: `acp()` = ACP Base Sepolia, `agent()` = `arbiter()` = 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894 (**agent == arbiter pada deploy ini** — pisahkan sebelum 1.2c/`sweepToken`), `MIN_BOND()` = 0; konstanta `CHALLENGE_WINDOW()` = 120, `MIN_ACP_GAS()` = 300000, `KIND_COMPLETE()` = 1, `KIND_REJECT()` = 2. Catatan deploy: `deployments/84532.json` |
| ACP Base mainnet | 0x238E541BfefD82238730D00a2208E5497F1832E0 |
| Fee ACP Base Sepolia | `platformFeeBP()` = 100 (1%), `evaluatorFeeBP()` = 500 (5%), `platformTreasury()` = 0xb3bdEdda2050a3615B73bB9a2684946eC38B5375 |
| Tenggang evaluator ACP | `EVALUATOR_GRACE_PERIOD()` = **900** detik (15 menit) — dibaca 2026-09-03 via `cast call <ACP> "EVALUATOR_GRACE_PERIOD()(uint256)"`. Setelah `expiredAt + 900`, SIAPA PUN boleh `claimRefund` job berstatus Submitted dan membatalkan verdict evaluator. Konstanta ini membatasi anggaran waktu vault; lihat `docs/api-facts.md` §A |
| Batas RPC publik | `eth_getLogs` maksimum rentang 10.000 blok (error `-32614`) |

## Model Claude (API) — platform.claude.com/docs/en/about-claude/models/overview
`claude-sonnet-5` (default rubric LLM; 1M ctx), `claude-opus-5`, `claude-fable-5`, `claude-haiku-4-5`. ID tanpa akhiran tanggal.
