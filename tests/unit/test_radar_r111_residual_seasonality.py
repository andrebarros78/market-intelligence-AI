from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.residual import UnexplainedResidualDetector


def _seasonal(current_value: float) -> RadarObservation:
    current = datetime(2026, 8, 16, 12, tzinfo=UTC)
    start = current - timedelta(days=56)
    points = []
    for offset in range(56):
        timestamp = start + timedelta(days=offset)
        value = 60.0 if timestamp.weekday() == 6 else 100.0
        points.append({"timestamp": timestamp, "value": value})
    return RadarObservation(
        entity_id="seasonal-residual",
        observed_at=current,
        metrics={"visits": current_value},
        timestamped_history={"visits": points},
        context={"residual_analysis": {"metric": "visits"}},
    )


def test_seasonal_expected_value_does_not_create_residual_alert() -> None:
    assert UnexplainedResidualDetector().evaluate(_seasonal(60.0)) is None
