# Live Base Sepolia pipeline (84532) — ACP job 417

> **Historical.** This records the earlier product direction, the escrow referee, where the vault
> itself was the evaluator. It is kept because the run really happened and the transactions are
> still on chain. The current direction is the Execution Passport.

One real job drove the whole pipeline on 2026-09-04: **createJob → setBudget → fund → submit →
postVerdict → finalize → `JobCompleted`**. The evaluator on this job is the `EvaluatorVault`
contract, not an EOA, so the vault really does decide the provider payout.

The verdict was hardcoded and memory was still empty on this run — the ONLY thing proven here
is the pipeline.

## Roles (three distinct addresses, enforced by the contract)

| Role | Address |
|---|---|
| Client | `0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2` |
| Provider | `0x20212E4D95A75E6716575ED26e884cdeFf66b321` |
| Evaluator (contract) | `0x5c6EE4586ACABcb6326069c229E58091B21ef384` |
| Agent wallet (drives the vault) | `0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894` |
| ACP | `0x0b93793923CD5De81850aF8604a233f3f24d461e` |
| Escrow token | `0xECc22a8F6fD62388498fBa19813E214605a2BDb3` |

`createJob` reverts `ClientIsProvider()` `0x332ff0f9` when client == provider, so these three
addresses are not a matter of taste. The agent wallet is deliberately NOT the provider
(ADR-017 point 3).

## Four key transactions

1. **createJob** — [`0x20bc0e46…be70a`](https://sepolia.basescan.org/tx/0x20bc0e469d86316089ab1868d396819804419168ff256300ae7c7f821bfbe70a)
2. **fund** — [`0xa5b5ea60…81f370`](https://sepolia.basescan.org/tx/0xa5b5ea60a35cfb2d253144772fee6016cb67441c5ec441e6ae4d4357cd81f370)
3. **postVerdict** — [`0x54a72152…b86dfb`](https://sepolia.basescan.org/tx/0x54a72152a922f02f62ca18d71d781ea7bc833b6df70e415ce84a9888f7b86dfb) (block 46378567)
4. **finalize** — [`0x808d63be…db9f33`](https://sepolia.basescan.org/tx/0x808d63be45a506ef13a9cc047194f9bb5d3f3eb875ad513b1c08b09836db9f33) (block 46378631)

Two provider transactions complete the flow:
`setBudget` [`0x969b0e54…c014153`](https://sepolia.basescan.org/tx/0x969b0e54d82e5e0da3c157dc19ca404d22e58e22142924067dc2c2303c014153),
`submit` [`0x607f88b3…9f53eb`](https://sepolia.basescan.org/tx/0x607f88b3fcbc5141fe6dad9d805bca7fbc55c7a14d2a199a570ff7cbba9f53eb).

The basescan links above are artifacts for HUMANS, not machine proof: basescan blocks
automated access with HTTP 403. The machine proof is below.

## `JobCompleted` on chain

```
$ cast logs --address 0x0b93793923CD5De81850aF8604a233f3f24d461e \
    "JobCompleted(uint256,address,bytes32)" 417 \
    --from-block 46368632 --to-block 46378631 --rpc-url https://sepolia.base.org
- address: 0x0b93793923CD5De81850aF8604a233f3f24d461e
  blockHash: 0xb3a1b93c27dd7bcd7dfdd07bda32cef9ff704a829b2b8d5bd04da6312de37345
  blockNumber: 46378631
  data: 0x6478e788a7953cf990091291d8d1b4f3f046567a915e5158d4dcf57d9fd845b0
  logIndex: 127
  removed: false
  topics: [
  	0x0fd54bd364fa9e67f17b091aefe930932c09fe7651cf5ad02c71a418f3341444
  	0x00000000000000000000000000000000000000000000000000000000000001a1
  	0x0000000000000000000000005c6ee4586acabcb6326069c229e58091b21ef384
  ]
  transactionHash: 0x808d63be45a506ef13a9cc047194f9bb5d3f3eb875ad513b1c08b09836db9f33
  transactionIndex: 10
```

Topic 1 = `0x1a1` = jobId 417. Topic 2 = the vault address: **the evaluator that passed this
job is our contract**. `data` = the `reasonHash` the vault announced at `postVerdict`.

The block range MUST be <= 10,000; go wider and the public RPC answers HTTP 413 (`-32614`),
not an empty result.

## Final status & fund flow

```
$ cast call 0x0b93793923CD5De81850aF8604a233f3f24d461e \
    "jobs(uint256)(address,uint8,address,uint48,address,address,uint256,string)" 417 \
    --rpc-url https://sepolia.base.org
0xbe2c447e577F95ed2D5cD20C75cF7633FA0602C2
3
0x20212E4D95A75E6716575ED26e884cdeFf66b321
1788527304
0x5c6EE4586ACABcb6326069c229E58091B21ef384
0x0000000000000000000000000000000000000000
1000000
"the-evaluator smoke job: provider menyerahkan satu deliverable, EvaluatorVault yang menilai."
```

status = 3 (Completed). The 1 USDC budget splits exactly:

| Recipient | Amount | Note |
|---|---|---|
| Provider | 940,000 | payout |
| Vault (evaluator fee) | 50,000 | `evaluatorFeeBP()` = 500 = 5% |
| Platform | 10,000 | 1% |

940,000 + 50,000 + 10,000 = 1,000,000 was measured from `balanceOf` after `finalize`, not
worked out on paper.

**Debt visible from here, and NOT closed:** the vault holds 50,000 tokens and has no way out.
`sweepToken(address,address) onlyArbiter` landed in the source (commit `e675234`) as code +
tests ONLY; ADR-022 froze the addresses above as the submission contracts and cancelled the
redeploy, so that function IS NOT in the deployed bytecode — proven directly:
`cast call 0x5c6EE4586ACABcb6326069c229E58091B21ef384 "sweepToken(address,address)" ...` →
`execution reverted`. 50,000 units (0.05 testnet USDC) are stranded permanently; ADR-018
decision 2 gave this up knowingly, it is not an oversight.

## How to replay

```
pnpm --filter sim run job:min          # createJob + setBudget + fund + submit → new jobId
cd agent && uv run python -m agent.vault_client --job-id <jobId>   # postVerdict → wait 120 s → finalize
```

Time budget: the verdict MUST be `finalize`d before `expiredAt + 900`. Past that threshold
anyone may `claimRefund` a Submitted job and the verdict is orphaned — a later `complete()`
reverts `WrongStatus()`. This run finished 2,655 seconds before that threshold.
