from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.exceptions import ApplicationError

from market_intelligence.intelligence.radar.sovereign_learning import SovereignLearningEngine
from market_intelligence.persistence.learning import PostgresLearningRepository
from market_intelligence.workflows.names import ACTIVITY_PROCESS_SOVEREIGN_LEARNING


class SovereignLearningActivities:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        engine: SovereignLearningEngine | None = None,
    ) -> None:
        self._repository = PostgresLearningRepository(sessions)
        self._engine = engine or SovereignLearningEngine()

    @activity.defn(name=ACTIVITY_PROCESS_SOVEREIGN_LEARNING)
    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            marketplace = str(payload["marketplace"])
            entity_type = str(payload["entity_type"])
            entity_id = str(payload["entity_id"])
            finding = dict(payload["finding"])
            investigation_raw = payload.get("investigation")
            investigation = dict(investigation_raw) if isinstance(investigation_raw, dict) else None
            official_resource_fetched = bool(payload.get("official_resource_fetched", False))
            marketplace_read_only = bool(payload.get("marketplace_read_only", False))
            marketplace_writes = int(payload.get("marketplace_writes", 0))
        except Exception as exc:
            raise ApplicationError(
                "invalid sovereign learning payload",
                non_retryable=True,
            ) from exc

        try:
            decision = self._engine.evaluate(
                marketplace=marketplace,
                entity_type=entity_type,
                entity_id=entity_id,
                finding=finding,
                investigation=investigation,
                official_resource_fetched=official_resource_fetched,
                marketplace_read_only=marketplace_read_only,
                marketplace_writes=marketplace_writes,
            )
        except RuntimeError as exc:
            raise ApplicationError(str(exc), non_retryable=True) from exc

        episode_id = await self._repository.persist_episode(decision)
        candidates = await self._repository.ensure_promotion_candidates(
            episode_id=episode_id,
            decision=decision,
        )
        return {
            "episode_id": str(episode_id),
            "state": decision.state.value,
            "confidence": decision.confidence,
            "observation_count": decision.observation_count,
            "feedback_targets": [item.value for item in decision.feedback_targets],
            "promotion_candidates": list(candidates),
            "watchdogs": decision.watchdogs,
            "reason": decision.reason,
            "marketplace_writes": 0,
            "engine_version": self._engine.version,
        }
