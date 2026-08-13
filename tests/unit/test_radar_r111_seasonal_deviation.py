from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.time_series import find_seasonal_reference


def _weekly(current_value: float) -> RadarObservation:
    current = datetime(2026, 8, 16, 12, tzinfo=UTC)
    start = current - timedelta(days=56)
    points = []
    for offset in range(56):
        timestamp = start + timedelta(days=offset)
        points.append(
            {"timestamp": timestamp, "value": 60.0 if timestamp.weekday() == 6 else 100.0}
        )
    return RadarObservation(
        entity_id="weekly-deviation",
        observed_at=current,
        metrics={"visits": current_value},
        timestamped_history={"visits": points},
    )


def test_value_outside_its_own_weekly_band_is_anomalous() -> None:
    finding = build_default_radar().evaluate(_weekly(20.0))
    assert finding.anomalous is True
    seasonal = next(
        result for result in finding.detector_results if result.detector == "seasonality_v1"
    )
    assert seasonal.attributes["pattern"] == "seasonal_deviation"
    assert seasonal.attributes["seasonal_expected"] == 60.0
    assert seasonal.score >= 0.60


def test_hour_of_day_reference_uses_repeated_daily_cycles() -> None:
    current = datetime(2026, 8, 16, 22, tzinfo=UTC)
    points = []
    for days_ago in range(30, 0, -1):
        day = current - timedelta(days=days_ago)
        points.append({"timestamp": day.replace(hour=10), "value": 100.0})
        points.append({"timestamp": day.replace(hour=22), "value": 50.0})
    observation = RadarObservation(
        entity_id="hourly-cycle",
        observed_at=current,
        metrics={"visits": 50.0},
        timestamped_history={"visits": points},
    )
    reference = find_seasonal_reference(observation, "visits")
    assert reference is not None
    assert reference.period == "hour_of_day"
    assert reference.expected == 50.0
