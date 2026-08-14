from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.iad import (
    DistributionAnomalyIndex,
    IADCalibrationProfile,
    IADCalibrator,
)
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation


HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


def _result(
    detector: str,
    score: float,
    *,
    metric: str | None = None,
    attributes: dict | None = None,
) -> DetectorResult:
    attrs = dict(attributes or {})
    if metric is not None:
        attrs["metric"] = metric
    return DetectorResult(
        detector=detector,
        score=score,
        level=EvidenceLevel.INFERENCE,
        summary=detector,
        attributes=attrs,
    )


def _approved_profile(**overrides):
    payload = {
        "version": "historical-fixture-v1",
        "source_type": "historical_validation",
        "weights": {
            "traffic_deviation": 0.5,
            "control_divergence": 0.5,
        },
        "threshold": 0.70,
        "min_components": 2,
        "production_approved": True,
        "sample_count": 20,
        "positive_count": 10,
        "negative_count": 10,
        "metrics": {"balanced_accuracy": 0.9},
    }
    payload.update(overrides)
    return payload


def _control_candidates():
    return [
        {
            "entity_id": f"C{index}",
            "metrics": {"visits": current},
            "history": {"visits": HISTORY},
        }
        for index, current in enumerate((100, 101, 99), start=1)
    ]


def _observation(*, calibration: dict | None = None) -> RadarObservation:
    context = {"control_candidates": _control_candidates()}
    if calibration is not None:
        context["iad_calibration"] = calibration
    return RadarObservation(
        entity_id="TARGET-R116",
        observed_at=datetime.now(UTC),
        metrics={"visits": 75},
        history={"visits": HISTORY},
        context=context,
    )


def test_iad_calibrator_learns_weights_and_threshold_deterministically() -> None:
    samples = [
        {"label": False, "components": {"traffic_deviation": 0.10, "control_divergence": 0.15, "unexplained_residual": 0.10}},
        {"label": False, "components": {"traffic_deviation": 0.20, "control_divergence": 0.10, "unexplained_residual": 0.15}},
        {"label": True, "components": {"traffic_deviation": 0.90, "control_divergence": 0.85, "unexplained_residual": 0.90}},
        {"label": True, "components": {"traffic_deviation": 0.80, "control_divergence": 0.90, "unexplained_residual": 0.80}},
    ]
    first = IADCalibrator().fit(samples, version="synthetic-calibration-v1", source_type="synthetic_test")
    second = IADCalibrator().fit(samples, version="synthetic-calibration-v1", source_type="synthetic_test")
    assert first == second
    assert first.production_approved is False
    assert first.source_type == "synthetic_test"
    assert first.min_components >= 2
    assert sum(first.weights.values()) == pytest.approx(1.0)
    assert 0.20 < first.threshold < 0.90
    assert first.metrics["balanced_accuracy"] == 1.0


def test_iad_calibrator_rejects_single_component_signal() -> None:
    samples = [
        {"label": False, "components": {"traffic_deviation": 0.1, "control_divergence": 0.5}},
        {"label": True, "components": {"traffic_deviation": 0.9, "control_divergence": 0.5}},
    ]
    with pytest.raises(ValueError, match="at least two"):
        IADCalibrator().fit(samples, version="invalid-v1")


def test_synthetic_iad_profile_can_never_be_production_approved() -> None:
    with pytest.raises(ValidationError):
        IADCalibrationProfile.model_validate(
            {
                "version": "synthetic-v1",
                "source_type": "synthetic_test",
                "weights": {"traffic_deviation": 0.5, "control_divergence": 0.5},
                "threshold": 0.6,
                "min_components": 2,
                "production_approved": True,
                "sample_count": 20,
                "positive_count": 10,
                "negative_count": 10,
            }
        )


def test_production_iad_profile_requires_recorded_both_classes() -> None:
    with pytest.raises(ValidationError):
        IADCalibrationProfile.model_validate(
            {
                "version": "historical-v1",
                "source_type": "historical_validation",
                "weights": {"traffic_deviation": 0.5, "control_divergence": 0.5},
                "threshold": 0.6,
                "min_components": 2,
                "production_approved": True,
            }
        )


