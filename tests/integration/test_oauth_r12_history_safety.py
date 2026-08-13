from __future__ import annotations

import base64
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from temporalio.testing import WorkflowEnvironment

from market_intelligence.marketplaces.mercadolivre.oauth.crypto import state_digest
from market_intelligence.marketplaces.mercadolivre.oauth.db_models import OAuthCredentialRecord
from market_intelligence.marketplaces.mercadolivre.oauth.runtime import build_synthetic_oauth_runtime
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import OAuthStateRecord
from market_intelligence.workflows.names import WORKFLOW_OAUTH_REFRESH
from market_intelligence.workflows.temporal_engine import TemporalWorkflowEngine
from market_intelligence.workflows.worker import build_temporal_worker


@pytest.mark.temporal
@pytest.mark.postgres
def test_r12_temporal_history_excludes_all_oauth_material() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        now = datetime.now(UTC)
        account_id = f"history-safe-{uuid4().hex}"
        request_key = f"request-safe-{uuid4().hex}"
        callback_code = "synthetic-history-code"
        runtime = build_synthetic_oauth_runtime(
            sessions=sessions, encryption_key=b"h" * 32, clock=lambda: now
        )
        try:
            plan = await runtime.transactions.start(account_id=account_id)
            digest = state_digest(plan.state)
            async with sessions() as session:
                state_row = (await session.execute(
                    select(OAuthStateRecord).where(OAuthStateRecord.state_hash == digest)
                )).scalar_one()
                verifier_box = bytes(state_row.verifier_envelope)
            verifier = runtime.transactions.crypto.open(
                verifier_box, context=f"oauth-state:{digest}"
            )

            assert await runtime.transactions.callback(
                account_id=account_id, state=plan.state, code=callback_code
            ) == 1
            async with sessions() as session:
                before = (await session.execute(
                    select(OAuthCredentialRecord).where(
                        OAuthCredentialRecord.account_id == account_id
                    )
                )).scalar_one()
                boxes_before = [bytes(before.access_envelope), bytes(before.refresh_envelope)]
                values_before = [
                    runtime.transactions.crypto.open(
                        boxes_before[0], context=f"oauth-access:mercadolivre:{account_id}"
                    ),
                    runtime.transactions.crypto.open(
                        boxes_before[1], context=f"oauth-refresh:mercadolivre:{account_id}"
                    ),
                ]

            async with await WorkflowEnvironment.start_time_skipping() as env:
                queue = f"history-safe-{uuid4().hex}"
                worker = build_temporal_worker(
                    env.client, task_queue=queue, sessions=sessions,
                    adapters={}, oauth_runtime=runtime
                )
                async with worker:
                    engine = TemporalWorkflowEngine(env.client, task_queue=queue)
                    workflow_id = await engine.start(
                        WORKFLOW_OAUTH_REFRESH,
                        {"account_id": account_id},
                        idempotency_key=request_key,
                    )
                    handle = env.client.get_workflow_handle(
                        workflow_id, result_type=dict[str, int]
                    )
                    assert await handle.result() == {"credential_version": 2}
                    async with sessions() as session:
                        after = (await session.execute(
                            select(OAuthCredentialRecord).where(
                                OAuthCredentialRecord.account_id == account_id
                            )
                        )).scalar_one()
                        boxes_after = [bytes(after.access_envelope), bytes(after.refresh_envelope)]
                        values_after = [
                            runtime.transactions.crypto.open(
                                boxes_after[0], context=f"oauth-access:mercadolivre:{account_id}"
                            ),
                            runtime.transactions.crypto.open(
                                boxes_after[1], context=f"oauth-refresh:mercadolivre:{account_id}"
                            ),
                        ]

                    history = await handle.fetch_history()
                    raw = b"".join(event.SerializeToString() for event in history.events)
                    for value in [
                        plan.state, verifier, callback_code, request_key,
                        *values_before, *values_after,
                    ]:
                        assert value.encode() not in raw
                    for box in [verifier_box, *boxes_before, *boxes_after]:
                        assert box not in raw
                        assert base64.b64encode(box) not in raw
                        assert box.hex().encode() not in raw
        finally:
            await database.dispose()

    import asyncio
    asyncio.run(scenario())
