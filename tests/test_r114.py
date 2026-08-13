from datetime import UTC, datetime

from market_intelligence.intelligence.radar.counterfactual import OperationalCounterfactualDetector
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation


HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


def _candidates(currents=(100, 101, 99), *, include_contaminated=False):
    candidates = [
        {
            "entity_id": f"C{index}",
            "metrics": {"visits": current},
            "history": {"visits": HISTORY},
        }
        for index, current in enumerate(currents, start=1)
    ]
    if include_contaminated:
        candidates.append(
            {
                "entity_id": "BAD",
                "metrics": {"visits": 300},
                "history": {"visits": HISTORY},
                "attributes": {"contaminated": True},
            }
        )
    return candidates


def _observation(current=75, *, controls=None):
    return RadarObservation(
        entity_id="TARGET",
        observed_at=datetime.now(UTC),
        metrics={"visits": current},
        history={"visits": HISTORY},
        context={"control_candidates": controls or _candidates()},
    )


def test_counterfactual_estimate_is_independent_from_current_target_fit():
    detector = OperationalCounterfactualDetector()
    first = detector.estimate(_observation(75), "visits")
    second = detector.estimate(_observation(60), "visits")
    assert first is not None and second is not None
    assert first.expected == second.expected
    assert first.control_median_signal == second.control_median_signal
    assert first.selection["selection_uses_current_values"] is False
    assert first.as_dict()["estimator_uses_current_target_to_fit"] is False


def test_counterfactual_detector_is_inference_without_causal_claim():
    result = OperationalCounterfactualDetector().evaluate(_observation(75))
    assert result is not None
    assert result.level.value == "inference"
    assert result.score >= 0.60
    assert result.attributes["counterfactual_kind"] == "operational_not_causal"
    assert result.attributes["causal_claim"] is False
    assert result.attributes["fit_uses_current_target"] is False
    analysis = result.attributes["counterfactual_analysis"]
    assert analysis["counterfactual_expected"] == 100.0
    assert analysis["counterfactual_gap"] == -25.0


def test_counterfactual_rejects_inconsistent_current_control_group():
    controls = _candidates((80, 100, 120))
    assert OperationalCounterfactualDetector().evaluate(
        _observation(75, controls=controls)
    ) is None


def test_counterfactual_rejects_insufficient_control_group():
    controls = _candidates((100, 101))
    assert OperationalCounterfactualDetector().evaluate(
        _observation(75, controls=controls)
    ) is None


def test_counterfactual_excludes_declared_contaminated_candidate():
    estimate = OperationalCounterfactualDetector().estimate(
        _observation(75, controls=_candidates(include_contaminated=True)),
        "visits",
    )
    assert estimate is not None
    assert estimate.control_count == 3
    assert "BAD" not in estimate.control_entity_ids
    assert estimate.selection["excluded"]["declared_contaminated"] == 1


def test_counterfactual_does_not_flag_target_that_moves_with_controls():
    controls = _candidates((90, 91, 89))
    assert OperationalCounterfactualDetector().evaluate(
        _observation(90, controls=controls)
    ) is None


def test_default_radar_registers_operational_counterfactual():
    finding = build_default_radar().evaluate(_observation(75))
    result = next(
        item for item in finding.detector_results
        if item.detector == "operational_counterfactual_v1"
    )
    assert result.attributes["counterfactual_expected"] == 100.0
    assert result.attributes["causal_claim"] is False
