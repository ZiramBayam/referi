---
title: "We changed the product on day nine, and the memory argument got stronger"
date: 2026-09-10
project: REFERI (Sibyl hackathon, Base Sepolia)
repo: EvaluatorVault 0x5c6EE4586ACABcb6326069c229E58091B21ef384 (earlier direction, frozen)
---

Two posts ago this project was an escrow referee. It still runs, it is still deployed, and five
evaluation jobs really landed on Base Sepolia. This post is about why we stopped building it, and
what the change did to the one claim we actually care about: that the memory is load-bearing.

## What gate 1 proved, and where it stopped

The referee read a provider's history out of Sibyl and used it to set two things: how deeply the
deliverable got checked, and how large a budget that provider was allowed. Jobs 421 and 422 carry
byte-for-byte identical deliverables. 421 passed. 422 was rejected. The only difference was memory.

That is a real result and we are keeping it. But look at where memory sat in that design: it changed
**how carefully we graded a document**. If the memory had been wrong, or missing, the worst outcome
was a document graded at the wrong depth. Nobody's money moved because of it.

The uncomfortable question a judge asks in one sentence: is memory doing work here, or is it
decorating a decision that would have been fine anyway?

## The version where the answer is not arguable

So we moved memory to the place where being wrong is expensive: the transaction boundary.

Execution Passport takes an incident (an agent moved value on an oracle reading that was already two
minutes stale), stores it as a structured Control Hypothesis, and compiles it into four proof
obligations that have to hold before that class of action can move value again. Only when all four
hold does the agent sign a short-lived EIP-712 passport bound to the exact target, selector, calldata
hash, chain, memory root, and nonce. A verifier accepts that passport once.

The test we could not run before, and can now:

```
passport_memory_deleted=True after_delete_decision=human-review-required
```

Delete the hypothesis and the same action goes back to human review. Not to a permissive default, not
to a cached answer, to a stop. There is no fallback threshold in the code to fall back to, which is
the point: the sixty-second oracle window and the reserve floor are read out of memory, and
`thresholds_from_memory=oracle=60 reserve=250000` is printed by the run so you do not have to take our
word for it.

## The part that cost us

Changing direction on day nine is not free, and we would rather write the bill down than have someone
find it.

**The on-chain evidence belonged to the old product.** `EvaluatorVault` is on Base Sepolia. The
passport verifier was not, so for a while the thing we were pitching had no chain footprint while the
thing we had abandoned had a frozen, verified contract. That is fixed: `PassportVerifier`,
`MockTreasury`, and `MockOracle` are on Base Sepolia at block 46629087, all three verified on Sourcify,
for 0.0000088 ETH. The verifier is bound to that treasury and to one signer, both immutable, and you
can read both back with a single `cast call`. Addresses and the post-deploy state are in
`deployments/passport-84532.json`.

**Every artifact told the old story.** The README opened with "an ERC-8183 escrow referee". The demo
video script did not contain the word "passport" once. Both build-in-public posts were about
providers and escrow. Meanwhile the website had already been rebuilt around the new product. Anyone
reading the repo top to bottom would have seen two projects. That is fixed now, and this post exists
partly because a third artifact saying "the direction changed, here is why" is cheaper than hoping
nobody notices the seam.

**We had to say no to the more impressive-sounding version.** Execution Passport only reaches failures
that can be written down as a checkable precondition: oracle staleness, a reserve floor, an exact
simulation match. It does not catch bad judgement, a novel exploit, or a mispriced risk. The headline
we wanted was "an agent should not repeat the failure it already survived". The headline the mechanism
earns is narrower, and we would rather ship the narrow one that works.

## What is actually enforced today

One action class, `treasury-rebalance`, against a mock treasury and a mock oracle on testnet. Four
obligations, all blocking. Sixty-second passport lifetime, single use. Missing or conflicting memory
produces human review, never a pass.

Safe integration, production oracles, and other action classes are roadmap. They are not in the demo,
so they are not in the pitch.

## Run it yourself

```sh
make demo-passport
```

Anvil and nothing else. It deploys the fixture, seeds the incident, proves recall from a fresh
process, rejects a mutated passport, executes exactly once, then deletes the memory and shows the
behaviour revert. Roughly forty seconds.

If it does something different from what this post says, the run is right and the post is wrong.

## A correction to this post

Calling this a pivot was accurate about our attention and wrong about the architecture.
The two gates share one Sibyl store, one `pattern:` namespace, and one root function, and
the root the ACP gate announces on chain commits to the Base gate's policy. We did not
abandon half the project, we added a second enforcement point to the same memory. Post 4
shows the command that proves it.
