from datetime import UTC, datetime

from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings


def _payload() -> dict:
    return {
        "entity_id": "R118-HTTP",
        "observed_at": datetime.now(UTC).isoformat(),
        "metrics": {"visits": 10.0},
        "history": {"visits": [100.0, 101.0, 99.0, 100.0, 102.0, 98.0, 101.0, 99.0]},
        "context": {},
    }


def test_capabilities_expose_progressive_investigation_honestly() -> None:
    capabilities = TestClient(create_app(Settings())).get("/v1/system/capabilities").json()
    radar = capabilities["radar"]
    persistence = capabilities["persistence"]
    workflows = capabilities["production_workflows"]
    assert radar["progressive_investigation"] is True
    assert radar["progressive_investigation_engine"] == "progressive-investigation@1.0.0"
    assert radar["investigation_persistence"] == "postgresql_via_temporal_activity"
    assert radar["investigation_http_mode"] == "stateless_preview"
    assert radar["investigation_causal_claim"] is False
    assert persistence["investigation_cases"] is True
    assert persistence["investigation_timeline"] is True
    assert persistence["investigation_event_idempotency"] is True
    assert workflows["durable_progressive_investigation"] is True


def test_http_investigation_is_explicitly_stateless_preview() -> None:
    response = TestClient(create_app(Settings())).post("/v1/radar/investigate", json=_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["persistent"] is False
    assert data["mode"] == "stateless_preview"
    assert data["causal_claim"] is False
    assert data["finding"]["anomalous"] is True
    assert data["investigation"]["status_after"] == "open"
    assert data["investigation"]["causal_claim"] is False
