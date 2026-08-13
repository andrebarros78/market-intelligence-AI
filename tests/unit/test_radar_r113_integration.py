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
