"""Unit tests for the Passport memory/control-plane foundation."""

from __future__ import annotations

import pytest
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from sibyl_memory_client import MemoryClient
from web3 import Web3

from agent import execution_passport as ep
from agent import memory_policy as mp

TARGET = "0x00000000000000000000000000000000000000aa"
STATE_HASH = "0x" + "11" * 32
EXECUTOR = "0xc3c6bf20dde1a547a35f6479d54b08e1548daeff"
CLEAN = mp.ProviderProfile(address=EXECUTOR)


def action(*, amount: int = 100_000, block: int = 10) -> ep.ActionProposal:
    calldata = "0x" + (ep.REBALANCE_SELECTOR + abi_encode(["uint256"], [amount])).hex()
    return ep.ActionProposal(
        chain_id=84532,
        target=TARGET,
        selector="0x" + ep.REBALANCE_SELECTOR.hex(),
        calldata=calldata,
        value=0,
        state_block_number=block,
        state_block_hash=STATE_HASH,
    )


@pytest.fixture
def client(tmp_path):
    return MemoryClient.local(str(tmp_path / "memory.db"))


def test_action_digest_is_stable_and_calldata_bound():
    first = action()
    second = action()
    changed = action(amount=100_001)

    assert first.calldata_hash == second.calldata_hash
    assert first.action_digest == second.action_digest
    assert first.calldata_hash != changed.calldata_hash
    assert first.action_digest != changed.action_digest


def test_action_rejects_selector_or_calldata_mismatch():
    with pytest.raises(ep.PassportValidationError, match="selector"):
        ep.ActionProposal(
            chain_id=84532,
            target=TARGET,
            selector="0x00000000",
            calldata=action().calldata,
            value=0,
            state_block_number=10,
            state_block_hash=STATE_HASH,
        )


def test_fresh_process_recalls_control_hypothesis(client, tmp_path):
    incident = ep.IncidentEvidence(
        incident_id="incident-001",
        incident_type=ep.INCIDENT_TYPE,
        action=action(),
        oracle_timestamp=100,
        observed_at=200,
        evidence_digest="0x" + "22" * 32,
    )
    stored = ep.record_incident(client, incident)

    fresh = MemoryClient.local(str(tmp_path / "memory.db"))
    loaded = ep.load_control_hypotheses(fresh)

    assert stored.hypothesis_id == ep.HYPOTHESIS_ID
    assert stored.created_at == 200
    assert stored.updated_at == 200
    assert stored.observed_actions == (incident.action.action_digest,)
    assert len(loaded) == 1
    assert loaded[0].required_obligations == stored.required_obligations
    assert loaded[0].required_obligations[1].max_age_seconds == 60
    assert ep.select_hypothesis(loaded, action()).hypothesis_id == ep.HYPOTHESIS_ID


def test_fresh_evidence_cannot_create_hypothesis(client):
    fresh = ep.IncidentEvidence(
        incident_id="incident-fresh",
        incident_type=ep.INCIDENT_TYPE,
        action=action(),
        oracle_timestamp=150,
        observed_at=200,
        evidence_digest="0x" + "33" * 32,
    )
    with pytest.raises(ep.PassportValidationError, match="fresh-oracle"):
        ep.record_incident(client, fresh)

    assert ep.load_control_hypotheses(client) == ()


def test_wrong_action_scope_does_not_match(client):
    hypothesis = ep.initial_control_hypothesis(action())
    ep.save_control_hypothesis(client, hypothesis)

    assert ep.select_hypothesis(ep.load_control_hypotheses(client), action(amount=999)) is not None
    assert ep.select_hypothesis(ep.load_control_hypotheses(client), action(block=11)) is not None

    different_target = ep.ActionProposal(
        chain_id=84532,
        target="0x00000000000000000000000000000000000000bb",
        selector="0x" + ep.REBALANCE_SELECTOR.hex(),
        calldata=action().calldata,
        value=0,
        state_block_number=10,
        state_block_hash=STATE_HASH,
    )
    assert ep.select_hypothesis(ep.load_control_hypotheses(client), different_target) is None


