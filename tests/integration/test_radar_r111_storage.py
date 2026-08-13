import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import AlertRecord
from market_intelligence.persistence.postgresql import PostgresAlertRepository


@pytest.mark.postgres
def test_seasonal_alert_is_persisted_and_deduplicated() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        db = create_database_engine(url)
        sessions = create_session_factory(db)
        current = datetime(2026, 8, 16, 12, tzinfo=UTC)
        start = current - timedelta(days=56)
        points = []
        for offset in range(56):
            timestamp = start + timedelta(days=offset)
            value = 60.0 if timestamp.weekday() == 6 else 100.0
            points.append({"timestamp": timestamp, "value": value})
        entity_id = f"R111-{uuid4().hex}"
        finding = build_default_radar().evaluate(
            RadarObservation(
                entity_id=entity_id,
                observed_at=current,
                metrics={"visits": 20.0},
                timestamped_history={"visits": points},
            )
        )
        alert = alert_from_finding(
            finding=finding,
            marketplace="mercadolivre",
            entity_type="item",
            observed_at=current,
            context={},
        )
        assert alert is not None
        repo = PostgresAlertRepository(sessions)
        try:
            assert await repo.save_if_new(alert) is True
            assert await repo.save_if_new(alert) is False
            async with sessions() as session:
                row = (
                    await session.execute(
                        select(AlertRecord).where(AlertRecord.entity_id == entity_id)
                    )
                ).scalar_one()
                assert "seasonality@1.0.0" in (row.detector_version or "")
        finally:
            await db.dispose()

    asyncio.run(run())
