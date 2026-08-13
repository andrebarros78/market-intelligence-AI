from __future__ import annotations

from datetime import UTC, datetime, timedelta

from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.workflows.activities import RadarActivities


async def test_temporal_activity_uses_factor_attribution() -> None:
    observation = RadarObservation(
        entity_id="TARGET-R113-TEMPORAL",
        observed_at=datetime.now(UTC),
        metrics={"visits": 90},
        history={"visits": [100, 110, 105, 115, 110, 120, 115, 125, 120, 130]},
        context={
            "factor_attribution": {
                "metric": "visits",
                "expected": 130,
                "factors": [
                    {
                        "name": "competition",
                        "current": 60,
                        "history": [50, 55, 52.5, 57.5, 55, 60, 57.5, 62.5, 60, 65],
                    }
                ],
            }
        },
    )
    result = await RadarActivities(build_default_radar()).evaluate(
        observation.model_dump(mode="json")
    )
    by_name = {item["detector"]: item for item in result["detector_results"]}
    attribution = by_name["factor_attribution_v1"]
    assert attribution["level"] == "inference"
    assert attribution["attributes"]["causal_claim"] is False
    assert attribution["attributes"]["fit_uses_current_target"] is False
    assert by_name["unexplained_residual_v1"]["attributes"]["unexplained_residual"] == -30.0


async def test_temporal_activity_uses_channel_regime_correlation() -> None:
    now = datetime.now(UTC)
    start = now - timedelta(minutes=11)
    channel_events = []
    for index in range(12):
        recent = index >= 8
        channel_events.append(
            {
                "marketplace": "mercadolivre",
                "direction": "inbound",
                "operation": "/items/R115",
                "observed_at": start + timedelta(minutes=index),
                "status_code": 503 if recent else 200,
                "latency_ms": 430.0 if recent else 90.0,
                "attempt": 2 if recent else 1,
                "attributes": {"partial_content": True} if recent else {},
            }
        )
    observation = RadarObservation(
        entity_id="TARGET-R115-TEMPORAL",
        observed_at=now,
        metrics={"visits": 55},
        history={"visits": [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]},
        context={"channel_events": channel_events},
    )
    result = await RadarActivities(build_default_radar()).evaluate(
        observation.model_dump(mode="json")
    )
    by_name = {item["detector"]: item for item in result["detector_results"]}
    channel = by_name["channel_regime_correlation_v1"]
    assert channel["level"] == "inference"
    assert channel["attributes"]["correlation_status"] == "joint_regime_detected"
    assert channel["attributes"]["causal_claim"] is False
    assert channel["attributes"]["internal_platform_cause_confirmed"] is False
