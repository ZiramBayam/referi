.PHONY: doctor test demo demo-passport deploy-passport dual-gate virtuals-evidence passport-request
# doctor: cetak versi toolchain DAN gagal keras (exit 1) bila tidak cocok docs/versions.md.
# Ambang sengaja major/minor saja (lihat "Ambang ADR" di docs/versions.md): drift patch tidak
# memerahkan gate. Kecuali forge, yang dipin persis karena memengaruhi bytecode.
# Python dibaca lewat `uv python find`, BUKAN `python3` polos — /usr/bin/python3 di mesin dev
# bisa 3.12.x dan akan memberi merah palsu.
doctor:
	@FAIL=""; \
	v=$$(node -v 2>/dev/null); \
	case "$$v" in v24.*) ;; "") v=MISSING; FAIL="$$FAIL node";; *) FAIL="$$FAIL node";; esac; \
	echo "node   : $$v  (harus v24.x LTS)"; \
	v=$$(pnpm -v 2>/dev/null); \
	case "$$v" in 11.*) ;; "") v=MISSING; FAIL="$$FAIL pnpm";; *) FAIL="$$FAIL pnpm";; esac; \
	echo "pnpm   : $$v  (harus 11.x — mayor dipin; ganti mayor = ADR, docs/versions.md)"; \
	py=$$(uv python find 2>/dev/null); \
	v=$$([ -n "$$py" ] && "$$py" --version 2>/dev/null); \
	case "$$v" in "Python 3.13."*) ;; "") v=MISSING; FAIL="$$FAIL python";; *) FAIL="$$FAIL python";; esac; \
	echo "python : $$v  (harus 3.13.x, via uv — bukan /usr/bin/python3)"; \
	v=$$(uv --version 2>/dev/null); \
	case "$$v" in "uv 0.12."*) ;; "") v=MISSING; FAIL="$$FAIL uv";; *) FAIL="$$FAIL uv";; esac; \
	echo "uv     : $$v  (harus 0.12.x)"; \
	v=$$(forge --version 2>/dev/null | head -1); \
	case "$$v" in *" 1.7.1") ;; *" 1.7.1 "*) ;; "") v=MISSING; FAIL="$$FAIL forge";; *) FAIL="$$FAIL forge";; esac; \
	echo "forge  : $$v  (harus 1.7.1 persis)"; \
	if [ -f contracts/foundry.toml ]; then \
	  echo "solc   : lihat contracts/foundry.toml (0.8.36, evm osaka)"; \
	else \
	  echo "solc   : contracts/ belum ada — dicek saat kontrak dibuat"; \
	fi; \
	if [ -n "$$FAIL" ]; then \
	  echo ""; \
	  echo "DOCTOR MERAH:$$FAIL — tidak cocok docs/versions.md. Perbaiki toolchain, jangan ubah pin tanpa ADR."; \
	  echo "(dipanggil dari hook/non-interaktif? cek PATH dulu: nvm & foundry dimuat SETELAH guard di ~/.bashrc,"; \
	  echo " jadi hanya shell interaktif yang melihatnya — lihat docs/versions.md)"; \
	  exit 1; \
	fi; \
	echo ""; \
	echo "DOCTOR HIJAU — semua cocok docs/versions.md"
test:
	cd contracts && forge test
	cd agent && uv run pytest
	pnpm -r test
# demo: naskah docs/spec.md §7 langkah 1-4 DARI NOL di Anvil lokal, lalu bongkar lagi.
#
# Langkah 1-4 varian A berjalan sepenuhnya lokal: `sim/src/demo.ts` menyalakan
# `anvil --chain-id 84532` di 127.0.0.1, men-deploy mock ACP + MockUSDC + EvaluatorVault, lalu
# menjalankan sim dan agen di atasnya. chainId 84532 WAJIB (bukan 31337): SDK Virtuals memetakan
# chainId lewat registri bawaannya dan gagal-tertutup untuk id yang tidak terdaftar.
#
# BUTUH INTERNET: varian B membaca vault BEKU di Base Sepolia (https://sepolia.base.org) — NOL
# dana, NOL transaksi, NOL kunci privat, hanya dua pembacaan view. Syarat itu diperiksa PREFLIGHT
# di detik pertama, sebelum anvil menyala; tanpa jaringan demo berhenti di situ dengan exit 1
# alih-alih membuang beberapa menit lebih dulu. Kegagalannya memang keras: melewati varian B dan
# tetap keluar 0 berarti mencetak klaim mode aman yang tidak pernah dibaca dari chain.
#
# `SIBYL_DB_PATH`, `VERDICT_BUNDLE_DIR`, dan `DELIVERABLE_DIR` diteruskan EKSPLISIT oleh skrip
# itu ke `agent/data/demo/`, dan TIDAK PERNAH diwarisi dari `.env` — `.env` repo ini menunjuk
# memori operasional yang terikat vault Base Sepolia.
#
# Butuh `anvil`/`forge` (foundry), `node`/`pnpm`, dan `uv` di PATH: jalankan dari shell
# INTERAKTIF, alasan yang sama dengan `make doctor`.
demo:
	cd sim && pnpm run demo

# Execution Passport MVP: isolated Anvil + mock treasury/verifier + Sibyl memory loop.
# No real funds, external RPC, or frontend is used. The Python demo stops its own Anvil.
# Kunci akun 0 Anvil, diterbitkan Foundry dan sengaja publik. Ia hidup di sini, bukan di
# dalam modul Python, supaya penjaga "nol konstanta 32-byte di agent/**.py" di
# tests/test_verdict_root.py tetap berlaku tanpa satu pun pengecualian. Lihat komentar di
# agent/agent/passport_demo.py.
PASSPORT_DEMO_KEY ?= 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

