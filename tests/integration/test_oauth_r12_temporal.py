from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer

from market_intelligence.marketplaces.mercadolivre.oauth.runtime import build_synthetic_oauth_runtime
from market_intelligence.marketplaces.mercadolivre.oauth.types import SyntheticTokenSet
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.workflows.activities import OAuthActivities
from market_intelligence.workflows.names import WORKFLOW_OAUTH_REFRESH
from market_intelligence.workflows.oauth_temporal_workflow import SyntheticOAuthRefreshWorkflow
from market_intelligence.workflows.temporal_engine import TemporalWorkflowEngine
from market_intelligence.workflows.worker import build_temporal_worker

ACCESS_V1 = "history-must-not-contain-access-v1"
REFRESH_V1 = "history-must-not-contain-refresh-v1"
ACCESS_V2 = "history-must-not-contain-access-v2"
REFRESH_V2 = "history-must-not-contain-refresh-v2"
CALLBACK_CODE = "history-must-not-contain-callback-code"
REQUEST_KEY = "history-must-not-contain-original-request-key"


class KnownSecretSyntheticClient:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.exchange_calls = 0
        self.refresh_calls = 0

    async def exchange(self, *, code: str, verifier: str) -> SyntheticTokenSet:
        self.exchange_calls += 1
        assert code == CALLBACK_CODE
        assert verifier
        return SyntheticTokenSet(access_token=ACCESS_V1, refresh_token=REFRESH_V1,
                                 expires_at=self.now + timedelta(hours=1), scopes=("read",))

    async def refresh(self, *, refresh_token: str) -> SyntheticTokenSet:
        self.refresh_calls += 1
        assert refresh_token == REFRESH_V1
        return SyntheticTokenSet(access_token=ACCESS_V2, refresh_token=REFRESH_V2,
                                 expires_at=self.now + timedelta(hours=2), scopes=("read",))


@pytest.mark.temporal
@pytest.mark.postgres
def test_r12_temporal_refresh_is_durable_idempotent_and_history_contains_no_secrets() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        now = datetime.now(UTC); suffix = uuid4().hex
        account_id = f"oauth-temporal-{suffix}"; client = KnownSecretSyntheticClient(now)
        runtime = build_synthetic_oauth_runtime(sessions=sessions, encryption_key=b"r" * 32,
                                                clock=lambda: now, client=client)  # type: ignore[arg-type]
        try:
            plan = await runtime.transactions.start(account_id=account_id)
            assert await runtime.transactions.callback(account_id=account_id, state=plan.state,
                                                        code=CALLBACK_CODE) == 1
            async with await WorkflowEnvironment.start_time_skipping() as env:
                task_queue = f"mi-r12-oauth-{suffix}"
                worker = build_temporal_worker(env.client, task_queue=task_queue, sessions=sessions,
                                               adapters={}, oauth_runtime=runtime)
                async with worker:
                    engine = TemporalWorkflowEngine(env.client, task_queue=task_queue)
                    payload = {"account_id": account_id, "correlation_id": f"corr-{suffix}"}
                    first_id = await engine.start(WORKFLOW_OAUTH_REFRESH, payload,
                                                  idempotency_key=REQUEST_KEY)
                    second_id = await engine.start(WORKFLOW_OAUTH_REFRESH, payload,
                                                   idempotency_key=REQUEST_KEY)
                    assert first_id == second_id and REQUEST_KEY not in first_id
                    handle = env.client.get_workflow_handle(first_id, result_type=dict[str, int])
                    assert await handle.result() == {"credential_version": 2}
                    assert client.refresh_calls == 1

                    history = await handle.fetch_history()
                    raw_history = b"".join(event.SerializeToString() for event in history.events)
                    for value in [plan.state, CALLBACK_CODE, ACCESS_V1, REFRESH_V1,
                                  ACCESS_V2, REFRESH_V2, REQUEST_KEY]:
                        assert value.encode("utf-8") not in raw_history
                    await Replayer(workflows=[SyntheticOAuthRefreshWorkflow]).replay_workflow(history)

                    repeated = await OAuthActivities(runtime).refresh(
                        {"account_id": account_id, "idempotency_key": first_id})
                    assert repeated == {"credential_version": 2}
                    assert client.refresh_calls == 1
                    operation = await runtime.operations.get(idempotency_key=first_id)
                    assert operation is not None and operation.status == "completed"
                    assert operation.metadata == {
                        "account_id": account_id,
                        "base_version": 1,
                        "credential_version": 2,
                    }
        finally:
            await database.dispose()

    asyncio.run(scenario())


@pytest.mark.postgres
def test_r12_activity_recovers_after_refresh_commit_without_operation_completion_even_after_long_outage() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        moving_now = [datetime.now(UTC)]; suffix = uuid4().hex
        account_id = f"oauth-crash-{suffix}"; client = KnownSecretSyntheticClient(moving_now[0])
        runtime = build_synthetic_oauth_runtime(sessions=sessions, encryption_key=b"c" * 32,
                                                clock=lambda: moving_now[0], client=client)  # type: ignore[arg-type]
        operation_key = f"mi-crash-recovery-{suffix}"
        try:
            plan = await runtime.transactions.start(account_id=account_id)
            assert await runtime.transactions.callback(account_id=account_id, state=plan.state,
                                                        code=CALLBACK_CODE) == 1
            assert await runtime.operations.begin(
                operation="synthetic_refresh_temporal",
                idempotency_key=operation_key,
                metadata={"account_id": account_id, "base_version": 1},
            ) is True
            assert await runtime.refresh.refresh(account_id=account_id) == 2
            assert client.refresh_calls == 1

            # Simulates a worker disappearing after credential commit but before operation.complete().
            moving_now[0] = moving_now[0] + timedelta(days=1)
            recovered = await OAuthActivities(runtime).refresh(
                {"account_id": account_id, "idempotency_key": operation_key})
            assert recovered == {"credential_version": 2}
            assert client.refresh_calls == 1
            operation = await runtime.operations.get(idempotency_key=operation_key)
            assert operation is not None and operation.status == "completed"
            assert operation.metadata["credential_version"] == 2
        finally:
            await database.dispose()

    asyncio.run(scenario())
