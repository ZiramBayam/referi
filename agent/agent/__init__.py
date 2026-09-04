"""Paket `agent` — seluruh kode evaluator (spec §6: watcher, criteria, checks/, memory_policy,
vault_client, judge_llm, x402_server, main) tinggal DI SINI, satu paket datar tanpa shim.

Layout dipilih sadar di task 2.0 (T13): direktori paket `agent/agent/`, TANPA `src/` dan tanpa
build backend, sehingga `import agent.<modul>` bekerja dari root `agent/` lewat `pythonpath`
pytest dan lewat `python -m` (cwd ada di `sys.path`). Manipulasi sys.path DILARANG di seluruh paket.
"""
