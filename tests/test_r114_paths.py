import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.workflows.activities import RadarActivities


HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


def _payload() -> dict:
    observation = RadarObservation(
        entity_id="R114-PATH",
        observed_at=datetime.now(UTC),
        metrics={"visits": 75},
        history={"visits": HISTORY},
        context={
            "control_candidates": [
                {
                    "entity_id": name,
                    "metrics": {"visits": current},
                    "history": {"visits": HISTORY},
                }
                for name, current in [("C1", 100), ("C2", 101), ("C3", 99)]
            ]
        },
    )
    return observation.model_dump(mode="json")


def _counterfactual(results: list[dict]) -> dict:
    return next(item for item in results if item["detector"] == "operational_counterfactual_v1")


def test_http_radar_evaluate_exposes_operational_counterfactual() -> None:
    response = TestClient(create_app(Settings())).post("/v1/radar/evaluate", json=_payload())
    assert response.status_code == 200
    result = _counterfactual(response.json()["detector_results"])
    assert result["attributes"]["counterfactual_expected"] == 100.0
    assert result["attributes"]["causal_claim"] is False


def test_radar_activity_preserves_operational_counterfactual() -> None:
    finding = asyncio.run(RadarActivities(build_default_radar()).evaluate(_payload()))
    result = _counterfactual(finding["detector_results"])
    assert result["attributes"]["counterfactual_kind"] == "operational_not_causal"
    assert result["attributes"]["fit_uses_current_target"] is False
