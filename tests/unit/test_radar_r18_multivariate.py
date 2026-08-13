from datetime import UTC, datetime

from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.multivariate import MultivariateRelationshipDetector


def _evaluate(metrics: dict[str, float], history: dict[str, list[float]]):
    return MultivariateRelationshipDetector().evaluate(
        RadarObservation(
            entity_id="MLB-R18",
            observed_at=datetime.now(UTC),
            metrics=metrics,
            history=history,
        )
    )


def test_multivariate_requires_two_supported_metrics() -> None:
    assert _evaluate({"visits": 120}, {"visits": [100, 110, 120, 130, 140, 150, 160, 170]}) is None


def test_multivariate_ignores_stable_relationship() -> None:
    visits = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190]
    sales = [10.1, 11.0, 12.2, 12.9, 14.1, 15.0, 16.1, 16.9, 18.1, 19.0]
    assert _evaluate({"visits": 155, "sales": 15.5}, {"visits": visits, "sales": sales}) is None


def test_multivariate_detects_relationship_break_inside_each_metric_domain() -> None:
    visits = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190]
    sales = [10.1, 11.0, 12.2, 12.9, 14.1, 15.0, 16.1, 16.9, 18.1, 19.0]
    result = _evaluate(
        {"visits": 150, "sales": 12.5},
        {"visits": visits, "sales": sales},
    )
    assert result is not None
    assert result.level.value == "fact"
    assert result.attributes["pattern"] == "relationship_break"
    assert result.attributes["fit_quality"] >= 0.70
    assert result.attributes["residual_signal"] >= 4.0
    assert result.attributes["cause_status"] == "unknown_not_inferred"
    assert result.attributes["detector_version"] == "multivariate-relationship@1.0.0"


def test_multivariate_ignores_weak_inconsistent_relationship() -> None:
    visits = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190]
    sales = [10, 16, 11, 15, 12, 17, 10, 16, 11, 15]
    assert _evaluate({"visits": 150, "sales": 12}, {"visits": visits, "sales": sales}) is None


def test_multivariate_rejects_extreme_univariate_extrapolation() -> None:
    visits = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190]
    sales = [10.1, 11.0, 12.2, 12.9, 14.1, 15.0, 16.1, 16.9, 18.1, 19.0]
    assert _evaluate({"visits": 500, "sales": 12}, {"visits": visits, "sales": sales}) is None


def test_multivariate_requires_aligned_history_minimum() -> None:
    assert _evaluate(
        {"visits": 150, "sales": 12},
        {
            "visits": [100, 110, 120, 130, 140, 150, 160, 170],
            "sales": [10, 11, 12, 13, 14],
        },
    ) is None
