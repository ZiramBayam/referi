"""Deterministic Execution Passport control-plane primitives.

This module is deliberately separate from ``memory_policy``'s Escrow Firewall policy.
It owns the Passport memory namespace and the canonical action/proof data that will be
signed by the off-chain policy signer and checked by the narrow Solidity verifier.

The MVP has one action class (``treasury-rebalance``) and one incident seed
(``stale-oracle-rebalance``). No LLM, provider reputation score, or free-form instruction
is an input to a Passport decision.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Final

from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

from agent.memory_policy import (
    REFERENCE_PATTERN_PREFIX,
    DecisionMemoryView,
    MemoryIntegrityError,
    memory_root_for_onchain,
    normalize_address,
    under_memory_lock,
)

ACTION_CLASS: Final = "treasury-rebalance"
INCIDENT_TYPE: Final = "stale-oracle-rebalance"
HYPOTHESIS_ID: Final = "stale-oracle-rebalance/v1"
HYPOTHESIS_KEY_SUFFIX: Final = "passport.control-hypothesis.stale-oracle-rebalance.v1"
HYPOTHESIS_KEY: Final = f"{REFERENCE_PATTERN_PREFIX}{HYPOTHESIS_KEY_SUFFIX}"
HYPOTHESIS_SCHEMA: Final = "execution-passport/control-hypothesis/v1"
PASSPORT_VERSION: Final = 1
EIP712_DOMAIN_NAME: Final = "Execution Passport"
EIP712_DOMAIN_VERSION: Final = "1"
DEFAULT_FRESHNESS_SECONDS: Final = 60
DEFAULT_MIN_RESERVE: Final = 250_000
PASSPORT_MAX_LIFETIME_SECONDS: Final = 60
REBALANCE_SIGNATURE: Final = "rebalance(uint256)"
REBALANCE_SELECTOR: Final = Web3.keccak(text=REBALANCE_SIGNATURE)[:4]
ACTION_DIGEST_TYPEHASH: Final = Web3.keccak(
    text=(
        "Action(uint256 chainId,address target,bytes4 selector,bytes32 calldataHash,uint256 "
        "value,uint256 stateBlockNumber,bytes32 stateBlockHash)"
    )
)
ACTION_CLASS_HASH: Final = Web3.keccak(text=ACTION_CLASS)
PASSPORT_TYPE_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("passportVersion", "uint256"),
    ("actionClass", "bytes32"),
    ("chainId", "uint256"),
    ("target", "address"),
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
PROOF_ROLLBACK: Final = "rollback-route"
MVP_PROOF_IDS: Final[tuple[str, ...]] = (
    PROOF_STATE_ANCHOR,
    PROOF_ORACLE,
    PROOF_SIMULATION,
    PROOF_INVARIANT,
)
KNOWN_PROOF_IDS: Final[frozenset[str]] = frozenset((*MVP_PROOF_IDS, PROOF_ROLLBACK))
PROOF_RESULTS: Final[frozenset[str]] = frozenset({"satisfied", "unsatisfied", "unverifiable"})
DECISIONS: Final[frozenset[str]] = frozenset(
    {"passport-issued", "block", "human-review-required"}
)
OUTCOMES: Final[frozenset[str]] = frozenset({"worked", "failed", "inconclusive"})
HYPOTHESIS_STATUSES: Final[frozenset[str]] = frozenset({"active", "retired"})
ADDRESS_RE: Final = re.compile(r"^0x[0-9a-f]{40}$")
HEX_BYTES_RE: Final = re.compile(r"^0x[0-9a-f]*$")
SELECTOR_RE: Final = re.compile(r"^0x[0-9a-f]{8}$")
HASH_RE: Final = re.compile(r"^0x[0-9a-f]{64}$")


class PassportValidationError(ValueError):
    """Input is not a canonical Passport value."""


class PassportMemoryError(MemoryIntegrityError):
    """Passport memory is missing, malformed, or ambiguous."""


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PassportValidationError(f"{name} must be a non-negative integer")
    return value


def _hex_bytes(value: str, name: str) -> bytes:
    if not isinstance(value, str) or not HEX_BYTES_RE.fullmatch(value) or len(value) % 2:
        raise PassportValidationError(f"{name} must be an even-length lower-case hex string")
    try:
        return bytes.fromhex(value[2:])
    except ValueError as exc:  # pragma: no cover - regex already catches normal cases
        raise PassportValidationError(f"{name} is not valid hex") from exc


def _hash_hex(value: bytes, name: str) -> str:
    if len(value) != 32:
        raise PassportValidationError(f"{name} must contain exactly 32 bytes")
    return "0x" + value.hex()


def canonical_json(value: Any) -> str:
    """Canonical JSON for hashes and memory bodies; floats are forbidden."""

    def reject_float(item: Any) -> Any:
        if isinstance(item, float):
            raise PassportValidationError("floats are not allowed in Passport canonical JSON")
        if isinstance(item, Mapping):
            return {str(k): reject_float(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [reject_float(v) for v in item]
        return item

    return json.dumps(
        reject_float(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def generate_nonce() -> int:
    """Generate a local nonce candidate; the verifier remains authoritative on replay."""

    return int.from_bytes(secrets.token_bytes(32), "big")


def _canonical_address(value: str, name: str) -> str:
    try:
        address = normalize_address(value)
    except (TypeError, ValueError) as exc:
        raise PassportValidationError(f"{name} is not a canonical EVM address") from exc
    if not ADDRESS_RE.fullmatch(address):
        raise PassportValidationError(f"{name} is not a canonical EVM address")
    return address


def _canonical_selector(value: str, name: str = "selector") -> str:
    if not isinstance(value, str) or not SELECTOR_RE.fullmatch(value):
        raise PassportValidationError(f"{name} must be 4-byte lower-case hex")
    return value


def _canonical_hash(value: str, name: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise PassportValidationError(f"{name} must be a 32-byte lower-case hex value")
    return value


@dataclass(frozen=True)
class ActionProposal:
    chain_id: int
    target: str
    selector: str
    calldata: str
    value: int
    state_block_number: int
    state_block_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "chain_id", _nonnegative_int(self.chain_id, "chain_id"))
        object.__setattr__(self, "target", _canonical_address(self.target, "target"))
        object.__setattr__(self, "selector", _canonical_selector(self.selector))
        calldata = "0x" + _hex_bytes(self.calldata, "calldata").hex()
        if len(calldata) < 10:
            raise PassportValidationError("calldata must contain a selector")
        if calldata[2:10] != self.selector[2:]:
            raise PassportValidationError("selector does not match the first calldata bytes")
        object.__setattr__(self, "calldata", calldata)
        object.__setattr__(self, "value", _nonnegative_int(self.value, "value"))
        object.__setattr__(
            self,
            "state_block_number",
            _nonnegative_int(self.state_block_number, "state_block_number"),
        )
        object.__setattr__(
            self,
            "state_block_hash",
            _canonical_hash(self.state_block_hash, "state_block_hash"),
        )

    @property
    def calldata_bytes(self) -> bytes:
        return bytes.fromhex(self.calldata[2:])

    @property
    def calldata_hash(self) -> str:
        return _hash_hex(Web3.keccak(self.calldata_bytes), "calldata_hash")

    @property
    def action_digest(self) -> str:
        encoded = abi_encode(
            [
                "bytes32",
                "uint256",
                "address",
                "bytes4",
                "bytes32",
                "uint256",
                "uint256",
                "bytes32",
            ],
            [
                ACTION_DIGEST_TYPEHASH,
                self.chain_id,
                self.target,
                bytes.fromhex(self.selector[2:]),
                bytes.fromhex(self.calldata_hash[2:]),
                self.value,
                self.state_block_number,
                bytes.fromhex(self.state_block_hash[2:]),
            ],
        )
        return _hash_hex(Web3.keccak(encoded), "action_digest")

    def to_body(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "target": self.target,
            "selector": self.selector,
            "calldata": self.calldata,
            "value": self.value,
            "state_block_number": self.state_block_number,
            "state_block_hash": self.state_block_hash,
            "calldata_hash": self.calldata_hash,
            "action_digest": self.action_digest,
        }


@dataclass(frozen=True)
class SimulationResult:
    """Result of the deterministic mock rebalance simulator."""

    action_digest: str
    success: bool
    simulated_post_reserve: int
    evidence_digest: str

    def __post_init__(self) -> None:
        _canonical_hash(self.action_digest, "simulation.action_digest")
        if not isinstance(self.success, bool):
            raise PassportValidationError("simulation.success must be boolean")
        _nonnegative_int(self.simulated_post_reserve, "simulation.simulated_post_reserve")
        _canonical_hash(self.evidence_digest, "simulation.evidence_digest")

    def to_body(self) -> dict[str, Any]:
        return {
            "action_digest": self.action_digest,
            "success": self.success,
            "simulated_post_reserve": self.simulated_post_reserve,
            "evidence_digest": self.evidence_digest,
        }


def simulate_rebalance(
    action: ActionProposal, *, current_reserve: int, minimum_reserve: int
) -> SimulationResult:
    """Simulate the exact mock ABI and reserve transition without external state."""

    current_reserve = _nonnegative_int(current_reserve, "current_reserve")
    minimum_reserve = _nonnegative_int(minimum_reserve, "minimum_reserve")
    encoded_amount = action.calldata_bytes[4:]
    if len(encoded_amount) != 32:
        amount = 0
        abi_shape_valid = False
    else:
        amount = int.from_bytes(encoded_amount, "big")
        abi_shape_valid = True
    post_reserve = current_reserve - amount if amount <= current_reserve else 0
    success = (
        abi_shape_valid
        and action.value == 0
        and amount <= current_reserve
        and post_reserve >= minimum_reserve
    )
    body = {
        "action_digest": action.action_digest,
        "current_reserve": current_reserve,
        "amount": amount,
        "minimum_reserve": minimum_reserve,
        "post_reserve": post_reserve,
        "success": success,
    }
    return SimulationResult(
        action_digest=action.action_digest,
        success=success,
        simulated_post_reserve=post_reserve,
        evidence_digest=_hash_hex(Web3.keccak(text=canonical_json(body)), "simulation.evidence_digest"),
    )


@dataclass(frozen=True)
class IncidentEvidence:
    incident_id: str
    incident_type: str
    action: ActionProposal
    oracle_timestamp: int
    observed_at: int
    evidence_digest: str

    def __post_init__(self) -> None:
        if not self.incident_id or not isinstance(self.incident_id, str):
            raise PassportValidationError("incident_id must be non-empty")
        if self.incident_type != INCIDENT_TYPE:
            raise PassportValidationError("unsupported incident type")
        object.__setattr__(
            self, "oracle_timestamp", _nonnegative_int(self.oracle_timestamp, "oracle_timestamp")
        )
        object.__setattr__(self, "observed_at", _nonnegative_int(self.observed_at, "observed_at"))
        _canonical_hash(self.evidence_digest, "evidence_digest")

    @property
    def oracle_age_seconds(self) -> int:
        return max(0, self.observed_at - self.oracle_timestamp)

    def to_body(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "action_digest": self.action.action_digest,
            "oracle_timestamp": self.oracle_timestamp,
            "observed_at": self.observed_at,
            "oracle_age_seconds": self.oracle_age_seconds,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True)
class ObligationDefinition:
    obligation_id: str
    blocking: bool = True
    max_age_seconds: int | None = None
    min_reserve: int | None = None

    def __post_init__(self) -> None:
        if self.obligation_id not in KNOWN_PROOF_IDS:
            raise PassportValidationError(f"unknown obligation: {self.obligation_id!r}")
        if not isinstance(self.blocking, bool):
            raise PassportValidationError("blocking must be boolean")
        if self.max_age_seconds is not None:
            _nonnegative_int(self.max_age_seconds, "max_age_seconds")
        if self.min_reserve is not None:
            _nonnegative_int(self.min_reserve, "min_reserve")
        if self.obligation_id == PROOF_ROLLBACK:
            raise PassportValidationError("rollback-route is roadmap-only in the MVP")

    def to_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"id": self.obligation_id, "blocking": self.blocking}
        if self.max_age_seconds is not None:
            body["max_age_seconds"] = self.max_age_seconds
        if self.min_reserve is not None:
            body["min_reserve"] = self.min_reserve
        return body


def _counts(value: Mapping[str, Any]) -> tuple[int, int, int]:
    output = []
    for outcome in ("worked", "failed", "inconclusive"):
        output.append(_nonnegative_int(value.get(outcome, 0), f"outcome_counts.{outcome}"))
    return tuple(output)  # type: ignore[return-value]


@dataclass(frozen=True)
class ControlHypothesis:
    hypothesis_id: str
    version: int
    action_class: str
    chain_id: int
    target: str
    selector: str
    assets: tuple[str, ...]
    incident_type: str
    incident_age_threshold_seconds: int
    required_obligations: tuple[ObligationDefinition, ...]
    enforcement_mode: str
    counterfactual: str
    validity_window_seconds: int
    worked_count: int = 0
    failed_count: int = 0
    inconclusive_count: int = 0
    confidence_bps: int = 10_000
    status: str = "active"
    incident_ids: tuple[str, ...] = ()
    observed_actions: tuple[str, ...] = ()
    outcome_action_ids: tuple[str, ...] = ()
    created_at: int = 0
    updated_at: int = 0

    def __post_init__(self) -> None:
        if self.hypothesis_id != HYPOTHESIS_ID or self.version != 1:
            raise PassportValidationError("only stale-oracle-rebalance/v1 is supported in the MVP")
        if self.action_class != ACTION_CLASS:
            raise PassportValidationError("unsupported action class")
        object.__setattr__(self, "chain_id", _nonnegative_int(self.chain_id, "chain_id"))
        object.__setattr__(self, "target", _canonical_address(self.target, "scope.target"))
        object.__setattr__(self, "selector", _canonical_selector(self.selector, "scope.selector"))
        if self.selector != "0x" + REBALANCE_SELECTOR.hex():
            raise PassportValidationError("hypothesis selector is not the mock rebalance selector")
        if self.incident_type != INCIDENT_TYPE:
            raise PassportValidationError("unsupported incident predicate")
        object.__setattr__(
            self,
            "incident_age_threshold_seconds",
            _nonnegative_int(self.incident_age_threshold_seconds, "incident age threshold"),
        )
        if not self.required_obligations or len({o.obligation_id for o in self.required_obligations}) != len(
            self.required_obligations
        ):
            raise PassportValidationError("hypothesis obligations must be non-empty and unique")
        if tuple(o.obligation_id for o in self.required_obligations) != MVP_PROOF_IDS:
            raise PassportValidationError("MVP hypothesis must select the four approved obligations in order")
        if self.enforcement_mode != "block":
            raise PassportValidationError("MVP stale-oracle hypothesis must be blocking")
        if not self.counterfactual:
            raise PassportValidationError("counterfactual must be non-empty")
        object.__setattr__(
            self,
            "validity_window_seconds",
            _nonnegative_int(self.validity_window_seconds, "validity_window_seconds"),
        )
        for field_name in ("worked_count", "failed_count", "inconclusive_count"):
            _nonnegative_int(getattr(self, field_name), field_name)
        if not isinstance(self.confidence_bps, int) or not 0 <= self.confidence_bps <= 10_000:
            raise PassportValidationError("confidence_bps must be between 0 and 10000")
        if self.status not in HYPOTHESIS_STATUSES:
            raise PassportValidationError("invalid hypothesis status")
        for field_name in ("created_at", "updated_at"):
            _nonnegative_int(getattr(self, field_name), field_name)
        if self.updated_at < self.created_at:
            raise PassportValidationError("updated_at cannot precede created_at")
        for action_digest in self.observed_actions:
            _canonical_hash(action_digest, "observed_actions item")

    @property
    def outcome_counts(self) -> dict[str, int]:
        return {
            "worked": self.worked_count,
            "failed": self.failed_count,
            "inconclusive": self.inconclusive_count,
        }

    def to_body(self) -> dict[str, Any]:
        return {
            "schema": HYPOTHESIS_SCHEMA,
            "hypothesis_id": self.hypothesis_id,
            "version": self.version,
            "action_class": self.action_class,
            "scope": {
                "chain_id": self.chain_id,
                "target": self.target,
                "selector": self.selector,
                "assets": list(self.assets),
            },
            "incident_predicates": {
                "incident_type": self.incident_type,
                "oracle_age_strictly_greater_than_seconds": self.incident_age_threshold_seconds,
            },
            "required_obligations": [o.to_body() for o in self.required_obligations],
            "enforcement_mode": self.enforcement_mode,
            "counterfactual": self.counterfactual,
            "validity_window_seconds": self.validity_window_seconds,
            "outcome_counts": self.outcome_counts,
            "confidence_bps": self.confidence_bps,
            "status": self.status,
            "incident_ids": list(self.incident_ids),
            "observed_actions": list(self.observed_actions),
            "outcome_action_ids": list(self.outcome_action_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> ControlHypothesis:
        if body.get("schema") != HYPOTHESIS_SCHEMA:
            raise PassportMemoryError("invalid Control Hypothesis schema")
        scope = body.get("scope")
        predicate = body.get("incident_predicates")
        raw_obligations = body.get("required_obligations")
        counts = body.get("outcome_counts", {})
        if not isinstance(scope, Mapping) or not isinstance(predicate, Mapping):
            raise PassportMemoryError("Control Hypothesis scope/predicates are malformed")
        if not isinstance(raw_obligations, list) or not isinstance(counts, Mapping):
            raise PassportMemoryError("Control Hypothesis obligations/counts are malformed")
        try:
            obligations = tuple(
                ObligationDefinition(
                    obligation_id=str(item["id"]),
                    blocking=item.get("blocking", True),
                    max_age_seconds=item.get("max_age_seconds"),
                    min_reserve=item.get("min_reserve"),
                )
                for item in raw_obligations
                if isinstance(item, Mapping)
            )
            return cls(
                hypothesis_id=str(body["hypothesis_id"]),
                version=int(body["version"]),
                action_class=str(body["action_class"]),
                chain_id=int(scope["chain_id"]),
                target=str(scope["target"]),
                selector=str(scope["selector"]),
                assets=tuple(str(asset) for asset in scope.get("assets", [])),
                incident_type=str(predicate["incident_type"]),
                incident_age_threshold_seconds=int(
                    predicate["oracle_age_strictly_greater_than_seconds"]
                ),
                required_obligations=obligations,
                enforcement_mode=str(body["enforcement_mode"]),
                counterfactual=str(body["counterfactual"]),
                validity_window_seconds=int(body["validity_window_seconds"]),
                worked_count=_counts(counts)[0],
                failed_count=_counts(counts)[1],
                inconclusive_count=_counts(counts)[2],
                confidence_bps=int(body["confidence_bps"]),
                status=str(body["status"]),
                incident_ids=tuple(str(item) for item in body.get("incident_ids", [])),
                observed_actions=tuple(str(item) for item in body.get("observed_actions", [])),
                outcome_action_ids=tuple(str(item) for item in body.get("outcome_action_ids", [])),
                created_at=int(body["created_at"]),
                updated_at=int(body["updated_at"]),
            )
        except (KeyError, TypeError, ValueError, PassportValidationError) as exc:
            raise PassportMemoryError(f"malformed Control Hypothesis: {exc}") from exc


@dataclass(frozen=True)
class OutcomeRecord:
    action_id: str
    outcome: str

    def __post_init__(self) -> None:
        if not self.action_id or not isinstance(self.action_id, str):
            raise PassportValidationError("outcome action_id must be non-empty")
        if self.outcome not in OUTCOMES:
            raise PassportValidationError(f"invalid outcome: {self.outcome!r}")

    def to_body(self) -> dict[str, str]:
        return {"action_id": self.action_id, "outcome": self.outcome}


def initial_control_hypothesis(action: ActionProposal, *, observed_at: int = 0) -> ControlHypothesis:
    """Create the only supported hypothesis shape for the MVP."""

    return ControlHypothesis(
        hypothesis_id=HYPOTHESIS_ID,
        version=1,
        action_class=ACTION_CLASS,
        chain_id=action.chain_id,
        target=action.target,
        selector=action.selector,
        assets=("MOCK",),
        incident_type=INCIDENT_TYPE,
        incident_age_threshold_seconds=DEFAULT_FRESHNESS_SECONDS,
        required_obligations=(
            ObligationDefinition(PROOF_STATE_ANCHOR, max_age_seconds=DEFAULT_FRESHNESS_SECONDS),
            ObligationDefinition(PROOF_ORACLE, max_age_seconds=DEFAULT_FRESHNESS_SECONDS),
            ObligationDefinition(PROOF_SIMULATION),
            ObligationDefinition(PROOF_INVARIANT, min_reserve=DEFAULT_MIN_RESERVE),
        ),
        enforcement_mode="block",
        counterfactual="simulation alone did not establish oracle freshness and reserve safety",
        validity_window_seconds=DEFAULT_FRESHNESS_SECONDS,
        created_at=_nonnegative_int(observed_at, "observed_at"),
        updated_at=_nonnegative_int(observed_at, "observed_at"),
    )


@under_memory_lock
def save_control_hypothesis(client: Any, hypothesis: ControlHypothesis) -> ControlHypothesis:
    if not isinstance(hypothesis, ControlHypothesis):
        raise TypeError("hypothesis must be ControlHypothesis")
    client.set_reference(HYPOTHESIS_KEY, hypothesis.to_body())
    return hypothesis


@under_memory_lock
def load_control_hypotheses(client: Any) -> tuple[ControlHypothesis, ...]:
    """Read only Passport references through the existing decision-path reader."""

    references = DecisionMemoryView(client).raw_references(REFERENCE_PATTERN_PREFIX)
    result: list[ControlHypothesis] = []
    for key, raw_body in references.items():
        if not key.startswith(HYPOTHESIS_KEY):
            continue
        try:
            body = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
            if not isinstance(body, Mapping):
                raise PassportMemoryError("body is not an object")
            result.append(ControlHypothesis.from_body(body))
        except (TypeError, json.JSONDecodeError, PassportMemoryError) as exc:
            raise PassportMemoryError(f"cannot read {key}: {exc}") from exc
    return tuple(sorted(result, key=lambda item: (item.action_class, item.hypothesis_id)))


def matching_hypotheses(
    hypotheses: Iterable[ControlHypothesis], action: ActionProposal
) -> tuple[ControlHypothesis, ...]:
    return tuple(
        item
        for item in hypotheses
        if item.status == "active"
        and item.action_class == ACTION_CLASS
        and item.chain_id == action.chain_id
        and item.target == action.target
        and item.selector == action.selector
    )


def select_hypothesis(
    hypotheses: Iterable[ControlHypothesis], action: ActionProposal
) -> ControlHypothesis | None:
    """Return exactly one applicable policy; conflicts fail closed."""

    matches = matching_hypotheses(hypotheses, action)
    if len(matches) > 1:
        raise PassportMemoryError("multiple equally applicable Control Hypotheses")
    return matches[0] if matches else None


@under_memory_lock
def record_incident(client: Any, evidence: IncidentEvidence) -> ControlHypothesis:
    """Persist a hypothesis only for deterministic stale-oracle evidence."""

    if evidence.oracle_age_seconds <= DEFAULT_FRESHNESS_SECONDS:
        raise PassportValidationError("fresh-oracle evidence cannot create an incident hypothesis")
    hypothesis = initial_control_hypothesis(evidence.action, observed_at=evidence.observed_at)
    existing = load_control_hypotheses(client)
    if existing:
        selected = select_hypothesis(existing, evidence.action)
        if selected is None:
            raise PassportMemoryError("existing Passport memory conflicts with incident scope")
        if evidence.incident_id in selected.incident_ids:
            return selected
        hypothesis = replace(
            selected,
            incident_ids=(*selected.incident_ids, evidence.incident_id),
            observed_actions=(*selected.observed_actions, evidence.action.action_digest),
            updated_at=max(selected.updated_at, evidence.observed_at),
        )
    else:
        hypothesis = replace(
            hypothesis,
            incident_ids=(evidence.incident_id,),
            observed_actions=(evidence.action.action_digest,),
        )
    return save_control_hypothesis(client, hypothesis)


@under_memory_lock
def record_outcome(
    client: Any,
    hypothesis_id: str,
    *,
    outcome: str,
    action_id: str,
    observed_at: int | None = None,
) -> ControlHypothesis:
    if hypothesis_id != HYPOTHESIS_ID or not action_id:
        raise PassportValidationError("unknown hypothesis or empty action_id")
    record = OutcomeRecord(action_id=action_id, outcome=outcome)
    hypotheses = load_control_hypotheses(client)
    selected = next((item for item in hypotheses if item.hypothesis_id == hypothesis_id), None)
    if selected is None:
        raise PassportMemoryError("Control Hypothesis not found")
    if record.action_id in selected.outcome_action_ids:
        return selected
    # Outcome IDs are kept in the incident_ids-free aggregate for this MVP. A caller must
    # make its action idempotent; recording the same action twice is rejected by the caller
    # in the E2E adapter before this aggregate is updated.
    updates = {
        "worked_count": selected.worked_count,
        "failed_count": selected.failed_count,
        "inconclusive_count": selected.inconclusive_count,
    }
    updates[f"{record.outcome}_count"] += 1
    confidence = max(0, min(10_000, 8_000 + updates["worked_count"] * 200 - updates["failed_count"] * 500))
    next_updated_at = selected.updated_at
    if observed_at is not None:
        next_updated_at = max(selected.updated_at, _nonnegative_int(observed_at, "observed_at"))
    return save_control_hypothesis(
        client,
        replace(
            selected,
            worked_count=updates["worked_count"],
            failed_count=updates["failed_count"],
            inconclusive_count=updates["inconclusive_count"],
            confidence_bps=confidence,
            outcome_action_ids=(*selected.outcome_action_ids, record.action_id),
            updated_at=next_updated_at,
        ),
    )


@under_memory_lock
def delete_control_hypothesis(client: Any) -> bool:
    """Atomically delete only the Passport reference from a shared Sibyl database.

    sibyl-memory-client 0.7.0 has ``delete_entity`` but no public ``delete_reference``.
    The storage transaction is the supported atomic escape hatch; SQLite triggers keep
    the reference/search indexes consistent. No other provider, Firewall, or rubric row
    is touched.
    """

    tenant_id = client.get_tenant()
    with client.storage.transaction() as connection:
        cursor = connection.execute(
            "DELETE FROM reference_documents WHERE tenant_id = ? AND doc_key = ?",
            (tenant_id, HYPOTHESIS_KEY),
        )
        return cursor.rowcount > 0


def hypothesis_ids_hash(hypotheses: Iterable[ControlHypothesis]) -> str:
    ids = sorted(item.hypothesis_id for item in hypotheses)
    return _hash_hex(Web3.keccak(text=canonical_json(ids)), "hypothesis_ids_hash")


def obligation_results_hash(results: Iterable[Mapping[str, Any]]) -> str:
    return _hash_hex(
        Web3.keccak(text=canonical_json(list(results))), "obligation_results_hash"
    )


def memory_root_hex(client: Any) -> str:
    return "0x" + memory_root_for_onchain(client).hex()


@dataclass(frozen=True)
class DeterministicEnvironment:
    """All off-chain observations used by the MVP proof evaluator.

    The environment is injected so tests and the local demo never depend on wall-clock
    timing or a live oracle. A production adapter would have to independently define how
    these observations are obtained; that is outside the mock MVP trust boundary.
    """

    now: int
    current_block_number: int
    current_block_hash: str
    state_block_timestamp: int | None
    oracle_timestamp: int | None
    simulation_action_digest: str | None
    simulation_succeeded: bool | None
    simulated_post_reserve: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "now", _nonnegative_int(self.now, "now"))
        object.__setattr__(
            self,
            "current_block_number",
            _nonnegative_int(self.current_block_number, "current_block_number"),
        )
        object.__setattr__(
            self,
            "current_block_hash",
            _canonical_hash(self.current_block_hash, "current_block_hash"),
        )
        for field_name in ("state_block_timestamp", "oracle_timestamp", "simulated_post_reserve"):
            value = getattr(self, field_name)
            if value is not None:
                _nonnegative_int(value, field_name)
        if self.simulation_action_digest is not None:
            _canonical_hash(self.simulation_action_digest, "simulation_action_digest")
        if self.simulation_succeeded is not None and not isinstance(self.simulation_succeeded, bool):
            raise PassportValidationError("simulation_succeeded must be boolean or None")


@dataclass(frozen=True)
class ObligationResult:
    obligation_id: str
    result: str
    observed: Mapping[str, Any]
    threshold: Mapping[str, Any]
    evidence_digest: str

    def __post_init__(self) -> None:
        if self.obligation_id not in KNOWN_PROOF_IDS or self.obligation_id == PROOF_ROLLBACK:
            raise PassportValidationError("invalid MVP obligation result ID")
        if self.result not in PROOF_RESULTS:
            raise PassportValidationError("invalid obligation result")
        _canonical_hash(self.evidence_digest, "evidence_digest")

    def to_body(self) -> dict[str, Any]:
        return {
            "id": self.obligation_id,
            "result": self.result,
            "observed": dict(self.observed),
            "threshold": dict(self.threshold),
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True)
class ExecutionPassport:
    """Action-bound EIP-712 message produced after all blocking proofs pass."""

    passport_version: int
    action_class: str
    chain_id: int
    target: str
    selector: str
    calldata_hash: str
    value: int
    state_block_number: int
    state_block_hash: str
    hypothesis_ids_hash: str
    obligation_results_hash: str
    memory_root: str
    issued_at: int
    expires_at: int
    nonce: int

    def __post_init__(self) -> None:
        if self.passport_version != PASSPORT_VERSION:
            raise PassportValidationError("unsupported passport version")
        if self.action_class != "0x" + ACTION_CLASS_HASH.hex():
            raise PassportValidationError("passport action class is not treasury-rebalance")
        object.__setattr__(self, "chain_id", _nonnegative_int(self.chain_id, "chain_id"))
        object.__setattr__(self, "target", _canonical_address(self.target, "target"))
        object.__setattr__(self, "selector", _canonical_selector(self.selector))
        for field_name in (
            "calldata_hash",
            "state_block_hash",
            "hypothesis_ids_hash",
            "obligation_results_hash",
            "memory_root",
        ):
            _canonical_hash(getattr(self, field_name), field_name)
        for field_name in (
            "value",
            "state_block_number",
            "issued_at",
            "expires_at",
            "nonce",
        ):
            _nonnegative_int(getattr(self, field_name), field_name)
        if self.expires_at < self.issued_at:
            raise PassportValidationError("expires_at precedes issued_at")
        if self.expires_at - self.issued_at > PASSPORT_MAX_LIFETIME_SECONDS:
            raise PassportValidationError("passport lifetime exceeds MVP maximum")

    def to_message(self) -> dict[str, Any]:
        return {
            "passportVersion": self.passport_version,
            "actionClass": self.action_class,
            "chainId": self.chain_id,
            "target": self.target,
            "selector": self.selector,
            "calldataHash": self.calldata_hash,
            "value": self.value,
            "stateBlockNumber": self.state_block_number,
            "stateBlockHash": self.state_block_hash,
            "hypothesisIdsHash": self.hypothesis_ids_hash,
            "obligationResultsHash": self.obligation_results_hash,
            "memoryRoot": self.memory_root,
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
            "nonce": self.nonce,
        }

    def typed_data(self, verifier_address: str) -> dict[str, Any]:
        return {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "ExecutionPassport": [
                    {"name": name, "type": field_type}
                    for name, field_type in PASSPORT_TYPE_FIELDS
                ],
            },
            "primaryType": "ExecutionPassport",
            "domain": {
                "name": EIP712_DOMAIN_NAME,
                "version": EIP712_DOMAIN_VERSION,
                "chainId": self.chain_id,
                "verifyingContract": _canonical_address(verifier_address, "verifier_address"),
            },
            "message": self.to_message(),
        }

    def sign(self, verifier_address: str, private_key: str | bytes | int) -> str:
        signable = encode_typed_data(full_message=self.typed_data(verifier_address))
        return "0x" + Account.sign_message(signable, private_key).signature.hex()


def build_execution_passport(
    action: ActionProposal,
    hypothesis: ControlHypothesis,
    results: Iterable[ObligationResult],
    *,
    memory_root_value: str,
    issued_at: int,
    expires_at: int,
    nonce: int,
) -> ExecutionPassport:
    """Create a passport only after all blocking results have passed."""

    ordered_results = tuple(results)
    if not obligations_allow_execution(hypothesis, ordered_results):
        raise PassportValidationError("cannot mint passport while a blocking obligation is not satisfied")
    return ExecutionPassport(
        passport_version=PASSPORT_VERSION,
        action_class="0x" + ACTION_CLASS_HASH.hex(),
        chain_id=action.chain_id,
        target=action.target,
        selector=action.selector,
        calldata_hash=action.calldata_hash,
        value=action.value,
        state_block_number=action.state_block_number,
        state_block_hash=action.state_block_hash,
        hypothesis_ids_hash=hypothesis_ids_hash((hypothesis,)),
        obligation_results_hash=obligation_results_hash(
            result.to_body() for result in ordered_results
        ),
        memory_root=_canonical_hash(memory_root_value, "memory_root"),
        issued_at=_nonnegative_int(issued_at, "issued_at"),
        expires_at=_nonnegative_int(expires_at, "expires_at"),
        nonce=_nonnegative_int(nonce, "nonce"),
    )


def _obligation_result(
    obligation: ObligationDefinition,
    result: str,
    observed: Mapping[str, Any],
    threshold: Mapping[str, Any],
) -> ObligationResult:
    body = {
        "id": obligation.obligation_id,
        "result": result,
        "observed": dict(observed),
        "threshold": dict(threshold),
    }
    digest = _hash_hex(Web3.keccak(text=canonical_json(body)), "evidence_digest")
    return ObligationResult(obligation.obligation_id, result, observed, threshold, digest)


def evaluate_obligations(
    action: ActionProposal,
    hypothesis: ControlHypothesis,
    environment: DeterministicEnvironment,
) -> tuple[ObligationResult, ...]:
    """Evaluate exactly the proof list selected by the retrieved hypothesis.

    No default result is a pass. Unknown/missing observations are explicitly
    ``unverifiable`` so the caller can fail closed.
    """

    if select_hypothesis((hypothesis,), action) is None:
        raise PassportValidationError("hypothesis does not match action scope")
    results: list[ObligationResult] = []
    for obligation in hypothesis.required_obligations:
        if obligation.obligation_id == PROOF_STATE_ANCHOR:
            age = (
                None
                if environment.state_block_timestamp is None
                else environment.now - environment.state_block_timestamp
            )
            threshold = {"max_age_seconds": obligation.max_age_seconds}
            observed = {
                "age_seconds": age,
                "state_block_number": action.state_block_number,
                "current_block_number": environment.current_block_number,
                "state_block_hash": action.state_block_hash,
                "current_block_hash": environment.current_block_hash,
            }
            if age is None or age < 0 or obligation.max_age_seconds is None:
                result = "unverifiable"
            elif action.state_block_number > environment.current_block_number:
                result = "unverifiable"
            elif age > obligation.max_age_seconds:
                result = "unsatisfied"
            elif action.state_block_hash != environment.current_block_hash:
                result = "unsatisfied"
            else:
                result = "satisfied"
        elif obligation.obligation_id == PROOF_ORACLE:
            age = (
                None
                if environment.oracle_timestamp is None
                else environment.now - environment.oracle_timestamp
            )
            threshold = {"max_age_seconds": obligation.max_age_seconds}
            observed = {"age_seconds": age, "oracle_timestamp": environment.oracle_timestamp}
            if age is None or age < 0 or obligation.max_age_seconds is None:
                result = "unverifiable"
            elif age <= obligation.max_age_seconds:
                result = "satisfied"
            else:
                result = "unsatisfied"
        elif obligation.obligation_id == PROOF_SIMULATION:
            threshold = {"action_digest": action.action_digest}
            observed = {
                "simulation_action_digest": environment.simulation_action_digest,
                "simulation_succeeded": environment.simulation_succeeded,
            }
            if (
                environment.simulation_action_digest is None
                or environment.simulation_succeeded is None
            ):
                result = "unverifiable"
            elif environment.simulation_action_digest != action.action_digest:
                result = "unsatisfied"
            elif not environment.simulation_succeeded:
                result = "unsatisfied"
            else:
                result = "satisfied"
        elif obligation.obligation_id == PROOF_INVARIANT:
            threshold = {"min_reserve": obligation.min_reserve}
            observed = {"simulated_post_reserve": environment.simulated_post_reserve}
            if obligation.min_reserve is None or environment.simulated_post_reserve is None:
                result = "unverifiable"
            elif environment.simulated_post_reserve >= obligation.min_reserve:
                result = "satisfied"
            else:
                result = "unsatisfied"
        else:  # pragma: no cover - ControlHypothesis validation prevents this
            result = "unverifiable"
            threshold = {}
            observed = {}
        results.append(_obligation_result(obligation, result, observed, threshold))
    return tuple(results)


def obligations_allow_execution(
    hypothesis: ControlHypothesis, results: Iterable[ObligationResult]
) -> bool:
    by_id = {result.obligation_id: result for result in results}
    return all(
        obligation.obligation_id in by_id
        and by_id[obligation.obligation_id].result == "satisfied"
        for obligation in hypothesis.required_obligations
        if obligation.blocking
    )


@dataclass(frozen=True)
class PassportEvidenceBundle:
    action: ActionProposal
    hypothesis_id: str
    memory_root: str
    results: tuple[ObligationResult, ...]
    simulation_action_digest: str | None
    simulated_post_reserve: int | None

    def to_body(self) -> dict[str, Any]:
        return {
            "action": self.action.to_body(),
            "hypothesis_id": self.hypothesis_id,
            "memory_root": self.memory_root,
            "obligation_results": [result.to_body() for result in self.results],
            "obligation_results_hash": obligation_results_hash(
                result.to_body() for result in self.results
            ),
            "simulation_action_digest": self.simulation_action_digest,
            "simulated_post_reserve": self.simulated_post_reserve,
        }


@dataclass(frozen=True)
class PassportDecision:
    decision: str
    reason: str
    hypothesis: ControlHypothesis | None = None
    results: tuple[ObligationResult, ...] = ()
    passport: ExecutionPassport | None = None
    evidence: PassportEvidenceBundle | None = None

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise PassportValidationError(f"invalid passport decision: {self.decision!r}")
        if not self.reason:
            raise PassportValidationError("passport decision reason must be non-empty")
        if self.decision == "passport-issued" and self.passport is None:
            raise PassportValidationError("issued decision must include a passport")
        if self.decision != "passport-issued" and self.passport is not None:
            raise PassportValidationError("blocked/review decision cannot include a passport")

    @property
    def issued(self) -> bool:
        return self.decision == "passport-issued"


@under_memory_lock
def evaluate_rebalance_for_passport(
    client: Any,
    action: ActionProposal,
    environment: DeterministicEnvironment,
    *,
    verifier_address: str,
    issued_at: int,
    nonce: int,
    expires_at: int | None = None,
) -> PassportDecision:
    """Single decision entry point from action proposal to review/block/passport.

    The strict policy is never selected from a code fallback. If Passport memory is
    empty, unreadable, or conflicting, the result is human review and no signature.
    """

    try:
        hypotheses = load_control_hypotheses(client)
        selected = select_hypothesis(hypotheses, action)
    except (PassportMemoryError, MemoryIntegrityError, OSError) as exc:
        return PassportDecision("human-review-required", f"memory-unavailable: {exc}")
    if selected is None:
        return PassportDecision(
            "human-review-required",
            "no-matching-hypothesis: bootstrap human review required",
        )

    results = evaluate_obligations(action, selected, environment)
    if not obligations_allow_execution(selected, results):
        failed = ",".join(
            result.obligation_id
            for result in results
            if result.result != "satisfied"
        )
        return PassportDecision("block", f"blocking obligations failed: {failed}", selected, results)

    root = memory_root_hex(client)
    expiry = issued_at + PASSPORT_MAX_LIFETIME_SECONDS if expires_at is None else expires_at
    passport = build_execution_passport(
        action,
        selected,
        results,
        memory_root_value=root,
        issued_at=issued_at,
        expires_at=expiry,
        nonce=nonce,
    )
    evidence = PassportEvidenceBundle(
        action=action,
        hypothesis_id=selected.hypothesis_id,
        memory_root=root,
        results=results,
        simulation_action_digest=environment.simulation_action_digest,
        simulated_post_reserve=environment.simulated_post_reserve,
    )
    return PassportDecision(
        "passport-issued",
        "all blocking obligations satisfied",
        selected,
        results,
        passport,
        evidence,
    )
