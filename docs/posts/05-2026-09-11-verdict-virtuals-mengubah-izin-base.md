---
title: "Two rejections on Virtuals, and Base stops answering"
date: 2026-09-11
project: REFERI (Sibyl hackathon, Base Sepolia)
repo: PassportVerifier v2 0xfB59bE1D2bb2418406cFD02b7141978dc1cfE3Ea, EvaluatorVault 0x5c6EE4586ACABcb6326069c229E58091B21ef384
note: written and shipped after the submission deadline; see the README post-deadline note
---

Yesterday we showed that both gates hash the same memory. Today one gate changes its answer
because of what the other one learned.

## The flow, in the order it happened

1. A provider wallet with no verdict history asks the Base gate for a passport to move 100,000
   from the mock treasury. The fifth obligation, `actor-standing`, reads that wallet's profile
   from the ACP gate's store: nothing there. Passport issued, bound to the wallet. The wallet
   consumes it: `PassportConsumed` with `executor=0xa2be…2cde`, treasury reserve 1,000,000 to
   900,000. [tx](https://base-sepolia.blockscout.com/tx/0x680c74dfb3568dfed2bdf425cd4141f9924ccbe43f50fac34ac44ee482e212a4)
2. Two ACP jobs from that same wallet, 424 and 425, carry a deliverable with a placeholder line.
   The evaluator vault rejects both. After the second, the profile holds two incident jobs,
   `risk_level=2`, and a confirmed pattern. [424](https://base-sepolia.blockscout.com/tx/0x065d334397080c312143579e8891b6ce3b901f7a8fbce015c4ea9ed200562ccd)
   [425](https://base-sepolia.blockscout.com/tx/0x8d158744ec48319ad54e1461f322da33078f2b5b53128a200559d8e847627fa3)
3. The same request again. Output, verbatim:

```
executor=0xa2beb04be7f3d0948828cf1893876513f4fa2cde
acp_profile=found risk_level=2 incident_jobs=424,425 confirmed_patterns=format.placeholder-text
actor_standing=unsatisfied max_risk_level=0
decision=block
```

No code path was flipped between step 1 and step 3. The only thing that changed is memory, and
memory changed because of verdicts on a different protocol.

## What the contract enforces

`PassportVerifier` v2 does not read Sibyl. It enforces two things memory decided: the calldata
hash and the executor. Anyone else who presents that passport gets `WrongExecutor`. That is the
line between "the agent said no" and "the chain would not let it happen anyway".

## What we are still not claiming

The refusal itself is off-chain. The key is the identity, not a legal party. Nothing flows from
Base back to Virtuals; that direction needs a rule change we chose not to make. And all of this
landed on 11 September, after the deadline: the tag `submission-2026-09-10` marks what was
submitted. All four are in `docs/limitations.md` item 37.
