from __future__ import annotations

from datetime import UTC, datetime

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
