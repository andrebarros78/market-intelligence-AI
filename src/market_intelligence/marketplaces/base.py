from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.ingestion.events import RawEvent


@dataclass(frozen=True, slots=True)
class MarketplaceFetchResult:
    payload: dict[str, Any]
    channel_event: ChannelEvent | None = None


class MarketplaceReadError(RuntimeError):
    """Provider-neutral read failure classification for durable workflows."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        channel_event: ChannelEvent | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.channel_event = channel_event


class MarketplaceAdapter(Protocol):
    name: str

    async def fetch_resource(self, resource: str) -> dict[str, Any]: ...

    def normalize_notification(self, payload: dict[str, Any]) -> RawEvent: ...


class ObservedMarketplaceAdapter(Protocol):
    async def fetch_resource_observed(
        self, resource: str, *, attempt: int = 1
    ) -> MarketplaceFetchResult: ...
