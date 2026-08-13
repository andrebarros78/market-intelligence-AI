from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.seasonality import SeasonalityDetector


def _weekly_observation(current_value: float) -> RadarObservation:
    current = datetime(2026, 8, 16, 12, tzinfo=UTC)
    start = current - timedelta(days=56)
    points = []
    for offset in range(56):
        timestamp = start + timedelta(days=offset)
        value = 60.0 if timestamp.weekday() == 6 else 100.0
        points.append({"timestamp": timestamp, "value": value})
    return RadarObservation(
        entity_id="weekly",
        observed_at=current,
        metrics={"visits": current_value},
        timestamped_history={"visits": points},
    )


def test_normal_weekly_drop_is_recognized_as_expected_seasonality() -> None:
    observation = _weekly_observation(60.0)
    result = SeasonalityDetector().evaluate(observation)
    assert result is not None
    assert result.score == 0.0
    assert result.attributes["pattern"] == "seasonal_expected"
    assert result.attributes["period"] == "weekday"
    assert result.attributes["seasonal_expected"] == 60.0


def test_default_radar_suppresses_univariate_false_positive_for_expected_seasonality() -> None:
    finding = build_default_radar().evaluate(_weekly_observation(60.0))
    assert finding.anomalous is False
    detectors = {result.detector for result in finding.detector_results}
    assert "seasonality_v1" in detectors
    assert "robust_zscore" not in detectors
