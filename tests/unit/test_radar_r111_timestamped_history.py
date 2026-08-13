from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.models import RadarObservation


def test_legacy_numeric_history_remains_accepted() -> None:
    observation = RadarObservation(
        entity_id="legacy",
        observed_at=datetime.now(UTC),
        metrics={"visits": 10.0},
        history={"visits": [7.0, 8.0, 9.0]},
    )
    assert observation.history["visits"] == [7.0, 8.0, 9.0]
    assert observation.timestamped_history == {}


def test_timestamped_history_projects_numeric_values() -> None:
    base = datetime(2026, 8, 1, 12, tzinfo=UTC)
    observation = RadarObservation(
        entity_id="timestamped",
        observed_at=base + timedelta(days=2),
        metrics={"visits": 12.0},
        timestamped_history={
            "visits": [
                {"timestamp": base + timedelta(days=1), "value": 11.0},
                {"timestamp": base, "value": 10.0},
            ]
        },
    )
    assert observation.history["visits"] == [10.0, 11.0]
