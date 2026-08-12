from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from market_intelligence.core.contracts import EntityRef
from market_intelligence.ingestion.events import RawEvent
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.service import RadarService
from market_intelligence.marketplaces.base import MarketplaceAdapter
from market_intelligence.persistence.contracts import (
    EntityRepository,
    RawEventRepository,
    SnapshotRepository,
)
from market_intelligence.workflows.names import (
    ACTIVITY_EVALUATE_RADAR,
    ACTIVITY_FETCH_RESOURCE,
    ACTIVITY_PERSIST_RAW_EVENT,
    ACTIVITY_PERSIST_RESOURCE,
)


class PersistenceActivities:
    def __init__(
        self,
        raw_events: RawEventRepository,
        entities: EntityRepository,
        snapshots: SnapshotRepository,
    ) -> None:
        self._raw_events = raw_events
        self._entities = entities
        self._snapshots = snapshots

    @activity.defn(name=ACTIVITY_PERSIST_RAW_EVENT)
    async def persist_raw_event(self, payload: dict[str, Any]) -> bool:
        try:
            event = RawEvent.model_validate(payload)
        except Exception as exc:
            raise ApplicationError(
                "invalid raw event payload",
                non_retryable=True,
            ) from exc
        return await self._raw_events.append_if_new(event)

    @activity.defn(name=ACTIVITY_PERSIST_RESOURCE)
    async def persist_resource_snapshot(self, payload: dict[str, Any]) -> bool:
        try:
            entity = EntityRef(
                marketplace=str(payload["marketplace"]),
                entity_type=str(payload["entity_type"]),
                entity_id=str(payload["entity_id"]),
            )
            resource_payload = payload["payload"]
            if not isinstance(resource_payload, dict):
                raise TypeError("payload must be an object")
            observed_at = datetime.fromisoformat(str(payload["observed_at"]))
        except Exception as exc:
            raise ApplicationError(
                "invalid resource snapshot payload",
                non_retryable=True,
            ) from exc

        await self._entities.upsert(entity, resource_payload, observed_at)
        return await self._snapshots.append_if_changed(entity, resource_payload, observed_at)


class MarketplaceActivities:
    def __init__(self, adapters: Mapping[str, MarketplaceAdapter]) -> None:
        self._adapters = dict(adapters)

    @activity.defn(name=ACTIVITY_FETCH_RESOURCE)
    async def fetch_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        marketplace = str(payload.get("marketplace") or "")
        resource = str(payload.get("resource") or "")
        adapter = self._adapters.get(marketplace)
        if adapter is None:
            raise ApplicationError(
                f"marketplace adapter not registered: {marketplace}",
                non_retryable=True,
            )
        if not resource:
            raise ApplicationError("resource is required", non_retryable=True)
        result = await adapter.fetch_resource(resource)
        if not isinstance(result, dict):
            raise ApplicationError(
                "marketplace resource response must be an object",
                non_retryable=True,
            )
        return result


class RadarActivities:
    def __init__(self, radar: RadarService) -> None:
        self._radar = radar

    @activity.defn(name=ACTIVITY_EVALUATE_RADAR)
    async def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            observation = RadarObservation.model_validate(payload)
        except Exception as exc:
            raise ApplicationError(
                "invalid radar observation",
                non_retryable=True,
            ) from exc
        return self._radar.evaluate(observation).model_dump(mode="json")
