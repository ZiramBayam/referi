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

Update, 11 Sep (after the deadline): the functional link now exists in one direction. See post 5.
