import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import AlertRecord
from market_intelligence.persistence.postgresql import PostgresAlertRepository

HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


@pytest.mark.postgres
def test_automatic_control_comparison_is_persisted_and_deduplicated() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("database not configured")

    async def run() -> None:
        db = create_database_engine(url)
        sessions = create_session_factory(db)
        observed_at = datetime.now(UTC)
        entity_id = f"R112-{uuid4().hex}"
        candidates = [
            {
                "entity_id": name,
                "metrics": {"visits": current},
                "history": {"visits": HISTORY},
            }
            for name, current in [("C1", 100), ("C2", 101), ("C3", 99)]
        ]
        finding = build_default_radar().evaluate(
            RadarObservation(
                entity_id=entity_id,
                observed_at=observed_at,
                metrics={"visits": 94},
                history={"visits": HISTORY},
                context={"control_candidates": candidates},
            )
        )
        alert = alert_from_finding(
            finding=finding,
            marketplace="mercadolivre",
            entity_type="item",
            observed_at=observed_at,
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
            assert "relational-control@2.0.0" in (row.detector_version or "")
            assert row.control_comparison is not None
            assert row.control_comparison["selection"]["mode"] == "automatic"
            assert row.control_comparison["selection"]["selection_uses_current_values"] is False
        finally:
            await db.dispose()

    asyncio.run(run())
