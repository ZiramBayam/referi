.PHONY: doctor test demo
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
	case "$$v" in "") v=MISSING; FAIL="$$FAIL pnpm";; esac; \
	echo "pnpm   : $$v  (pin = latest via corepack)"; \
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
demo:
	@echo "Belum tersedia."

# Satu-satunya entrypoint deploy yang sah (ADR-016).
# `--json` DILARANG: forge mendump calldata cheatcode MENTAH tanpa sensor, dan Deploy.s.sol
# menyerahkan kunci sebagai argumen cheatcode (vm.addr, vm.startBroadcast), sehingga kunci privat
# UTUH tercetak 2x per run ke stdout — pada jalur SUKSES, di verbositas DEFAULT.
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
