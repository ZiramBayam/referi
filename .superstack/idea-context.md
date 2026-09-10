---
project: The Evaluator
phase: idea
landscape:
  direct_competitors:
    - name: ERC-8004 Reputation and Validation Registries
      url: https://eips.ethereum.org/EIPS/eip-8004
      status: active standard
      strength: portable public agent feedback and validation
      weakness: intentionally leaves scoring and context-specific policy to downstream systems
    - name: OpenRank
      url: https://docs.openrank.com/
      status: live
      strength: verifiable contextual reputation graph computation
      weakness: ranks entities but does not automatically convert incidents into escrow controls
  substitutes:
    - name: Kleros Escrow
      approach: crowdsourced human arbitration after a dispute
      why_users_stay: subjective judgment, appeals, and established dispute workflow
    - name: Ethereum Attestation Service
      approach: generic on-chain and off-chain attestations
      why_users_stay: neutral primitive with broad ecosystem composability
    - name: Marketplace ratings and manual allowlists
      approach: centralized reputation and moderation
      why_users_stay: familiar UX, low cost, and strong platform distribution
  dead_projects:
    - name: Bitrated-style designated-arbitrator marketplaces
      why_failed: escrow plus generic reputation lacked durable distribution and a sufficiently sharp recurring workflow
  crowdedness: crowded
  moat_type: data advantages plus distribution/ecosystem integrations
  differentiation: remember semantic failure patterns and convert them into preventive, task-specific acceptance controls before escrow funding
research_artifact: docs/research/2026-09-09-memory-differentiation-landscape.html
---

The current product uses Sibyl on the decision path, but much of the provider profile can be reconstructed from ACP events plus local artifacts. The next concept should make private or semantic off-chain evidence—not public outcome counters—the irreducible memory.
