from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client
from temporalio.worker import Worker

from market_intelligence.intelligence.radar.detectors import KnownRuleDetector, RobustZScoreDetector
from market_intelligence.intelligence.radar.service import RadarService
from market_intelligence.marketplaces.base import MarketplaceAdapter
from market_intelligence.persistence.postgresql import (
    PostgresEntityRepository,
    PostgresRawEventRepository,
    PostgresSnapshotRepository,
)
from market_intelligence.workflows.activities import (
    MarketplaceActivities,
    PersistenceActivities,
    RadarActivities,
)
from market_intelligence.workflows.temporal_workflow import MarketIntelligenceIngestionWorkflow


def build_temporal_worker(
    client: Client,
    *,
    task_queue: str,
    sessions: async_sessionmaker[AsyncSession],
    adapters: Mapping[str, MarketplaceAdapter],
    radar: RadarService | None = None,
) -> Worker:
    persistence = PersistenceActivities(
        PostgresRawEventRepository(sessions),
        PostgresEntityRepository(sessions),
        PostgresSnapshotRepository(sessions),
    )
    marketplace = MarketplaceActivities(adapters)
    radar_activities = RadarActivities(
        radar or RadarService([KnownRuleDetector(), RobustZScoreDetector()])
    )

    return Worker(
        client,
        task_queue=task_queue,
        workflows=[MarketIntelligenceIngestionWorkflow],
        activities=[
            persistence.persist_raw_event,
            persistence.persist_resource_snapshot,
            marketplace.fetch_resource,
            radar_activities.evaluate,
        ],
    )
