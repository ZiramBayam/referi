.PHONY: doctor test demo
doctor:
	@echo "node   : $$(node -v 2>/dev/null || echo MISSING)  (harus v24.x LTS)"
	@echo "pnpm   : $$(pnpm -v 2>/dev/null || echo MISSING)"
	@echo "python : $$( $$(uv python find 2>/dev/null || echo false) --version 2>/dev/null || echo MISSING)  (harus 3.13.x, via uv + .python-version)"
	@echo "uv     : $$(uv --version 2>/dev/null || echo MISSING)"
	@echo "forge  : $$(forge --version 2>/dev/null | head -1 || echo MISSING)  (harus 1.7.1)"
	@echo "solc   : lihat contracts/foundry.toml (0.8.36, evm osaka)"
test:
	cd contracts && forge test
	cd agent && uv run pytest
	pnpm -r test
demo:
	@echo "Belum tersedia."

-include Makefile.local
