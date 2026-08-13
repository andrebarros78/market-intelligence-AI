from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings


def test_operational_counterfactual_capability_is_separate_from_causal() -> None:
    client = TestClient(create_app(Settings()))
    radar = client.get("/v1/system/capabilities").json()["radar"]
    assert radar["operational_counterfactual"] is True
    assert radar["operational_counterfactual_detector"] == "operational-counterfactual@1.0.0"
    assert radar["counterfactual"] is False


def test_channel_sensor_exposes_noncausal_regime_correlation() -> None:
    client = TestClient(create_app(Settings()))
    details = client.get("/v1/system/capabilities").json()["channel_sensor_details"]
    assert details["persistent"] is True
    assert details["regime_correlation"] is True
    assert details["regime_correlation_detector"] == "channel-regime-correlation@1.0.0"
    assert details["business_correlation"] is True
    assert details["causal_claim"] is False
