from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from market_intelligence.core.contracts import EntityRef
from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.intelligence.radar.detectors import KnownRuleDetector, RobustZScoreDetector
from market_intelligence.intelligence.radar.service import RadarService
from market_intelligence.workflows.activities import (
    MarketplaceActivities,
    PersistenceActivities,
    RadarActivities,
)


class RawRepo:
    def __init__(self) -> None:
        self.hashes: set[str] = set()

    async def append_if_new(self, event: Any) -> bool:
        if event.payload_hash in self.hashes:
            return False
        self.hashes.add(event.payload_hash)
        return True


class ChannelRepo:
    async def append_if_new(self, event: Any) -> bool:
        return True


class EntityRepo:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    async def upsert(self, entity: EntityRef, payload: dict[str, Any], observed_at: datetime) -> None:
        self.items[entity.entity_id] = payload


class SnapshotRepo:
    def __init__(self) -> None:
        self.hashes: set[str] = set()

    async def append_if_changed(
        self,
        entity: EntityRef,
        payload: dict[str, Any],
        captured_at: datetime,
    ) -> bool:
        key = f"{entity.entity_id}:{payload}"
        if key in self.hashes:
            return False
        self.hashes.add(key)
        return True


class AlertRepo:
    async def save(self, alert: Any) -> None:
        return None

    async def save_if_new(self, alert: Any) -> bool:
        return True


class FakeAdapter:
    name = "mercadolivre"

    async def fetch_resource(self, resource: str) -> dict[str, Any]:
        return {"id": resource.rsplit("/", 1)[-1], "status": "active"}

    def normalize_notification(self, payload: dict[str, Any]) -> Any:
        raise NotImplementedError


def test_temporal_activities_keep_side_effects_outside_workflow() -> None:
    async def scenario() -> None:
        raw = RawRepo()
        entities = EntityRepo()
        snapshots = SnapshotRepo()
        persistence = PersistenceActivities(
            raw, ChannelRepo(), entities, snapshots, AlertRepo()
        )
        marketplace = MarketplaceActivities({"mercadolivre": FakeAdapter()})
        radar = RadarActivities(RadarService([KnownRuleDetector(), RobustZScoreDetector()]))

        now = datetime.now(UTC)
        event = build_raw_event(
            source="mercadolivre",
            event_type="items",
            external_id="event-1",
            resource="/items/MLB1",
            received_at=now,
            payload={"resource": "/items/MLB1"},
        )
        assert await persistence.persist_raw_event(event.model_dump(mode="json")) is True
        assert await persistence.persist_raw_event(event.model_dump(mode="json")) is False

        resource = await marketplace.fetch_resource(
            {"marketplace": "mercadolivre", "resource": "/items/MLB1"}
        )
        assert resource["id"] == "MLB1"

        assert await persistence.persist_resource_snapshot(
            {
                "marketplace": "mercadolivre",
                "entity_type": "listing",
                "entity_id": "MLB1",
                "payload": resource,
                "observed_at": now.isoformat(),
            }
        ) is True

        finding = await radar.evaluate(
            {
                "entity_id": "MLB1",
                "observed_at": now.isoformat(),
                "metrics": {"sales": 1.0},
                "history": {"sales": [10.0, 10.0, 10.0, 10.0, 10.0]},
                "context": {},
            }
        )
        assert finding["entity_id"] == "MLB1"

    asyncio.run(scenario())
