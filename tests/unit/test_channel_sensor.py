from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.channel_regime import ChannelRegimeCorrelationDetector
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.marketplaces.mercadolivre.channel_sensor import build_channel_telemetry
from market_intelligence.workflows.activities import _operation_contains_entity


HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


def test_channel_sensor_never_persists_authorization() -> None:
    telemetry = build_channel_telemetry(
        direction="meli->us",
        endpoint="/notifications",
        status_code=206,
        headers={
            "Authorization": "Bearer SHOULD-NOT-LEAK",
            "X-Request-Id": "req-123",
            "X-Content-Missing": "orders",
            "Retry-After": "2",
            "X-Unknown": "discard-me",
        },
    )
    assert "authorization" not in telemetry.operational_headers
    assert telemetry.request_id == "req-123"
    assert telemetry.partial_content is True
    assert "x-unknown" not in telemetry.operational_headers


def test_stale_channel_events_are_excluded_from_radar_correlation() -> None:
    now = datetime.now(UTC)
    start = now - timedelta(days=1, minutes=11)
    events = []
    for index in range(12):
        recent = index >= 8
        events.append(
            {
                "marketplace": "mercadolivre",
                "direction": "inbound",
                "operation": "/items/STALE",
                "observed_at": start + timedelta(minutes=index),
                "status_code": 503 if recent else 200,
                "latency_ms": 450.0 if recent else 90.0,
                "attempt": 2 if recent else 1,
                "attributes": {"partial_content": True} if recent else {},
            }
        )
    observation = RadarObservation(
        entity_id="STALE",
        observed_at=now,
        metrics={"visits": 55},
        history={"visits": HISTORY},
        context={"channel_events": events},
    )
    assert observation.context["channel_events"] == []
    assert observation.context["channel_events_rejected_as_stale"] is True
    assert observation.context["channel_alignment_seconds"] > 21600
    assert ChannelRegimeCorrelationDetector().evaluate(observation) is None


def test_channel_schema_cadence_and_partial_signals_are_aggregated_without_raw_attributes() -> None:
    now = datetime.now(UTC)
    events = []
    baseline_start = now - timedelta(minutes=37)
    for index in range(8):
        events.append(
            {
                "marketplace": "mercadolivre",
                "direction": "inbound",
                "operation": "/notifications",
                "observed_at": baseline_start + timedelta(minutes=index),
                "status_code": 200,
                "latency_ms": 100.0,
                "attempt": 1,
                "attributes": {},
            }
        )
    for index, minutes_ago in enumerate((30, 20, 10, 0)):
        events.append(
            {
                "marketplace": "mercadolivre",
                "direction": "inbound",
                "operation": "/notifications",
                "observed_at": now - timedelta(minutes=minutes_ago),
                "status_code": 206,
                "latency_ms": 100.0,
                "attempt": 1,
                "attributes": {
                    "partial_content": True,
                    "schema_changed": index == 3,
                    "opaque_marker": "MUST_NOT_APPEAR",
                },
            }
        )
    observation = RadarObservation(
        entity_id="CHANNEL-SIGNALS",
        observed_at=now,
        metrics={"visits": 55},
        history={"visits": HISTORY},
        context={"channel_events": events},
    )
    result = ChannelRegimeCorrelationDetector().evaluate(observation)
    assert result is not None
    signals = set(result.attributes["channel_signals"])
    assert "partial_content_shift" in signals
    assert "schema_change_shift" in signals
    assert "cadence_shift" in signals
    rendered = str(result.model_dump(mode="json"))
    assert "MUST_NOT_APPEAR" not in rendered
    assert "opaque_marker" not in rendered


def test_entity_path_scope_rejects_prefix_collisions() -> None:
    entity_id = "MLB123"
    assert _operation_contains_entity("/items/MLB123", entity_id) is True
    assert _operation_contains_entity("/items/MLB123/price_to_win", entity_id) is True
    assert _operation_contains_entity("/items/MLB1234", entity_id) is False
    assert _operation_contains_entity("synthetic-notification", entity_id) is False
