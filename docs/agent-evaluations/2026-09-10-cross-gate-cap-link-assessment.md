## What was checked

The proposed link would make a treasury incident recorded by gate 2 tighten a provider's
budget cap at gate 1. I checked the promotion rule in ADR-002, the write contract of
`record_failure_observation`, the inputs and guarantees of `derive_cap`, and the frozen
root boundary guarded by `MEMORY_ROOT_ENCODING_FROZEN`.

`record_failure_observation(client, pattern, *, job_id)` requires a non-negative integer
ACP job ID. A treasury incident has no ACP job ID. There is no truthful value to pass, and
inventing one would make the evidence journal claim that an ACP job existed when it did
not.

Provider `risk_level` is recomputed from distinct deterministic incident jobs. A confirmed
failure pattern reaches the provider only after `promotion_eligible` sees evidence from at
least two distinct jobs. `derive_cap` then consumes that risk level, the provider's prior
cap, budgets from jobs that actually passed, and fixed constants.

The frozen root flag protects the encoding algorithm and the single approved on-chain root
entrypoint. Adding a truthful record under an already-covered namespace would change the
root value, as intended, without changing its encoding. Changing the provider schema or the
set encoded by `memory_root` would put the frozen encoding in scope.

## What it would break

Answer 1 is blocking: the existing observation API cannot represent a treasury incident
without a false ACP `job_id`. Answer 2 is also blocking: directly increasing provider risk
from one treasury incident would bypass ADR-002's requirement for deterministic evidence
from at least two distinct jobs. The proposal also lacks an established identity mapping
from the treasury actor in gate 2 to an ACP provider in gate 1.

Answer 3 remains true only in the narrow numeric sense. The budgets used by `derive_cap`
could remain limited to passed ACP jobs and constants, but the meaning of its risk input
would change. That is still a rule change, not a new write path.

Answer 4 does not independently forbid the feature. A new record inside the existing
`pattern:` coverage can move the root without changing the frozen encoding. Any attempt to
add a new root namespace or reshape the encoded provider data would require explicit root
compatibility work and its frozen-vector tests.

## Recommendation

**needs-rule-change**. Defer this link until after submission. Answers 1 and 2 decide the
recommendation: the current API requires a fictional ACP job ID, and the desired one-event
risk increase conflicts with ADR-002's two-distinct-job promotion rule. A later design must
first define a truthful cross-protocol evidence identifier, an authenticated mapping from a
treasury actor to an ACP provider, and a new ADR that explicitly revises the promotion and
risk semantics. It should preserve `derive_cap`'s passed-budget-only numeric guarantee and
leave the frozen root encoding unchanged.
