from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings


def test_health_and_readiness_are_read_only() -> None:
    client = TestClient(create_app(Settings()))
    assert client.get("/health").status_code == 200
    readiness = client.get("/ready").json()
    assert readiness["ready"] is True
    assert readiness["read_only"] is True
    assert readiness["marketplace_writes"] is False
    assert readiness["temporal_enabled"] is False


def test_capabilities_are_honest_about_unimplemented_layers() -> None:
    client = TestClient(create_app(Settings()))
    capabilities = client.get("/v1/system/capabilities").json()
    assert capabilities["radar"]["statistical_baseline"] is True
    assert capabilities["radar"]["multivariate"] is False
    workflows = capabilities["production_workflows"]
    assert workflows["engine"] == "temporal"
    assert workflows["implemented"] is True
    assert workflows["runtime_enabled"] is False
    assert workflows["marketplace_reads_only"] is True
