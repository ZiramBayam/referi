# Actor Standing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A provider's verdict history on Virtuals ACP decides whether the Base gate issues that provider an Execution Passport, and `PassportVerifier` refuses to let anyone else use it.

**Architecture:** The passport gains an `executor` address (EIP-712 field, checked against `msg.sender` on chain). The Control Hypothesis gains a fifth obligation, `actor-standing`, whose threshold lives in memory. The decision path reads the executor's ACP provider profile through the existing guarded reader and evaluates the obligation with no default pass. A thin CLI requests, signs, and executes passports against Base Sepolia.

**Tech Stack:** Python 3.13 (`uv`), `sibyl-memory-client` 0.7.0, `web3` 7.16.0, Foundry (solc 0.8.36), Next.js 16 (`pnpm`), Base Sepolia (84532).

**Spec:** `docs/superpowers/specs/2026-09-11-actor-standing-design.md`. One deviation from the spec, decided here: `executor` lives on `ExecutionPassport` and is a keyword argument of the decision function, NOT a field of `ActionProposal`. Reason: `ActionProposal` feeds the action digest, incident evidence, and hypothesis scope matching; touching it widens the blast radius for no benefit. The executor profile is passed to `evaluate_obligations` as a keyword, not stored on `DeterministicEnvironment`, for the same reason.

## Global Constraints

Every task's requirements implicitly include this section.

- **No em dash (`—`) anywhere** in code, comments, docs, or UI copy. Use a comma, period, colon, or parentheses. Exceptions unchanged from the previous plan: `agent/agent/checks/base.py`, `web/src/lib/checks.js`, and the `awk` scanner commands.
- **No new runtime dependency.** This plan needs none.
- **Run tests from the right directory.** Python: `cd agent && uv run pytest`. Contracts: `cd contracts && forge test`. Web: `cd web && pnpm test`.
- **Do not modify `contracts/src/EvaluatorVault.sol`**, `derive_cap`, `promote_suspicions`, `_recompute_risk`, or any ADR-002 rule. The Base gate only READS provider profiles.
- **No 32-byte hex constants in `agent/agent/*.py`.** `tests/test_verdict_root.py::test_no_production_module_contains_a_32_byte_constant` scans for them. Test files are exempt.
- **Never put a private key in a command, a file, or a committed env.** The CLI reads keys only from environment variable NAMES passed on the command line (`--signer-key-env`, `--executor-key-env`). Deploy uses the Foundry keystore `agent` (holds `0xfA4F11Ec0e0C060D0471028633B954a7CA739911`).
- **Addresses are lowercase** inside the agent (`normalize_address`, `_canonical_address`). Checksum only when handing to web3 contract calls.
- **Comments in `agent/` and `web/src/` are Indonesian.** Prose in `README.md`, `docs/posts/`, `demo/`, UI copy, and Solidity comments is English. ADRs and `docs/limitations.md` items follow the language of their neighbours (ADR: Indonesian; limitations: English).
- **Commit after every task** with conventional prefixes and the session attribution trailer.

---

## Context you must have

- Rubric multiplier: `docs/spec.md:58`. 1.25 only if judges confirm Base plus Virtuals is "doing real work".
- Provider risk: `risk_level = min(2, len(incident_jobs))` (`agent/agent/memory_policy.py:2523-2529`). It rises only through `promote_suspicions`, which needs quarantine evidence from **two distinct jobs**, every piece from a deterministic check id in `{"chain","links","format","sandbox"}` (`memory_policy.py:150`, `:2402-2416`). Tests build history through `record_suspicion` then `promote_suspicions`, never by writing `risk_level` directly.
- Guarded reader: `DecisionMemoryView(client).provider(address)` returns `ProviderProfile` and an empty profile (risk 0) for unknown addresses (`memory_policy.py:1597-1605`). This is the only way the decision path may read a provider.
- Hypothesis validation currently forces exactly the four `MVP_PROOF_IDS` in order (`execution_passport.py:432-433`). Task 2 relaxes this to "four legacy or five current".
- Fixed cross-language vector: `agent/tests/test_execution_passport.py:363-390` hardcodes hashes for verifier `0x…cc`, nonce 1, issued 1000, expires 1030, memory root `0x44*32`, signer key `0x12*32`. The passport typehash changes, so `hypothesis_ids_hash` stays, `obligation_results_hash` changes (five results), and the message hash changes. Task 3 regenerates them and Task 1 pins the same digest in Solidity.
- Current deployment: `deployments/passport-84532.json`, policySigner `0xfA4F11Ec0e0C060D0471028633B954a7CA739911`, keystore name `agent`, Makefile target `deploy-passport` (`Makefile:121-127`).
- Provider Beta: `0xc3c6bf20dde1a547a35f6479d54b08e1548daeff`, key env `PROVIDER2_PRIVATE_KEY`. Provider Alpha: `0x20212e4d95a75e6716575ed26e884cdeff66b321`, key env `PROVIDER_PRIVATE_KEY`. Operational ACP store: `SIBYL_DB_PATH=./data/memory.db` relative to `agent/` (`.env.example:61`), currently empty.

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `agent/agent/passport_request.py` | CLI: request, sign, execute one passport for one executor against one store. Prints fixed lines. |
| `agent/tests/test_passport_request.py` | Formatting and exit codes against a temp store, no network. |
| `docs/posts/05-2026-09-11-verdict-virtuals-mengubah-izin-base.md` | Build-in-public post 5. |

**Modified:**

| File | Change |
|---|---|
| `contracts/src/PassportVerifier.sol` | `executor` field, `WrongExecutor`, event topic, version 2. |
| `contracts/test/ExecutionPassportVerifier.t.sol` | Executor tests, fixture field, cross-language digest pin. |
| `agent/agent/execution_passport.py` | `PROOF_ACTOR`, `max_risk_level`, executor on passport, obligation evaluation, decision reads the profile. |
| `agent/agent/passport_client.py` | `passport_tuple` gains executor. |
| `agent/agent/passport_demo.py` | Passes `executor=caller`. Prints `executor_standing=` line. |
| `agent/agent/passport_preflight.py` | Accepts optional `executor` in the request, defaults to the deployer. |
| `agent/agent/dual_gate_report.py` | Prints the executor standing of the seeded provider. |
| `agent/tests/test_execution_passport.py` | Fixed vector, five obligations, actor table. |
| `agent/tests/test_dual_gate_memory.py` | The multiplier-locking test. |
| `agent/tests/test_passport_preflight.py` | Executor default and override. |
| `web/src/lib/agentPreflight.js`, `web/src/lib/passportDemo.js`, `web/src/components/ExecutionRoom.jsx` | Label, fixture proof, copy "five". |
| `Makefile` | `passport-request` target. |
| `deployments/passport-84532.json` | New addresses, `previous` block. |
| `README.md`, `docs/decisions.md`, `docs/limitations.md`, `docs/evidence.md`, `demo/video-script.md`, `docs/posts/03-*.md`, `docs/posts/04-*.md` | Docs. |

---

## Task 1: PassportVerifier v2 with a bound executor

**Files:**
- Modify: `contracts/src/PassportVerifier.sol`
- Modify: `contracts/test/ExecutionPassportVerifier.t.sol`

**Interfaces:**
- Produces: struct field `address executor` at position 5 (after `target`), error `WrongExecutor()`, event `PassportConsumed(uint256 indexed nonce, bytes32 indexed passportDigest, address indexed executor, bytes32 actionDigest, bytes32 hypothesisIdsHash, bytes32 obligationResultsHash, bytes32 memoryRoot)`, `PASSPORT_VERSION == 2`, typehash string `ExecutionPassport(uint256 passportVersion,bytes32 actionClass,uint256 chainId,address target,address executor,bytes4 selector,bytes32 calldataHash,uint256 value,uint256 stateBlockNumber,bytes32 stateBlockHash,bytes32 hypothesisIdsHash,bytes32 obligationResultsHash,bytes32 memoryRoot,uint256 issuedAt,uint256 expiresAt,uint256 nonce)`. Task 3 must match this string byte for byte.

- [ ] **Step 1: Add the failing executor tests**

In `contracts/test/ExecutionPassportVerifier.t.sol`, add after `test_wrongSignerReverts`:

```solidity
    function test_wrongExecutorRevertsBeforeSignatureCheck() public {
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 15, 1_000, 1_030);
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.prank(address(0xBEEF));
        vm.expectRevert(PassportVerifier.WrongExecutor.selector);
        verifier.execute(passport, signature, calldata_);
        assertEq(treasury.reserve(), 1_000_000);
        assertFalse(verifier.usedNonces(15));
    }

    function test_boundExecutorConsumesPassportAndIsIndexedInEvent() public {
        address executor = address(0xD00D);
        PassportVerifier.ExecutionPassport memory passport = _passport(100_000, 16, 1_000, 1_030);
        passport.executor = executor;
        bytes memory signature = _sign(POLICY_KEY, passport);
        bytes memory calldata_ = _calldata(100_000);

        vm.expectEmit(true, true, true, true, address(verifier));
        emit PassportVerifier.PassportConsumed(
            passport.nonce,
            _digest(passport),
            executor,
            _actionDigest(passport),
            passport.hypothesisIdsHash,
            passport.obligationResultsHash,
            passport.memoryRoot
        );
        vm.prank(executor);
        verifier.execute(passport, signature, calldata_);
        assertEq(treasury.reserve(), 900_000);
    }

    function test_passportVersionIsTwo() public view {
        assertEq(verifier.PASSPORT_VERSION(), 2);
    }
```

