from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from market_intelligence.api.webhook_server import create_mercadolivre_webhook_app_from_env


def _safe_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MI_READ_ONLY", "true")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "false")


def test_webhook_bootstrap_requires_database(monkeypatch: pytest.MonkeyPatch) -> None:
    _safe_runtime(monkeypatch)
    monkeypatch.delenv("MI_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="MI_DATABASE_URL is required"):
        create_mercadolivre_webhook_app_from_env()


def test_webhook_bootstrap_requires_application_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _safe_runtime(monkeypatch)
    monkeypatch.setenv(
        "MI_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/unused",
    )
    monkeypatch.delenv("MI_ML_APP_ID", raising=False)
    with pytest.raises(RuntimeError, match="MI_ML_APP_ID is required"):
        create_mercadolivre_webhook_app_from_env()


def test_webhook_bootstrap_rejects_marketplace_write_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MI_READ_ONLY", "false")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "true")
    with pytest.raises(PermissionError):
        create_mercadolivre_webhook_app_from_env()


def test_webhook_bootstrap_runs_lifespan_without_legacy_event_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _safe_runtime(monkeypatch)
    monkeypatch.setenv(
        "MI_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@127.0.0.1:1/unused",
    )
    monkeypatch.setenv("MI_ML_APP_ID", "2767330231710080")

    app = create_mercadolivre_webhook_app_from_env()

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
