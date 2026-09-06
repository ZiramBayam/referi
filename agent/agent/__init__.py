"""Paket `agent` — seluruh kode evaluator (spec §6: watcher, criteria, checks/, memory_policy,
vault_client, judge_llm, x402_server, main) tinggal DI SINI, satu paket datar tanpa shim.

SATU NAMA BERBEDA dari daftar spec §6 itu, sengaja: `x402_server` mendarat sebagai
`payment_402.py` (task 2.6). ADR-010 melarang mengklaim kompatibilitas x402 — endpoint kita
tidak memahami header `X-PAYMENT` EIP-3009 — dan sebuah file bernama `x402_server.py` adalah
undangan paling murah untuk klaim itu. Alasan lengkapnya di docstring `payment_402.py`.

Layout dipilih sadar di task 2.0 (T13): direktori paket `agent/agent/`, TANPA `src/` dan tanpa
build backend, sehingga `import agent.<modul>` bekerja dari root `agent/` lewat `pythonpath`
pytest dan lewat `python -m` (cwd ada di `sys.path`). Manipulasi sys.path DILARANG di seluruh paket.
"""
