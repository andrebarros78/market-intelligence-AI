from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.workflows.activities import RadarActivities

TARGET_HISTORY = [100, 110, 105, 115, 110, 120, 115, 125, 120, 130]
FACTOR_HISTORY = [50, 55, 52.5, 57.5, 55, 60, 57.5, 62.5, 60, 65]


def _payload() -> dict:
    return {
        "entity_id": "TARGET-R113",
        "observed_at": datetime.now(UTC).isoformat(),
        "metrics": {"visits": 90},
        "history": {"visits": TARGET_HISTORY},
        "context": {
            "factor_attribution": {
                "metric": "visits",
                "expected": 130,
                "factors": [
                    {
                        "name": "competition",
                        "current": 60,
                        "history": FACTOR_HISTORY,
                        "source": "market",
                    }
                ],
            }
        },
    }


def test_api_exposes_non_causal_factor_attribution() -> None:
    response = TestClient(create_app(Settings())).post("/v1/radar/evaluate", json=_payload())
    assert response.status_code == 200
    by_name = {item["detector"]: item for item in response.json()["detector_results"]}
    attribution = by_name["factor_attribution_v1"]
    assert attribution["level"] == "inference"
    assert attribution["attributes"]["causal_claim"] is False
    assert attribution["attributes"]["fit_uses_current_target"] is False
    assert attribution["attributes"]["observable_causes"] == ["competition"]
    assert attribution["attributes"]["detector_version"] == "factor-attribution@1.0.0"
