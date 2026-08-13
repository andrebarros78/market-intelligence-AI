from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.channel_regime import ChannelRegimeCorrelationDetector
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.marketplaces.mercadolivre.channel_sensor import build_channel_telemetry


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
