from datetime import UTC, datetime

from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.multivariate import MultivariateRelationshipDetector
from market_intelligence.workflows.activities import RadarActivities

VISITS = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190]
SALES = [10.1, 11.0, 12.2, 12.9, 14.1, 15.0, 16.1, 16.9, 18.1, 19.0]


def _observation(metrics: dict[str, float], history: dict[str, list[float]]) -> RadarObservation:
    return RadarObservation(
        entity_id="MLB-R18",
        observed_at=datetime.now(UTC),
        metrics=metrics,
        history=history,
    )


def _evaluate(metrics: dict[str, float], history: dict[str, list[float]]):
    return MultivariateRelationshipDetector().evaluate(_observation(metrics, history))


def test_multivariate_requires_two_supported_metrics() -> None:
    assert _evaluate({"visits": 120}, {"visits": [100, 110, 120, 130, 140, 150, 160, 170]}) is None


def test_multivariate_ignores_stable_relationship() -> None:
    assert _evaluate({"visits": 155, "sales": 15.5}, {"visits": VISITS, "sales": SALES}) is None


def test_multivariate_detects_relationship_break_inside_each_metric_domain() -> None:
    result = _evaluate(
        {"visits": 150, "sales": 12.5},
        {"visits": VISITS, "sales": SALES},
    )
    assert result is not None
    assert result.level.value == "fact"
    assert result.attributes["pattern"] == "relationship_break"
    assert result.attributes["fit_quality"] >= 0.70
    assert result.attributes["residual_signal"] >= 4.0
    assert result.attributes["cause_status"] == "unknown_not_inferred"
    assert result.attributes["detector_version"] == "multivariate-relationship@1.0.0"


def test_multivariate_ignores_weak_inconsistent_relationship() -> None:
    weak = [10, 16, 11, 15, 12, 17, 10, 16, 11, 15]
    assert _evaluate({"visits": 150, "sales": 12}, {"visits": VISITS, "sales": weak}) is None


def test_multivariate_rejects_extreme_univariate_extrapolation() -> None:
    assert _evaluate({"visits": 500, "sales": 12}, {"visits": VISITS, "sales": SALES}) is None


def test_multivariate_requires_aligned_history_minimum() -> None:
    assert _evaluate(
        {"visits": 150, "sales": 12},
        {
            "visits": [100, 110, 120, 130, 140, 150, 160, 170],
            "sales": [10, 11, 12, 13, 14],
        },
    ) is None


def test_default_radar_contains_multivariate_detector() -> None:
    finding = build_default_radar().evaluate(
        _observation({"visits": 150, "sales": 12.5}, {"visits": VISITS, "sales": SALES})
    )
    detectors = {result.detector: result for result in finding.detector_results}
    assert finding.anomalous is True
    assert "multivariate_relationship_v1" in detectors


async def test_temporal_radar_activity_uses_same_multivariate_detector() -> None:
    payload = _observation(
        {"visits": 150, "sales": 12.5}, {"visits": VISITS, "sales": SALES}
    ).model_dump(mode="json")
    result = await RadarActivities(build_default_radar()).evaluate(payload)
    detectors = {item["detector"]: item for item in result["detector_results"]}
    assert detectors["multivariate_relationship_v1"]["attributes"]["detector_version"] == "multivariate-relationship@1.0.0"