demo-passport:
	cd agent && PASSPORT_DEMO_KEY=$(PASSPORT_DEMO_KEY) uv run python -m agent.passport_demo --start-anvil

# Satu-satunya entrypoint deploy yang sah (ADR-016).
#
# WAJIB diberi wallet lewat ARGS, contoh:
#   make deploy ARGS="--account agent --sender 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894"
# Keystore dibuat sekali oleh user: `cast wallet import agent --interactive`.
# Tanpa flag wallet, forge berhenti di default sender SEBELUM broadcast (nol transaksi terkirim),
# jadi lupa memberinya tidak bisa berakhir jadi deploy yang salah.
#
# `--json` tetap DILARANG sebagai pertahanan BERLAPIS. Catatan: sejak ADR-016 tahap 2 skrip TIDAK
# lagi menyerahkan kunci sebagai argumen cheatcode (`_envPrivateKey`/`_parsePrivateKey` dihapus,
# `vm.startBroadcast()` tanpa argumen, `deployer` dari `msg.sender`), jadi MOTIF kebocoran sudah
# hilang di akarnya — larangan ini dipertahankan supaya kanalnya tetap tertutup bila kelak ada
# cheatcode pembawa rahasia yang masuk lagi. JANGAN dicabut hanya karena akarnya sudah ditambal.
# Alamat vault TIDAK butuh --json: pakai target `deploy-address` di bawah.
deploy:
	@case " $(ARGS) " in \
	  *" --json"*|*"--json "*|*"--json="*) \
	    echo "DITOLAK: --json membocorkan private key lewat calldata cheatcode (ADR-016)." >&2; \
	    echo "Alamat vault: jalankan 'make deploy-address'." >&2; \
	    exit 1;; \
	esac; \
	cd contracts && forge script script/Deploy.s.sol:Deploy --rpc-url $${RPC_URL:-https://sepolia.base.org} --broadcast $(ARGS)

# Baca alamat hasil deploy dari artefak broadcast (berisi transaksi, bukan calldata cheatcode).
deploy-address:
	@python3 -c "import json;d=json.load(open('contracts/broadcast/Deploy.s.sol/84532/run-latest.json'));\
print([t['contractAddress'] for t in d['transactions'] if t.get('contractName')=='EvaluatorVault'][0])"

-include Makefile.local

# Broadcast fixture Execution Passport ke Base Sepolia (ADR-033).
#
# Kunci privat TIDAK pernah masuk ke perintah ini. Ia dibaca Foundry dari keystore
# TERENKRIPSI, dan Foundry sendiri yang meminta passphrase-nya secara interaktif
# (ADR-016). `--sender` sengaja ditulis sebagai alamat LITERAL, bukan hasil
# substitusi perintah. Buat keystore-nya sekali:
#
#   cast wallet import agent --interactive
#
# Jalankan simulasi lebih dulu bila ragu: hapus `--broadcast`.
# WAJIB memenuhi tiga hal sekaligus, dan kegagalan salah satunya baru terlihat saat
# broadcast: (1) sama dengan AGENT_ADDRESS di .env, (2) punya keystore bernama `agent`,
# (3) PUNYA SALDO ETH di jaringan target. Ia juga menjadi `policySigner` verifier secara
# default, artinya HANYA tanda tangan alamat ini yang akan diterima passport verifier
# seumur hidup kontrak itu. Set POLICY_SIGNER bila penanda tangan passport beda wallet.
DEPLOY_SENDER ?= 0xfA4F11Ec0e0C060D0471028633B954a7CA739911
DEPLOY_RPC    ?= https://sepolia.base.org

deploy-passport:
	cd contracts && forge script script/DeployPassport.s.sol:DeployPassport \
		--rpc-url $(DEPLOY_RPC) --broadcast \
		--account agent --sender $(DEPLOY_SENDER)

# Laporan baca-saja: satu memori Sibyl melayani gerbang ACP dan gerbang passport, dan
# root yang diumumkan on-chain mengikat keduanya. Nol jaringan, nol transaksi, nol kunci.
dual-gate:
	cd agent && uv run python -m agent.dual_gate_report

# Bukti baca-saja bahwa gerbang Virtuals berjalan di chain: membaca kontrak ACP asli di
# Base Sepolia dan mencocokkannya dengan jobs.json. BUTUH jaringan. Nol transaksi, nol kunci.
virtuals-evidence:
	cd agent && uv run python -m agent.virtuals_evidence

# Minta passport untuk SATU executor dari memori operasional gerbang ACP (SIBYL_DB_PATH). Tanpa
# SIGNER_KEY_ENV/EXECUTOR_KEY_ENV: nol tanda tangan, nol transaksi (RPC hanya dibaca untuk anchor).
# Contoh: make passport-request EXECUTOR=0xc3c6... SIGNER_KEY_ENV=PASSPORT_SIGNER_KEY EXECUTOR_KEY_ENV=PROVIDER2_PRIVATE_KEY
passport-request:
	cd agent && uv run python -m agent.passport_request --executor $(EXECUTOR) \
		$(if $(SIGNER_KEY_ENV),--signer-key-env $(SIGNER_KEY_ENV),) \
		$(if $(EXECUTOR_KEY_ENV),--executor-key-env $(EXECUTOR_KEY_ENV),)
