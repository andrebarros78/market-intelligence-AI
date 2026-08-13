from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

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


def test_timestamped_history_is_sorted_and_projects_numeric_values() -> None:
    base = datetime(2026, 8, 1, 12, tzinfo=UTC)
    observation = RadarObservation(
        entity_id="timestamped",
        observed_at=base + timedelta(days=3),
        metrics={"visits": 13.0},
        timestamped_history={
            "visits": [
                {"timestamp": base + timedelta(days=2), "value": 12.0},
                {"timestamp": base, "value": 10.0},
                {"timestamp": base + timedelta(days=1), "value": 11.0},
            ]
        },
    )
    assert [point.value for point in observation.timestamped_history["visits"]] == [
        10.0,
        11.0,
        12.0,
    ]
    assert observation.history["visits"] == [10.0, 11.0, 12.0]


def test_explicit_legacy_history_is_preserved_during_transition() -> None:
    base = datetime(2026, 8, 1, 12, tzinfo=UTC)
    observation = RadarObservation(
        entity_id="mixed",
        observed_at=base + timedelta(days=2),
        metrics={"visits": 12.0},
        history={"visits": [1.0, 2.0]},
        timestamped_history={
            "visits": [
                {"timestamp": base, "value": 10.0},
                {"timestamp": base + timedelta(days=1), "value": 11.0},
            ]
        },
    )
    assert observation.history["visits"] == [1.0, 2.0]


def test_duplicate_timestamps_are_rejected() -> None:
    timestamp = datetime(2026, 8, 1, 12, tzinfo=UTC)
    with pytest.raises(ValidationError):
        RadarObservation(
            entity_id="duplicate",
            observed_at=timestamp + timedelta(days=1),
            metrics={"visits": 10.0},
            timestamped_history={
                "visits": [
                    {"timestamp": timestamp, "value": 9.0},
                    {"timestamp": timestamp, "value": 10.0},
                ]
            },
        )


def test_naive_timestamped_history_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RadarObservation(
            entity_id="naive",
            observed_at=datetime(2026, 8, 2, 12),
            metrics={"visits": 10.0},
            timestamped_history={
                "visits": [{"timestamp": datetime(2026, 8, 1, 12), "value": 9.0}]
            },
        )
