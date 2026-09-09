import test from "node:test";
import assert from "node:assert/strict";

import { firewallDemo } from "../src/lib/escrowFirewall.js";

test("fixture makes the pre-funding safeguard explicit", () => {
  assert.equal(firewallDemo.generic.evidence.includes("Commit hash"), false);
  assert.equal(firewallDemo.recalled.evidence.includes("Commit hash"), true);
  assert.match(firewallDemo.recalled.pattern, /^[a-z-]+$/);
});

test("fixture labels illustrative values instead of representing a live commitment", () => {
  assert.match(firewallDemo.recalled.commitment, /illustrative/);
  assert.match(firewallDemo.recalled.confidence, /demo fixture/);
});
