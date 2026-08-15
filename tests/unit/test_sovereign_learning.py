from __future__ import annotations

import pytest

from market_intelligence.intelligence.radar.sovereign_learning import (
    FeedbackTarget,
    LearningState,
    SovereignLearningEngine,
)


def confirmed_investigation(**overrides):
    payload = {
        "finding_hash": "a" * 64,
        "status_after": "confirmed",
        "confidence_after": 0.91,
        "observation_count": 3,
        "causal_claim": False,
        "evidence_summary": {"counts_by_evidence_level": {"fato": 1}},
        "hypotheses": [{"key": "h1", "status": "supported"}],
    }
    payload.update(overrides)
    return payload


def evaluate(engine: SovereignLearningEngine, **overrides):
    kwargs = {
        "marketplace": "mercadolivre",
        "entity_type": "listing",
        "entity_id": "MLB1",
        "finding": {"score": 0.91, "anomalous": True},
        "investigation": confirmed_investigation(),
        "official_resource_fetched": True,
        "marketplace_read_only": True,
        "marketplace_writes": 0,
    }
    kwargs.update(overrides)
    return engine.evaluate(**kwargs)


def test_validated_fact_creates_guarded_feedback_candidates():
    decision = evaluate(SovereignLearningEngine())
    assert decision.state is LearningState.VALIDATED_FACT
    assert decision.feedback_targets == (
        FeedbackTarget.KNOWLEDGE_MEMORY,
        FeedbackTarget.RADAR_RULE_CANDIDATE,
        FeedbackTarget.SKILL_UPDATE_CANDIDATE,
    )
    assert all(decision.watchdogs.values())


def test_no_official_read_stays_under_investigation():
    decision = evaluate(SovereignLearningEngine(), official_resource_fetched=False)
    assert decision.state is LearningState.UNDER_INVESTIGATION
    assert decision.feedback_targets == (FeedbackTarget.KNOWLEDGE_MEMORY,)


def test_single_observation_cannot_be_promoted():
    decision = evaluate(
        SovereignLearningEngine(),
        investigation=confirmed_investigation(observation_count=1),
    )
    assert decision.state is LearningState.UNDER_INVESTIGATION


def test_low_confidence_cannot_be_promoted():
    decision = evaluate(
        SovereignLearningEngine(),
        investigation=confirmed_investigation(confidence_after=0.79),
    )
    assert decision.state is LearningState.UNDER_INVESTIGATION


def test_rejected_investigation_is_preserved_but_not_promoted():
    decision = evaluate(
        SovereignLearningEngine(),
        investigation=confirmed_investigation(status_after="rejected"),
    )
    assert decision.state is LearningState.REJECTED
    assert decision.feedback_targets == (FeedbackTarget.KNOWLEDGE_MEMORY,)


def test_causal_claim_is_quarantined():
    decision = evaluate(
        SovereignLearningEngine(),
        investigation=confirmed_investigation(causal_claim=True),
    )
    assert decision.state is LearningState.QUARANTINED
    assert decision.feedback_targets == (FeedbackTarget.KNOWLEDGE_MEMORY,)


def test_marketplace_write_fails_closed():
    with pytest.raises(RuntimeError, match="read_only_violation"):
        evaluate(SovereignLearningEngine(), marketplace_writes=1)


def test_non_read_only_policy_fails_closed():
    with pytest.raises(RuntimeError, match="read_only_violation"):
        evaluate(SovereignLearningEngine(), marketplace_read_only=False)


def test_secret_contamination_fails_closed():
    with pytest.raises(RuntimeError, match="secret_contamination"):
        evaluate(
            SovereignLearningEngine(),
            finding={"score": 0.9, "access_token": "secret"},
        )


def test_promotion_requires_all_three_gates():
    engine = SovereignLearningEngine()
    for regression, verifier, watchdog, expected in [
        (True, True, True, True),
        (False, True, True, False),
        (True, False, True, False),
        (True, True, False, False),
    ]:
        decision = engine.decide_promotion(
            target=FeedbackTarget.RADAR_RULE_CANDIDATE,
            regression_passed=regression,
            independent_verifier_passed=verifier,
            watchdog_passed=watchdog,
        )
        assert decision.approved is expected


def test_dedupe_key_is_deterministic():
    engine = SovereignLearningEngine()
    assert evaluate(engine).dedupe_key == evaluate(engine).dedupe_key
