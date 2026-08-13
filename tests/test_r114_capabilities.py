from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings


def test_operational_counterfactual_capability_is_separate_from_causal() -> None:
    client = TestClient(create_app(Settings()))
    radar = client.get("/v1/system/capabilities").json()["radar"]
    assert radar["operational_counterfactual"] is True
    assert radar["operational_counterfactual_detector"] == "operational-counterfactual@1.0.0"
    assert radar["counterfactual"] is False
