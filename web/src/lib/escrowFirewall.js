// Fixture UI untuk demo juri. Ini BUKAN state live dan tidak mengaku berasal dari chain;
// hash sesungguhnya dibentuk oleh agent/agent/escrow_firewall.py sebelum createJob.
//
// Nilai di bawah adalah TEKS TAMPILAN, bukan byte yang di-hash, berbeda dari string
// bundel di /verdict/[jobId] yang wajib tetap Indonesia karena ia yang masuk
// `reasonHash`. Karena tidak terikat apa pun, teks ini ditulis dalam bahasa halaman.

export const firewallDemo = Object.freeze({
  taskCategory: "smart-contract audit",
  generic: Object.freeze({
    acceptance: ["Deliverable meets the brief the client approved."],
    evidence: ["Deliverable artifact"],
    milestone: "Not required",
    review: "Client review",
  }),
  recalled: Object.freeze({
    pattern: "missing-reproducible-evidence",
    confidence: "80% (demo fixture)",
    acceptance: [
      "Deliverable meets the brief the client approved.",
      "Reproducible evidence is required before the milestone.",
    ],
    evidence: ["Commit hash", "Test command", "Test output", "Environment version"],
    milestone: "Required before release",
    review: "Client approval required",
    commitment: "0x7d3f…e91a (illustrative)",
  }),
});
