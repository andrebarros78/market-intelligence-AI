from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from market_intelligence.intelligence.sovereign.core import SovereignIntelligenceCore
from market_intelligence.intelligence.sovereign.models import SignalEnvelope
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.sovereign_intelligence import PostgresSovereignIntelligenceRepository


def _signal(signal_id: str, *, seconds: int = 0) -> SignalEnvelope:
    return SignalEnvelope(
        signal_id=signal_id,
        marketplace="mercadolivre",
        entity_type="item",
        entity_id="MLB-SOVEREIGN-CORE-TEST",
        kind="catalog_suggestion",
        source="integration_test_official_get",
        observed_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC) + timedelta(seconds=seconds),
        payload={"price": 100.0, "available_quantity": 10},
        provenance={"endpoint": "/test/catalog_suggestion", "method": "GET"},
        official_resource_fetched=True,
        confidence=0.90,
    )


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_sovereign_core_persists_intelligence_exposure_audit_and_zero_write_checkpoint() -> None:
    database_url = (os.getenv("TEST_DATABASE_URL") or "").strip()
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    try:
        core = SovereignIntelligenceCore()
        report = core.process(
            _signal("core-persistence-current"),
            history=(
                _signal("core-persistence-h1", seconds=-120),
                _signal("core-persistence-h2", seconds=-60),
            ),
            investigation={
                "finding_hash": "b" * 64,
                "status_after": "confirmed",
                "confidence_after": 0.91,
                "observation_count": 3,
                "evidence_summary": {"integration": True},
                "hypotheses": [],
                "causal_claim": False,
            },
        )
        repo = PostgresSovereignIntelligenceRepository(sessions)
        await repo.persist_report(report)
        await repo.save_checkpoint(
            mission_id="sovereign-core-integration-test",
            cursor={"signal_id": report.signal.signal_id},
            processed_count=1,
            marketplace_writes=0,
        )

        async with sessions() as session:
            intelligence_count = int((await session.execute(text("SELECT count(*) FROM sovereign_intelligence WHERE entity_id='MLB-SOVEREIGN-CORE-TEST'"))).scalar_one())
            exposure_count = int((await session.execute(text("SELECT count(*) FROM exposure_map WHERE marketplace='mercadolivre' AND data_point='catalog_suggestion'"))).scalar_one())
            audit_count = int((await session.execute(text("SELECT count(*) FROM cognitive_audits WHERE signal_id='core-persistence-current'"))).scalar_one())
            writes = int((await session.execute(text("SELECT marketplace_writes FROM sovereign_core_checkpoints WHERE mission_id='sovereign-core-integration-test'"))).scalar_one())

        assert intelligence_count >= 1
        assert exposure_count >= 1
        assert audit_count >= 1
        assert writes == 0
    finally:
        await engine.dispose()
