# Execution Passport — Canonical Formats

This document freezes the bytes shared by the Python agent, the local simulator, and
`PassportVerifier.sol`. A change to any field name, order, type, enum string, timestamp
unit, or hash preimage requires a new format version and a new fixed test vector.

## MVP constants

```text
action_class       = treasury-rebalance
incident_type      = stale-oracle-rebalance
rebalance ABI      = rebalance(uint256 amount)
obligation window  = 60 Unix seconds (loaded from Control Hypothesis)
timestamp unit     = Unix seconds
expiry semantics   = issued_at <= now <= expires_at
```

The MVP target is one deployed `MockTreasury` and the only allowed selector is the first
four bytes of `rebalance(uint256)`.

## Canonical strings

```text
proof results: satisfied | unsatisfied | unverifiable
decisions:     passport-issued | block | human-review-required
outcomes:      worked | failed | inconclusive
hypothesis:    active | retired
```

The action class and incident type are encoded as UTF-8 strings in JSON memory bodies.
They are encoded as `bytes32` hashes in the EIP-712 passport:

```text
ACTION_CLASS_HASH = keccak256(utf8("treasury-rebalance"))
```

## Action proposal

The canonical JSON field order is illustrative only; hashes use the typed ABI encoding
below, not JSON:

```json
{
  "chain_id": 84532,
  "target": "0x0000000000000000000000000000000000000001",
  "selector": "0xf4993018",
  "calldata": "0xf499301800000000000000000000000000000000000000000000000000000000000f4240",
  "value": 0,
  "state_block_number": 123,
  "state_block_hash": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

Addresses are lower-case `0x` + 40 hexadecimal characters. `calldata` is the complete
ABI-encoded bytes including the four-byte selector. Integers are non-negative integers.

## Action and calldata hashes

```text
calldata_hash = keccak256(calldata)
action_digest = keccak256(abi.encode(
  ACTION_DIGEST_TYPEHASH,
  uint256(chain_id),
  address(target),
  bytes4(selector),
  bytes32(calldata_hash),
  uint256(value),
  uint256(state_block_number),
  bytes32(state_block_hash)
))
```

The type hash is:

```text
ACTION_DIGEST_TYPEHASH = keccak256(
  "Action(uint256 chainId,address target,bytes4 selector,bytes32 calldataHash,uint256 value,uint256 stateBlockNumber,bytes32 stateBlockHash)"
)
```

`selector` must equal the first four bytes of `calldata`. The agent rejects a proposal where
they disagree before any proof is evaluated.

## Control Hypothesis memory

The Sibyl reference key is:

```text
pattern:passport.control-hypothesis.stale-oracle-rebalance.v1
```

The body is a structured object. It is not executable prose and must pass validation:

```json
{
  "schema": "execution-passport/control-hypothesis/v1",
  "hypothesis_id": "stale-oracle-rebalance/v1",
  "version": 1,
  "action_class": "treasury-rebalance",
  "scope": {
    "chain_id": 84532,
    "target": "0x0000000000000000000000000000000000000001",
    "selector": "0xf4993018",
    "assets": ["MOCK"]
  },
  "incident_predicates": {
    "incident_type": "stale-oracle-rebalance",
    "oracle_age_strictly_greater_than_seconds": 60
  },
  "required_obligations": [
    {"id": "state-anchor-fresh", "blocking": true, "max_age_seconds": 60},
    {"id": "oracle-freshness", "blocking": true, "max_age_seconds": 60},
    {"id": "simulation-match", "blocking": true},
    {"id": "post-state-invariant", "blocking": true, "min_reserve": 250000}
  ],
  "enforcement_mode": "block",
  "counterfactual": "simulation alone did not establish oracle freshness and reserve safety",
  "validity_window_seconds": 60,
  "outcome_counts": {"worked": 0, "failed": 0, "inconclusive": 0},
  "confidence_bps": 10000,
  "status": "active",
  "created_at": 0,
  "updated_at": 0,
  "incident_ids": [],
  "observed_actions": [],
  "outcome_action_ids": []
}
```

`created_at` and `updated_at` are Unix-second timestamps from deterministic incident or
outcome observations. They are metadata for lifecycle/auditability and are not hidden
policy inputs.

`rollback-route` is a recognized future obligation type but is not included in this MVP
list. Passport memory deletion removes the targeted Control Hypothesis reference from the
shared database; a strict policy must not be reconstructed from code when the reference is
absent.

## EIP-712 passport

The domain is:

```text
EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)
name    = Execution Passport
version = 1
```

The exact typed struct is:

```text
ExecutionPassport(
  uint256 passportVersion,
  bytes32 actionClass,
  uint256 chainId,
  address target,
  bytes4 selector,
  bytes32 calldataHash,
  uint256 value,
  uint256 stateBlockNumber,
  bytes32 stateBlockHash,
  bytes32 hypothesisIdsHash,
  bytes32 obligationResultsHash,
  bytes32 memoryRoot,
  uint256 issuedAt,
  uint256 expiresAt,
  uint256 nonce
)
```

The passport type hash is:

```text
EXECUTION_PASSPORT_TYPEHASH = keccak256(
  "ExecutionPassport(uint256 passportVersion,bytes32 actionClass,uint256 chainId,address target,bytes4 selector,bytes32 calldataHash,uint256 value,uint256 stateBlockNumber,bytes32 stateBlockHash,bytes32 hypothesisIdsHash,bytes32 obligationResultsHash,bytes32 memoryRoot,uint256 issuedAt,uint256 expiresAt,uint256 nonce)"
)
```

The signer signs the EIP-712 digest:

```text
keccak256("\\x19\\x01" || domain_separator || struct_hash)
```

The verifier checks the exact supplied calldata against `calldataHash`; it does not trust
a separately supplied human-readable action description.

## Obligation result hash

Results are sorted in the same order as `required_obligations`. Each result is canonical
JSON with no floating point values:

```json
{
  "id": "oracle-freshness",
  "result": "satisfied",
  "observed": {"age_seconds": 12, "oracle_timestamp": 1000},
  "threshold": {"max_age_seconds": 60},
  "evidence_digest": "0x...",
  "explanation": "oracle observation is within the remembered freshness window"
}
```

```text
obligation_results_hash = keccak256(UTF-8(canonical_json(results_array)))
hypothesis_ids_hash     = keccak256(UTF-8(canonical_json(sorted_ids_array)))
```

The contract binds both hashes through the trusted policy signer but does not independently
query Sibyl, the oracle, or the simulator. The off-chain evidence bundle is authoritative
only within the mock MVP trust boundary and must never be described as an audited proof.

Outcome calibration is deterministic and duplicate-safe: a repeated `action_id` is a
no-op; otherwise `worked` increments confidence by 200 BPS, `failed` decreases it by 500
BPS, and `inconclusive` leaves the score unchanged. The score is recomputed from the
bounded baseline formula `clamp(8000 + worked_count*200 - failed_count*500, 0, 10000)`.
`updated_at` advances only from an explicitly supplied observation timestamp and never
moves backwards; calibration never auto-retires or relaxes the blocking policy.

## Fixed vector 1

The following values are a cross-language regression vector. Inputs are: chain `84532`,
target `0x00000000000000000000000000000000000000aa`, amount `100000`, state block `10`,
state block hash `0x11` repeated 32 times, hypothesis `stale-oracle-rebalance/v1`, memory
root `0x44` repeated 32 times, `issued_at=1000`, `expires_at=1030`, nonce `1`, and verifier
`0x00000000000000000000000000000000000000cc`.

```text
selector                 = 0xf4993018
calldata                 = 0xf499301800000000000000000000000000000000000000000000000000000000000186a0
calldata_hash            = 0xe88f9b14f8921d7450af76f0d8ab7aa348bde46316d628ab6f91e9dac0c582a3
action_digest            = 0xa5f373496d1d79b025a7d8154046861cbc61ed45a24cf8533ee974d95d5bc830
hypothesis_ids_hash      = 0xb1e9546ad67d2b7e25027c4ed279adafc69e9ec84dd1ef94ea3da9dca60d6ecd
obligation_results_hash  = 0x49a8d4f0ccf032c5649f4a25b0d3a35162c11b54bb6cd35a80ca711852f6140a
passport_digest           = 0x1f5ece583170ab17407e77846f1f5c4dab174153a93cebe81787221001b97b0b
```

The corresponding test-only private key is `0x12` repeated 32 times. It must never be
used for real funds. The signature is intentionally not frozen here because its `v/r/s`
representation can vary when a signing library normalizes the recovery ID; the digest and
recovered signer are the interoperability contract.
