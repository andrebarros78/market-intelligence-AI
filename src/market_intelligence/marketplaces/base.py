from __future__ import annotations

from typing import Any, Protocol

from market_intelligence.ingestion.events import RawEvent


class MarketplaceAdapter(Protocol):
    name: str

    async def fetch_resource(self, resource: str) -> dict[str, Any]: ...

    def normalize_notification(self, payload: dict[str, Any]) -> RawEvent: ...
