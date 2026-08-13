from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app
from market_intelligence.api.oauth import OAuthCallbackRequest
from market_intelligence.core.config import Settings


def test_health_and_readiness_are_read_only() -> None:
    client = TestClient(create_app(Settings()))
    assert client.get("/health").status_code == 200
    readiness = client.get("/ready").json()
    assert readiness["ready"] is True
    assert readiness["read_only"] is True
    assert readiness["marketplace_writes"] is False
    assert readiness["temporal_enabled"] is False
    assert readiness["oauth_synthetic_configured"] is False
    assert readiness["oauth_refresh_workflow_configured"] is False
    assert readiness["synthetic_ingestion_workflow_configured"] is False


def test_capabilities_are_honest_about_unimplemented_and_optional_layers() -> None:
    client = TestClient(create_app(Settings()))
    capabilities = client.get("/v1/system/capabilities").json()
    assert capabilities["radar"]["statistical_baseline"] is True
    assert capabilities["radar"]["vertical_synthetic_path"] is True
    assert capabilities["radar"]["multivariate"] is False
    assert capabilities["oauth"]["synthetic_foundation"] is True
    assert capabilities["oauth"]["runtime_configured"] is False
    assert capabilities["oauth"]["temporal_refresh_configured"] is False
    assert capabilities["oauth"]["real_network_enabled"] is False
    assert capabilities["channel_sensor"]["synthetic_only"] is True
    workflows = capabilities["production_workflows"]
    assert workflows["engine"] == "temporal"
    assert workflows["implemented"] is True
    assert workflows["runtime_enabled"] is False
    assert workflows["marketplace_reads_only"] is True


def test_synthetic_ingestion_route_fails_closed_without_engine() -> None:
    client = TestClient(create_app(Settings()))
    response = client.post(
        "/v1/internal/ingestion/synthetic",
        json={
            "idempotency_key": "event-1",
            "marketplace": "mercadolivre",
            "raw_event": {},
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "synthetic_ingestion_workflow_not_configured"


def test_synthetic_oauth_routes_fail_closed_without_runtime() -> None:
    client = TestClient(create_app(Settings()))
    response = client.post(
        "/v1/internal/oauth/synthetic/start",
        json={"account_id": "account-1"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "synthetic_oauth_runtime_not_configured"


def test_callback_model_redacts_state_and_code_in_repr() -> None:
    request = OAuthCallbackRequest(
        account_id="account-1",
        state="state-value-must-not-appear",
        code="code-value-must-not-appear",
    )
    rendered = repr(request)
    assert "state-value-must-not-appear" not in rendered
    assert "code-value-must-not-appear" not in rendered
    assert "**********" in rendered
