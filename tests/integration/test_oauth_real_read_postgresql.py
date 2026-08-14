from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from market_intelligence.marketplaces.mercadolivre.oauth.crypto import state_digest
from market_intelligence.marketplaces.mercadolivre.oauth.db_models import (
    OAuthAuditRecord,
    OAuthCredentialRecord,
)
from market_intelligence.marketplaces.mercadolivre.oauth.real_read import (
    RealReadOAuthSettings,
    build_real_read_oauth_runtime,
    close_real_read_oauth_runtime,
)
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import ChannelEventRecord, OAuthStateRecord


@pytest.mark.postgres
def test_real_read_oauth_first_gate_postgresql_with_mock_transport() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        engine = create_database_engine(url)
        sessions = create_session_factory(engine)
        now = datetime.now(UTC)
        account_id = str(9000000000 + int(uuid4().hex[:6], 16))
        secret = "client-secret-that-must-never-persist"
        access = f"access-{uuid4().hex}"
        refresh = f"refresh-{uuid4().hex}"
        authorization_code = f"code-{uuid4().hex}"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                body = request.content.decode("utf-8", errors="ignore")
                assert request.method == "POST"
                assert secret in body
                assert authorization_code in body
                return httpx.Response(
                    200,
                    json={
                        "access_token": access,
                        "refresh_token": refresh,
                        "expires_in": 21600,
                        "scope": "read offline_access",
                    },
                )
            if request.url.path == "/users/me":
                assert request.method == "GET"
                assert request.headers["Authorization"] == f"Bearer {access}"
                return httpx.Response(
                    200,
                    headers={"x-request-id": "rr01-integration-request"},
                    json={
                        "id": int(account_id),
                        "nickname": "integration-seller",
                        "site_id": "MLB",
                        "status": "active",
                    },
                )
            raise AssertionError(f"unexpected request {request.method} {request.url}")

        settings = RealReadOAuthSettings(
            app_id="2767330231710080",
            client_secret=SecretStr(secret),
            redirect_uri="https://example.test/v1/oauth/mercadolivre/callback",
            real_read_enabled=False,
        )
        runtime = build_real_read_oauth_runtime(
            sessions=sessions,
            encryption_key=b"r" * 32,
            settings=settings,
            clock=lambda: now,
            transport=httpx.MockTransport(handler),
        )
        try:
            plan = await runtime.service.start(expected_account_id=account_id)
            assert plan.authorization_url.startswith(
                "https://auth.mercadolivre.com.br/authorization?"
            )
            parsed_state = None
            from urllib.parse import parse_qs, urlsplit

            parsed_state = parse_qs(urlsplit(plan.authorization_url).query)["state"][0]
            digest = state_digest(parsed_state)
            async with sessions() as session:
                state_row = (
                    await session.execute(
                        select(OAuthStateRecord).where(OAuthStateRecord.state_hash == digest)
                    )
                ).scalar_one()
                assert state_row.synthetic is False
                assert state_row.state_hash != parsed_state
                assert authorization_code not in repr(state_row.metadata_json)

            identity = await runtime.service.callback(
                state=parsed_state,
                code=authorization_code,
                correlation_id="rr01-correlation",
            )
            assert identity.account_id == account_id
            assert identity.site_id == "MLB"
            assert identity.credential_version == 1
            assert identity.channel_event_persisted is True

            with pytest.raises(PermissionError, match="oauth_callback_rejected"):
                await runtime.service.callback(
                    state=parsed_state,
                    code=authorization_code,
                    correlation_id="rr01-replay",
                )

            async with sessions() as session:
                credential = (
                    await session.execute(
                        select(OAuthCredentialRecord).where(
                            OAuthCredentialRecord.marketplace == "mercadolivre",
                            OAuthCredentialRecord.account_id == account_id,
                        )
                    )
                ).scalar_one()
                assert credential.version == 1
                assert access.encode() not in credential.access_envelope
                assert refresh.encode() not in credential.refresh_envelope

                channel = (
                    await session.execute(
                        select(ChannelEventRecord).where(
                            ChannelEventRecord.correlation_id == "rr01-correlation"
                        )
                    )
                ).scalar_one()
                assert channel.operation == "/users/me"
                assert channel.status_code == 200
                assert channel.request_id == "rr01-integration-request"

                audit_rows = (
                    await session.execute(
                        select(OAuthAuditRecord).where(
                            OAuthAuditRecord.marketplace == "mercadolivre",
                            OAuthAuditRecord.action.in_(
                                ["real_read_transaction_start", "real_read_callback"]
                            ),
                        )
                    )
                ).scalars().all()
                serialized = repr(
                    [
                        (row.action, row.outcome, row.reason, row.metadata_json)
                        for row in audit_rows
                    ]
                )
                assert audit_rows
                for forbidden in (
                    secret,
                    access,
                    refresh,
                    authorization_code,
                    parsed_state,
                ):
                    assert forbidden not in serialized
        finally:
            await close_real_read_oauth_runtime(runtime)
            await engine.dispose()

    asyncio.run(scenario())
