from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from market_intelligence.marketplaces.mercadolivre.oauth.db_models import (
    OAuthAuditRecord,
    OAuthCredentialRecord,
)
from market_intelligence.marketplaces.mercadolivre.oauth.runtime import (
    build_synthetic_oauth_runtime,
)
from market_intelligence.persistence.database import (
    create_database_engine,
    create_session_factory,
)


@pytest.mark.postgres
def test_r11_callback_is_bound_to_originating_account_and_mismatch_is_burned() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        engine = create_database_engine(url)
        sessions = create_session_factory(engine)
        now = datetime.now(UTC)
        suffix = uuid4().hex
        bound_account = f"bound-{suffix}"
        wrong_account = f"wrong-{suffix}"
        runtime = build_synthetic_oauth_runtime(
            sessions=sessions,
            encryption_key=b"b" * 32,
            clock=lambda: now,
        )
        try:
            plan = await runtime.transactions.start(account_id=bound_account)
            with pytest.raises(PermissionError, match="oauth_callback_rejected"):
                await runtime.transactions.callback(
                    account_id=wrong_account,
                    state=plan.state,
                    code="synthetic-code-never-log",
                )

            # The mismatched attempt consumes the one-time state: fail closed.
            with pytest.raises(PermissionError, match="oauth_callback_rejected"):
                await runtime.transactions.callback(
                    account_id=bound_account,
                    state=plan.state,
                    code="synthetic-code-never-log",
                )

            async with sessions() as session:
                credentials = (
                    await session.execute(
                        select(OAuthCredentialRecord).where(
                            OAuthCredentialRecord.account_id.in_(
                                [bound_account, wrong_account]
                            )
                        )
                    )
                ).scalars().all()
                assert credentials == []

                audits = (
                    await session.execute(
                        select(OAuthAuditRecord).where(
                            OAuthAuditRecord.marketplace == "mercadolivre",
                            OAuthAuditRecord.metadata_json["account_id"].as_string()
                            == wrong_account,
                        )
                    )
                ).scalars().all()
                assert any(row.reason == "account_binding_mismatch" for row in audits)
                serialized = repr(
                    [(row.action, row.outcome, row.reason, row.metadata_json) for row in audits]
                )
                assert plan.state not in serialized
                assert "synthetic-code-never-log" not in serialized
        finally:
            await engine.dispose()

    asyncio.run(scenario())
