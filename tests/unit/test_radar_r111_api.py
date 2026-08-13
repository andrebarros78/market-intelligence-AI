from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings


def test_radar_api_accepts_timestamped_history() -> None:
    current = datetime(2026, 8, 16, 12, tzinfo=UTC)
    start = current - timedelta(days=56)
    points = []
    for offset in range(56):
        timestamp = start + timedelta(days=offset)
        value = 60.0 if timestamp.weekday() == 6 else 100.0
        points.append({"timestamp": timestamp.isoformat(), "value": value})
    client = TestClient(create_app(Settings()))
    response = client.post(
        "/v1/radar/evaluate",
        json={
            "entity_id": "api-seasonal",
            "observed_at": current.isoformat(),
            "metrics": {"visits": 20.0},
            "timestamped_history": {"visits": points},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["anomalous"] is True
    assert any(
        item["detector"] == "seasonality_v1"
        and item["attributes"]["pattern"] == "seasonal_deviation"
        for item in payload["detector_results"]
    )