Update the `_passport` helper so the default executor is the test contract (the caller in every existing test) and the version is 2:

```solidity
        passport = PassportVerifier.ExecutionPassport({
            passportVersion: 2,
            actionClass: verifier.ACTION_CLASS(),
            chainId: block.chainid,
            target: address(treasury),
            executor: address(this),
            selector: verifier.REBALANCE_SELECTOR(),
            calldataHash: keccak256(calldata_),
            value: 0,
            stateBlockNumber: block.number,
            stateBlockHash: bytes32(uint256(0x11)),
            hypothesisIdsHash: bytes32(uint256(0x22)),
            obligationResultsHash: bytes32(uint256(0x33)),
            memoryRoot: bytes32(uint256(0x44)),
            issuedAt: issuedAt,
            expiresAt: expiresAt,
            nonce: nonce
        });
```

Update the existing `test_validPassportExecutesOneMatchingRebalance` emit to include `address(this)` as the third argument and `vm.expectEmit(true, true, true, true, address(verifier))`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd contracts && forge test --match-contract ExecutionPassportVerifierTest`
Expected: compile error, `executor` is not a member of the struct.

- [ ] **Step 3: Implement in the contract**

In `contracts/src/PassportVerifier.sol`:

```solidity
    uint256 public constant PASSPORT_VERSION = 2;

    bytes32 private constant EXECUTION_PASSPORT_TYPEHASH = keccak256(
        "ExecutionPassport(uint256 passportVersion,bytes32 actionClass,uint256 chainId,address target,address executor,bytes4 selector,bytes32 calldataHash,uint256 value,uint256 stateBlockNumber,bytes32 stateBlockHash,bytes32 hypothesisIdsHash,bytes32 obligationResultsHash,bytes32 memoryRoot,uint256 issuedAt,uint256 expiresAt,uint256 nonce)"
    );

    struct ExecutionPassport {
        uint256 passportVersion;
        bytes32 actionClass;
        uint256 chainId;
        address target;
        /// @dev The only account allowed to consume this passport. The policy signer bound
        ///      it after reading that account's standing in memory; the contract enforces it.
        address executor;
        bytes4 selector;
        bytes32 calldataHash;
        uint256 value;
        uint256 stateBlockNumber;
        bytes32 stateBlockHash;
        bytes32 hypothesisIdsHash;
        bytes32 obligationResultsHash;
        bytes32 memoryRoot;
        uint256 issuedAt;
        uint256 expiresAt;
        uint256 nonce;
    }

    error WrongExecutor();

    event PassportConsumed(
        uint256 indexed nonce,
        bytes32 indexed passportDigest,
        address indexed executor,
        bytes32 actionDigest,
        bytes32 hypothesisIdsHash,
        bytes32 obligationResultsHash,
        bytes32 memoryRoot
    );
```

In `execute`, after `if (passport.target != address(treasury)) revert WrongTarget();`:

```solidity
        if (msg.sender != passport.executor) revert WrongExecutor();
```

In the emit at the end of `execute`, add `passport.executor` as the third argument.

In `_hashPassport`, the encoding must include the executor in position 5. Open the function and insert `passport.executor,` immediately after `passport.target,` in the `abi.encode(...)` call. If the function encodes in two halves to avoid stack-too-deep, put it in the first half; the order must match the typehash string.

- [ ] **Step 4: Run the contract tests**

Run: `cd contracts && forge test`
Expected: all pass. Count rises from 175 to 178.

- [ ] **Step 5: Commit**

```bash
git add contracts/src/PassportVerifier.sol contracts/test/ExecutionPassportVerifier.t.sol
git commit -m "feat(contracts): bind execution passports to one executor (v2)"
```

---

## Task 2: The `actor-standing` obligation, read from ACP memory

**Files:**
- Modify: `agent/agent/execution_passport.py`
- Test: `agent/tests/test_execution_passport.py`

**Interfaces:**
- Produces: `PROOF_ACTOR: Final = "actor-standing"`; `MVP_PROOF_IDS` is now five ids ending with `PROOF_ACTOR`; `LEGACY_PROOF_IDS` is the old four; `ObligationDefinition(obligation_id, blocking=True, max_age_seconds=None, min_reserve=None, max_risk_level=None)`; `evaluate_obligations(action, hypothesis, environment, *, executor_profile: ProviderProfile | None = None)`; `evaluate_rebalance_for_passport(client, action, environment, *, executor: str, verifier_address, issued_at, nonce, expires_at=None)`; `ExecutionPassport.executor: str` placed after `target`; `PASSPORT_VERSION = 2`; `build_execution_passport(..., executor: str, ...)`.

- [ ] **Step 1: Write the failing tests**

Append to `agent/tests/test_execution_passport.py`:

```python
EXECUTOR = "0xc3c6bf20dde1a547a35f6479d54b08e1548daeff"


def _decide(client, proposal, *, executor=EXECUTOR, **env_overrides):
    return ep.evaluate_rebalance_for_passport(
        client,
        proposal,
        environment(proposal, **env_overrides),
        executor=executor,
        verifier_address="0x00000000000000000000000000000000000000cc",
        issued_at=1_000,
        nonce=7,
    )


def test_hypothesis_selects_five_obligations_with_actor_standing_last():
    hypothesis = ep.initial_control_hypothesis(action())
    ids = [o.obligation_id for o in hypothesis.required_obligations]
    assert ids == list(ep.MVP_PROOF_IDS)
    assert ids[-1] == ep.PROOF_ACTOR
    assert hypothesis.required_obligations[-1].max_risk_level == 0


def test_legacy_four_obligation_body_still_loads(client):
    # Store yang ditulis sebelum actor-standing ada harus tetap terbaca: memori lama bukan
    # memori rusak, ia hanya belum memilih obligasi kelima.
    body = ep.initial_control_hypothesis(action()).to_body()
    body["required_obligations"] = body["required_obligations"][:4]
    loaded = ep.ControlHypothesis.from_body(body)
    assert [o.obligation_id for o in loaded.required_obligations] == list(ep.LEGACY_PROOF_IDS)


def test_max_risk_level_is_rejected_on_other_obligations():
    with pytest.raises(ep.PassportValidationError):
        ep.ObligationDefinition(ep.PROOF_ORACLE, max_age_seconds=60, max_risk_level=0)


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (None, "unverifiable"),
        (mp.ProviderProfile(address=EXECUTOR), "satisfied"),
        (mp.ProviderProfile(address=EXECUTOR, risk_level=1, incident_jobs=(418,)), "unsatisfied"),
        (
            mp.ProviderProfile(address=EXECUTOR, confirmed_patterns=("format.bad",)),
            "unsatisfied",
        ),
    ],
)
def test_actor_standing_table(profile, expected):
    proposal = action()
    hypothesis = ep.initial_control_hypothesis(proposal)
    results = ep.evaluate_obligations(
        proposal, hypothesis, environment(proposal), executor_profile=profile
    )
    by_id = {r.obligation_id: r for r in results}
    assert by_id[ep.PROOF_ACTOR].result == expected
    if expected == "unsatisfied":
        assert "418" in by_id[ep.PROOF_ACTOR].explanation or "format.bad" in by_id[ep.PROOF_ACTOR].explanation


def test_unknown_executor_is_satisfied_and_says_so(client):
    proposal = action()
    ep.record_incident(client, incident(proposal))
    decision = _decide(client, proposal)
    assert decision.decision == "passport-issued"
    actor = next(r for r in decision.results if r.obligation_id == ep.PROOF_ACTOR)
    assert actor.observed["acp_history"] == "none"
    assert decision.passport.executor == EXECUTOR


def test_risky_acp_provider_is_blocked_at_the_base_gate(client):
    proposal = action()
    ep.record_incident(client, incident(proposal))
    # Riwayat dibangun lewat jalur ACP yang asli: karantina dua job berbeda, lalu promosi.
    mp.record_suspicion(client, EXECUTOR, "format.bad", mp.Evidence(job_id=418, check_id="format"))
    mp.record_suspicion(client, EXECUTOR, "format.bad", mp.Evidence(job_id=419, check_id="format"))
    assert mp.promote_suspicions(client, EXECUTOR) == ["format.bad"]

    decision = _decide(client, proposal)
    assert decision.decision == "block"
    assert decision.passport is None
    assert "actor-standing" in decision.reason
    assert "418" in decision.reason and "419" in decision.reason


def test_passport_executor_is_part_of_the_signed_message(client):
    proposal = action()
    ep.record_incident(client, incident(proposal))
    a = _decide(client, proposal).passport
    b = _decide(client, proposal, executor="0x20212e4d95a75e6716575ed26e884cdeff66b321").passport
    verifier = "0x00000000000000000000000000000000000000cc"
    assert a.to_message()["executor"] == EXECUTOR
    assert a.sign(verifier, "0x" + "12" * 32) != b.sign(verifier, "0x" + "12" * 32)