def test_duplicate_incident_is_idempotent(client):
    incident = ep.IncidentEvidence(
        incident_id="incident-same",
        incident_type=ep.INCIDENT_TYPE,
        action=action(),
        oracle_timestamp=100,
        observed_at=200,
        evidence_digest="0x" + "44" * 32,
    )
    first = ep.record_incident(client, incident)
    second = ep.record_incident(client, incident)
    assert first == second
    assert len(ep.load_control_hypotheses(client)[0].incident_ids) == 1
    assert len(ep.load_control_hypotheses(client)[0].observed_actions) == 1


def test_malformed_memory_requires_human_review(client):
    client.set_reference(ep.HYPOTHESIS_KEY, {"schema": "not-a-passport"})

    decision = ep.evaluate_rebalance_for_passport(
        client,
        action(),
        environment(action()),
        executor=EXECUTOR,
        verifier_address="0x00000000000000000000000000000000000000cc",
        issued_at=1_000,
        nonce=31,
    )

    assert decision.decision == "human-review-required"
    assert "memory-unavailable" in decision.reason
    assert decision.passport is None


def test_conflicting_memory_requires_human_review(client):
    hypothesis = ep.initial_control_hypothesis(action())
    ep.save_control_hypothesis(client, hypothesis)
    client.set_reference(ep.HYPOTHESIS_KEY + ".conflict", hypothesis.to_body())

    decision = ep.evaluate_rebalance_for_passport(
        client,
        action(),
        environment(action()),
        executor=EXECUTOR,
        verifier_address="0x00000000000000000000000000000000000000cc",
        issued_at=1_000,
        nonce=32,
    )

    assert decision.decision == "human-review-required"
    assert "multiple equally applicable" in decision.reason
    assert decision.passport is None


def test_outcome_updates_are_bounded_and_persisted(client):
    hypothesis = ep.initial_control_hypothesis(action())
    ep.save_control_hypothesis(client, hypothesis)

    worked = ep.record_outcome(client, ep.HYPOTHESIS_ID, outcome="worked", action_id="tx-1")
    failed = ep.record_outcome(client, ep.HYPOTHESIS_ID, outcome="failed", action_id="tx-2")

    assert worked.worked_count == 1
    assert failed.failed_count == 1
    assert 0 <= failed.confidence_bps <= 10_000
    assert ep.load_control_hypotheses(client)[0].outcome_counts == {
        "worked": 1,
        "failed": 1,
        "inconclusive": 0,
    }

    duplicate = ep.record_outcome(client, ep.HYPOTHESIS_ID, outcome="failed", action_id="tx-2")
    assert duplicate.failed_count == 1


def test_outcome_observation_advances_updated_timestamp(client):
    hypothesis = ep.initial_control_hypothesis(action(), observed_at=100)
    ep.save_control_hypothesis(client, hypothesis)

    updated = ep.record_outcome(
        client,
        ep.HYPOTHESIS_ID,
        outcome="worked",
        action_id="tx-timestamped",
        observed_at=125,
    )

    assert updated.created_at == 100
    assert updated.updated_at == 125


def test_simulation_fixture_binds_exact_action_and_reserve_invariant():
    proposal = action(amount=100_000)
    result = ep.simulate_rebalance(
        proposal, current_reserve=1_000_000, minimum_reserve=250_000
    )
    unsafe = ep.simulate_rebalance(
        action(amount=800_000), current_reserve=1_000_000, minimum_reserve=250_000
    )

    assert result.success is True
    assert result.simulated_post_reserve == 900_000
    assert unsafe.success is False
    assert unsafe.simulated_post_reserve == 200_000
    assert result.action_digest != unsafe.action_digest
    assert result.evidence_digest != unsafe.evidence_digest


def test_delete_control_hypothesis_preserves_other_references(client):
    client.set_reference("pattern:firewall-survivor", {"kind": "unrelated"})
    ep.save_control_hypothesis(client, ep.initial_control_hypothesis(action()))

    assert ep.delete_control_hypothesis(client) is True
    assert ep.load_control_hypotheses(client) == ()
    assert client.get_reference("pattern:firewall-survivor") is not None
    assert ep.delete_control_hypothesis(client) is False


def test_passport_reference_changes_existing_memory_root(client):
    before = mp.memory_root_hex(client)
    ep.save_control_hypothesis(client, ep.initial_control_hypothesis(action()))
    after = mp.memory_root_hex(client)
    assert before != after


