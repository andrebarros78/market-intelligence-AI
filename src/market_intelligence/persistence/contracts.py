from __future__ import annotations

from typing import Protocol

from market_intelligence.core.contracts import Alert
from market_intelligence.ingestion.events import RawEvent


class RawEventRepository(Protocol):
    async def append_if_new(self, event: RawEvent) -> bool: ...


class AlertRepository(Protocol):
    async def save(self, alert: Alert) -> None: ...
