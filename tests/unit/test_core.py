import asyncio
from datetime import UTC, datetime

import pytest

from market_intelligence.core.config import Settings
from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.persistence.memory import InMemoryRawEventRepository


def test_write_guard_is_denied_by_default() -> None:
    with pytest.raises(PermissionError):
        Settings().assert_marketplace_write_allowed()


def test_raw_event_hash_is_stable() -> None:
    event_a = build_raw_event(source="meli", event_type="listing", payload={"b": 2, "a": 1})
    event_b = build_raw_event(source="meli", event_type="listing", payload={"a": 1, "b": 2})
    assert event_a.payload_hash == event_b.payload_hash


def test_raw_event_repository_deduplicates() -> None:
    async def scenario() -> None:
        repo = InMemoryRawEventRepository()
        event = build_raw_event(source="meli", event_type="listing", payload={"id": "MLB1"}, occurred_at=datetime.now(UTC))
        assert await repo.append_if_new(event) is True
        assert await repo.append_if_new(event) is False

    asyncio.run(scenario())