def environment(action_value: ep.ActionProposal, *, now: int = 1_000, **overrides):
    values = {
        "now": now,
        "current_block_number": action_value.state_block_number,
        "current_block_hash": action_value.state_block_hash,
        "state_block_timestamp": now - 5,
        "oracle_timestamp": now - 5,
        "simulation_action_digest": action_value.action_digest,
        "simulation_succeeded": True,
        "simulated_post_reserve": 900_000,
    }
    values.update(overrides)
    return ep.DeterministicEnvironment(**values)


def test_all_mvp_obligations_satisfy_only_with_matching_fresh_evidence():
    proposal = action()
    hypothesis = ep.initial_control_hypothesis(proposal)
    results = ep.evaluate_obligations(proposal, hypothesis, environment(proposal), executor_profile=CLEAN)

    assert [result.obligation_id for result in results] == list(ep.MVP_PROOF_IDS)
    assert [result.result for result in results] == ["satisfied"] * 5
    assert ep.obligations_allow_execution(hypothesis, results) is True


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("oracle_timestamp", 900, "unsatisfied"),
        ("state_block_timestamp", 900, "unsatisfied"),
        ("simulation_action_digest", "0x" + "55" * 32, "unsatisfied"),
        ("simulated_post_reserve", 249_999, "unsatisfied"),
    ],
)
def test_failed_obligation_blocks_passport(field, value, expected):
    proposal = action()
    hypothesis = ep.initial_control_hypothesis(proposal)
    results = ep.evaluate_obligations(
        proposal, hypothesis, environment(proposal, **{field: value}), executor_profile=CLEAN
    )

    assert expected in [result.result for result in results]
    assert ep.obligations_allow_execution(hypothesis, results) is False


def test_missing_observation_is_unverifiable_and_never_a_pass():
    proposal = action()
    hypothesis = ep.initial_control_hypothesis(proposal)
    results = ep.evaluate_obligations(
        proposal,
        hypothesis,
        environment(proposal, oracle_timestamp=None, simulation_succeeded=None),
        executor_profile=CLEAN,
    )

    by_id = {result.obligation_id: result.result for result in results}
    assert by_id[ep.PROOF_ORACLE] == "unverifiable"
    assert by_id[ep.PROOF_SIMULATION] == "unverifiable"
    assert ep.obligations_allow_execution(hypothesis, results) is False


def test_obligation_hash_is_order_and_content_sensitive():
    proposal = action()
    hypothesis = ep.initial_control_hypothesis(proposal)
    results = ep.evaluate_obligations(proposal, hypothesis, environment(proposal), executor_profile=CLEAN)

    digest = ep.obligation_results_hash(result.to_body() for result in results)
    changed = ep.obligation_results_hash(
        [
            results[0].to_body(),
            {**results[1].to_body(), "result": "unsatisfied"},
            *(result.to_body() for result in results[2:]),
        ]
    )
    assert digest.startswith("0x") and len(digest) == 66
    assert digest != changed


def test_execution_passport_is_typed_and_recoverable(client):
    proposal = action()
    hypothesis = ep.initial_control_hypothesis(proposal)
    ep.save_control_hypothesis(client, hypothesis)
    results = ep.evaluate_obligations(proposal, hypothesis, environment(proposal), executor_profile=CLEAN)
    passport = ep.build_execution_passport(
        proposal,
        hypothesis,
        results,
        executor=EXECUTOR,
        memory_root_value=mp.memory_root_hex(client),
        issued_at=1_000,
        expires_at=1_030,
        nonce=1,
    )
    private_key = "0x" + "12" * 32
    signer = Account.from_key(private_key).address
    verifier = "0x00000000000000000000000000000000000000cc"
    signature = passport.sign(verifier, private_key)
    recovered = Account.recover_message(
        encode_typed_data(full_message=passport.typed_data(verifier)), signature=signature
    )

    assert recovered == signer
    assert passport.to_message()["selector"] == "0x" + ep.REBALANCE_SELECTOR.hex()
    assert len(signature) == 132