```

At the top of the test file add `import agent.memory_policy as mp` if it is not already imported, and confirm a helper named `incident(proposal)` exists (it is used by `test_fresh_process_recalls_control_hypothesis`); if it has a different name, use that name.

Update the two existing assertions that expect four results: `test_all_mvp_obligations_satisfy_only_with_matching_fresh_evidence` becomes `["satisfied"] * 5` and its `evaluate_obligations` call passes `executor_profile=mp.ProviderProfile(address=EXECUTOR)`. `test_decision_entry_point_*` tests (lines 401-449) gain `executor=EXECUTOR` in their calls. `test_execution_passport_is_typed_and_recoverable`, `test_passport_cannot_be_built_from_failed_obligation`, and `test_fixed_cross_language_vector` pass `executor=EXECUTOR` to `build_execution_passport`. The fixed vector's three hashes will now fail; leave them, Task 3 regenerates.

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd agent && uv run pytest tests/test_execution_passport.py -q`
Expected: failures with `AttributeError: module 'agent.execution_passport' has no attribute 'PROOF_ACTOR'` and `TypeError: unexpected keyword argument 'executor'`.

- [ ] **Step 3: Implement constants and the obligation definition**

In `agent/agent/execution_passport.py`:

```python
PASSPORT_VERSION: Final = 2
PASSPORT_TYPE_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("passportVersion", "uint256"),
    ("actionClass", "bytes32"),
    ("chainId", "uint256"),
    ("target", "address"),
    ("executor", "address"),
    ("selector", "bytes4"),
    ("calldataHash", "bytes32"),
    ("value", "uint256"),
    ("stateBlockNumber", "uint256"),
    ("stateBlockHash", "bytes32"),
    ("hypothesisIdsHash", "bytes32"),
    ("obligationResultsHash", "bytes32"),
    ("memoryRoot", "bytes32"),
    ("issuedAt", "uint256"),
    ("expiresAt", "uint256"),
    ("nonce", "uint256"),
)

PROOF_STATE_ANCHOR: Final = "state-anchor-fresh"
PROOF_ORACLE: Final = "oracle-freshness"
PROOF_SIMULATION: Final = "simulation-match"
PROOF_INVARIANT: Final = "post-state-invariant"
PROOF_ACTOR: Final = "actor-standing"
PROOF_ROLLBACK: Final = "rollback-route"
# Empat obligasi pertama sudah ada sebelum actor-standing. Store yang menyimpannya tetap
# sah: ia hanya belum memilih obligasi kelima, dan itu keputusan memori, bukan kesalahan.
LEGACY_PROOF_IDS: Final[tuple[str, ...]] = (
    PROOF_STATE_ANCHOR,
    PROOF_ORACLE,
    PROOF_SIMULATION,
    PROOF_INVARIANT,
)
MVP_PROOF_IDS: Final[tuple[str, ...]] = (*LEGACY_PROOF_IDS, PROOF_ACTOR)
DEFAULT_MAX_RISK_LEVEL: Final = 0
```

`ObligationDefinition`:

```python
@dataclass(frozen=True)
class ObligationDefinition:
    obligation_id: str
    blocking: bool = True
    max_age_seconds: int | None = None
    min_reserve: int | None = None
    max_risk_level: int | None = None

    def __post_init__(self) -> None:
        if self.obligation_id not in KNOWN_PROOF_IDS:
            raise PassportValidationError(f"unknown obligation: {self.obligation_id!r}")
        if not isinstance(self.blocking, bool):
            raise PassportValidationError("blocking must be boolean")
        if self.max_age_seconds is not None:
            _nonnegative_int(self.max_age_seconds, "max_age_seconds")
        if self.min_reserve is not None:
            _nonnegative_int(self.min_reserve, "min_reserve")
        if self.max_risk_level is not None:
            _nonnegative_int(self.max_risk_level, "max_risk_level")
            if self.obligation_id != PROOF_ACTOR:
                raise PassportValidationError("max_risk_level only applies to actor-standing")
        if self.obligation_id == PROOF_ROLLBACK:
            raise PassportValidationError("rollback-route is roadmap-only in the MVP")

    def to_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"id": self.obligation_id, "blocking": self.blocking}
        if self.max_age_seconds is not None:
            body["max_age_seconds"] = self.max_age_seconds
        if self.min_reserve is not None:
            body["min_reserve"] = self.min_reserve
        if self.max_risk_level is not None:
            body["max_risk_level"] = self.max_risk_level
        return body
```

`ControlHypothesis.__post_init__`, replace the MVP order check:

```python
        ids = tuple(o.obligation_id for o in self.required_obligations)
        if ids not in (MVP_PROOF_IDS, LEGACY_PROOF_IDS):
            raise PassportValidationError(
                "hypothesis must select the approved obligations in order (four legacy or five current)"
            )
```

`ControlHypothesis.from_body`, in the `ObligationDefinition(...)` construction add `max_risk_level=item.get("max_risk_level"),`.

`initial_control_hypothesis`, add the fifth obligation:

```python
            ObligationDefinition(PROOF_INVARIANT, min_reserve=DEFAULT_MIN_RESERVE),
            ObligationDefinition(PROOF_ACTOR, max_risk_level=DEFAULT_MAX_RISK_LEVEL),
```

- [ ] **Step 4: Implement the executor on the passport**

`ExecutionPassport`: add `executor: str` immediately after `target: str`. In `__post_init__` add `object.__setattr__(self, "executor", _canonical_address(self.executor, "executor"))` after the target line. In `to_message` add `"executor": self.executor,` after `"target"`.

`build_execution_passport` signature gains `executor: str` as a required keyword (after `*`), and passes `executor=executor` to `ExecutionPassport`.

- [ ] **Step 5: Implement obligation evaluation**

`evaluate_obligations` signature:

```python
def evaluate_obligations(
    action: ActionProposal,
    hypothesis: ControlHypothesis,
    environment: DeterministicEnvironment,
    *,
    executor_profile: "ProviderProfile | None" = None,
) -> tuple[ObligationResult, ...]:
```

Import `ProviderProfile` from `agent.memory_policy` alongside the existing imports. Add a branch before the final `else`:

```python
        elif obligation.obligation_id == PROOF_ACTOR:
            threshold = {"max_risk_level": obligation.max_risk_level}
            if executor_profile is None or obligation.max_risk_level is None:
                observed = {"acp_history": "unread"}
                result = "unverifiable"
            else:
                has_history = bool(executor_profile.incident_jobs) or bool(
                    executor_profile.confirmed_patterns
                )
                observed = {
                    "executor": executor_profile.address,
                    "risk_level": executor_profile.risk_level,
                    "incident_jobs": list(executor_profile.incident_jobs),
                    "confirmed_patterns": list(executor_profile.confirmed_patterns),
                    "acp_history": "found" if has_history else "none",
                }
                if executor_profile.risk_level > obligation.max_risk_level:
                    result = "unsatisfied"
                elif executor_profile.confirmed_patterns:
                    result = "unsatisfied"
                else:
                    result = "satisfied"
```

In `_obligation_result`, add explanations. The `unsatisfied` text must name the evidence, so build it from `observed`:

```python
        PROOF_ACTOR: {
            "satisfied": "executor has no disqualifying verdict history on ACP",
            "unsatisfied": (
                "executor is disqualified by ACP verdict history: "
                f"risk_level={observed.get('risk_level')} "
                f"incident_jobs={','.join(str(j) for j in observed.get('incident_jobs', [])) or 'none'} "
                f"confirmed_patterns={','.join(observed.get('confirmed_patterns', [])) or 'none'}"
            ),
            "unverifiable": "executor standing cannot be verified because ACP memory was not read",
        },
```

- [ ] **Step 6: Implement the decision path read**

`evaluate_rebalance_for_passport` signature gains `executor: str` as a required keyword. Inside the `try` block that loads hypotheses, add the profile read through the guarded reader:

```python
    executor_address = _canonical_address(executor, "executor")
    try:
        hypotheses = load_control_hypotheses(client)
        selected = select_hypothesis(hypotheses, action)
        # Profil executor dibaca lewat reader jalur keputusan yang sama dengan gerbang ACP:
        # entity `suspicion` tidak pernah tersentuh (ADR-002 aturan 1). Ini SATU-SATUNYA
        # jembatan Virtuals -> Base, dan ia baca-saja.
        executor_profile = DecisionMemoryView(client).provider(executor_address)
    except (PassportMemoryError, MemoryIntegrityError, OSError) as exc:
        return PassportDecision("human-review-required", f"memory-unavailable: {exc}")
```

`DecisionMemoryView` is already imported at the top of the module (line 28). Pass `executor_profile=executor_profile` to `evaluate_obligations`, and `executor=executor_address` to `build_execution_passport`. In the `block` branch, extend the reason so the ACP evidence is visible:

```python
        failed = ",".join(r.obligation_id for r in results if r.result != "satisfied")
        detail = "; ".join(r.explanation for r in results if r.result != "satisfied")
        return PassportDecision("block", f"blocking obligations failed: {failed} ({detail})", selected, results)
```

- [ ] **Step 7: Run the module tests**

