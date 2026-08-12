from __future__ import annotations

from market_intelligence.core.contracts import Alert
from market_intelligence.ingestion.events import RawEvent


class InMemoryRawEventRepository:
    def __init__(self) -> None:
        self._events: dict[str, RawEvent] = {}

    async def append_if_new(self, event: RawEvent) -> bool:
        if event.payload_hash in self._events:
            return False
        self._events[event.payload_hash] = event
        return True

    def values(self) -> list[RawEvent]:
        return list(self._events.values())


class InMemoryAlertRepository:
    def __init__(self) -> None:
        self.items: list[Alert] = []

    async def save(self, alert: Alert) -> None:
        self.items.append(alert)
