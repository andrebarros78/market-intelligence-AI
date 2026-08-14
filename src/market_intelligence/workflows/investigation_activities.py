from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.exceptions import ApplicationError

from market_intelligence.intelligence.radar.investigation import ProgressiveInvestigationEngine
from market_intelligence.intelligence.radar.models import RadarFinding, RadarObservation
from market_intelligence.persistence.investigations import PostgresInvestigationRepository
from market_intelligence.workflows.names import ACTIVITY_ADVANCE_INVESTIGATION


class InvestigationActivities:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        engine: ProgressiveInvestigationEngine | None = None,
    ) -> None:
        self._repository = PostgresInvestigationRepository(sessions, engine=engine)

    @activity.defn(name=ACTIVITY_ADVANCE_INVESTIGATION)
    async def advance(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            finding = RadarFinding.model_validate(payload["finding"])
            observation = RadarObservation.model_validate(payload["observation"])
            marketplace = str(payload["marketplace"])
            entity_type = str(payload["entity_type"])
            if not marketplace or not entity_type:
                raise ValueError("marketplace and entity_type are required")
            if finding.entity_id != observation.entity_id:
                raise ValueError("finding and observation entity_id must match")
        except Exception as exc:
            raise ApplicationError(
                "invalid progressive investigation payload",
                non_retryable=True,
            ) from exc
        return await self._repository.advance(
            marketplace=marketplace,
            entity_type=entity_type,
            finding=finding,
            observation=observation,
        )
