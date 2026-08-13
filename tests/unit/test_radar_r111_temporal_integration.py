from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.workflows.activities import RadarActivities


async def test_temporal_activity_uses_same_seasonality_detector() -> None:
    current = datetime(2026, 8, 16, 12, tzinfo=UTC)
    start = current - timedelta(days=56)
    points = []
    for offset in range(56):
        timestamp = start + timedelta(days=offset)
        value = 60.0 if timestamp.weekday() == 6 else 100.0
        points.append({"timestamp": timestamp, "value": value})
    observation = RadarObservation(
        entity_id="temporal-seasonal",
        observed_at=current,
        metrics={"visits": 20.0},
        timestamped_history={"visits": points},
    )
    result = await RadarActivities(build_default_radar()).evaluate(
        observation.model_dump(mode="json")
    )
    seasonal = next(
        item for item in result["detector_results"] if item["detector"] == "seasonality_v1"
    )
    assert seasonal["attributes"]["pattern"] == "seasonal_deviation"
