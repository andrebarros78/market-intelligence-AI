from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from market_intelligence.marketplaces.mercadolivre.oauth.acceptance import run_synthetic_acceptance
from market_intelligence.marketplaces.mercadolivre.oauth.crypto import state_digest
from market_intelligence.marketplaces.mercadolivre.oauth.db_models import OAuthAuditRecord, OAuthCredentialRecord, OAuthOperationRecord
from market_intelligence.marketplaces.mercadolivre.oauth.runtime import build_synthetic_oauth_runtime
from market_intelligence.marketplaces.mercadolivre.oauth.settings import OAuthRuntimeSettings
from market_intelligence.marketplaces.mercadolivre.oauth.synthetic_client import SyntheticOAuthClient
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import OAuthStateRecord


@pytest.mark.postgres
def test_r11_oauth_synthetic_end_to_end_postgresql() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    async def scenario() -> None:
        engine = create_database_engine(url); sessions = create_session_factory(engine)
        now = datetime.now(UTC); suffix = uuid4().hex; account = f"acct-{suffix}"
        runtime = build_synthetic_oauth_runtime(sessions=sessions, encryption_key=b"k"*32, clock=lambda: now)
        try:
            readiness = await runtime.readiness()
            assert readiness.ready and readiness.database_ok and readiness.schema_ok
            external_down_runtime = build_synthetic_oauth_runtime(
                sessions=sessions, encryption_key=b"z"*32, clock=lambda: now,
                client=SyntheticOAuthClient(clock=lambda: now, fail_exchange=True, fail_refresh=True))
            assert (await external_down_runtime.readiness()).ready is True
            plan = await runtime.transactions.start(account_id=account); digest = state_digest(plan.state)
            async with sessions() as session:
                row = (await session.execute(select(OAuthStateRecord).where(OAuthStateRecord.state_hash==digest))).scalar_one()
                assert row.state_hash == digest and row.state_hash != plan.state
                assert plan.state.encode() not in (row.verifier_envelope or b"")
            version = await runtime.transactions.callback(account_id=account, state=plan.state, code="synthetic-code")
            assert version == 1
            with pytest.raises(PermissionError, match="oauth_callback_rejected"):
                await runtime.transactions.callback(account_id=account, state=plan.state, code="synthetic-code")
            moving_clock=[now]
            expiring = build_synthetic_oauth_runtime(sessions=sessions, encryption_key=b"e"*32,
                settings=OAuthRuntimeSettings(transaction_ttl_seconds=1), clock=lambda: moving_clock[0])
            expired_plan=await expiring.transactions.start(account_id=f"expired-{suffix}"); moving_clock[0]=now+timedelta(seconds=2)
            with pytest.raises(PermissionError, match="oauth_callback_rejected"):
                await expiring.transactions.callback(account_id=f"expired-{suffix}", state=expired_plan.state, code="synthetic-expired-code")
            failing_client=SyntheticOAuthClient(clock=lambda:now, fail_exchange=True)
            failing=build_synthetic_oauth_runtime(sessions=sessions,encryption_key=b"f"*32,clock=lambda:now,client=failing_client)
            failed_plan=await failing.transactions.start(account_id=f"failed-{suffix}")
            with pytest.raises(Exception):
                await failing.transactions.callback(account_id=f"failed-{suffix}",state=failed_plan.state,code="synthetic-secret-code")
            async with sessions() as session:
                credential=(await session.execute(select(OAuthCredentialRecord).where(OAuthCredentialRecord.account_id==account))).scalar_one()
                assert credential.version==1 and b"syn_at_" not in credential.access_envelope and b"syn_rt_" not in credential.refresh_envelope
            health=await runtime.health.get(account_id=account)
            assert health.status.value=="healthy" and not hasattr(health,"access_token") and not hasattr(health,"refresh_token")
            refresh_versions=await asyncio.gather(runtime.refresh.refresh(account_id=account),runtime.refresh.refresh(account_id=account),return_exceptions=True)
            successes=[v for v in refresh_versions if isinstance(v,int)]; failures=[v for v in refresh_versions if isinstance(v,Exception)]
            assert successes==[2] and len(failures)==1
            opkey=f"op-{suffix}"
            assert await runtime.operations.begin(operation="synthetic_refresh",idempotency_key=opkey) is True
            assert await runtime.operations.begin(operation="synthetic_refresh",idempotency_key=opkey) is False
            with pytest.raises(PermissionError): await runtime.operations.begin(operation="real_oauth",idempotency_key=f"real-{suffix}")
            with pytest.raises(PermissionError): await runtime.operations.begin(operation="marketplace_write",idempotency_key=f"write-{suffix}")
            result=await run_synthetic_acceptance(runtime,account_id=f"accept-{suffix}")
            assert result["replay_rejected"] and result["refresh_rotated"] and result["network_blocked"] and result["writes_blocked"] and result["ready"]
            async with sessions() as session:
                audit_rows=(await session.execute(select(OAuthAuditRecord).where(OAuthAuditRecord.marketplace=="mercadolivre"))).scalars().all()
                serialized=repr([(r.action,r.outcome,r.reason,r.metadata_json) for r in audit_rows])
                assert audit_rows and "syn_at_" not in serialized and "syn_rt_" not in serialized
                assert "synthetic-code" not in serialized and "synthetic-secret-code" not in serialized
                assert plan.state not in serialized and failed_plan.state not in serialized
                op_count=await session.scalar(select(func.count()).select_from(OAuthOperationRecord)); assert op_count and op_count>=1
        finally: await engine.dispose()
    asyncio.run(scenario())


@pytest.mark.postgres
def test_r11_refresh_failure_preserves_previous_version_and_readiness_detects_schema() -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not configured")
    async def scenario() -> None:
        engine=create_database_engine(url); sessions=create_session_factory(engine); now=datetime.now(UTC)
        account=f"failure-{uuid4().hex}"; client=SyntheticOAuthClient(clock=lambda:now)
        runtime=build_synthetic_oauth_runtime(sessions=sessions,encryption_key=b"q"*32,clock=lambda:now,client=client)
        try:
            plan=await runtime.transactions.start(account_id=account)
            await runtime.transactions.callback(account_id=account,state=plan.state,code="synthetic-code")
            client.fail_refresh=True
            with pytest.raises(Exception): await runtime.refresh.refresh(account_id=account)
            async with sessions() as session:
                credential=(await session.execute(select(OAuthCredentialRecord).where(OAuthCredentialRecord.account_id==account))).scalar_one()
                assert credential.version==1
            wrong=build_synthetic_oauth_runtime(sessions=sessions,encryption_key=b"w"*32,
                settings=OAuthRuntimeSettings(expected_schema_revision="wrong_revision"),clock=lambda:now)
            report=await wrong.readiness()
            assert report.ready is False and report.database_ok is True and report.schema_ok is False
            assert "schema_revision_mismatch" in report.reasons
        finally: await engine.dispose()
    asyncio.run(scenario())