Run: `cd agent && uv run pytest tests/test_execution_passport.py -q`
Expected: everything passes except `test_fixed_cross_language_vector` (three hash assertions), which Task 3 fixes. If `test_risky_acp_provider_is_blocked_at_the_base_gate` fails on `promote_suspicions` returning `[]`, check the pattern id validator (`validate_pattern_id`) and use a pattern id it accepts; the test's job is the block, not the id.

- [ ] **Step 8: Commit**

```bash
git add agent/agent/execution_passport.py agent/tests/test_execution_passport.py
git commit -m "feat(agent): actor-standing obligation reads ACP provider history at the Base gate"
```

---

## Task 3: Cross-language vector and every caller of the passport

**Files:**
- Modify: `agent/tests/test_execution_passport.py:363-390`
- Modify: `contracts/test/ExecutionPassportVerifier.t.sol`
- Modify: `agent/agent/passport_client.py:44-63`
- Modify: `agent/agent/passport_demo.py`
- Modify: `agent/agent/passport_preflight.py`
- Modify: `agent/tests/test_passport_preflight.py`

- [ ] **Step 1: Regenerate the fixed vector from Python**

Run:

```bash
cd agent && uv run python - <<'PY'
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
import tests.test_execution_passport as t, agent.execution_passport as ep, agent.memory_policy as mp
p = t.action(); h = ep.initial_control_hypothesis(p)
r = ep.evaluate_obligations(p, h, t.environment(p), executor_profile=mp.ProviderProfile(address=t.EXECUTOR))
pp = ep.build_execution_passport(p, h, r, executor=t.EXECUTOR, memory_root_value="0x"+"44"*32, issued_at=1000, expires_at=1030, nonce=1)
typed = encode_typed_data(full_message=pp.typed_data("0x00000000000000000000000000000000000000cc"))
print("hypothesis_ids_hash", pp.hypothesis_ids_hash)
print("obligation_results_hash", pp.obligation_results_hash)
print("message_hash", Web3.to_hex(Account.sign_message(typed, "0x"+"12"*32).message_hash))
print("calldata_hash", p.calldata_hash, "state_hash", t.STATE_HASH, "target", t.TARGET)
PY
```

Paste the three printed hashes into `test_fixed_cross_language_vector` in place of the old `obligation_results_hash` and message hash values (the `hypothesis_ids_hash` should be unchanged; if it changed, stop and report, because that means the hypothesis body changed shape in a way the plan did not intend).

- [ ] **Step 2: Pin the same message hash in Solidity**

Add to `contracts/test/ExecutionPassportVerifier.t.sol`:

```solidity
    /// Cross-language pin. The Python test `test_fixed_cross_language_vector` signs this exact
    /// message for verifier 0x…cc on chain 84532; both sides must agree on the digest.
    function test_fixedCrossLanguageDigest() public {
        vm.chainId(84532);
        PassportVerifier pinned = new PassportVerifier(treasury, policySigner);
        vm.etch(address(0xcc), address(pinned).code);
        // Domain separator uses address(this) of the verifier, so call through the etched copy.
        PassportVerifier at = PassportVerifier(address(0xcc));
        PassportVerifier.ExecutionPassport memory passport = PassportVerifier.ExecutionPassport({
            passportVersion: 2,
            actionClass: keccak256("treasury-rebalance"),
            chainId: 84532,
            target: <TARGET from Step 1, checksummed>,
            executor: 0xc3c6Bf20ddE1a547a35f6479D54B08E1548dAeff,
            selector: bytes4(keccak256("rebalance(uint256)")),
            calldataHash: <calldata_hash from Step 1>,
            value: 0,
            stateBlockNumber: <block used by tests.action(), read it from the helper>,
            stateBlockHash: <STATE_HASH from Step 1>,
            hypothesisIdsHash: <hypothesis_ids_hash from Step 1>,
            obligationResultsHash: <obligation_results_hash from Step 1>,
            memoryRoot: 0x4444444444444444444444444444444444444444444444444444444444444444,
            issuedAt: 1_000,
            expiresAt: 1_030,
            nonce: 1
        });
        assertEq(at.hashPassport(passport), <message_hash from Step 1>);
    }
```

Fill every `<...>` with literal values from Step 1 and from the Python helpers `action()` (`agent/tests/test_execution_passport.py:20-36`). Immutable `treasury` in the etched copy is baked into bytecode, which is fine: `hashPassport` never reads it.

Run: `cd contracts && forge test --match-test test_fixedCrossLanguageDigest -vv`
Expected: PASS. If the digest differs, the typehash strings differ between `PassportVerifier.sol` and `PASSPORT_TYPE_FIELDS`; diff them character by character before touching anything else.

- [ ] **Step 3: `passport_tuple` gains the executor**

In `agent/agent/passport_client.py`, insert `Web3.to_checksum_address(message["executor"]),` after the `target` line in `passport_tuple`.

- [ ] **Step 4: `passport_demo.py` passes and prints the executor**

Every call to `evaluate_rebalance_for_passport` in `agent/agent/passport_demo.py` (three of them: `blocked`, `current`, `deleted`) gains `executor=caller,`. After the `thresholds_from_memory=` print add:

```python
    actor = next(r for r in current.results if r.obligation_id == PROOF_ACTOR)
    print(
        f"executor_standing={actor.result} acp_history={actor.observed.get('acp_history')} "
        f"max_risk_level={actor.threshold.get('max_risk_level')}"
    )
```

Import `PROOF_ACTOR` in the existing `from agent.execution_passport import (...)` block.

- [ ] **Step 5: `passport_preflight.py` accepts an executor**

In `evaluate`, after `oracle_fresh = ...`:

```python
    # Executor default = deployer fixture. Situs boleh mengirim alamat lain supaya juri bisa
    # mencoba provider ACP yang riwayatnya ada di store yang sama.
    executor = str(request.get("executor") or deployment.get("deployer") or "").lower()
```

Move the `deployment = _deployment()` line above it. Pass `executor=executor` to `evaluate_rebalance_for_passport`. Add `"executor": executor,` to the returned dict. Check `_deployment()` exposes `deployer`; if it only returns `chain_id/treasury/verifier/status`, add `"deployer": data["deployer"].lower()` to it.

- [ ] **Step 6: Preflight tests**

Append to `agent/tests/test_passport_preflight.py`:

```python
def test_executor_defaults_to_deployer_and_can_be_overridden(memory_db):
    out = evaluate({"amount": 100_000, "memoryAvailable": True, "oracleFresh": True})
    assert out["executor"] == out["passport"]["executor"]

    beta = "0xc3c6bf20dde1a547a35f6479d54b08e1548daeff"
    out = evaluate({"amount": 100_000, "oracleFresh": True, "executor": beta})
    assert out["passport"]["executor"] == beta
    actor = next(o for o in out["obligations"] if o["id"] == "actor-standing")
    assert actor["result"] == "satisfied"
```

- [ ] **Step 7: Run the whole Python suite**

Run: `cd agent && uv run pytest -q`
Expected: 0 failed. The Anvil integration test (`test_execution_passport_integration.py`) must pass too; it exercises `passport_demo.run` end to end with the v2 contract from `contracts/out`. Run `cd contracts && forge build` first if `contracts/out` is stale.

- [ ] **Step 8: Commit**

```bash
git add agent contracts/test/ExecutionPassportVerifier.t.sol
git commit -m "feat(agent): thread the executor through every passport caller and pin the v2 digest"
```

---

## Task 4: The multiplier-locking test in the dual-gate file

**Files:**
- Test: `agent/tests/test_dual_gate_memory.py` (append)
- Modify: `agent/agent/dual_gate_report.py`

**Interfaces:**
- Consumes: `build_incident`, `_store`, `PROVIDER`, `TREASURY` from the existing test file.
- Produces: report lines `demo_executor=…`, `demo_executor_standing=satisfied|unsatisfied` printed by `agent.dual_gate_report.report`.

- [ ] **Step 1: Write the failing tests**

Append to `agent/tests/test_dual_gate_memory.py`:

```python
def _environment_for(action: ep.ActionProposal) -> ep.DeterministicEnvironment:
    simulation = ep.simulate_rebalance(action, current_reserve=1_000_000, minimum_reserve=250_000)
    return ep.DeterministicEnvironment(
        now=2_000,
        current_block_number=action.state_block_number,
        current_block_hash=action.state_block_hash,
        state_block_timestamp=2_000,
        oracle_timestamp=1_990,
        simulation_action_digest=simulation.action_digest,
        simulation_succeeded=simulation.success,
        simulated_post_reserve=simulation.simulated_post_reserve,
    )


def test_acp_rejections_block_the_base_passport(tmp_path):
    """Verdict Virtuals mengubah izin Base. Ini klaim yang menopang multiplier 1.25."""
    client = _store(tmp_path)
    incident = build_incident(TREASURY, 100_000)
    ep.record_incident(client, incident)
    action = incident.action
    beta = "0xc3c6bf20dde1a547a35f6479d54b08e1548daeff"

    before = ep.evaluate_rebalance_for_passport(
        client, action, _environment_for(action), executor=beta,
        verifier_address=TREASURY, issued_at=2_000, nonce=1,
    )
    assert before.decision == "passport-issued"
    assert before.passport.executor == beta

    # Dua job ACP berbeda, bukti deterministik, lalu promosi: jalur yang SAMA dengan yang
    # dipakai gerbang ACP di Base Sepolia. Tidak ada tulisan langsung ke risk_level.
    mp.record_suspicion(client, beta, "format.bad", mp.Evidence(job_id=423, check_id="format"))
    mp.record_suspicion(client, beta, "format.bad", mp.Evidence(job_id=424, check_id="format"))
    assert mp.promote_suspicions(client, beta) == ["format.bad"]
    assert mp.load_snapshot(client).providers  # profil Beta kini ada di preimage root

    after = ep.evaluate_rebalance_for_passport(
        client, action, _environment_for(action), executor=beta,
        verifier_address=TREASURY, issued_at=2_000, nonce=2,
    )
    assert after.decision == "block"
    assert "actor-standing" in after.reason
    assert "423" in after.reason and "424" in after.reason
    # Root yang diumumkan gerbang ACP ikut berubah, karena profil Beta masuk preimage.
    assert mp.memory_root_for_onchain(client) != before.passport.memory_root


def test_report_shows_the_demo_executor_standing(tmp_path):
    from agent.dual_gate_report import report

    lines = "\n".join(report())
    assert "demo_executor=" in lines
    assert "demo_executor_standing=unsatisfied" in lines
```

