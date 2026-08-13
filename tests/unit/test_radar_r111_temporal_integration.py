from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.workflows.activities import RadarActivities


async def test_temporal_activity_receives_timestamped_history() -> None:
    current = datetime(2026, 8, 16, 12, tzinfo=UTC)
    points = [
        {"timestamp": current - timedelta(days=offset), "value": 60.0}
        for offset in range(1, 18)
    ]
    observation = RadarObservation(
        entity_id="temporal-history",
        observed_at=current,
        metrics={"visits": 60.0},
        timestamped_history={"visits": points},
    )
    result = await RadarActivities(build_default_radar()).evaluate(
        observation.model_dump(mode="json")
    )
    assert result["entity_id"] == "temporal-history"
