from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client
from temporalio.worker import Worker

from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.service import RadarService
from market_intelligence.marketplaces.base import MarketplaceAdapter
from market_intelligence.marketplaces.mercadolivre.oauth.runtime import SyntheticOAuthRuntime
from market_intelligence.persistence.postgresql import (
    PostgresAlertRepository,
    PostgresChannelEventRepository,
    PostgresEntityRepository,
    PostgresRawEventRepository,
    PostgresSnapshotRepository,
)
from market_intelligence.workflows.activities import (
    MarketplaceActivities,
    OAuthActivities,
    PersistenceActivities,
    RadarActivities,
)
from market_intelligence.workflows.oauth_temporal_workflow import SyntheticOAuthRefreshWorkflow
from market_intelligence.workflows.temporal_workflow import MarketIntelligenceIngestionWorkflow


def build_temporal_worker(
    client: Client,
    *,
    task_queue: str,
    sessions: async_sessionmaker[AsyncSession],
    adapters: Mapping[str, MarketplaceAdapter],
    radar: RadarService | None = None,
    oauth_runtime: SyntheticOAuthRuntime | None = None,
) -> Worker:
    channel_events = PostgresChannelEventRepository(sessions)
    persistence = PersistenceActivities(
        PostgresRawEventRepository(sessions),
        channel_events,
        PostgresEntityRepository(sessions),
        PostgresSnapshotRepository(sessions),
        PostgresAlertRepository(sessions),
    )
    marketplace = MarketplaceActivities(adapters, channel_events=channel_events)
    radar_activities = RadarActivities(radar or build_default_radar())
    workflows: list[type] = [MarketIntelligenceIngestionWorkflow]
    activities: list = [
        persistence.persist_channel_event,
        persistence.persist_raw_event,
        persistence.persist_resource_snapshot,
        persistence.persist_radar_alert,
        marketplace.fetch_resource,
        radar_activities.evaluate,
    ]
    if oauth_runtime is not None:
        oauth = OAuthActivities(oauth_runtime)
        workflows.append(SyntheticOAuthRefreshWorkflow)
        activities.append(oauth.refresh)

    return Worker(
        client,
        task_queue=task_queue,
        workflows=workflows,
        activities=activities,
    )