def test_passport_cannot_be_built_from_failed_obligation(client):
    proposal = action()
    hypothesis = ep.initial_control_hypothesis(proposal)
    ep.save_control_hypothesis(client, hypothesis)
    results = ep.evaluate_obligations(
        proposal, hypothesis, environment(proposal, oracle_timestamp=900), executor_profile=CLEAN
    )

    with pytest.raises(ep.PassportValidationError, match="blocking obligation"):
        ep.build_execution_passport(
            proposal,
            hypothesis,
            results,
            executor=EXECUTOR,
            memory_root_value=mp.memory_root_hex(client),
            issued_at=1_000,
            expires_at=1_030,
            nonce=2,
        )


def test_fixed_cross_language_vector():
    proposal = action()
    hypothesis = ep.initial_control_hypothesis(proposal)
    results = ep.evaluate_obligations(proposal, hypothesis, environment(proposal), executor_profile=CLEAN)
    passport = ep.build_execution_passport(
        proposal,
        hypothesis,
        results,
        executor=EXECUTOR,
        memory_root_value="0x" + "44" * 32,
        issued_at=1_000,
        expires_at=1_030,
        nonce=1,
    )
    typed = encode_typed_data(
        full_message=passport.typed_data("0x00000000000000000000000000000000000000cc")
    )

    assert proposal.calldata_hash == "0xe88f9b14f8921d7450af76f0d8ab7aa348bde46316d628ab6f91e9dac0c582a3"
    assert proposal.action_digest == "0xa5f373496d1d79b025a7d8154046861cbc61ed45a24cf8533ee974d95d5bc830"
    assert passport.hypothesis_ids_hash == (
        "0xb1e9546ad67d2b7e25027c4ed279adafc69e9ec84dd1ef94ea3da9dca60d6ecd"
    )
    assert passport.obligation_results_hash == (
        "0x49a8d4f0ccf032c5649f4a25b0d3a35162c11b54bb6cd35a80ca711852f6140a"
    )
    assert Web3.to_hex(Account.sign_message(typed, "0x" + "12" * 32).message_hash) == (
        "0x1f5ece583170ab17407e77846f1f5c4dab174153a93cebe81787221001b97b0b"
    )


def test_nonce_generator_returns_distinct_uint256_candidates():
    first = ep.generate_nonce()
    second = ep.generate_nonce()
    assert 0 <= first < 2**256
    assert 0 <= second < 2**256
    assert first != second


def test_decision_entry_point_requires_memory(client):
    decision = ep.evaluate_rebalance_for_passport(
        client,
        action(),
        environment(action()),
        executor=EXECUTOR,
        verifier_address="0x00000000000000000000000000000000000000cc",
        issued_at=1_000,
        nonce=3,
    )

    assert decision.decision == "human-review-required"
    assert decision.passport is None
    assert "no-matching-hypothesis" in decision.reason


def test_decision_entry_point_blocks_stale_observation(client):
    proposal = action()
    ep.save_control_hypothesis(client, ep.initial_control_hypothesis(proposal))
    decision = ep.evaluate_rebalance_for_passport(
        client,
        proposal,
        environment(proposal, oracle_timestamp=900),
        executor=EXECUTOR,
        verifier_address="0x00000000000000000000000000000000000000cc",
        issued_at=1_000,
        nonce=4,
    )

    assert decision.decision == "block"
    assert decision.passport is None
    assert ep.PROOF_ORACLE in decision.reason


def test_decision_entry_point_issues_passport_from_recalled_memory(client):
    proposal = action()
    ep.save_control_hypothesis(client, ep.initial_control_hypothesis(proposal))
    decision = ep.evaluate_rebalance_for_passport(
        client,
        proposal,
        environment(proposal),
        executor=EXECUTOR,
        verifier_address="0x00000000000000000000000000000000000000cc",
        issued_at=1_000,
        nonce=5,
    )

    assert decision.issued is True
    assert decision.passport is not None
    assert decision.evidence is not None
    assert decision.passport.memory_root == mp.memory_root_hex(client)
    assert [result.obligation_id for result in decision.results] == list(ep.MVP_PROOF_IDS)


def _decide(client, proposal, *, executor=EXECUTOR, **env_overrides):
    return ep.evaluate_rebalance_for_passport(
        client,
        proposal,
        environment(proposal, **env_overrides),
        executor=executor,
        verifier_address="0x00000000000000000000000000000000000000cc",
        issued_at=1_000,
        nonce=7,
    )


