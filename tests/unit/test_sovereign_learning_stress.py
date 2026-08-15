from __future__ import annotations

from market_intelligence.intelligence.radar.sovereign_learning import (
    FeedbackTarget,
    LearningState,
    SovereignLearningEngine,
)


def test_sovereign_learning_11000_deterministic_scenarios() -> None:
    engine = SovereignLearningEngine()
    passed = 0
    for index in range(11000):
        kind = index % 11
        investigation = {
            "finding_hash": f"{index:064x}"[-64:],
            "status_after": "confirmed",
            "confidence_after": 0.91,
            "observation_count": 3,
            "causal_claim": False,
            "evidence_summary": {"index": index},
            "hypotheses": [{"key": f"h{index}", "status": "supported"}],
        }
        kwargs = {
            "marketplace": "mercadolivre",
            "entity_type": "listing",
            "entity_id": f"MLB{index}",
            "finding": {"score": 0.91, "anomalous": True, "index": index},
            "investigation": investigation,
            "official_resource_fetched": True,
            "marketplace_read_only": True,
            "marketplace_writes": 0,
        }

        if kind == 0:
            decision = engine.evaluate(**kwargs)
            assert decision.state is LearningState.VALIDATED_FACT
            assert FeedbackTarget.RADAR_RULE_CANDIDATE in decision.feedback_targets
        elif kind == 1:
            kwargs["official_resource_fetched"] = False
            assert engine.evaluate(**kwargs).state is LearningState.UNDER_INVESTIGATION
        elif kind == 2:
            investigation["observation_count"] = 1
            assert engine.evaluate(**kwargs).state is LearningState.UNDER_INVESTIGATION
        elif kind == 3:
            investigation["confidence_after"] = 0.79
            assert engine.evaluate(**kwargs).state is LearningState.UNDER_INVESTIGATION
        elif kind == 4:
            investigation["status_after"] = "rejected"
            assert engine.evaluate(**kwargs).state is LearningState.REJECTED
        elif kind == 5:
            investigation["causal_claim"] = True
            assert engine.evaluate(**kwargs).state is LearningState.QUARANTINED
        elif kind == 6:
            first = engine.evaluate(**kwargs)
            second = engine.evaluate(**kwargs)
            assert first.dedupe_key == second.dedupe_key
        elif kind == 7:
            result = engine.decide_promotion(
                target=FeedbackTarget.RADAR_RULE_CANDIDATE,
                regression_passed=True,
                independent_verifier_passed=True,
                watchdog_passed=True,
            )
            assert result.approved is True
        elif kind == 8:
            result = engine.decide_promotion(
                target=FeedbackTarget.SKILL_UPDATE_CANDIDATE,
                regression_passed=False,
                independent_verifier_passed=True,
                watchdog_passed=True,
            )
            assert result.approved is False
        elif kind == 9:
            kwargs["finding"] = {"score": 0.91, "authorization": "secret"}
            try:
                engine.evaluate(**kwargs)
            except RuntimeError as exc:
                assert "secret_contamination" in str(exc)
            else:
                raise AssertionError("secret contamination was not blocked")
        else:
            kwargs["marketplace_writes"] = 1
            try:
                engine.evaluate(**kwargs)
            except RuntimeError as exc:
                assert "read_only_violation" in str(exc)
            else:
                raise AssertionError("marketplace write was not blocked")
        passed += 1

    assert passed == 11000
