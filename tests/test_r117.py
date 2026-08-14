from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.pyod_ensemble import (
    PyODBenchmarkCalibrator,
    PyODBenchmarkProfile,
    PyODEnsembleDetector,
)


VISITS_HISTORY = [
    100, 101, 99, 100, 102, 98, 101, 99, 100, 100, 101, 99,
    100, 102, 98, 101, 99, 100, 101, 100, 99, 102, 98, 100,
]
CONVERSION_HISTORY = [
    0.100, 0.101, 0.099, 0.100, 0.102, 0.098, 0.101, 0.099,
    0.100, 0.100, 0.101, 0.099, 0.100, 0.102, 0.098, 0.101,
    0.099, 0.100, 0.101, 0.100, 0.099, 0.102, 0.098, 0.100,
]


def _train_features() -> list[list[float]]:
    return [list(row) for row in zip(VISITS_HISTORY, CONVERSION_HISTORY)]


def _validation_samples() -> list[dict]:
    return [
        {"label": False, "features": [100, 0.100]},
        {"label": False, "features": [101, 0.101]},
        {"label": False, "features": [99, 0.099]},
        {"label": False, "features": [100, 0.098]},
        {"label": True, "features": [155, 0.260]},
        {"label": True, "features": [165, 0.300]},
        {"label": True, "features": [175, 0.330]},
        {"label": True, "features": [185, 0.360]},
    ]


def _benchmark_profile(*, source_type: str = "historical_validation") -> PyODBenchmarkProfile:
    return PyODBenchmarkCalibrator().fit(
        _train_features(),
        _validation_samples(),
        feature_names=["visits", "conversion"],
        version="r117-benchmark-fixture-v1",
        source_type=source_type,
    )


def _approved_profile() -> PyODBenchmarkProfile:
    profile = _benchmark_profile()
    payload = profile.model_dump(mode="json")
    payload["production_approved"] = True
    return PyODBenchmarkProfile.model_validate(payload)


def _observation(*, experimental: bool = False) -> RadarObservation:
    return RadarObservation(
        entity_id="R117-TARGET",
        observed_at=datetime.now(UTC),
        metrics={"visits": 180, "conversion": 0.35},
        history={
            "visits": VISITS_HISTORY,
            "conversion": CONVERSION_HISTORY,
        },
        context={"pyod_experimental": True} if experimental else {},
    )


def _pyod_result(finding):
    return next(
        result
        for result in finding.detector_results
        if result.detector == "pyod_ensemble_v1"
    )


def test_benchmark_selects_multiple_detectors_and_never_auto_approves() -> None:
    profile = _benchmark_profile()
    assert profile.production_approved is False
    assert profile.source_type == "historical_validation"
    assert len(profile.detector_weights) >= 2
    assert sum(profile.detector_weights.values()) == pytest.approx(1.0)
    assert profile.positive_count == 4
    assert profile.negative_count == 4
    assert profile.metrics["balanced_accuracy"] >= 0.75
    assert set(profile.detector_weights).issubset({"ecod", "iforest", "knn"})


def test_benchmark_is_deterministic_for_same_dataset() -> None:
    first = _benchmark_profile()
    second = _benchmark_profile()
    assert first.detector_weights == pytest.approx(second.detector_weights)
    assert first.threshold == pytest.approx(second.threshold)
    assert first.metrics == pytest.approx(second.metrics)


def test_synthetic_benchmark_cannot_be_production_approved() -> None:
    profile = _benchmark_profile(source_type="synthetic_test")
    payload = profile.model_dump(mode="json")
    payload["production_approved"] = True
    with pytest.raises(ValidationError):
        PyODBenchmarkProfile.model_validate(payload)


def test_production_profile_requires_multiple_detectors_and_both_classes() -> None:
    with pytest.raises(ValidationError):
        PyODBenchmarkProfile.model_validate(
            {
                "version": "invalid-v1",
                "source_type": "historical_validation",
                "detector_weights": {"ecod": 1.0},
                "threshold": 0.8,
                "feature_names": ["visits", "conversion"],
                "production_approved": True,
                "sample_count": 8,
                "positive_count": 4,
                "negative_count": 4,
                "metrics": {"balanced_accuracy": 1.0},
            }
        )


def test_default_radar_does_not_run_pyod_without_explicit_lab_request() -> None:
    finding = build_default_radar().evaluate(_observation())
    assert all(result.detector != "pyod_ensemble_v1" for result in finding.detector_results)


def test_experimental_request_cannot_promote_pyod_alert() -> None:
    finding = build_default_radar().evaluate(_observation(experimental=True))
    result = _pyod_result(finding)
    assert result.level is EvidenceLevel.HYPOTHESIS
    assert result.score < 0.60
    assert result.attributes["ensemble_threshold"] is None
    assert result.attributes["ensemble_decision"] is False
    assert result.attributes["alert_eligible"] is False
    assert result.attributes["production_approved"] is False
    assert result.attributes["trust_boundary"] == "request_experimental"
    assert result.attributes["causal_claim"] is False
    assert set(result.attributes["detector_percentiles"]) == {"ecod", "iforest", "knn"}


def test_trusted_runtime_profile_can_promote_benchmarked_ensemble() -> None:
    profile = _approved_profile()
    finding = build_default_radar(pyod_profile=profile).evaluate(_observation())
    result = _pyod_result(finding)
    assert result.level is EvidenceLevel.INFERENCE
    assert result.score >= 0.60
    assert result.attributes["ensemble_decision"] is True
    assert result.attributes["alert_eligible"] is True
    assert result.attributes["production_approved"] is True
    assert result.attributes["trust_boundary"] == "trusted_runtime"
    assert result.attributes["profile_version"] == "r117-benchmark-fixture-v1"
    assert result.attributes["causal_claim"] is False


def test_ensemble_result_is_deterministic_with_fixed_runtime_profile() -> None:
    profile = _approved_profile()
    detector = PyODEnsembleDetector(trusted_profile=profile)
    first = detector.evaluate(_observation())
    second = detector.evaluate(_observation())
    assert first is not None and second is not None
    assert first.score == pytest.approx(second.score)
    assert first.attributes["ensemble_score"] == pytest.approx(
        second.attributes["ensemble_score"]
    )
    assert first.attributes["detector_percentiles"] == pytest.approx(
        second.attributes["detector_percentiles"]
    )
