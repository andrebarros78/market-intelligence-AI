from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text

from market_intelligence.intelligence.radar.sovereign_learning import SovereignLearningEngine
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.learning import PostgresLearningRepository


@pytest.mark.postgres
def test_learning_episode_evolves_idempotently_and_checkpoint_fails_closed() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        database = create_database_engine(database_url)
        sessions = create_session_factory(database)
        repository = PostgresLearningRepository(sessions)
        engine = SovereignLearningEngine()
        base = {
            "marketplace": "mercadolivre",
            "entity_type": "listing",
            "entity_id": "MLB-PERSISTENCE-PROOF",
            "finding": {"score": 0.91, "anomalous": True},
            "official_resource_fetched": True,
            "marketplace_read_only": True,
            "marketplace_writes": 0,
        }
        early = engine.evaluate(
            **base,
            investigation={
                "finding_hash": "b" * 64,
                "status_after": "monitoring",
                "confidence_after": 0.7,
                "observation_count": 1,
                "causal_claim": False,
                "evidence_summary": {},
                "hypotheses": [],
            },
        )
        confirmed = engine.evaluate(
            **base,
            investigation={
                "finding_hash": "b" * 64,
                "status_after": "confirmed",
                "confidence_after": 0.91,
                "observation_count": 3,
                "causal_claim": False,
                "evidence_summary": {"official": True},
                "hypotheses": [{"key": "h1", "status": "supported"}],
            },
        )
        assert early.dedupe_key == confirmed.dedupe_key

        try:
            first_id = await repository.persist_episode(early)
            second_id = await repository.persist_episode(confirmed)
            assert first_id == second_id
            candidates = await repository.ensure_promotion_candidates(
                episode_id=second_id,
                decision=confirmed,
            )
            assert set(candidates) == {"radar_rule_candidate", "skill_update_candidate"}

            async with sessions() as session:
                count = (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM learning_episodes WHERE dedupe_key = :key"
                        ),
                        {"key": confirmed.dedupe_key},
                    )
                ).scalar_one()
                state = (
                    await session.execute(
                        text(
                            "SELECT state FROM learning_episodes WHERE dedupe_key = :key"
                        ),
                        {"key": confirmed.dedupe_key},
                    )
                ).scalar_one()
            assert count == 1
            assert state == "validated_fact"

            await repository.save_checkpoint(
                mission_id="mcl-integration-proof",
                checkpoint={"last_dedupe_key": confirmed.dedupe_key},
                processed_count=1,
                marketplace_writes=0,
            )
            restored = await repository.load_checkpoint("mcl-integration-proof")
            assert restored is not None
            assert restored["processed_count"] == 1
            assert restored["marketplace_writes"] == 0

            with pytest.raises(RuntimeError, match="checkpoint_contains_marketplace_write"):
                await repository.save_checkpoint(
                    mission_id="mcl-invalid-write",
                    checkpoint={},
                    processed_count=1,
                    marketplace_writes=1,
                )
        finally:
            await database.dispose()

    asyncio.run(scenario())
