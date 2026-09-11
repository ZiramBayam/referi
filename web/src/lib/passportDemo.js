/**
 * Browser-safe fixture for the public Execution Passport room.
 *
 * This mirrors the canonical MVP vocabulary without pretending to be a live
 * signer or chain connection. The production adapter can replace this pure
 * function when public testnet deployment addresses are available.
 */

export const ACTION_CLASS = "treasury-rebalance";
export const INCIDENT_TYPE = "stale-oracle-rebalance";
export const HYPOTHESIS_ID = "stale-oracle-rebalance/v1";
export const CHAIN_ID = 84532;
export const CHAIN_LABEL = "Base Sepolia";
export const INITIAL_RESERVE = 1_000_000;
export const MINIMUM_RESERVE = 250_000;
export const FRESHNESS_WINDOW = 60;
export const REBALANCE_SELECTOR = "0xf4993018";

/** @param {number} amount */
function calldataFor(amount) {
  const encoded = Math.max(0, amount).toString(16).padStart(64, "0");
  return `${REBALANCE_SELECTOR}${encoded}`;
}

/**
 * Evaluate the same user-visible decision states as the MVP control plane.
 * No private key, RPC, or transaction is touched here.
 *
 * @param {{ amount?: number, memoryAvailable?: boolean, oracleFresh?: boolean }} input
 */
export function evaluateDemoAction(input = {}) {
  const amount = typeof input.amount === "number" && Number.isInteger(input.amount) ? input.amount : 100_000;
  const memoryAvailable = input.memoryAvailable !== false;
  const oracleFresh = input.oracleFresh === true;
  const safeAmount = Math.max(0, amount);
  const postReserve = Math.max(0, INITIAL_RESERVE - safeAmount);
  const invariantSatisfied = postReserve >= MINIMUM_RESERVE;
  const simulationSatisfied = safeAmount <= INITIAL_RESERVE;
  const calldata = calldataFor(safeAmount);

  const proofs = [
    {
      id: "state-anchor-fresh",
      label: "State anchor freshness",
      result: memoryAvailable ? "satisfied" : "unverifiable",
      observed: "latest block / fixture anchor",
      threshold: "within 60 seconds",
      explanation: memoryAvailable
        ? "The proposal is anchored to a recent state snapshot."
        : "The remembered policy is unavailable, so the anchor obligation cannot be trusted.",
    },
    {
      id: "oracle-freshness",
      label: "Oracle freshness",
      result: memoryAvailable ? (oracleFresh ? "satisfied" : "unsatisfied") : "unverifiable",
      observed: oracleFresh ? "5 seconds old" : "120 seconds old",
      threshold: "no older than 60 seconds",
      explanation: oracleFresh
        ? "The fixture observation is inside the remembered freshness window."
        : "The incident memory says this action must stop when the oracle is stale.",
    },
    {
      id: "simulation-match",
      label: "Exact simulation match",
      result: memoryAvailable && simulationSatisfied ? "satisfied" : "unverifiable",
      observed: `${safeAmount.toLocaleString("en-US")} MOCK outflow`,
      threshold: "same calldata and action digest",
      explanation: simulationSatisfied
        ? "The simulator evaluated the exact rebalance calldata proposed for execution."
        : "The requested amount exceeds the fixture reserve.",
    },
    {
      id: "post-state-invariant",
      label: "Post-state invariant",
      result: memoryAvailable && invariantSatisfied ? "satisfied" : "unsatisfied",
      observed: `${postReserve.toLocaleString("en-US")} MOCK remaining`,
      threshold: `at least ${MINIMUM_RESERVE.toLocaleString("en-US")} MOCK`,
      explanation: invariantSatisfied
        ? "The simulated treasury remains above its remembered minimum reserve."
        : "The proposed rebalance would cross the remembered minimum reserve.",
    },
    {
      id: "actor-standing",
      label: "Executor standing on ACP",
      // Fixture: tidak ada memori ACP di browser, jadi executor fixture dianggap tanpa riwayat.
      result: memoryAvailable ? "satisfied" : "unverifiable",
      observed: memoryAvailable ? "acp history: none" : "acp memory not read",
      threshold: "risk level at most 0, no confirmed patterns",
      explanation: memoryAvailable
        ? "The executor has no disqualifying verdict history on the ACP gate."
        : "The provider profile could not be read, so standing cannot be verified.",
    },
  ];

  let decision = "passport-issued";
  let reason = "Every blocking obligation is satisfied for this exact action.";
  if (!memoryAvailable) {
    decision = "human-review-required";
    reason = "The incident-conditioned policy is missing; the agent will not reconstruct it from code.";
  } else if (proofs.some((proof) => proof.result !== "satisfied")) {
    decision = "block";
    const failed = proofs.find((proof) => proof.result !== "satisfied");
    reason = failed?.id === "oracle-freshness"
      ? "Known failure mechanism recalled: oracle freshness is not proven."
      : "A blocking proof obligation is not satisfied for this proposal.";
  }

  const passport = decision === "passport-issued"
    ? {
        passportVersion: 1,
        actionClass: ACTION_CLASS,
        chainId: CHAIN_ID,
        target: "MockTreasury",
        selector: REBALANCE_SELECTOR,
        calldataHash: "keccak256(exact rebalance calldata)",
        memoryRoot: "Sibyl root loaded at issuance",
        expiresIn: "60 seconds",
        nonce: 42,
      }
    : null;

  return {
    action: {
      amount: safeAmount,
      asset: "MOCK",
      target: "MockTreasury",
      calldata,
      chain: CHAIN_LABEL,
    },
    incident: {
      type: INCIDENT_TYPE,
      oracleAge: oracleFresh ? 5 : 120,
      rememberedWindow: FRESHNESS_WINDOW,
    },
    hypothesis: memoryAvailable
      ? {
          id: HYPOTHESIS_ID,
          status: "active",
          enforcement: "block without a valid passport",
          counterfactual: "simulation alone did not establish oracle freshness and reserve safety",
        }
      : null,
    proofs,
    decision,
    reason,
    passport,
    memoryAvailable,
    oracleFresh,
    postReserve,
  };
}

export const DEMO_DEFAULTS = Object.freeze({
  amount: 100_000,
  memoryAvailable: true,
  oracleFresh: false,
});