Note the second test calls `report()` with no path, so it uses the seeded demo store, whose provider has `risk_level=1` and therefore fails `actor-standing` at `max_risk_level=0`.

- [ ] **Step 2: Run to verify they fail**

Run: `cd agent && uv run pytest tests/test_dual_gate_memory.py -q`
Expected: the first fails only if Task 2 is incomplete; the second fails with `assert "demo_executor=" in lines`.

- [ ] **Step 3: Extend the report**

In `agent/agent/dual_gate_report.py`, inside the `with locked_client(client):` block after `root = ...`, add nothing. After the block, compute the standing using the pure evaluator:

```python
        standing_lines: list[str] = []
        if providers:
            demo_executor = sorted(providers)[0]
            profile = mp.ProviderProfile.from_body(demo_executor, providers[demo_executor])
            hypothesis = next(
                (
                    ep.ControlHypothesis.from_body(patterns[key])
                    for key in hypotheses
                    if isinstance(patterns.get(key), dict)
                ),
                None,
            )
            if hypothesis is not None:
                actor = next(
                    (o for o in hypothesis.required_obligations if o.obligation_id == ep.PROOF_ACTOR),
                    None,
                )
                if actor is not None:
                    disqualified = (
                        profile.risk_level > (actor.max_risk_level or 0) or bool(profile.confirmed_patterns)
                    )
                    standing_lines = [
                        f"demo_executor={demo_executor}",
                        f"demo_executor_risk_level={profile.risk_level}",
                        f"demo_executor_standing={'unsatisfied' if disqualified else 'satisfied'}",
                    ]
```

Append `*standing_lines` to the returned list, after `root_covers_both_gates=`. Check `raw_references` returns bodies as dicts (`patterns[key]`); if it returns `(key, body)` tuples or wrapped rows, adapt the lookup so `ep.ControlHypothesis.from_body` receives the body dict.

In `_seed_demo_store`, change the seeded provider so the disqualification is honest and traceable, not hand-set: replace the `save_provider(...)` call with:

```python
    mp.save_provider(client, mp.ProviderProfile(address=DEMO_PROVIDER, passed_budgets=(1_000,)))
    mp.record_suspicion(client, DEMO_PROVIDER, "format.bad", mp.Evidence(job_id=418, check_id="format"))
    mp.record_suspicion(client, DEMO_PROVIDER, "format.bad", mp.Evidence(job_id=419, check_id="format"))
    mp.promote_suspicions(client, DEMO_PROVIDER)
```

- [ ] **Step 4: Run and read**

Run: `cd agent && uv run pytest tests/test_dual_gate_memory.py -q && uv run python -m agent.dual_gate_report`
Expected: all pass; the command prints `demo_executor_standing=unsatisfied` and still `root_covers_both_gates=True`.

- [ ] **Step 5: Commit**

```bash
git add agent/tests/test_dual_gate_memory.py agent/agent/dual_gate_report.py
git commit -m "test: lock the Virtuals-to-Base link and show it in the dual-gate report"
```

---

## Task 5: `passport_request` CLI

**Files:**
- Create: `agent/agent/passport_request.py`
- Create: `agent/tests/test_passport_request.py`
- Modify: `Makefile`

**Interfaces:**
- Produces: `def request(client, *, executor: str, amount: int, deployment: dict, now: int, oracle_timestamp: int, anchor_number: int, anchor_hash: str, nonce: int) -> tuple[PassportDecision, list[str]]` (pure), `def main() -> int` (exit 0 issued, 3 block, 4 review, 1 rpc/other error).
- Printed lines, quoted by docs:

```
executor=0x…
acp_profile=found|none risk_level=N incident_jobs=… confirmed_patterns=…
actor_standing=satisfied|unsatisfied|unverifiable max_risk_level=0
decision=passport-issued|block|human-review-required
reason=…
memory_root=0x…
```

and, when executing, `execute_tx=0x… consumed_executor=0x…`.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_passport_request.py`:

```python
"""CLI permintaan passport: yang diuji adalah barisnya dan kode keluarnya, tanpa jaringan."""

from __future__ import annotations

from sibyl_memory_client import MemoryClient
from web3 import Web3

import agent.execution_passport as ep
import agent.memory_policy as mp
from agent.passport_request import EXIT_BLOCK, EXIT_ISSUED, exit_code_for, request
from tests.test_dual_gate_memory import TREASURY, build_incident

BETA = "0xc3c6bf20dde1a547a35f6479d54b08e1548daeff"
DEPLOYMENT = {"chain_id": 84532, "treasury": TREASURY.lower(), "verifier": TREASURY.lower()}


def _client(tmp_path):
    client = MemoryClient.local(str(tmp_path / "m.db"))
    ep.record_incident(client, build_incident(TREASURY, 100_000))
    return client


def _request(client):
    return request(
        client,
        executor=BETA,
        amount=100_000,
        deployment=DEPLOYMENT,
        now=2_000,
        oracle_timestamp=1_990,
        anchor_number=100,
        anchor_hash=Web3.to_hex(Web3.keccak(text="anchor:100000")),
        nonce=5,
    )


def test_clean_executor_is_issued_and_lines_are_fixed(tmp_path):
    decision, lines = _request(_client(tmp_path))
    joined = "\n".join(lines)
    assert decision.decision == "passport-issued"
    assert f"executor={BETA}" in joined
    assert "acp_profile=none risk_level=0" in joined
    assert "actor_standing=satisfied max_risk_level=0" in joined
    assert "decision=passport-issued" in joined
    assert "memory_root=0x" in joined
    assert exit_code_for(decision) == EXIT_ISSUED


def test_risky_executor_is_blocked_with_job_ids(tmp_path):
    client = _client(tmp_path)
    mp.record_suspicion(client, BETA, "format.bad", mp.Evidence(job_id=423, check_id="format"))
    mp.record_suspicion(client, BETA, "format.bad", mp.Evidence(job_id=424, check_id="format"))
    mp.promote_suspicions(client, BETA)

    decision, lines = _request(client)
    joined = "\n".join(lines)
    assert decision.decision == "block"
    assert "acp_profile=found risk_level=2 incident_jobs=423,424" in joined
    assert "actor_standing=unsatisfied" in joined
    assert exit_code_for(decision) == EXIT_BLOCK
