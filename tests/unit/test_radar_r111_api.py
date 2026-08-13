from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings


def test_radar_api_is_available() -> None:
    client = TestClient(create_app(Settings()))
    assert client.get("/health").status_code == 200
