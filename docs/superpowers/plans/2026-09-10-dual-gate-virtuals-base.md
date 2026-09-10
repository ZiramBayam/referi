# Dual Gate: making the Virtuals half of Referi visible and load bearing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Referi legible and provable as one memory system with two enforcement gates, one on Virtuals ACP and one on Base, so a judge can confirm both halves are doing real work.

**Architecture:** Referi already stores the ACP evaluator's provider profiles and the Execution Passport's Control Hypothesis in the *same* Sibyl store, under the *same* `pattern:` reference namespace, anchored by the *same* `memory_root_for_onchain` function. That link exists in code today but is invisible from every artifact. This plan proves it with tests, exposes it with two read-only commands, rewrites the artifacts around it, and then evaluates one optional functional link under a hard stop gate.

**Tech Stack:** Python 3.13 (`uv`), `sibyl-memory-client` 0.7.0, `web3` 7.16.0, Foundry (solc 0.8.36), Next.js 16 + Tailwind v4 (`pnpm`), Base Sepolia (chain 84532).

**Spec:** This document. Read [Context you must have](#context-you-must-have) before Task 1. There is no separate spec file.

---

## Global Constraints

Every task's requirements implicitly include this section. Violating any line here fails the task.

- **No em dash (`—`) anywhere.** Not in code, comments, docs, or UI copy. Use a comma, a period, a colon, or parentheses. En dash `–` is allowed only for numeric ranges. Two exceptions, both because the character is the thing being matched rather than punctuation: `agent/agent/checks/base.py` and `web/src/lib/checks.js`, where it sits inside a regex character class that strips it, and the `awk` verification commands in this plan, which search for it. Do not "fix" either; removing the character from a scanner that hunts for it breaks the scanner.
- **No new runtime dependency** without an ADR in `docs/decisions.md` and a pinned row in `docs/versions.md`. This plan needs none.
- **Run tests from the right directory.** Python: `cd agent && uv run pytest`. Contracts: `cd contracts && forge test`. Web: `cd web && pnpm test`. Running `forge` from the repo root fails with "invalid solc version" because `foundry.toml` lives in `contracts/`.
- **Do not modify `contracts/src/EvaluatorVault.sol` or redeploy it.** ADR-022 freezes `0x5c6EE4586ACABcb6326069c229E58091B21ef384` as the submission address.
- **Do not change `derive_cap`, `promote_suspicions`, or the suspicion promotion rules** in `agent/agent/memory_policy.py`. ADR-002 governs them. Task 5 assesses that link and explicitly stops rather than touching them.
- **Never put a private key in a command, an env var you set, or a file.** The repo's deploy path is a Foundry encrypted keystore (ADR-016). No task in this plan needs a key.
- **Provider addresses must be lowercase** when constructing a `ProviderProfile`. `load_snapshot` raises `MemoryIntegrityError` on a checksummed address. This will bite you in Task 1 if you paste an address from a block explorer.
- **Comments in `agent/` and `web/src/` are written in Indonesian**, matching the surrounding files. Prose in `README.md`, `docs/posts/`, `demo/`, and all UI copy is English.
- **Commit after every task.** Use conventional commit prefixes (`feat:`, `test:`, `docs:`, `chore:`).

---

## Context you must have

Read this once. Every task assumes it.

### What Referi is

Referi is a hackathon project with **two enforcement gates that share one memory**.

**Gate 1, on Virtuals ACP.** An evaluator agent watches ERC-8183 escrow jobs on the Virtuals Agent Commerce Protocol contract at `0x0b93793923CD5De81850aF8604a233f3f24d461e` (Base Sepolia). Sibyl memory decides how deeply a deliverable is checked and what budget cap a provider gets. Every verdict announces a `memoryRoot` on chain through `EvaluatorVault.postVerdict`. Five jobs (418 to 422) really ran.

**Gate 2, on Base.** The Execution Passport turns a past incident into deterministic proof obligations. Only when all four hold does the agent issue a single use, 60 second, EIP-712 passport bound to exact calldata. `PassportVerifier` at `0x43D978e26bEe32A8f2E2DaB1f212F9A36F5937C1` accepts it once.

### The link that already exists and is currently invisible

This is the single most important fact in this plan. It was verified empirically on 2026-09-10:

- The passport's Control Hypothesis is stored at the reference key `pattern:passport.control-hypothesis.stale-oracle-rebalance.v1` (`agent/agent/execution_passport.py:38-39`, constant `HYPOTHESIS_KEY`).
- `MemorySnapshot`, the preimage of the on-chain memory root, covers "all `provider` entities, all `reference:pattern:*`, all `reference:rubric:*`" (ADR-020 decision 7, `agent/agent/memory_policy.py:986-989`).
- Therefore **the memory root that `EvaluatorVault.postVerdict` announces on chain already commits to the passport gate's policy**, when both live in one store. Adding the hypothesis changes the root.

Verified output from a throwaway store holding both:

```
kunci pattern : ['pattern:passport.control-hypothesis.stale-oracle-rebalance.v1']
provider      : ['0x20212e4d95a75e6716575ed26e884cdeff66b321']
root berubah  : True
```

Nothing in the repo demonstrates this. Task 1 turns it into a test. Task 2 turns it into a command anyone can run.

### Addresses and constants you will need

| Thing | Value |
|---|---|
| RPC | `https://sepolia.base.org` |
| Chain id | `84532` |
| Virtuals ACP contract | `0x0b93793923CD5De81850aF8604a233f3f24d461e` |
| EvaluatorVault (frozen) | `0x5c6EE4586ACABcb6326069c229E58091B21ef384` |
| PassportVerifier | `0x43D978e26bEe32A8f2E2DaB1f212F9A36F5937C1` |
| MockTreasury | `0x68Cca28DceFAd1c7a73f97FACC74cD51B145772B` |
| MockOracle | `0x8b0e7572eDF67Fded93ff8dBFfD318d2E3D2bDe3` |
| Escrow token | `0xECc22a8F6fD62388498fBa19813E214605a2BDb3` |
| Explorer (use this one) | `https://base-sepolia.blockscout.com` |

Use Blockscout, not BaseScan: only Blockscout picks up the Sourcify verification, so only there does source show instead of bytecode.

Deployment records: `deployments/84532.json` (gate 1) and `deployments/passport-84532.json` (gate 2). Job data: `web/public/jobs.json`.

### Why this plan exists

The submission currently reads as a project that pivoted and abandoned half of itself. The scoring rubric (`docs/spec.md:58`) is: memory load-bearing 40, innovation 25, technical 20, pitch 15, PMF +10, multiplied by 1.15 for one stack or **1.25 for Base plus Virtuals, only if judges confirm the integration is doing real work**. Gate 2 mentions ACP zero times in seven files. This plan does not invent an integration; it proves and exposes the one that is already there.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `agent/tests/test_dual_gate_memory.py` | Locks the shared-root property between both gates. |
| `agent/agent/dual_gate_report.py` | Read-only report: one store, two gates, one root. Prints deterministic lines. |
| `agent/agent/virtuals_evidence.py` | Read-only on-chain check of the Virtuals ACP jobs. Needs network, no key, no transactions. |
| `agent/tests/test_virtuals_evidence.py` | Tests the parsing and formatting of the above against fixtures, with no network. |
| `docs/posts/04-2026-09-10-satu-memori-dua-gerbang.md` | Build-in-public post 4, the dual gate argument. |

**Modified:**

| File | Change |
|---|---|
| `Makefile` | Add `dual-gate` and `virtuals-evidence` targets. |
| `README.md` | Reframe from "we pivoted" to "one memory, two gates". |
| `docs/posts/03-2026-09-10-kenapa-kami-mengganti-arah-produk.md` | Soften the abandonment framing, point to post 4. |
| `demo/video-script.md` | Add a dual-gate beat to section 5. |
| `web/src/components/Landing.jsx` | Add a "two gates" section. |
| `docs/decisions.md` | ADR-034 recording the dual gate framing and its limits. |

---

## Task 1: Lock the shared memory root with a test

**Files:**
- Create: `agent/tests/test_dual_gate_memory.py`

**Interfaces:**
- Consumes: `agent.memory_policy` (`ProviderProfile`, `save_provider`, `load_snapshot`, `memory_root_for_onchain`), `agent.execution_passport` (`HYPOTHESIS_KEY`, `ActionProposal`, `IncidentEvidence`, `record_incident`, `REBALANCE_SELECTOR`).
- Produces: a helper `build_incident(target: str, amount: int) -> IncidentEvidence` used by Task 2's test, which appends to the same file. Signature is exact.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_dual_gate_memory.py`:

```python
"""Kedua gerbang berbagi SATU memori, dan root yang diumumkan on-chain mengikat keduanya.

Ini properti yang sudah benar di kode hari ini tetapi tidak dibuktikan di mana pun. Tanpa
tes ini, memindahkan Control Hypothesis keluar dari namespace `pattern:` akan memutus
klaim terbesar submission tanpa satu pun tes memerah.
"""

from __future__ import annotations

import pathlib

from eth_abi import encode as abi_encode
from sibyl_memory_client import MemoryClient
from web3 import Web3

import agent.execution_passport as ep
import agent.memory_policy as mp

# Provider Beta dari `.env.example`. HURUF KECIL wajib: `load_snapshot` menolak alamat
# ber-checksum karena ia akan dijangkar root tetapi tidak pernah dibaca jalur keputusan.
PROVIDER = "0x20212e4d95a75e6716575ed26e884cdeff66b321"
TREASURY = "0x68Cca28DceFAd1c7a73f97FACC74cD51B145772B"


def build_incident(target: str, amount: int) -> ep.IncidentEvidence:
    """Bukti insiden oracle basi yang deterministik, dipakai kedua tes lintas gerbang."""
    calldata = "0x" + (ep.REBALANCE_SELECTOR + abi_encode(["uint256"], [amount])).hex()
    action = ep.ActionProposal(
        chain_id=84532,
        target=target,
        selector="0x" + ep.REBALANCE_SELECTOR.hex(),
        calldata=calldata,
        value=0,
        state_block_number=100,
        state_block_hash=Web3.to_hex(Web3.keccak(text=f"anchor:{amount}")),
    )
    return ep.IncidentEvidence(
        incident_id=f"dual-gate-{amount}",
        incident_type="stale-oracle-rebalance",
        action=action,
        oracle_timestamp=1_000,
        observed_at=1_120,
        evidence_digest=Web3.to_hex(Web3.keccak(text=action.action_digest)),
    )


def _store(tmp_path: pathlib.Path) -> MemoryClient:
    return MemoryClient.local(str(tmp_path / "dual-gate.db"))


def test_one_store_holds_both_gates(tmp_path):
    client = _store(tmp_path)
    mp.save_provider(client, mp.ProviderProfile(address=PROVIDER, risk_level=1))
    ep.record_incident(client, build_incident(TREASURY, 100_000))

    snapshot = mp.load_snapshot(client)

    assert PROVIDER in snapshot.providers, "profil provider gerbang ACP hilang dari snapshot"
    assert ep.HYPOTHESIS_KEY in snapshot.patterns, "hipotesis gerbang passport hilang dari snapshot"


def test_onchain_root_commits_to_the_passport_gate(tmp_path):
    client = _store(tmp_path)
    mp.save_provider(client, mp.ProviderProfile(address=PROVIDER, risk_level=1))
    root_before = mp.memory_root_for_onchain(client)

    ep.record_incident(client, build_incident(TREASURY, 100_000))
    root_after = mp.memory_root_for_onchain(client)

    # Kalau ini pernah gagal, artinya hipotesis passport keluar dari preimage root, dan
    # root yang diumumkan `postVerdict` berhenti mengikat kebijakan gerbang Base.
    assert root_before != root_after
    assert len(root_after) == 32


def test_passport_hypothesis_lives_in_the_shared_pattern_namespace():
    # Bukan detail penamaan: prefix inilah yang membuat hipotesis masuk `MemorySnapshot`
    # (ADR-020 keputusan 7). Memindahkannya keluar memutus jangkar on-chain.
    assert ep.HYPOTHESIS_KEY.startswith(mp.REFERENCE_PATTERN_PREFIX)


def test_deleting_the_hypothesis_moves_the_root_back(tmp_path):
    client = _store(tmp_path)
    mp.save_provider(client, mp.ProviderProfile(address=PROVIDER, risk_level=1))
    baseline = mp.memory_root_for_onchain(client)

    ep.record_incident(client, build_incident(TREASURY, 100_000))
    assert mp.memory_root_for_onchain(client) != baseline

    ep.delete_control_hypothesis(client)
    assert mp.memory_root_for_onchain(client) == baseline
```

- [ ] **Step 2: Run the test**

Run: `cd agent && uv run pytest tests/test_dual_gate_memory.py -v`
Expected: 4 passed.

These tests document a property the code already has rather than driving new code, which is why they pass on first run. That is correct and intended: the property is currently true and completely unguarded, so one refactor could silently break the submission's largest claim. If any test FAILS, stop and report; something in the shared namespace has already drifted.

- [ ] **Step 3: Prove the tests can actually fail**

A test that cannot fail proves nothing. Verify the guard bites by temporarily breaking it:

```bash
cd agent && uv run python - <<'CHECK'
import pathlib, re
p = pathlib.Path("agent/execution_passport.py")
original = p.read_text()
broken = original.replace(
    'HYPOTHESIS_KEY: Final = f"{REFERENCE_PATTERN_PREFIX}{HYPOTHESIS_KEY_SUFFIX}"',
    'HYPOTHESIS_KEY: Final = f"orphan:{HYPOTHESIS_KEY_SUFFIX}"',
)
assert broken != original, "anchor tidak ditemukan, jangan lanjut"
p.write_text(broken)
print("sengaja dirusak, jalankan pytest sekarang")
CHECK
uv run pytest tests/test_dual_gate_memory.py -q
```

Expected: FAIL, at minimum `test_passport_hypothesis_lives_in_the_shared_pattern_namespace` and `test_onchain_root_commits_to_the_passport_gate`.

Then restore it immediately:

```bash
cd /Users/scientivan/Programming/Ramz/Referi && git checkout agent/agent/execution_passport.py
cd agent && uv run pytest tests/test_dual_gate_memory.py -q
```

Expected: 4 passed.

- [ ] **Step 4: Confirm the signature assumption held**

Run: `cd agent && uv run python -c "import inspect, agent.execution_passport as ep; print(inspect.signature(ep.delete_control_hypothesis))"`
Expected: `(client: 'Any') -> 'bool'`. If it differs, the fourth test's call needs adjusting to match. Do **not** change `delete_control_hypothesis` itself.

- [ ] **Step 5: Run the full Python suite to prove nothing regressed**

Run: `cd agent && uv run pytest -q`
Expected: `789 passed` or higher, `0 failed`. The baseline before this task is 782 passed.

- [ ] **Step 6: Commit**

```bash
git add agent/tests/test_dual_gate_memory.py
git commit -m "test: lock the shared memory root across both enforcement gates"
```

---

## Task 2: A report command that shows one store serving two gates

**Files:**
- Create: `agent/agent/dual_gate_report.py`
- Modify: `Makefile`
- Test: `agent/tests/test_dual_gate_memory.py` (append)

**Interfaces:**
- Consumes: `build_incident` from Task 1.
- Produces: module `agent.dual_gate_report` with `def report(db_path: str | None = None) -> list[str]` returning the printed lines, and a `main()` entrypoint. Task 3 quotes these line names in documentation, so do not rename them.

- [ ] **Step 1: Write the failing test**

Append to `agent/tests/test_dual_gate_memory.py`:

```python
def test_report_names_both_gates_and_one_root(tmp_path):
    from agent.dual_gate_report import report

    client = _store(tmp_path)
    mp.save_provider(client, mp.ProviderProfile(address=PROVIDER, risk_level=1))
    ep.record_incident(client, build_incident(TREASURY, 100_000))

    lines = report(str(tmp_path / "dual-gate.db"))
    joined = "\n".join(lines)

    assert "gate_acp_providers=1" in joined
    assert "gate_passport_hypotheses=1" in joined
    assert "shared_memory_root=0x" in joined
    assert "root_covers_both_gates=True" in joined
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd agent && uv run pytest tests/test_dual_gate_memory.py::test_report_names_both_gates_and_one_root -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.dual_gate_report'`

- [ ] **Step 3: Write the implementation**

Create `agent/agent/dual_gate_report.py`:

```python
"""Laporan baca-saja: satu memori, dua gerbang, satu root.

Kenapa berkas ini ada. Kedua gerbang Referi sudah berbagi satu store Sibyl dan satu
fungsi root, tetapi tidak ada satu pun perintah yang menunjukkannya. Argumen terbesar
submission karena itu hanya bisa dipercaya, tidak bisa diperiksa. Modul ini mengubahnya
jadi keluaran yang bisa dijalankan siapa pun.

Ia TIDAK menulis apa pun ke memori mana pun kecuali database sementara yang ia buat
sendiri saat dijalankan tanpa argumen, dan ia tidak menyentuh jaringan sama sekali.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from sibyl_memory_client import MemoryClient
from web3 import Web3

import agent.execution_passport as ep
import agent.memory_policy as mp

DEMO_PROVIDER = "0x20212e4d95a75e6716575ed26e884cdeff66b321"
DEMO_TREASURY = "0x68Cca28DceFAd1c7a73f97FACC74cD51B145772B"


def _seed_demo_store(db_path: Path) -> None:
    """Isi store contoh: satu provider gerbang ACP, satu hipotesis gerbang passport."""
    from eth_abi import encode as abi_encode

    client = MemoryClient.local(str(db_path))
    mp.save_provider(
        client, mp.ProviderProfile(address=DEMO_PROVIDER, risk_level=1, passed_budgets=(1_000,))
    )
    calldata = "0x" + (ep.REBALANCE_SELECTOR + abi_encode(["uint256"], [100_000])).hex()
    action = ep.ActionProposal(
        chain_id=84532,
        target=DEMO_TREASURY,
        selector="0x" + ep.REBALANCE_SELECTOR.hex(),
        calldata=calldata,
        value=0,
        state_block_number=100,
        state_block_hash=Web3.to_hex(Web3.keccak(text="dual-gate-anchor")),
    )
    ep.record_incident(
        client,
        ep.IncidentEvidence(
            incident_id="dual-gate-demo",
            incident_type="stale-oracle-rebalance",
            action=action,
            oracle_timestamp=1_000,
            observed_at=1_120,
            evidence_digest=Web3.to_hex(Web3.keccak(text=action.action_digest)),
        ),
    )


def report(db_path: str | None = None) -> list[str]:
    """Kembalikan baris laporan. Tanpa `db_path`, buat store contoh sementara."""
    temp_dir = None
    if db_path is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="referi-dual-gate-")
        path = Path(temp_dir.name) / "dual-gate.db"
        _seed_demo_store(path)
    else:
        path = Path(db_path)

    try:
        client = MemoryClient.local(str(path))
        snapshot = mp.load_snapshot(client)
        hypotheses = [k for k in snapshot.patterns if k.startswith(ep.HYPOTHESIS_KEY)]
        root = mp.memory_root_for_onchain(client)
        covers_both = bool(snapshot.providers) and bool(hypotheses)

        return [
            f"memory_db={path}",
            f"gate_acp_providers={len(snapshot.providers)}",
            f"gate_acp_provider_ids={','.join(sorted(snapshot.providers)) or 'none'}",
            f"gate_passport_hypotheses={len(hypotheses)}",
            f"gate_passport_keys={','.join(sorted(hypotheses)) or 'none'}",
            f"shared_pattern_namespace={mp.REFERENCE_PATTERN_PREFIX}",
            f"shared_memory_root=0x{root.hex()}",
            f"root_covers_both_gates={covers_both}",
            "root_function=agent.memory_policy.memory_root_for_onchain",
            "announced_onchain_by=EvaluatorVault.postVerdict(jobId,kind,reasonHash,memoryRoot)",
        ]
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="store Sibyl yang mau diperiksa")
    args = parser.parse_args()
    for line in report(args.db):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd agent && uv run pytest tests/test_dual_gate_memory.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run the command by hand and read the output**

Run: `cd agent && uv run python -m agent.dual_gate_report`

Expected: ten lines, with `gate_acp_providers=1`, `gate_passport_hypotheses=1`, and `root_covers_both_gates=True`. If any line reads `0` or `False`, stop and report; the seeding is wrong.

- [ ] **Step 6: Add the Makefile target**

In `Makefile`, find the line beginning `.PHONY:` and append `dual-gate` to it. Then add at the end of the file:

```makefile
# Laporan baca-saja: satu memori Sibyl melayani gerbang ACP dan gerbang passport, dan
# root yang diumumkan on-chain mengikat keduanya. Nol jaringan, nol transaksi, nol kunci.
dual-gate:
	cd agent && uv run python -m agent.dual_gate_report
```

- [ ] **Step 7: Verify the target**

Run: `make dual-gate`
Expected: the same ten lines.

- [ ] **Step 8: Commit**

```bash
git add agent/agent/dual_gate_report.py agent/tests/test_dual_gate_memory.py Makefile
git commit -m "feat: add dual-gate report showing one memory serving both gates"
```

---

## Task 3: A read-only command that verifies the Virtuals jobs on chain

**Files:**
- Create: `agent/agent/virtuals_evidence.py`
- Create: `agent/tests/test_virtuals_evidence.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `web/public/jobs.json` (fields per job: `jobId`, `provider`, `providerLabel`, `acpStatus`, `verdictKind`, `verdictTxHash`).
- Produces: module `agent.virtuals_evidence` with `def format_rows(jobs: list[dict], onchain: dict[int, dict]) -> list[str]` (pure, testable without network) and `def main() -> int` (does the RPC calls). Task 4 quotes the printed line names.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_virtuals_evidence.py`:

```python
"""Perintah bukti Virtuals: yang diuji adalah PEMBACAAN dan PEMBENTUKAN barisnya.

Panggilan RPC-nya sendiri tidak diuji: ia butuh jaringan, dan tes yang butuh jaringan
akan merah karena wifi juri, bukan karena kode kita. Yang dikunci di sini adalah bahwa
ketidakcocokan antara berkas dan chain DILAPORKAN, bukan disamarkan.
"""

from __future__ import annotations

from agent.virtuals_evidence import format_rows

JOBS = [
    {"jobId": "421", "provider": "0xc3c6Bf20ddE1a547a35f6479D54B08E1548dAeff",
     "providerLabel": "Beta", "acpStatus": 3, "verdictKind": 1,
     "verdictTxHash": "0x02356b07…8a1467"},
    {"jobId": "422", "provider": "0x20212E4D95A75E6716575ED26e884cdeFf66b321",
     "providerLabel": "Alpha", "acpStatus": 4, "verdictKind": 2,
     "verdictTxHash": "0xe95910d2…295830"},
]


def test_matching_job_reports_confirmed():
    onchain = {
        421: {"exists": True, "provider": "0xc3c6bf20dde1a547a35f6479d54b08e1548daeff"},
        422: {"exists": True, "provider": "0x20212e4d95a75e6716575ed26e884cdeff66b321"},
    }
    rows = format_rows(JOBS, onchain)
    joined = "\n".join(rows)

    assert "job=421 onchain=yes provider_match=yes" in joined
    assert "job=422 onchain=yes provider_match=yes" in joined
    assert "jobs_confirmed_onchain=2/2" in joined


def test_provider_mismatch_is_reported_not_hidden():
    onchain = {
        421: {"exists": True, "provider": "0x0000000000000000000000000000000000000001"},
        422: {"exists": True, "provider": "0x20212e4d95a75e6716575ed26e884cdeff66b321"},
    }
    rows = format_rows(JOBS, onchain)
    joined = "\n".join(rows)

    assert "job=421 onchain=yes provider_match=NO" in joined
    assert "jobs_confirmed_onchain=1/2" in joined


def test_missing_job_is_reported():
    onchain = {
        421: {"exists": False, "provider": None},
        422: {"exists": True, "provider": "0x20212e4d95a75e6716575ed26e884cdeff66b321"},
    }
    rows = format_rows(JOBS, onchain)
    joined = "\n".join(rows)

    assert "job=421 onchain=NO" in joined
    assert "jobs_confirmed_onchain=1/2" in joined
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd agent && uv run pytest tests/test_virtuals_evidence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.virtuals_evidence'`

- [ ] **Step 3: Write the implementation**

Create `agent/agent/virtuals_evidence.py`:

```python
"""Bukti baca-saja bahwa gerbang Virtuals benar-benar berjalan di chain.

Tanpa perintah ini, integrasi Virtuals hanya bisa dipercaya lewat tangkapan layar. Ia
membaca kontrak ACP Virtuals yang sungguhan di Base Sepolia dan membandingkan isinya
dengan berkas `web/public/jobs.json` yang dipakai situs.

NOL transaksi, NOL kunci, NOL tulisan ke chain maupun ke memori. Satu-satunya syaratnya
adalah akses jaringan ke RPC. Ketidakcocokan DILAPORKAN, tidak disamarkan: perintah yang
selalu hijau tidak membuktikan apa pun.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from web3 import Web3

ACP_ADDRESS = "0x0b93793923CD5De81850aF8604a233f3f24d461e"
EVALUATOR_VAULT = "0x5c6EE4586ACABcb6326069c229E58091B21ef384"
DEFAULT_RPC = "https://sepolia.base.org"
EXPLORER = "https://base-sepolia.blockscout.com"

# Hanya `jobs(uint256)` yang dipakai. ABI sengaja seminimal itu supaya perintah ini tidak
# ikut membeku pada bentuk ABI penuh yang bisa berubah di luar kendali kita.
ACP_MIN_ABI: list[dict[str, Any]] = [
    {
        "name": "jobs",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "jobId", "type": "uint256"}],
        "outputs": [
            {"name": "client", "type": "address"},
            {"name": "phase", "type": "address"},
            {"name": "provider", "type": "address"},
            {"name": "expiredAt", "type": "uint256"},
            {"name": "budget", "type": "uint256"},
            {"name": "status", "type": "uint8"},
        ],
    }
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_jobs() -> list[dict[str, Any]]:
    path = _repo_root() / "web" / "public" / "jobs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["jobs"])


def format_rows(jobs: list[dict[str, Any]], onchain: dict[int, dict[str, Any]]) -> list[str]:
    """Bentuk baris laporan. Murni, jadi ia bisa diuji tanpa jaringan sama sekali."""
    rows: list[str] = []
    confirmed = 0
    for job in jobs:
        job_id = int(job["jobId"])
        found = onchain.get(job_id, {"exists": False, "provider": None})
        if not found.get("exists"):
            rows.append(f"job={job_id} onchain=NO")
            continue
        expected = str(job["provider"]).lower()
        actual = str(found.get("provider") or "").lower()
        match = "yes" if expected == actual else "NO"
        if match == "yes":
            confirmed += 1
        rows.append(
            f"job={job_id} onchain=yes provider_match={match} "
            f"label={job.get('providerLabel', 'unknown')} acp_status={job.get('acpStatus')}"
        )
    rows.append(f"jobs_confirmed_onchain={confirmed}/{len(jobs)}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    args = parser.parse_args()

    w3 = Web3(Web3.HTTPProvider(args.rpc))
    if not w3.is_connected():
        print(f"rpc_unreachable={args.rpc}")
        print("Perintah ini butuh jaringan. Ia tidak pernah mengirim transaksi.")
        return 1

    contract = w3.eth.contract(address=Web3.to_checksum_address(ACP_ADDRESS), abi=ACP_MIN_ABI)
    jobs = load_jobs()
    onchain: dict[int, dict[str, Any]] = {}
    for job in jobs:
        job_id = int(job["jobId"])
        try:
            record = contract.functions.jobs(job_id).call()
            onchain[job_id] = {"exists": int(record[4]) > 0 or record[2] != ZERO, "provider": record[2]}
        except Exception as error:  # noqa: BLE001
            onchain[job_id] = {"exists": False, "provider": None, "error": str(error)}

    print(f"acp_contract={ACP_ADDRESS}")
    print(f"acp_contract_url={EXPLORER}/address/{ACP_ADDRESS}")
    print(f"evaluator_vault={EVALUATOR_VAULT}")
    print(f"chain_id={w3.eth.chain_id}")
    print(f"acp_bytecode_bytes={len(w3.eth.get_code(Web3.to_checksum_address(ACP_ADDRESS)))}")
    for line in format_rows(jobs, onchain):
        print(line)
    print("transactions_sent=0 keys_used=0")
    return 0


ZERO = "0x0000000000000000000000000000000000000000"


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd agent && uv run pytest tests/test_virtuals_evidence.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the real command against the network**

Run: `cd agent && uv run python -m agent.virtuals_evidence`

Expected: `jobs_confirmed_onchain=5/5`.

If it prints fewer than 5 or any `provider_match=NO`, **stop and report the exact output**. Do not adjust the expected value to match reality; the mismatch is the finding. The likely cause is that the `jobs(uint256)` tuple layout differs from `ACP_MIN_ABI`. Diagnose with:

```bash
cast call 0x0b93793923CD5De81850aF8604a233f3f24d461e \
  "jobs(uint256)(address,address,address,uint256,uint256,uint8)" 421 \
  --rpc-url https://sepolia.base.org
```

The third value is the provider address. Adjust `ACP_MIN_ABI` so the `provider` output sits at the same index, and re-run.

- [ ] **Step 6: Add the Makefile target**

Append `virtuals-evidence` to the `.PHONY:` line, then add at the end of `Makefile`:

```makefile
# Bukti baca-saja bahwa gerbang Virtuals berjalan di chain: membaca kontrak ACP asli di
# Base Sepolia dan mencocokkannya dengan jobs.json. BUTUH jaringan. Nol transaksi, nol kunci.
virtuals-evidence:
	cd agent && uv run python -m agent.virtuals_evidence
```

- [ ] **Step 7: Verify the target and the full suite**

Run: `make virtuals-evidence`
Expected: `jobs_confirmed_onchain=5/5`.

Run: `cd agent && uv run pytest -q`
Expected: `792 passed` or higher, `0 failed`.

- [ ] **Step 8: Commit**

```bash
git add agent/agent/virtuals_evidence.py agent/tests/test_virtuals_evidence.py Makefile
git commit -m "feat: add read-only on-chain verification of the Virtuals ACP jobs"
```

---

## Task 4: Reframe the artifacts around two gates

**Files:**
- Modify: `README.md`
- Modify: `docs/posts/03-2026-09-10-kenapa-kami-mengganti-arah-produk.md`
- Create: `docs/posts/04-2026-09-10-satu-memori-dua-gerbang.md`
- Modify: `demo/video-script.md`
- Modify: `web/src/components/Landing.jsx`
- Modify: `docs/decisions.md`

**Interfaces:**
- Consumes: the line names printed by `agent.dual_gate_report` (Task 2) and `agent.virtuals_evidence` (Task 3). Quote them exactly.
- Produces: nothing other tasks consume.

This task changes prose and one UI section. It changes no decision logic. Every claim it adds must be checkable by a command added in Tasks 2 or 3.

- [ ] **Step 1: Rewrite the README opening**

In `README.md`, replace the first paragraph after the `# REFERI` heading (currently beginning "**Proof before permission.** Referi turns a past incident") with:

```markdown
**Proof before permission.** Referi is one memory system with two enforcement gates.

Sibyl memory decides, and both gates read the same store through the same code. On
**Virtuals ACP**, memory sets how deeply a deliverable is checked and what budget cap a
provider gets, and every verdict announces the memory root on chain. On **Base**, that same
memory turns a past incident into deterministic proof obligations, and a treasury action
moves value only when all four hold.

The two are not neighbours, they are anchored together: the passport gate's Control
Hypothesis lives in the same `pattern:` reference namespace that `MemorySnapshot` covers,
so **the memory root that `EvaluatorVault.postVerdict` announces on chain commits to the
Base gate's policy too**. Run `make dual-gate` to see it.
```

- [ ] **Step 2: Replace the README "earlier direction" section heading and lead**

Find the heading `## The earlier direction: an escrow referee with recomputable memory` and replace that heading plus the paragraph beneath it (currently beginning "Everything below this line is the project Referi was before Execution Passport") with:

```markdown
## Gate 1, on Virtuals ACP

This is Referi's first enforcement gate. Development focus moved to the Base gate, and
this one is feature frozen, but it is not abandoned: it is deployed, it ran, and it is the
half that proves the memory argument on a live protocol.

Verify it yourself in one command, no key and no transaction:

```sh
make virtuals-evidence
```

It reads the real Virtuals ACP contract on Base Sepolia and confirms the five jobs against
`web/public/jobs.json`.
```

Then update the two internal links to that heading. Run this to find them:

```bash
grep -n "earlier-direction-an-escrow-referee" README.md
```

Replace each anchor with `#gate-1-on-virtuals-acp`.

- [ ] **Step 3: Verify the README has no em dash and no broken links**

Run:

```bash
awk '/—/{c++} END{print "em dash:", c+0}' README.md
python3 - <<'PY'
import re, pathlib
s = pathlib.Path("README.md").read_text()
missing = [m.group(1).split("#")[0] for m in re.finditer(r"\]\((?!https?:)([^)#]+)", s)]
print("missing:", sorted({t for t in missing if t and not pathlib.Path(t).exists()}) or "none")
PY
```

Expected: `em dash: 0` and `missing: none`.

- [ ] **Step 4: Soften post 03 and point it forward**

In `docs/posts/03-2026-09-10-kenapa-kami-mengganti-arah-produk.md`, replace the section heading `## What the escrow referee proved, and where it stopped` with `## What gate 1 proved, and where it stopped`, and append this at the very end of the file:

```markdown
## A correction to this post

Calling this a pivot was accurate about our attention and wrong about the architecture.
The two gates share one Sibyl store, one `pattern:` namespace, and one root function, and
the root the ACP gate announces on chain commits to the Base gate's policy. We did not
abandon half the project, we added a second enforcement point to the same memory. Post 4
shows the command that proves it.
```

- [ ] **Step 5: Write post 4**

Create `docs/posts/04-2026-09-10-satu-memori-dua-gerbang.md`:

```markdown
---
title: "One memory, two gates, and the root that ties them together"
date: 2026-09-10
project: REFERI (Sibyl hackathon, Base Sepolia)
repo: PassportVerifier 0x43D978e26bEe32A8f2E2DaB1f212F9A36F5937C1, EvaluatorVault 0x5c6EE4586ACABcb6326069c229E58091B21ef384
---

We spent a day describing this project as a pivot. That was wrong, and the fix is a
one-line command.

## Two gates

Referi enforces in two places. On **Virtuals ACP**, an evaluator reads a provider's history
out of Sibyl and uses it to set check depth and budget cap. Jobs 421 and 422 carry
byte-for-byte identical deliverables; 421 passed, 422 was rejected, and memory was the only
difference. On **Base**, the Execution Passport reads an incident out of the same Sibyl and
turns it into four proof obligations that a treasury action has to satisfy before it moves
value.

Different protocols, different failure modes, different contracts. We wrote about them as
two projects because that is how they felt to build.

## They were never two memories

The passport gate stores its Control Hypothesis at the reference key
`pattern:passport.control-hypothesis.stale-oracle-rebalance.v1`. The preimage of the
on-chain memory root covers every `provider` entity and every `reference:pattern:*` entry.

Read those two sentences together and the consequence falls out: **the memory root that
`EvaluatorVault.postVerdict` announces on the ACP gate already commits to the Base gate's
policy.** Change the passport's hypothesis and the root the evaluator announces changes.

We did not build that link this week. It has been true since the passport gate was written,
because both gates were built on the same memory primitives. We just never showed it.

## Now you can check it

```sh
make dual-gate
```

One store, seeded with a provider profile from gate 1 and a Control Hypothesis from gate 2.
It prints `gate_acp_providers`, `gate_passport_hypotheses`, the shared root, and
`root_covers_both_gates=True`. No network, no key.

```sh
make virtuals-evidence
```

Reads the real Virtuals ACP contract on Base Sepolia and confirms all five jobs against the
file the website serves. No transaction, no key.

## What we are not claiming

The Execution Passport does not send transactions to ACP. It guards treasury actions, not
escrow jobs, and pretending otherwise would be easy to check and false.

The ACP gate cannot post new verdicts right now either: we rotated the agent wallet, and
`EvaluatorVault.agent()` is immutable at the old address. The five jobs are history. The
local flow still runs end to end with `make demo`.

So the honest claim is narrow and, we think, more interesting than the wide one: two
enforcement surfaces, one memory, and a root on chain that binds both.
```

- [ ] **Step 6: Add a video beat**

In `demo/video-script.md`, find the row starting `| 3:48 |` and insert this row immediately after it:

```markdown
| 3:52 | Terminal: `make dual-gate` | ten lines, ending `root_covers_both_gates=True` | "One memory serves both. The root this evaluator announced on chain commits to the passport policy too, which is why these are two gates and not two projects." |
```

Then change the final row's timestamp from `4:00` to `4:10` and update the target duration near the top of the file from `4 minutes 05 seconds` to `4 minutes 15 seconds`, and the safe range from `3:50 to 4:20` to `4:00 to 4:30`.

- [ ] **Step 7: Add the two-gates section to the landing page**

In `web/src/components/Landing.jsx`, find `function DeployedOnChain()` and insert this component immediately **before** it:

```jsx
const GATES = [
  {
    name: "Gate 1 · Virtuals ACP",
    what: "Memory sets how deeply a deliverable is checked and what budget cap a provider gets.",
    proof: "Five jobs on the real ACP contract. Jobs 421 and 422 have identical text and opposite verdicts.",
    check: "make virtuals-evidence",
  },
  {
    name: "Gate 2 · Base",
    what: "Memory turns a past incident into four proof obligations a treasury action must satisfy.",
    proof: "PassportVerifier, MockTreasury, and MockOracle deployed and verified on Base Sepolia.",
    check: "make demo-passport",
  },
];

function TwoGates() {
  return (
    <section className="border-b border-border">
      <div className="mx-auto max-w-6xl px-5 py-20">
        <Reveal>
          <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
            <h2 className="font-display text-[clamp(1.8rem,3.5vw,2.6rem)] font-semibold leading-tight text-ink">
              One memory, two gates.
            </h2>
            <div className="flex flex-col gap-5 text-[15px] leading-relaxed text-muted lg:pt-2">
              <p>
                Referi enforces in two places, on two protocols, against two different failure
                modes. Both gates read the same Sibyl store through the same code.
              </p>
              <p className="text-ink">
                They are anchored together, not merely adjacent. The passport gate&apos;s Control
                Hypothesis lives in the same reference namespace the on-chain memory root commits
                to, so the root the ACP evaluator announces also commits to the Base gate&apos;s
                policy. Change one and the other&apos;s root changes.
              </p>
            </div>
          </div>
        </Reveal>

        <Reveal delay={0.08}>
          <ol className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-border bg-border md:grid-cols-2">
            {GATES.map((g) => (
              <li key={g.name} className="flex flex-col gap-4 bg-bg p-7">
                <h3 className="font-display text-xl font-semibold text-ink">{g.name}</h3>
                <p className="text-sm leading-relaxed text-muted">{g.what}</p>
                <p className="text-sm leading-relaxed text-ink">{g.proof}</p>
                <p className="mt-auto pt-2 font-mono text-xs text-primary-ink">{g.check}</p>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </section>
  );
}
```

Then add `<TwoGates />` to the `Landing` component's fragment, immediately after `<MemoryChangesCondition />` and before `<DeployedOnChain />`.

- [ ] **Step 8: Verify the web build and tests**

Run:

```bash
cd web && ./node_modules/.bin/tsc --noEmit -p tsconfig.lint.json && rm -rf .next && pnpm build && pnpm test
```

Expected: tsc silent, `Compiled successfully`, `pass 17`, `fail 0`.

- [ ] **Step 9: Write ADR-034**

Append to `docs/decisions.md`:

```markdown

## ADR-034 Referi disajikan sebagai satu memori dengan dua gerbang, bukan sebagai pivot
Tanggal: 2026-09-10. Status: diterima. Aditif; tidak mencabut ADR mana pun.

Konteks:
(a) Sejak arah produk berpindah ke Execution Passport, seluruh artefak menyajikan gerbang
    ACP sebagai pekerjaan yang ditinggalkan. Itu akurat soal fokus pengembangan dan KELIRU
    soal arsitekturnya.
(b) Diukur, bukan diduga: hipotesis kendali gerbang passport disimpan di
    `pattern:passport.control-hypothesis.stale-oracle-rebalance.v1`
    (`execution_passport.py` konstanta `HYPOTHESIS_KEY`), sedangkan cakupan `MemorySnapshot`
    adalah seluruh entity `provider` + seluruh `reference:pattern:*` + seluruh
    `reference:rubric:*` (ADR-020 keputusan 7). Konsekuensinya: root yang diumumkan
    `EvaluatorVault.postVerdict` MENGIKAT kebijakan gerbang Base.
(c) Properti itu benar sejak gerbang passport ditulis dan tidak pernah dibuktikan di mana pun.

Keputusan:
1. Artefak menyajikan Referi sebagai SATU sistem memori dengan DUA gerbang penegakan.
2. Setiap klaim tentang tautan itu harus punya perintah yang membuktikannya. Ditambahkan
   `make dual-gate` (nol jaringan) dan `make virtuals-evidence` (baca-saja, nol transaksi).
3. Properti root dikunci tes di `agent/tests/test_dual_gate_memory.py`, supaya memindahkan
   hipotesis keluar dari namespace `pattern:` memerahkan tes alih-alih diam-diam memutus
   klaim terbesar submission.
4. Batas yang DILARANG dikaburkan: Execution Passport TIDAK mengirim transaksi ke ACP, dan
   gerbang ACP TIDAK bisa memposting verdict baru dengan wallet sekarang karena
   `EvaluatorVault.agent()` immutable di alamat lama. Keduanya dinyatakan di post 04.

Konsekuensi:
(+) Argumen multiplier bersandar pada properti yang bisa diperiksa, bukan pada framing.
(-) Dua perintah dan satu berkas tes baru yang harus dijaga.
```

- [ ] **Step 10: Verify no em dash across every file this task touched**

Run:

```bash
for f in README.md demo/video-script.md docs/posts/03-*.md docs/posts/04-*.md \
         web/src/components/Landing.jsx; do
  printf "%-52s %s\n" "$f" "$(awk '/—/{c++} END{print c+0}' "$f")"
done
awk '/^## ADR-034/,0' docs/decisions.md | awk '/—/{c++} END{print "ADR-034:", c+0}'
```

Expected: every count `0`.

- [ ] **Step 11: Commit**

```bash
git add README.md demo/video-script.md docs/posts/ web/src/components/Landing.jsx docs/decisions.md
git commit -m "docs: present Referi as one memory with two enforcement gates"
```

---

## Task 5: Assess the optional functional link, then STOP

**Files:**
- Create: nothing yet.
- Read only: `agent/agent/memory_policy.py`, `agent/agent/execution_passport.py`, `docs/decisions.md` (ADR-002).

**Interfaces:**
- Consumes: everything from Tasks 1 to 4.
- Produces: a written assessment. **No code changes in this task.**

The idea under assessment: a treasury incident recorded by gate 2 should tighten a provider's budget cap at gate 1, so an agent that failed on Base becomes more constrained on ACP.

**This task must not implement anything.** It ends with a report and a recommendation. The reason is specific: `derive_cap` and the suspicion promotion rules are governed by ADR-002 and ADR-020, `memory_policy.py` is 129 KB with a 103 KB test file, and the submission is close. A change here that looks small can break the frozen root encoding or the quarantine rules.

- [ ] **Step 1: Read the three constraints that decide this**

Run:

```bash
cd /Users/scientivan/Programming/Ramz/Referi
sed -n "$(awk '/^## ADR-002/{print NR}' docs/decisions.md),+6p" docs/decisions.md
sed -n '1900,1925p' agent/agent/memory_policy.py
cd agent && uv run python -c "import inspect, agent.memory_policy as mp; print(inspect.signature(mp.record_failure_observation))"
```

Write down: what raises `risk_level`, what `derive_cap` actually consumes, and what `record_failure_observation` requires.

- [ ] **Step 2: Answer these four questions in writing**

1. Does `record_failure_observation` require an ACP `job_id`? A treasury incident has none. If yes, what would a truthful value be, and is inventing one acceptable? (Expected answer: no, it is not.)
2. Does raising `risk_level` from a treasury incident violate ADR-002's rule that promotion needs at least two distinct jobs with deterministic evidence?
3. Does `derive_cap`'s docstring constraint, that the only numeric input is budgets of jobs that actually passed, survive the change?
4. Would the change alter the frozen `memory_root` encoding? Check whether `MEMORY_ROOT_ENCODING_FROZEN` gates anything you would touch.

- [ ] **Step 3: Produce the recommendation**

Write your findings to `docs/agent-evaluations/2026-09-10-cross-gate-cap-link-assessment.md` with exactly three sections: `## What was checked`, `## What it would break`, `## Recommendation`.

The recommendation must be one of exactly these three, and must name which of the four answers decided it:

- **`safe-with-adr`**: no rule changes needed, only a new write path. Say precisely which function, which namespace, and which ADR must be written first.
- **`needs-rule-change`**: it requires touching ADR-002 or `derive_cap` semantics. Recommend deferring until after submission.
- **`not-worth-it`**: the link is cosmetic or the truthful `job_id` problem has no honest answer.

- [ ] **Step 4: STOP and report to the human**

Do not implement anything. Post the recommendation and wait.

If the recommendation is `safe-with-adr`, say so and ask whether to proceed, naming the estimated blast radius (which test files would need to run, and whether `memory_root` is in scope).

- [ ] **Step 5: Commit the assessment**

```bash
git add docs/agent-evaluations/2026-09-10-cross-gate-cap-link-assessment.md
git commit -m "docs: assess the cross-gate cap link before touching memory policy"
```

---

## Final verification, run after Task 4

All four must pass before this plan is considered done.

```bash
cd /Users/scientivan/Programming/Ramz/Referi

cd agent && uv run pytest -q && cd ..
cd contracts && forge test && cd ..
cd web && ./node_modules/.bin/tsc --noEmit -p tsconfig.lint.json && pnpm test && cd ..

make dual-gate
make virtuals-evidence
```

Expected:

| Check | Expected |
|---|---|
| pytest | 792 or higher passed, 0 failed |
| forge test | 175 tests passed |
| tsc | silent |
| web tests | pass 17, fail 0 |
| `make dual-gate` | `root_covers_both_gates=True` |
| `make virtuals-evidence` | `jobs_confirmed_onchain=5/5` |

Then confirm no em dash entered the repo:

```bash
for f in $(git diff --name-only HEAD~5 2>/dev/null | grep -E '\.(md|py|jsx|js|sol)$'); do
  n=$(awk '/—/{c++} END{print c+0}' "$f" 2>/dev/null)
  [ "$n" != "0" ] && echo "EM DASH in $f: $n"
done
echo "em dash scan done"
```

Expected: only `em dash scan done`, with no file listed. `web/src/lib/checks.js` and `agent/agent/checks/base.py` are the permitted exceptions and should not appear in a diff from this plan.

---

## What this plan deliberately does not do

Stated so a future reader does not mistake the omissions for oversights.

- **It does not make Execution Passport call ACP.** The passport guards treasury actions, ACP handles escrow jobs. A fake link would be trivially checkable and false.
- **It does not produce new on-chain ACP activity.** The agent wallet was rotated to `0xfA4F11Ec0e0C060D0471028633B954a7CA739911` and `EvaluatorVault.agent()` is immutable at `0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894`. Posting a new verdict needs the old key or a redeploy, and ADR-022 freezes the vault.
- **It does not touch `derive_cap` or ADR-002.** Task 5 assesses that and stops.
- **It does not claim the judges will award 1.25.** The rubric says the multiplier applies only if judges confirm the integration is doing real work. This plan makes that confirmable. It cannot make it certain.
