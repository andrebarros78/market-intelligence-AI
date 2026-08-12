from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from market_intelligence.core.contracts import Alert, EntityRef, Evidence, EvidenceLevel, Severity
from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import AlertRecord, EvidenceRecord
from market_intelligence.persistence.postgresql import (
    PostgresAlertRepository,
    PostgresEntityRepository,
    PostgresOAuthStateRepository,
    PostgresRawEventRepository,
    PostgresSnapshotRepository,
    database_healthcheck,
)


@pytest.mark.postgres
def test_postgres_repositories_and_atomic_oauth_consumption() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        engine = create_database_engine(url)
        sessions = create_session_factory(engine)
        suffix = uuid4().hex
        now = datetime.now(UTC)
        entity = EntityRef(marketplace="mercadolivre", entity_type="listing", entity_id=f"MLB-{suffix}")

        try:
            assert await database_healthcheck(sessions) is True

            raw_repo = PostgresRawEventRepository(sessions)
            event = build_raw_event(
                source="mercadolivre",
                event_type="items",
                external_id=f"notification-{suffix}",
                resource=f"/items/{entity.entity_id}",
                occurred_at=now,
                received_at=now,
                payload={"id": entity.entity_id, "status": "active"},
            )
            assert await raw_repo.append_if_new(event) is True
            assert await raw_repo.append_if_new(event) is False

            entity_repo = PostgresEntityRepository(sessions)
            await entity_repo.upsert(entity, {"status": "active"}, now)
            await entity_repo.upsert(entity, {"status": "paused"}, now + timedelta(seconds=1))
            stored = await entity_repo.get(entity)
            assert stored is not None
            assert stored.current_payload["status"] == "paused"

            snapshot_repo = PostgresSnapshotRepository(sessions)
            assert await snapshot_repo.append_if_changed(entity, {"status": "paused"}, now) is True
            assert await snapshot_repo.append_if_changed(entity, {"status": "paused"}, now + timedelta(seconds=1)) is False
            assert await snapshot_repo.append_if_changed(entity, {"status": "closed"}, now + timedelta(seconds=2)) is True

            oauth_repo = PostgresOAuthStateRepository(sessions)
            state_hash = hashlib.sha256(f"synthetic-{suffix}".encode()).hexdigest()
            await oauth_repo.create(
                marketplace="mercadolivre",
                state_hash=state_hash,
                expires_at=now + timedelta(minutes=10),
                metadata={"test": True},
                synthetic=True,
            )
            assert await oauth_repo.consume(state_hash=state_hash, consumed_at=now + timedelta(seconds=1)) is True
            assert await oauth_repo.consume(state_hash=state_hash, consumed_at=now + timedelta(seconds=2)) is False

            alert_repo = PostgresAlertRepository(sessions)
            await alert_repo.save(
                Alert(
                    entity=entity,
                    observed_change="status changed unexpectedly",
                    evidence=[
                        Evidence(
                            level=EvidenceLevel.FACT,
                            statement="listing status changed from active to paused",
                            source="synthetic-test",
                            observed_at=now,
                        )
                    ],
                    severity=Severity.MEDIUM,
                    confidence=0.9,
                )
            )
            async with sessions() as session:
                alert_count = await session.scalar(select(func.count()).select_from(AlertRecord))
                evidence_count = await session.scalar(select(func.count()).select_from(EvidenceRecord))
                assert alert_count is not None and alert_count >= 1
                assert evidence_count is not None and evidence_count >= 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())
