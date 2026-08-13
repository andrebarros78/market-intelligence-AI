from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings


def test_r110_capability_is_exposed_without_claiming_counterfactual() -> None:
    client = TestClient(create_app(Settings()))
    radar = client.get("/v1/system/capabilities").json()["radar"]
    assert radar["unexplained_residual_detector"] is True
    assert radar["unexplained_residual_detector_version"] == "unexplained-residual@1.0.0"
    assert radar["counterfactual"] is False