def _incident(proposal: ep.ActionProposal) -> ep.IncidentEvidence:
    return ep.IncidentEvidence(
        incident_id="incident-actor",
        incident_type=ep.INCIDENT_TYPE,
        action=proposal,
        oracle_timestamp=100,
        observed_at=200,
        evidence_digest="0x" + "22" * 32,
    )


def test_hypothesis_selects_five_obligations_with_actor_standing_last():
    hypothesis = ep.initial_control_hypothesis(action())
    ids = [o.obligation_id for o in hypothesis.required_obligations]
    assert ids == list(ep.MVP_PROOF_IDS)
    assert ids[-1] == ep.PROOF_ACTOR
    assert hypothesis.required_obligations[-1].max_risk_level == 0


def test_legacy_four_obligation_body_still_loads():
    # Store yang ditulis sebelum actor-standing ada harus tetap terbaca: memori lama bukan
    # memori rusak, ia hanya belum memilih obligasi kelima.
    body = ep.initial_control_hypothesis(action()).to_body()
    body["required_obligations"] = body["required_obligations"][:4]
    loaded = ep.ControlHypothesis.from_body(body)
    assert [o.obligation_id for o in loaded.required_obligations] == list(ep.LEGACY_PROOF_IDS)


def test_max_risk_level_is_rejected_on_other_obligations():
    with pytest.raises(ep.PassportValidationError):
        ep.ObligationDefinition(ep.PROOF_ORACLE, max_age_seconds=60, max_risk_level=0)


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (None, "unverifiable"),
        (CLEAN, "satisfied"),
        (mp.ProviderProfile(address=EXECUTOR, risk_level=1, incident_jobs=(418,)), "unsatisfied"),
        (mp.ProviderProfile(address=EXECUTOR, confirmed_patterns=("format.bad",)), "unsatisfied"),
    ],
)
def test_actor_standing_table(profile, expected):
    proposal = action()
    hypothesis = ep.initial_control_hypothesis(proposal)
    results = ep.evaluate_obligations(
        proposal, hypothesis, environment(proposal), executor_profile=profile
    )
    by_id = {r.obligation_id: r for r in results}
    assert by_id[ep.PROOF_ACTOR].result == expected
    if expected == "unsatisfied":
        explanation = by_id[ep.PROOF_ACTOR].explanation
        assert "418" in explanation or "format.bad" in explanation


def test_unknown_executor_is_satisfied_and_says_so(client):
    proposal = action()
    ep.record_incident(client, _incident(proposal))
    decision = _decide(client, proposal)
    assert decision.decision == "passport-issued"
    actor = next(r for r in decision.results if r.obligation_id == ep.PROOF_ACTOR)
    assert actor.observed["acp_history"] == "none"
    assert decision.passport.executor == EXECUTOR


def test_risky_acp_provider_is_blocked_at_the_base_gate(client):
    proposal = action()
    ep.record_incident(client, _incident(proposal))
    # Riwayat dibangun lewat jalur ACP yang asli: karantina dua job berbeda, lalu promosi.
    mp.record_suspicion(client, EXECUTOR, "format.bad", mp.Evidence(job_id=418, check_id="format"))
    mp.record_suspicion(client, EXECUTOR, "format.bad", mp.Evidence(job_id=419, check_id="format"))
    assert mp.promote_suspicions(client, EXECUTOR) == ["format.bad"]

    decision = _decide(client, proposal)
    assert decision.decision == "block"
    assert decision.passport is None
    assert "actor-standing" in decision.reason
    assert "418" in decision.reason and "419" in decision.reason


def test_passport_executor_is_part_of_the_signed_message(client):
    proposal = action()
    ep.record_incident(client, _incident(proposal))
    a = _decide(client, proposal).passport
    b = _decide(client, proposal, executor="0x20212e4d95a75e6716575ed26e884cdeff66b321").passport
    verifier = "0x00000000000000000000000000000000000000cc"
    assert a.to_message()["executor"] == EXECUTOR
    assert a.sign(verifier, "0x" + "12" * 32) != b.sign(verifier, "0x" + "12" * 32)
