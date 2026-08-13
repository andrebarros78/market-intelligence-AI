from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings
from market_intelligence.marketplaces.mercadolivre.oauth.runtime import build_synthetic_oauth_runtime
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.workflows.names import WORKFLOW_OAUTH_REFRESH


class CapturingWorkflowEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    async def start(
        self,
        workflow_name: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> str:
        self.calls.append((workflow_name, payload, idempotency_key))
        return "mi-safe-workflow-id"


@pytest.mark.postgres
def test_r12_internal_oauth_api_is_synthetic_fail_closed_and_refresh_payload_is_safe() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        now = datetime.now(UTC)
        account_id = f"api-oauth-{uuid4().hex}"
        runtime = build_synthetic_oauth_runtime(
            sessions=sessions,
            encryption_key=b"a" * 32,
            clock=lambda: now,
        )
        engine = CapturingWorkflowEngine()
        app = create_app(Settings(), oauth_runtime=runtime, oauth_refresh_engine=engine)
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                start = await client.post(
                    "/v1/internal/oauth/synthetic/start",
                    json={"account_id": account_id},
                )
                assert start.status_code == 200
                start_payload = start.json()
                assert start_payload["code_challenge_method"] == "S256"
                state = start_payload["state"]

                callback = await client.post(
                    "/v1/internal/oauth/synthetic/callback",
                    json={
                        "account_id": account_id,
                        "state": state,
                        "code": "synthetic-api-code",
                    },
                )
                assert callback.status_code == 200
                assert callback.json() == {"credential_version": 1}

                health = await client.get(
                    f"/v1/internal/oauth/synthetic/health/{account_id}"
                )
                assert health.status_code == 200
                assert health.json()["status"] == "healthy"
                assert "access_token" not in health.text
                assert "refresh_token" not in health.text

                ready = await client.get("/v1/internal/oauth/synthetic/ready")
                assert ready.status_code == 200
                assert ready.json()["ready"] is True
                assert ready.json()["real_network"] is False
                assert ready.json()["marketplace_writes"] is False

                refresh = await client.post(
                    "/v1/internal/oauth/synthetic/refresh",
                    json={
                        "account_id": account_id,
                        "idempotency_key": "request-123",
                        "correlation_id": "correlation-123",
                    },
                )
                assert refresh.status_code == 202
                assert refresh.json() == {"workflow_id": "mi-safe-workflow-id"}

                assert engine.calls == [
                    (
                        WORKFLOW_OAUTH_REFRESH,
                        {"account_id": account_id, "correlation_id": "correlation-123"},
                        "request-123",
                    )
                ]
                captured = repr(engine.calls)
                assert state not in captured
                assert "synthetic-api-code" not in captured
                assert "access_token" not in captured
                assert "refresh_token" not in captured
        finally:
            await database.dispose()

    asyncio.run(scenario())
