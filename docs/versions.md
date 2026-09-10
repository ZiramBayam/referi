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
- **Ganti major line: WAJIB ADR di `docs/decisions.md` SEBELUM instalasi.** Termasuk: Node 26, Python 3.14, TypeScript 5.x (turun dari 7.x), Foundry di atas major line 1.7, solc ≠ 0.8.36, viem 3.x.
- **Foundry dipin PERSIS 1.7.1; drift patch sekalipun (1.7.2) wajib ADR karena mengubah bytecode.** Ini pengecualian eksplisit terhadap aturan drift patch/minor di butir pertama: kompilator/toolchain masuk preimage artefak yang sudah dideploy dan dibekukan (ADR-022), jadi "patch aman" tidak berlaku di sini.
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
| @types/node | **26.4.1** | pin **EXACT** (bukan `^`), devDependency **`sim/` SAJA** (`grep -rn "@types/node" --include=package.json . --exclude-dir=node_modules` → hanya `sim/package.json:16`), **tipe-saja / NOL runtime**: isi paket hanya `.d.ts` + LICENSE/README (`find -L sim/node_modules/@types/node -maxdepth 1 -type f ! -name '*.d.ts'` → hanya LICENSE, README.md, package.json) dan `sim/` tetap dijalankan `tsx`, jadi ia tidak masuk bundel/eksekusi — ADR-027, TIDAK membalikkan ADR-010. Menarik `undici-types@8.3.0`, juga tipe-saja. Lockfile TIDAK menggerakkan versi apa pun: 26.4.1 sudah resolved transitif sebelumnya, diff `679724a` = entri importer `sim` + lepasnya `optional: true` saja (`git show 679724a -- pnpm-lock.yaml`). **Lockfile masih memuat `@types/node@12.20.55`** (transitif dari `@types/connect`, `@types/uuid`, `@types/ws`; `grep -c "12.20.55" pnpm-lock.yaml` → 5) dan salinan basi itu duduk di `node_modules/.pnpm/node_modules/@types/node` → `@types+node@12.20.55`. Karena itu `types: ["node"]` di `sim/tsconfig.json` WAJIB dipertahankan: ia mengunci himpunan tipe ambient jadi TEPAT satu paket, sehingga layout hoisted/flat tidak bisa menyeret 12.20.55 masuk program. Diverifikasi 2026-09-06: `realpath sim/node_modules/@types/node` → `node_modules/.pnpm/@types+node@26.4.1/...`; registry `curl -s https://registry.npmjs.org/@types/node/26.4.1` → integrity `sha512-k97ENvZ…`; `cd sim && pnpm exec tsc --noEmit` → exit 0, 0 error, sedangkan dengan `--typeRoots <dir kosong>` (simulasi paket ini tidak ada) → 6× TS2591 `Cannot find name 'node:fs'/'node:path'/'node:url'`. CATATAN JUJUR: pada layout pnpm hari ini `sim/node_modules/@types` HANYA berisi `node` → 26.4.1 dan `node_modules/@types/` root tidak ada, jadi menghapus `types: ["node"]` saat ini menghasilkan 0 error juga (diukur, dengan maupun tanpa `skipLibCheck`) — angka "39 error" TIDAK tereproduksi di sini; setelan itu bersifat preventif, bukan penahan aktif hari ini |
| next | 16.3.2 | App Router |
| react / react-dom | 19.2.8 | — |
| viem | 2.55.19 | **bukan** 3.0.0-next (prerelease) |
| wagmi | 3.7.6 | butuh @tanstack/react-query |
| @tanstack/react-query | 5.102.2 | — |
| @virtuals-protocol/acp-node-v2 | 0.1.12 | peer deps: viem, @account-kit/infra (4.88.5). Terpasang & dicocokkan 2026-09-07: `realpath sim/node_modules/@virtuals-protocol/acp-node-v2` → `.pnpm/@virtuals-protocol+acp-node-v2@0.1.12_...`, `package.json` `"version": "0.1.12"`. Permukaan chainId/alamat/token: api-facts §B.2 |
| vitest | 4.1.11 | bukan 5.0.0-rc |
| tailwindcss | **4.3.3** | devDependency `web/` saja. Dipin PERSIS (bukan `^`). Diverifikasi 2026-09-10: `node -e "require('web/node_modules/tailwindcss/package.json').version"` → `4.3.3`; `pnpm view tailwindcss version` → `4.3.3`. Tidak ada `tailwind.config.js`: di v4 seluruh token hidup di `@theme inline` dalam `web/src/app/globals.css`, jadi hanya ada SATU sumber sistem desain |
| @tailwindcss/postcss | **4.3.3** | devDependency `web/` saja; plugin PostCSS resmi Tailwind v4, dipasang lewat `web/postcss.config.mjs`. Versinya WAJIB sama dengan `tailwindcss` |
| motion | **12.43.0** | dependency `web/`. Penerus `framer-motion`; dipakai untuk transisi state di `ExecutionRoom` dan penanda nav yang bergeser. Major line 12 dipilih supaya sama dengan frontend rujukan Veritas-UHI9 (`^12.40.0`), **13.x = ganti major line → wajib ADR**. `AnimatePresence` SENGAJA tidak dipakai di mana pun (ADR-032 keputusan 4) |
| lucide-react | **1.43.0** | dependency `web/`. Menggantikan `web/src/components/Icon.jsx` (7 path Lucide yang di-inline tangan). Ikon Referi kini datang dari satu pustaka dengan bobot garis seragam, sama seperti frontend rujukan |
| clsx | **2.1.1** | dependency `web/`. Penggabung kelas kondisional; dipakai HANYA lewat `cn()` di `web/src/lib/utils.js` |
| tailwind-merge | **3.6.0** | dependency `web/`. Membuat override kelas dari pemanggil benar-benar menang atas kelas bawaan komponen; dipakai HANYA lewat `cn()` |

