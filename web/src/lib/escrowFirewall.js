// Fixture UI untuk demo juri. Ini BUKAN state live dan tidak mengaku berasal dari chain;
// hash sesungguhnya dibentuk oleh agent/agent/escrow_firewall.py sebelum createJob.

export const firewallDemo = Object.freeze({
  taskCategory: "smart-contract audit",
  generic: Object.freeze({
    acceptance: ["Deliverable memenuhi brief yang disetujui client."],
    evidence: ["Deliverable artifact"],
    milestone: "Tidak diwajibkan",
    review: "Client review",
  }),
  recalled: Object.freeze({
    pattern: "missing-reproducible-evidence",
    confidence: "80% (demo fixture)",
    acceptance: [
      "Deliverable memenuhi brief yang disetujui client.",
      "Bukti reproducible wajib sebelum milestone.",
    ],
    evidence: ["Commit hash", "Test command", "Test output", "Environment version"],
    milestone: "Wajib sebelum release",
    review: "Client approval required",
    commitment: "0x7d3f…e91a (illustrative)",
  }),
});