def test_iad_extracts_sovereign_components_without_claiming_cause() -> None:
    results = [
        _result("robust_zscore", 0.80, metric="visits"),
        _result("temporal_pattern_v1", 0.75, metric="conversion"),
        _result("relational_control_v1", 0.78, metric="visits"),
        _result("regime_change_v1", 0.82, metric="visits"),
        _result(
            "factor_attribution_v1",
            0.55,
            metric="visits",
            attributes={"factor_attribution": {"explained_fraction": 0.25}},
        ),
        _result("unexplained_residual_v1", 0.88, metric="visits"),
        _result("channel_regime_correlation_v1", 0.84, metric="visits"),
    ]
    components, sources = DistributionAnomalyIndex().components(results)
    assert components["traffic_deviation"] == 0.82
    assert components["conversion_deviation"] == 0.75
    assert components["control_divergence"] == 0.78
    assert components["regime_change"] == 0.82
    assert components["observable_gap"] == 0.75
    assert components["unexplained_residual"] == 0.88
    assert components["channel_regime"] == 0.84
    assert "regime_change_v1" in sources["traffic_deviation"]


def test_unapproved_request_calibration_is_never_alert_eligible() -> None:
    observation = RadarObservation(
        entity_id="EXPERIMENTAL",
        observed_at=datetime.now(UTC),
        metrics={},
        context={
            "iad_calibration": {
                "version": "synthetic-v1",
                "source_type": "synthetic_test",
                "weights": {"traffic_deviation": 0.5, "control_divergence": 0.5},
                "threshold": 0.6,
                "min_components": 2,
                "production_approved": False,
                "sample_count": 4,
                "positive_count": 2,
                "negative_count": 2,
            }
        },
    )
    result = DistributionAnomalyIndex().evaluate(
        observation,
        [
            _result("robust_zscore", 0.95, metric="visits"),
            _result("relational_control_v1", 0.95, metric="visits"),
        ],
    )
    assert result is not None
    assert result.level is EvidenceLevel.HYPOTHESIS
    assert result.score < 0.60
    assert result.attributes["iad_score"] > result.attributes["iad_threshold"]
    assert result.attributes["iad_decision"] is False
    assert result.attributes["alert_eligible"] is False
    assert result.attributes["calibration_trust"] == "request_experimental"
    assert result.attributes["causal_claim"] is False


def test_request_payload_cannot_self_promote_an_approved_profile() -> None:
    observation = RadarObservation(
        entity_id="UNTRUSTED-APPROVAL",
        observed_at=datetime.now(UTC),
        metrics={},
        context={"iad_calibration": _approved_profile()},
    )
    result = DistributionAnomalyIndex().evaluate(
        observation,
        [
            _result("robust_zscore", 0.95, metric="visits"),
            _result("relational_control_v1", 0.95, metric="visits"),
        ],
    )
    assert result is None


def test_trusted_runtime_profile_can_promote_calibrated_iad() -> None:
    observation = RadarObservation(
        entity_id="HISTORICAL-FIXTURE",
        observed_at=datetime.now(UTC),
        metrics={},
    )
    result = DistributionAnomalyIndex(trusted_profile=_approved_profile()).evaluate(
        observation,
        [
            _result("robust_zscore", 0.90, metric="visits"),
            _result("relational_control_v1", 0.90, metric="visits"),
        ],
    )
    assert result is not None
    assert result.level is EvidenceLevel.INFERENCE
    assert result.score >= 0.60
    assert result.attributes["iad_decision"] is True
    assert result.attributes["alert_eligible"] is True
    assert result.attributes["calibration_trust"] == "trusted_runtime"
    assert result.attributes["causal_claim"] is False
    assert result.attributes["internal_platform_cause_confirmed"] is False


def test_default_radar_has_no_iad_without_calibration() -> None:
    finding = build_default_radar().evaluate(_observation())
    assert all(
        result.detector != "distribution_anomaly_index_v1"
        for result in finding.detector_results
    )


def test_default_radar_rejects_request_self_promotion() -> None:
    finding = build_default_radar().evaluate(_observation(calibration=_approved_profile()))
    assert all(
        result.detector != "distribution_anomaly_index_v1"
        for result in finding.detector_results
    )


def test_default_radar_registers_iad_from_trusted_runtime_profile() -> None:
    finding = build_default_radar(iad_profile=_approved_profile()).evaluate(_observation())
    iad = next(
        result for result in finding.detector_results
        if result.detector == "distribution_anomaly_index_v1"
    )
    assert iad.attributes["component_count"] == 2
    assert iad.attributes["components"]["traffic_deviation"] >= 0.60
    assert iad.attributes["components"]["control_divergence"] >= 0.60
    assert iad.attributes["iad_decision"] is True
    assert iad.attributes["calibration_version"] == "historical-fixture-v1"
    assert iad.attributes["calibration_trust"] == "trusted_runtime"
