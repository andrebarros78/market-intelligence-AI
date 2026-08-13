from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.residual import UnexplainedResidualDetector


def test_residual_reference_is_seasonal_when_available() -> None:
    current = datetime(2026, 8, 16, 12, tzinfo=UTC)
    start = current - timedelta(days=56)
    points = []
    for offset in range(56):
        timestamp = start + timedelta(days=offset)
        value = 60.0 if timestamp.weekday() == 6 else 100.0
        points.append({"timestamp": timestamp, "value": value})
    observation = RadarObservation(
        entity_id="seasonal-residual-deviation",
        observed_at=current,
        metrics={"visits": 20.0},
        timestamped_history={"visits": points},
        context={"residual_analysis": {"metric": "visits"}},
    )
    result = UnexplainedResidualDetector().evaluate(observation)
    assert result is not None
    assert result.attributes["expected"] == 60.0
    assert result.attributes["reference_source"] == "seasonal:weekday"