```

The `anchor_hash` must equal the one `build_incident` used for the same amount (`Web3.keccak(text=f"anchor:{amount}")`), because the state-anchor obligation compares the action's hash with the environment's current hash.

- [ ] **Step 2: Run to verify it fails**

Run: `cd agent && uv run pytest tests/test_passport_request.py -q`
Expected: `ModuleNotFoundError: No module named 'agent.passport_request'`.

- [ ] **Step 3: Implement**

Create `agent/agent/passport_request.py`:

```python
"""Minta, tandatangani, dan (opsional) eksekusi SATU Execution Passport untuk SATU executor.

Kenapa berkas ini ada. Jembatan Virtuals -> Base baru terbukti kalau seseorang bisa
meminta passport atas nama sebuah alamat, dan jawabannya berubah sesudah alamat itu
ditolak di ACP. Perintah ini adalah cara memintanya, dan barisnya dikutip di dokumentasi.

Kunci TIDAK PERNAH masuk lewat argumen. `--signer-key-env` dan `--executor-key-env` hanya
menyebut NAMA variabel lingkungan; tanpa keduanya perintah ini nol transaksi dan nol tanda
tangan. Store default adalah `SIBYL_DB_PATH` dari `.env`, yaitu memori operasional gerbang
ACP, supaya yang dibaca gerbang Base memang memori yang ditulis gerbang Virtuals.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from eth_abi import encode as abi_encode
from eth_account import Account
from sibyl_memory_client import MemoryClient
from web3 import Web3

from agent.execution_passport import (
    DEFAULT_MIN_RESERVE,
    PROOF_ACTOR,
    REBALANCE_SELECTOR,
    ActionProposal,
    DeterministicEnvironment,
    PassportDecision,
    evaluate_rebalance_for_passport,
    generate_nonce,
    memory_root_hex,
    simulate_rebalance,
)
from agent.memory_policy import normalize_address
from agent.passport_client import artifact, passport_tuple

EXIT_ISSUED = 0
EXIT_ERROR = 1
EXIT_BLOCK = 3
EXIT_REVIEW = 4
DEFAULT_RPC = "https://sepolia.base.org"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_deployment() -> dict[str, Any]:
    data = json.loads((_repo_root() / "deployments" / "passport-84532.json").read_text(encoding="utf-8"))
    return {
        "chain_id": int(data["chainId"]),
        "treasury": data["contracts"]["MockTreasury"].lower(),
        "verifier": data["contracts"]["PassportVerifier"].lower(),
        "oracle": data["contracts"]["MockOracle"].lower(),
        "rpc": data.get("rpcUrl", DEFAULT_RPC),
    }


def _calldata(amount: int) -> str:
    return "0x" + (REBALANCE_SELECTOR + abi_encode(["uint256"], [int(amount)])).hex()


def request(
    client: Any,
    *,
    executor: str,
    amount: int,
    deployment: dict[str, Any],
    now: int,
    oracle_timestamp: int,
    anchor_number: int,
    anchor_hash: str,
    nonce: int,
    current_reserve: int = 1_000_000,
) -> tuple[PassportDecision, list[str]]:
    """Jalur keputusan yang sama dengan demo dan situs. Murni: nol RPC, nol tanda tangan."""
    executor = normalize_address(executor)
    action = ActionProposal(
        chain_id=deployment["chain_id"],
        target=deployment["treasury"],
        selector="0x" + REBALANCE_SELECTOR.hex(),
        calldata=_calldata(amount),
        value=0,
        state_block_number=anchor_number,
        state_block_hash=anchor_hash,
    )
    simulation = simulate_rebalance(
        action, current_reserve=current_reserve, minimum_reserve=DEFAULT_MIN_RESERVE
    )
    decision = evaluate_rebalance_for_passport(
        client,
        action,
        DeterministicEnvironment(
            now=now,
            current_block_number=anchor_number,
            current_block_hash=anchor_hash,
            state_block_timestamp=now,
            oracle_timestamp=oracle_timestamp,
            simulation_action_digest=simulation.action_digest,
            simulation_succeeded=simulation.success,
            simulated_post_reserve=simulation.simulated_post_reserve,
        ),
        executor=executor,
        verifier_address=deployment["verifier"],
        issued_at=now,
        nonce=nonce,
    )
    actor = next((r for r in decision.results if r.obligation_id == PROOF_ACTOR), None)
    lines = [f"executor={executor}"]
    if actor is None:
        lines.append("acp_profile=unread")
        lines.append("actor_standing=unverifiable max_risk_level=none")
    else:
        obs = actor.observed
        lines.append(
            f"acp_profile={obs.get('acp_history', 'unread')} risk_level={obs.get('risk_level', 0)} "
            f"incident_jobs={','.join(str(j) for j in obs.get('incident_jobs', [])) or 'none'} "
            f"confirmed_patterns={','.join(obs.get('confirmed_patterns', [])) or 'none'}"
        )
        lines.append(f"actor_standing={actor.result} max_risk_level={actor.threshold.get('max_risk_level')}")
    lines.append(f"decision={decision.decision}")
    lines.append(f"reason={decision.reason}")
    lines.append(f"memory_root={memory_root_hex(client)}")
    return decision, lines


def exit_code_for(decision: PassportDecision) -> int:
    return {"passport-issued": EXIT_ISSUED, "block": EXIT_BLOCK}.get(decision.decision, EXIT_REVIEW)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor", required=True, help="alamat yang akan mengeksekusi passport")
    parser.add_argument("--amount", type=int, default=100_000)
    parser.add_argument("--db", default=os.environ.get("SIBYL_DB_PATH", "./data/memory.db"))
    parser.add_argument("--rpc", default=None)
    parser.add_argument("--signer-key-env", default=None, help="NAMA env var kunci policy signer")
    parser.add_argument("--executor-key-env", default=None, help="NAMA env var kunci executor")
    parser.add_argument("--out", default=None, help="tulis passport + tanda tangan ke berkas JSON")
    args = parser.parse_args()

    deployment = load_deployment()
    w3 = Web3(Web3.HTTPProvider(args.rpc or deployment["rpc"]))
    if not w3.is_connected():
        print(f"rpc_unreachable={args.rpc or deployment['rpc']}")
        return EXIT_ERROR
    latest = w3.eth.get_block("latest")
    oracle = w3.eth.contract(
        address=Web3.to_checksum_address(deployment["oracle"]), abi=artifact("MockOracle")["abi"]
    )
    treasury = w3.eth.contract(
        address=Web3.to_checksum_address(deployment["treasury"]), abi=artifact("MockTreasury")["abi"]
    )
    client = MemoryClient.local(str(Path(args.db)))
    decision, lines = request(
        client,
        executor=args.executor,
        amount=args.amount,
        deployment=deployment,
        now=int(latest["timestamp"]),
        oracle_timestamp=int(oracle.functions.timestamp().call()),
        anchor_number=int(latest["number"]),
        anchor_hash=Web3.to_hex(latest["hash"]),
        nonce=generate_nonce(),
        current_reserve=int(treasury.functions.reserve().call()),
    )
    for line in lines:
        print(line)
    if not decision.issued or decision.passport is None:
        return exit_code_for(decision)

    if args.signer_key_env is None:
        print("signed=False (beri --signer-key-env untuk menandatangani)")
        return EXIT_ISSUED
    signer_key = os.environ[args.signer_key_env]
    signature = decision.passport.sign(deployment["verifier"], signer_key)
    print(f"signed=True signer={Account.from_key(signer_key).address.lower()}")
    if args.out:
        Path(args.out).write_text(
            json.dumps({"passport": decision.passport.to_message(), "signature": signature,
                        "calldata": _calldata(args.amount)}, indent=2),
            encoding="utf-8",
        )
        print(f"passport_file={args.out}")

    if args.executor_key_env is None:
        return EXIT_ISSUED
    executor_account = Account.from_key(os.environ[args.executor_key_env])
    if executor_account.address.lower() != normalize_address(args.executor):
        print("executor_key_mismatch=True")
        return EXIT_ERROR
    verifier = w3.eth.contract(
        address=Web3.to_checksum_address(deployment["verifier"]), abi=artifact("PassportVerifier")["abi"]
    )
    tx = verifier.functions.execute(
        passport_tuple(decision.passport), bytes.fromhex(signature[2:]), bytes.fromhex(_calldata(args.amount)[2:])
    ).build_transaction(
        {
            "from": executor_account.address,
            "nonce": w3.eth.get_transaction_count(executor_account.address, "pending"),
            "chainId": deployment["chain_id"],
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = executor_account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        print(f"execute_tx={tx_hash.hex()} status=reverted")
        return EXIT_ERROR
    consumed = verifier.events.PassportConsumed().process_receipt(receipt)
    executor_topic = consumed[0]["args"]["executor"].lower() if consumed else "none"
    print(f"execute_tx={tx_hash.hex()} consumed_executor={executor_topic}")
    return EXIT_ISSUED


if __name__ == "__main__":
    raise SystemExit(main())
```

Timing note for the executor: the passport expires 60 seconds after `latest.timestamp`; signing and sending happen in the same process, so this fits. If Base Sepolia is slow and the tx lands late, the revert is `PassportExpired`, which is the intended behaviour; rerun.

- [ ] **Step 4: Run the tests**

Run: `cd agent && uv run pytest tests/test_passport_request.py -q`
Expected: 2 passed.

- [ ] **Step 5: Makefile target**

Append `passport-request` to `.PHONY:`. Add at the end of `Makefile`:

```makefile
# Minta passport untuk SATU executor dari memori operasional gerbang ACP. Tanpa
# SIGNER_KEY_ENV/EXECUTOR_KEY_ENV: nol tanda tangan, nol transaksi (butuh RPC untuk anchor).
# Contoh: make passport-request EXECUTOR=0xc3c6... SIGNER_KEY_ENV=PASSPORT_SIGNER_KEY EXECUTOR_KEY_ENV=PROVIDER2_PRIVATE_KEY
passport-request:
	cd agent && uv run python -m agent.passport_request --executor $(EXECUTOR) \
		$(if $(SIGNER_KEY_ENV),--signer-key-env $(SIGNER_KEY_ENV),) \
		$(if $(EXECUTOR_KEY_ENV),--executor-key-env $(EXECUTOR_KEY_ENV),)
```

- [ ] **Step 6: Commit**

```bash
git add agent/agent/passport_request.py agent/tests/test_passport_request.py Makefile
git commit -m "feat: passport_request CLI, one executor, one store, exit codes per decision"
```

---

## Task 6: Web parity

**Files:**
- Modify: `web/src/lib/agentPreflight.js:27-32`
- Modify: `web/src/lib/passportDemo.js:41-80`
- Modify: `web/src/components/ExecutionRoom.jsx:399`
- Modify: `web/src/components/Landing.jsx:235`, `web/src/components/illustrations/GateChain.jsx:85,173`

- [ ] **Step 1: Label and fixture proof**

`agentPreflight.js` LABELS: add `"actor-standing": "Executor standing on ACP",`.

`passportDemo.js`: after the `post-state-invariant` proof object in the `proofs` array, add:

```js
    {
      id: "actor-standing",
      label: "Executor standing on ACP",
      // Fixture: tidak ada memori ACP di browser, jadi executor fixture dianggap tanpa riwayat.
      result: memoryAvailable ? "satisfied" : "unverifiable",
      detail: memoryAvailable ? "acp history: none" : "acp memory not read",
    },
```

Match the shape of the neighbouring proof objects exactly (same keys). If they use `observed`/`threshold` instead of `detail`, mirror that.

- [ ] **Step 2: Copy**

`ExecutionRoom.jsx:399`: "evaluating four blocking proofs" becomes "evaluating five blocking proofs". `Landing.jsx:235`: "four proof obligations" becomes "five proof obligations, the fifth read from the provider's ACP verdict history". `GateChain.jsx:85` and `:173`: "selects four proof" becomes "selects five proof".

- [ ] **Step 3: Verify**

Run: `cd web && ./node_modules/.bin/tsc --noEmit -p tsconfig.lint.json && pnpm test`
Expected: tsc silent, all tests pass (`fail 0`).

- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat(web): show the fifth obligation, executor standing on ACP"
```

---

## Task 7: Redeploy the passport fixture (v2) to Base Sepolia

**Files:**
- Modify: `deployments/passport-84532.json`
- Modify: `Makefile` (no change needed unless `deploy-passport` differs from `Makefile:121-127`)

This task sends three deployment transactions plus `configureVerifier` from the `agent` keystore. It needs the user's keystore password, so **the executor of this plan asks the user to run the command** and pastes the output back.

- [ ] **Step 1: Build and dry-run**

Run: `cd contracts && forge build && forge test`
Expected: all pass.

- [ ] **Step 2: Ask the user to deploy**

Ask the user to run in their own terminal:

```bash
make deploy-passport
```

and paste the four `console.log` address lines plus the tx hashes from `contracts/broadcast/DeployPassport.s.sol/84532/run-latest.json`.

- [ ] **Step 3: Rewrite the deployment record**

In `deployments/passport-84532.json`: set `deployedAt` to `2026-09-11`, `deployedAtBlock`, `txHashes`, `contracts`, `totalGasUsed`, `totalPaidEth`, `verifiedOnChain` values to the new ones (read the last group back from chain with `cast call`, do not copy from forge logs). Add:

```json
  "passportVersion": 2,
  "previous": {
    "note": "v1 fixture, passports without an executor binding. Kept for the audit trail; superseded by ADR-035.",
    "deployedAt": "2026-09-10",
    "contracts": {
      "MockTreasury": "0x68Cca28DceFAd1c7a73f97FACC74cD51B145772B",
      "MockOracle": "0x8b0e7572eDF67Fded93ff8dBFfD318d2E3D2bDe3",
      "PassportVerifier": "0x43D978e26bEe32A8f2E2DaB1f212F9A36F5937C1"
    }
  }
```

- [ ] **Step 4: Sourcify verification**

Run for each of the three new addresses:

```bash
cd contracts && forge verify-contract --chain 84532 --verifier sourcify <address> src/<Name>.sol:<Name>
```

Then confirm: `curl -s https://sourcify.dev/server/v2/contract/84532/<address> | head -c 300`. Update `sourcify.checkedAt` and `status` in the JSON.

- [ ] **Step 5: Preflight tests still bind to the file**

Run: `cd agent && uv run pytest tests/test_passport_preflight.py -q`
Expected: pass (they read the JSON).

- [ ] **Step 6: Commit**

```bash
git add deployments/passport-84532.json
git commit -m "chore: deploy PassportVerifier v2 fixture to Base Sepolia"
```

---

## Task 8: The testnet proof, in order

**Files:**
- Modify: `docs/evidence.md` (new section)
- Modify: `web/public/jobs.json` (two new jobs, if the site's timeline should show them; optional)

Every key-bearing command below is run by the user. The plan executor prepares, verifies outputs, and records. Order is the argument: **passport first, rejections second, refusal third.**

- [ ] **Step 1: Confirm the operational store starts clean for Beta**

Run: `cd agent && uv run python -m agent.dual_gate_report --db ./data/memory.db`
Expected: `gate_acp_providers=0` or a list without Beta. If Beta is present with incidents, stop and report.

- [ ] **Step 2: Seed the hypothesis into the operational store**

The operational store has no Control Hypothesis (it was created by the ACP gate). Run:

```bash
cd agent && uv run python - <<'PY'
import os
from sibyl_memory_client import MemoryClient
from tests.test_dual_gate_memory import build_incident
import agent.execution_passport as ep, agent.passport_request as pr
d = pr.load_deployment()
c = MemoryClient.local(os.environ.get("SIBYL_DB_PATH", "./data/memory.db"))
print(ep.record_incident(c, build_incident(d["treasury"], 100_000)).hypothesis_id)
PY
```

Expected: `stale-oracle-rebalance/v1`. Record the root: `uv run python -m agent.dual_gate_report --db ./data/memory.db | grep shared_memory_root`.

- [ ] **Step 3: Set the oracle fresh (user runs; owner-only)**

```bash
cast send 0x<new MockOracle> "setObservation(uint256,uint256)" $(date +%s) 1000 \
  --rpc-url https://sepolia.base.org --account agent
```

- [ ] **Step 4: Beta gets and uses a passport (user runs)**

```bash
export PASSPORT_SIGNER_KEY=<agent wallet key, in the shell only>   # policySigner 0xfA4F…
make passport-request EXECUTOR=0xc3c6bf20dde1a547a35f6479d54b08e1548daeff \
  SIGNER_KEY_ENV=PASSPORT_SIGNER_KEY EXECUTOR_KEY_ENV=PROVIDER2_PRIVATE_KEY
```

Expected: `acp_profile=none`, `actor_standing=satisfied`, `decision=passport-issued`, `execute_tx=0x…`, `consumed_executor=0xc3c6…`. Record the tx hash and open it on Blockscout: the `PassportConsumed` event must show `executor` = Beta. Then `unset PASSPORT_SIGNER_KEY`.

- [ ] **Step 5: Two ACP jobs reject Beta (user runs)**

```bash
PROVIDER_SLOT=beta BUDGET_RAW=250000 DELIVERABLE_FILE=sim/scenarios/coarse-defect.md pnpm --filter sim run job:min
cd agent && uv run python -m agent.vault_client --job-id <jobId1> --kind reject
PROVIDER_SLOT=beta BUDGET_RAW=250000 DELIVERABLE_FILE=sim/scenarios/coarse-defect.md pnpm --filter sim run job:min
cd agent && uv run python -m agent.vault_client --job-id <jobId2> --kind reject
```

Note the exit-4 first-invocation behaviour on a fresh vault does not apply here (the vault is not fresh). If a job's deterministic checks all pass, the verdict is PASS whatever `--kind` says; `coarse-defect.md` contains a TODO line and a basescan link that the `format`/`links` checks reject, which is why it is used.

After both: `uv run python -m agent.dual_gate_report --db ./data/memory.db` must show Beta in `gate_acp_provider_ids` and `demo_executor_standing=unsatisfied` (Beta is the alphabetically first provider only if Alpha is absent; if not, read the profile directly with a two-line Python snippet and record `risk_level` and `incident_jobs`).

- [ ] **Step 6: Beta is refused (user or executor runs; no key needed)**

```bash
make passport-request EXECUTOR=0xc3c6bf20dde1a547a35f6479d54b08e1548daeff
```

Expected: `acp_profile=found risk_level=2 incident_jobs=<jobId1>,<jobId2>`, `actor_standing=unsatisfied`, `decision=block`, exit code 3. Record the full output verbatim.

- [ ] **Step 7: Record in `docs/evidence.md`**

Add a section `## Virtuals verdicts change Base permissions (11 Sep 2026)` listing, in order: the `PassportConsumed` tx (Blockscout link, executor topic), the two `JobRejected` txs, the `postVerdict` txs with their memory roots, and the verbatim refusal output. State the boundary: the refusal is an off-chain decision made visible by the absence of a second `PassportConsumed` for Beta and by the command output; the contract enforces only who may use an issued passport.

- [ ] **Step 8: Commit**

```bash
git add docs/evidence.md web/public/jobs.json
git commit -m "docs: record the Virtuals-to-Base proof transactions"
```

---

## Task 9: Docs and framing

**Files:**
- Modify: `README.md`, `docs/decisions.md`, `docs/limitations.md`, `demo/video-script.md`, `docs/posts/03-*.md`, `docs/posts/04-*.md`
- Create: `docs/posts/05-2026-09-11-verdict-virtuals-mengubah-izin-base.md`

- [ ] **Step 1: README**

In the "If you only have 3 minutes" block, add after `passport_memory_deleted=...`:

```
executor_standing=satisfied acp_history=none        # the fifth obligation reads the executor's ACP history
```

In the "How it works" diagram, change `FOUR OBLIGATIONS` to `FIVE OBLIGATIONS`, add a line `actor-standing` under `post-state-invariant`, change "all four must hold" to "all five must hold", and in the passport box change `bound to target + selector +` to `bound to target + executor + selector +`.

Replace the second paragraph of the README opening (starting "Sibyl memory decides") with:

```markdown
Sibyl memory decides, and both gates read the same store through the same code. On
**Virtuals ACP**, memory sets how deeply a deliverable is checked and what budget cap a
provider gets, and every verdict announces the memory root on chain. On **Base**, that same
memory turns a past incident into deterministic proof obligations, and a treasury action
moves value only when all five hold. The fifth obligation, `actor-standing`, reads the
executor's verdict history from the ACP gate: two rejections on Virtuals and the Base gate
refuses that address a passport. `PassportVerifier` then refuses anyone else the passport it
did issue. See `docs/evidence.md` for the transactions, in order.
```

Add under the Gate 2 commands: `make passport-request EXECUTOR=0x…` with a one-line description.

- [ ] **Step 2: ADR-035**

Append to `docs/decisions.md`:

```markdown

## ADR-035 Obligasi `actor-standing`: verdict Virtuals mengubah izin Base, dan verifier mengikat executor
Tanggal: 2026-09-11. Status: diterima. Aditif; tidak mencabut ADR-002, ADR-020, ADR-022, ADR-033.

Konteks:
(a) ADR-034 menyajikan dua gerbang satu memori, tetapi tautannya baru berupa ko-komitmen
    root: tidak ada keputusan di satu gerbang yang berubah karena data dari gerbang lain.
    Rubrik memberi 1.25 hanya bila integrasi "doing real work" (`docs/spec.md:58`).
(b) Asesmen 2026-09-10 menutup arah Base -> Virtuals (`needs-rule-change`). Arah sebaliknya
    hanya butuh PEMBACAAN profil provider, yang sudah punya reader jalur keputusan.
(c) Passport v1 tidak menyebut siapa yang boleh memakainya, jadi penilaian atas sebuah alamat
    tidak bisa ditegakkan kontrak.

Keputusan:
1. Hipotesis kendali memilih obligasi kelima `actor-standing` dengan ambang `max_risk_level`
   yang tersimpan di memori (default 0). Store lama berisi empat obligasi tetap sah dan
   TIDAK memeriksa executor: itu pilihan memori, bukan cacat.
2. Jalur keputusan passport membaca profil executor HANYA lewat `DecisionMemoryView.provider`.
   Entity `suspicion` tidak tersentuh. `derive_cap`, `promote_suspicions`, `_recompute_risk`
   tidak berubah. Alamat tanpa entity dinilai `satisfied` dengan `acp_history=none`, karena
   bagi ACP pun provider bersih dan alamat baru tidak bisa dibedakan.
3. `PassportVerifier` v2: field `executor` di struct dan typehash, `msg.sender` wajib sama,
   `PassportConsumed` mengindeks executor, `PASSPORT_VERSION=2`. Fixture v1
   (`0x43D978e2…37C1`) ditinggalkan dan dicatat di `deployments/passport-84532.json.previous`.
4. Bukti urutannya tetap: passport Beta dikonsumsi DULU, dua job ACP menolak Beta, lalu
   permintaan yang sama ditolak `decision=block` dengan menyebut kedua jobId. Semua di
   `docs/evidence.md`.

Konsekuensi:
(+) Ada satu keputusan Base yang berubah karena verdict Virtuals, dan kontrak Base menegakkan
    hasilnya (siapa yang boleh memakai passport). Klaim multiplier bersandar pada transaksi.
(-) Identitas yang diikat adalah KUNCI, bukan badan hukum: executor Beta di Base adalah kunci
    yang sama dengan provider Beta di ACP. Tanpa ERC-8004 itu tautan terkuat yang ada
    (`docs/limitations.md` item 37).
(-) Penolakan passport tidak meninggalkan jejak on-chain; yang terlihat adalah ketiadaan
    `PassportConsumed` kedua dan keluaran perintah.
```

- [ ] **Step 3: Limitation 37**

Append to `docs/limitations.md`:

```markdown

## 37. `actor-standing` binds a key, not a party, and a refusal leaves no on-chain trace

The fifth obligation reads the executor's provider profile from the same Sibyl store the ACP gate
writes, and `PassportVerifier` v2 refuses anyone but that executor. Two things this does NOT prove:

- That the executor on Base is the same legal party as the provider on ACP. It is the same **key**
  (`0xc3c6…Aeff` in the recorded proof). Without ERC-8004 identity that is the strongest link
  available, and it is stated as such.
- That a refusal happened. `decision=block` is an off-chain decision; the chain shows only that no
  second `PassportConsumed` for that executor exists. The command output is the record.

An unknown address (no provider entity) is `satisfied` with `acp_history=none`. That is deliberate:
ACP itself cannot tell a clean provider from a new one, and a gate that punished newcomers would be
lying about what memory knows.
```

- [ ] **Step 4: Post 5**

Create `docs/posts/05-2026-09-11-verdict-virtuals-mengubah-izin-base.md`:

```markdown
---
title: "Two rejections on Virtuals, and Base stops answering"
date: 2026-09-11
project: REFERI (Sibyl hackathon, Base Sepolia)
repo: PassportVerifier v2 <address>, EvaluatorVault 0x5c6EE4586ACABcb6326069c229E58091B21ef384
---

Yesterday we showed that both gates hash the same memory. Today one gate changes its answer
because of what the other one learned.

## The flow, in the order it happened

1. Provider Beta has no verdict history. It asks the Base gate for a passport to move 100,000 from
   the mock treasury. The fifth obligation, `actor-standing`, reads Beta's profile from the ACP
   gate's store: nothing there. Passport issued, bound to Beta's address. Beta consumes it:
   `PassportConsumed` with `executor=0xc3c6…Aeff`. <blockscout link>
2. Two ACP jobs from Beta carry a deliverable with a deterministic defect. The evaluator vault
   rejects both. Beta's profile now holds two incident jobs and `risk_level=2`. <two links>
3. The same request again. Output, verbatim:

```
executor=0xc3c6bf20dde1a547a35f6479d54b08e1548daeff
acp_profile=found risk_level=2 incident_jobs=<a>,<b> confirmed_patterns=<pattern>
actor_standing=unsatisfied max_risk_level=0
decision=block
```

No code path was flipped between step 1 and step 3. The only thing that changed is memory, and
memory changed because of verdicts on a different protocol.

## What the contract enforces

`PassportVerifier` v2 does not read Sibyl. It enforces two things memory decided: the calldata
hash and the executor. Anyone else who presents Beta's passport gets `WrongExecutor`. That is the
line between "the agent said no" and "the chain would not let it happen anyway".

## What we are still not claiming

The refusal itself is off-chain. The key is the identity, not a legal party. And nothing flows
from Base back to Virtuals; that direction needs a rule change we chose not to make under
deadline. All three are in `docs/limitations.md` item 37.
```

Fill `<address>`, links, job ids, and pattern from Task 8.

- [ ] **Step 5: Posts 03 and 04, video**

`docs/posts/03-*.md`: in the "correction" section, replace "Post 4 shows the command that proves it." with "Post 4 shows the shared root; post 5 shows a verdict on Virtuals changing a permission on Base." `docs/posts/04-*.md`: at the end of "What we are not claiming", add "Update, 11 Sep: the functional link now exists in one direction, see post 5."

`demo/video-script.md`: replace the `3:52` row with:

```markdown
| 3:52 | Terminal: `make passport-request EXECUTOR=0xc3c6…` | `acp_profile=found risk_level=2`, `decision=block` | "Same request that got a passport this morning. Two rejections on Virtuals later, Base says no. Memory is the only thing that changed." |
```

- [ ] **Step 6: Em dash scan and link check**

```bash
for f in README.md docs/decisions.md docs/limitations.md docs/evidence.md demo/video-script.md docs/posts/0[345]-*.md \
         agent/agent/passport_request.py agent/agent/execution_passport.py agent/agent/dual_gate_report.py \
         contracts/src/PassportVerifier.sol web/src/lib/agentPreflight.js web/src/lib/passportDemo.js; do
  printf "%-60s %s\n" "$f" "$(awk '/—/{c++} END{print c+0}' "$f")"
done
```

Expected: every count `0`.

- [ ] **Step 7: Commit**

```bash
git add README.md docs demo web/src
git commit -m "docs: ADR-035, limitation 37, post 5, the Virtuals-to-Base link"
```

---

## Final verification

```bash
cd /Users/scientivan/Programming/Ramz/Referi
cd agent && uv run pytest -q && cd ..
cd contracts && forge test && cd ..
cd web && ./node_modules/.bin/tsc --noEmit -p tsconfig.lint.json && pnpm test && cd ..
make dual-gate
make virtuals-evidence
make demo-passport
make passport-request EXECUTOR=0xc3c6bf20dde1a547a35f6479d54b08e1548daeff; echo "exit=$?"
```

| Check | Expected |
|---|---|
| pytest | 0 failed, count at least 790 + 12 |
| forge test | 179 passed |
| tsc | silent |
| web tests | fail 0 |
| `make dual-gate` | `root_covers_both_gates=True`, `demo_executor_standing=unsatisfied` |
| `make virtuals-evidence` | `jobs_confirmed_onchain=7/7` if jobs.json gained the two Beta jobs, else `5/5` |
| `make demo-passport` | `executor_standing=satisfied acp_history=none` and the existing five lines |
| `make passport-request` for Beta | `decision=block`, `exit=3` |