## Python (agent/)
| Paket | Versi | Catatan |
|---|---|---|
| sibyl-memory-client | **0.7.0** | python ≥3.10; verifikasi signature metode dengan `inspect.signature` sebelum dipakai. Registry dibaca 2026-09-06 (`curl -s https://pypi.org/pypi/sibyl-memory-client/json`): versi TERBARU kini **0.8.0** (unggah 2026-08-31) — pin TETAP 0.7.0, naik ke 0.8.0 = ganti minor line pada paket yang menopang seluruh `docs/api-facts.md` §C/§C.1/§C.2 → **wajib ADR + verifikasi ulang signature**. Cap free tier **5.242.880 B ditegakkan lokal dan TERBUKTI dipicu** (`CapExceededError`, api-facts §C.3); pemakaian kita ~12% dari cap. Klaim panitia "Pro tier active for the hackathon" (halaman tim, hanya tangkapan layar — URL-nya HTTP 404 tanpa login) TIDAK menjangkau jalur kita: `MemoryClient.local()` berjalan TIDAK teraktivasi (`account_id=None`), jadi cap free adalah satu-satunya cabang yang terjangkau. Jangan tulis "cap kita terangkat" di README/video/post |
| sibyl-memory-cli / -mcp / -langgraph / -hermes | **TIDAK DIPASANG** | PyPI 2026-09-06: cli **0.4.0**, mcp **0.2.0**, langgraph **0.2.0** (MIT, ≥3.10). Perkakas BUILDER (`sibyl setup` menyambungkan Claude Code/Codex/Hermes ke memori), BUKAN jalur submission — docs resmi `docs.sibyllabs.org/memory/integrations` memetakan "Your own Python → `sibyl-memory-client` → `import MemoryClient`", dan `hack.sibyllabs.org/rules` §08 tidak menuntut akun plugin. **Blokir keras:** `sibyl-memory-cli` 0.4.0 `requires_dist` memuat `sibyl-memory-client>=0.8.0` → memasangnya MEMAKSA pin 0.7.0 naik. Memasang salah satunya = keputusan PM + ADR. Rincian: api-facts §C.3 blok F |
| web3 | 7.16.0 | python ≥3.8,<4. Terpasang di `agent/.venv` dan DICOCOKKAN 2026-09-05: `agent/.venv/bin/python -c "import importlib.metadata as m; print(m.version('web3'))"` → `7.16.0` (Python 3.13.15, eth-abi 6.0.0). Signature yang boleh dipakai: `docs/api-facts.md` §F |
| anthropic | **1.0.0** | major baru (0.x→1.x) — baca changelog sebelum pakai; model default `claude-sonnet-5` |
| pydantic | 2.13.4 | skema kriteria/verdict |
| httpx | 0.28.1 | ambil deliverable off-chain |
| pytest | 9.1.1 | — |
| ruff | latest | versi persis tidak diverifikasi |
| x402 (server/facilitator lib) | **TIDAK DIPASANG — ADR-010** | Diverifikasi 2026-09-06: paket resminya ADA — PyPI `x402` **2.22.0** (author "x402 Foundation", MIT, `requires_python >=3.10`, classifier "Development Status :: 3 - Alpha", wheel 2026-09-04, `curl -s https://pypi.org/pypi/x402/json`); npm `x402` **1.2.0** dan npm `@coinbase/x402` **2.1.0** (`registry.npmjs.org/<pkg>/latest`). Middleware-nya HANYA FastAPI/Flask: `x402.http.middleware.fastapi.payment_middleware(routes, server, paywall_config=None, paywall_provider=None, sync_facilitator_on_start=True)` dan `x402.http.middleware.flask.payment_middleware(app, routes, server, paywall_config=None, paywall_provider=None, sync_facilitator_on_start=True)` (dibaca dari isi wheel 2.22.0, `x402/http/middleware/`). TIDAK dipakai: skema `exact` EVM-nya butuh EIP-3009 `transferWithAuthorization`, dan token escrow ACP `0xECc22a8F6fD62388498fBa19813E214605a2BDb3` NOL selector `0xe3ee160e`/`0x3644e515` di bytecode terdeploy (kontrol positif `0xa9059cbb` → 1). Memasangnya = dependensi baru dan WAJIB ADR yang membalikkan ADR-010. Task 2.6 memakai middleware 402 buatan sendiri (stdlib `http.server` + web3 7.16.0). |

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
| **EvaluatorVault (kontrak KITA) Base Sepolia** | **0x5c6EE4586ACABcb6326069c229E58091B21ef384**. Deploy tx `0xfcf339e2732f60809bd8c86232ccc386e9cb5285edb285e355fb2ca1fe98b601`, blok 46350667, status 1, gasUsed 816969, `effectiveGasPrice` 6.000.000 wei, deployer/`from` = 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894 (`cast receipt … --rpc-url https://sepolia.base.org`, 2026-09-04). Immutable on-chain: `acp()` = ACP Base Sepolia, `agent()` = `arbiter()` = 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894 (**agent == arbiter pada deploy ini, dan tetap begitu SELAMANYA**: ADR-022 membekukan alamat ini sebagai kontrak submission dan kontraknya immutable, jadi tidak ada redeploy yang akan memisahkannya. Pemisahan itu TIDAK diperlukan di sini: pada vault v1 arbiter TANPA wewenang on-chain apa pun. Diverifikasi langsung ke chain 2026-09-06: `cast call <vault> "resolve(uint256,bool)" 1 true --from <arbiter>` → revert `0xd6234725` = `NotImplemented()` (ADR-013), dan selector `sweepToken(address,address)` `0x258836fe` NOL kemunculan di `cast code <vault>` (sementara `resolve` `0x52a34b05` dan `NotImplemented()` `0xd6234725` ADA). Rincian: `deployments/84532.json`), `MIN_BOND()` = 0; konstanta `CHALLENGE_WINDOW()` = 120, `MIN_ACP_GAS()` = 300000, `KIND_COMPLETE()` = 1, `KIND_REJECT()` = 2. Catatan deploy: `deployments/84532.json` |
| ACP Base mainnet | 0x238E541BfefD82238730D00a2208E5497F1832E0 |
| Fee ACP Base Sepolia | `platformFeeBP()` = 100 (1%), `evaluatorFeeBP()` = 500 (5%), `platformTreasury()` = 0xb3bdEdda2050a3615B73bB9a2684946eC38B5375 |
| Tenggang evaluator ACP | `EVALUATOR_GRACE_PERIOD()` = **900** detik (15 menit) — dibaca 2026-09-03 via `cast call <ACP> "EVALUATOR_GRACE_PERIOD()(uint256)"`. Setelah `expiredAt + 900`, SIAPA PUN boleh `claimRefund` job berstatus Submitted dan membatalkan verdict evaluator. Konstanta ini membatasi anggaran waktu vault; lihat `docs/api-facts.md` §A |
| Batas RPC publik | `eth_getLogs`: yang dibatasi adalah SELISIH `toBlock - fromBlock`. Selisih **<= 10.000 DITERIMA** (10.001 blok inklusif), selisih **>= 10.001 → HTTP 413** + body `{"code":-32614,"message":"eth_getLogs is limited to a 10,000 range"}`. Bisection 2026-09-05 (D = 9998/9999/10000 → 200; D = 10001/19999/49999/50000/99999 → 413) di `https://sepolia.base.org`. Lewat web3.py galat ini muncul sebagai `requests.exceptions.HTTPError: 413 …`, BUKAN error JSON-RPC — rincian `docs/api-facts.md` §E |

## Model Claude (API) — platform.claude.com/docs/en/about-claude/models/overview
`claude-sonnet-5` (default rubric LLM; 1M ctx), `claude-opus-5`, `claude-fable-5`, `claude-haiku-4-5`. ID tanpa akhiran tanggal.
