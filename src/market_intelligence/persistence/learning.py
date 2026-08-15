from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.intelligence.radar.sovereign_learning import (
    FeedbackTarget,
    LearningPromotionDecision,
    SovereignLearningDecision,
)


class PostgresLearningRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def persist_episode(self, decision: SovereignLearningDecision) -> UUID:
        episode_id = uuid4()
        payload = decision.model_dump(mode="json")
        async with self._sessions() as session:
            result = await session.execute(
                text(
                    """
                    INSERT INTO learning_episodes (
                        id, dedupe_key, marketplace, entity_type, entity_id, state,
                        confidence, observation_count, official_resource_fetched,
                        causal_claim, evidence_summary, hypotheses, feedback_targets,
                        watchdogs, reason
                    ) VALUES (
                        :id, :dedupe_key, :marketplace, :entity_type, :entity_id, :state,
                        :confidence, :observation_count, :official_resource_fetched,
                        :causal_claim, CAST(:evidence_summary AS jsonb), CAST(:hypotheses AS jsonb),
                        CAST(:feedback_targets AS jsonb), CAST(:watchdogs AS jsonb), :reason
                    )
                    ON CONFLICT (dedupe_key) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        observation_count = GREATEST(learning_episodes.observation_count, EXCLUDED.observation_count),
                        official_resource_fetched = learning_episodes.official_resource_fetched OR EXCLUDED.official_resource_fetched,
                        state = EXCLUDED.state,
                        evidence_summary = EXCLUDED.evidence_summary,
                        hypotheses = EXCLUDED.hypotheses,
                        feedback_targets = EXCLUDED.feedback_targets,
                        watchdogs = EXCLUDED.watchdogs,
                        reason = EXCLUDED.reason,
                        updated_at = now()
                    RETURNING id
                    """
                ),
                {
                    "id": episode_id,
                    "dedupe_key": decision.dedupe_key,
                    "marketplace": decision.marketplace,
                    "entity_type": decision.entity_type,
                    "entity_id": decision.entity_id,
                    "state": decision.state.value,
                    "confidence": decision.confidence,
                    "observation_count": decision.observation_count,
                    "official_resource_fetched": decision.official_resource_fetched,
                    "causal_claim": decision.causal_claim,
                    "evidence_summary": __import__("json").dumps(payload["evidence_summary"], sort_keys=True),
                    "hypotheses": __import__("json").dumps(payload["hypotheses"], sort_keys=True),
                    "feedback_targets": __import__("json").dumps(payload["feedback_targets"], sort_keys=True),
                    "watchdogs": __import__("json").dumps(payload["watchdogs"], sort_keys=True),
                    "reason": decision.reason,
                },
            )
            persisted_id = result.scalar_one()
            await session.commit()
        return persisted_id

    async def ensure_promotion_candidates(
        self,
        *,
        episode_id: UUID,
        decision: SovereignLearningDecision,
    ) -> tuple[str, ...]:
        created: list[str] = []
        async with self._sessions() as session:
            for target in decision.feedback_targets:
                if target is FeedbackTarget.KNOWLEDGE_MEMORY:
                    continue
                await session.execute(
                    text(
                        """
                        INSERT INTO learning_promotions (
                            id, episode_id, target, status, candidate_payload
                        ) VALUES (
                            :id, :episode_id, :target, 'candidate', CAST(:candidate_payload AS jsonb)
                        )
                        ON CONFLICT (episode_id, target) DO NOTHING
                        """
                    ),
                    {
                        "id": uuid4(),
                        "episode_id": episode_id,
                        "target": target.value,
                        "candidate_payload": __import__("json").dumps(
                            {
                                "marketplace": decision.marketplace,
                                "entity_type": decision.entity_type,
                                "entity_id": decision.entity_id,
                                "confidence": decision.confidence,
                                "observation_count": decision.observation_count,
                                "reason": decision.reason,
                            },
                            sort_keys=True,
                        ),
                    },
                )
                created.append(target.value)
            await session.commit()
        return tuple(created)

    async def decide_promotion(
        self,
        *,
        episode_id: UUID,
        decision: LearningPromotionDecision,
    ) -> None:
        async with self._sessions() as session:
            result = await session.execute(
                text(
                    """
                    UPDATE learning_promotions
                    SET status = :status,
                        regression_passed = :regression_passed,
                        independent_verifier_passed = :independent_verifier_passed,
                        watchdog_passed = :watchdog_passed,
                        decided_at = :decided_at
                    WHERE episode_id = :episode_id AND target = :target
                    """
                ),
                {
                    "status": "approved" if decision.approved else "rejected",
                    "regression_passed": decision.regression_passed,
                    "independent_verifier_passed": decision.independent_verifier_passed,
                    "watchdog_passed": decision.watchdog_passed,
                    "decided_at": datetime.now(UTC),
                    "episode_id": episode_id,
                    "target": decision.target.value,
                },
            )
            if result.rowcount != 1:
                raise KeyError("learning_promotion_candidate_not_found")
            await session.commit()

    async def save_checkpoint(
        self,
        *,
        mission_id: str,
        checkpoint: dict[str, Any],
        processed_count: int,
        marketplace_writes: int,
    ) -> None:
        if marketplace_writes != 0:
            raise RuntimeError("learning_checkpoint_contains_marketplace_write")
        async with self._sessions() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO learning_checkpoints (
                        mission_id, checkpoint_json, processed_count, marketplace_writes
                    ) VALUES (
                        :mission_id, CAST(:checkpoint_json AS jsonb), :processed_count, 0
                    )
                    ON CONFLICT (mission_id) DO UPDATE SET
                        checkpoint_json = EXCLUDED.checkpoint_json,
                        processed_count = GREATEST(learning_checkpoints.processed_count, EXCLUDED.processed_count),
                        marketplace_writes = 0,
                        updated_at = now()
                    """
                ),
                {
                    "mission_id": mission_id,
                    "checkpoint_json": __import__("json").dumps(checkpoint, sort_keys=True),
                    "processed_count": int(processed_count),
                },
            )
            await session.commit()

    async def load_checkpoint(self, mission_id: str) -> dict[str, Any] | None:
        async with self._sessions() as session:
            result = await session.execute(
                text(
                    """
                    SELECT checkpoint_json, processed_count, marketplace_writes
                    FROM learning_checkpoints
                    WHERE mission_id = :mission_id
                    """
                ),
                {"mission_id": mission_id},
            )
            row = result.mappings().one_or_none()
        if row is None:
            return None
        if int(row["marketplace_writes"]) != 0:
            raise RuntimeError("learning_checkpoint_contains_marketplace_write")
        return {
            "checkpoint": dict(row["checkpoint_json"]),
            "processed_count": int(row["processed_count"]),
            "marketplace_writes": 0,
        }
