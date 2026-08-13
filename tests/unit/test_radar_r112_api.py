from datetime import UTC, datetime

from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings


HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


def test_api_uses_automatic_control_selection() -> None:
    candidates = [
        {"entity_id": name, "metrics": {"visits": current}, "history": {"visits": HISTORY}}
        for name, current in [("C1", 100), ("C2", 101), ("C3", 99)]
    ]
    response = TestClient(create_app(Settings())).post(
        "/v1/radar/evaluate",
        json={
            "entity_id": "TARGET-R112",
            "observed_at": datetime.now(UTC).isoformat(),
            "metrics": {"visits": 94},
            "history": {"visits": HISTORY},
            "context": {"control_candidates": candidates},
        },
    )
    assert response.status_code == 200
    relational = next(
        item for item in response.json()["detector_results"]
        if item["detector"] == "relational_control_v1"
    )
    selection = relational["attributes"]["control_comparison"]["selection"]
    assert selection["mode"] == "automatic"
    assert selection["selection_uses_current_values"] is False
