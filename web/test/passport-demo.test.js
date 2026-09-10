import test from "node:test";
import assert from "node:assert/strict";

import {
  evaluateDemoAction,
  MINIMUM_RESERVE,
} from "../src/lib/passportDemo.js";

test("stale oracle is blocked by recalled memory", () => {
  const result = evaluateDemoAction({ amount: 100_000, memoryAvailable: true, oracleFresh: false });

  assert.equal(result.decision, "block");
  assert.equal(result.passport, null);
  assert.equal(result.proofs.find((proof) => proof.id === "oracle-freshness")?.result, "unsatisfied");
});

test("fresh oracle and safe reserve issue a passport", () => {
  const result = evaluateDemoAction({ amount: 100_000, memoryAvailable: true, oracleFresh: true });

  assert.equal(result.decision, "passport-issued");
  assert.equal(result.passport?.actionClass, "treasury-rebalance");
  assert.equal(result.postReserve, 900_000);
  assert.ok(result.proofs.every((proof) => proof.result === "satisfied"));
});

test("minimum reserve violation blocks even with fresh oracle", () => {
  const result = evaluateDemoAction({ amount: 1_000_000 - MINIMUM_RESERVE + 1, memoryAvailable: true, oracleFresh: true });

  assert.equal(result.decision, "block");
  assert.equal(result.passport, null);
  assert.equal(result.proofs.find((proof) => proof.id === "post-state-invariant")?.result, "unsatisfied");
});

test("missing memory requires human review instead of reconstructing policy", () => {
  const result = evaluateDemoAction({ amount: 100_000, memoryAvailable: false, oracleFresh: true });

  assert.equal(result.decision, "human-review-required");
  assert.equal(result.hypothesis, null);
  assert.equal(result.passport, null);
  assert.ok(result.proofs.some((proof) => proof.result === "unverifiable"));
});
