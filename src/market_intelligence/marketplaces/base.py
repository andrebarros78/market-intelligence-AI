from __future__ import annotations

from typing import Any, Protocol

from market_intelligence.ingestion.events import RawEvent


class MarketplaceReadError(RuntimeError):
    """Provider-neutral read failure classification for durable workflows."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


class MarketplaceAdapter(Protocol):
    name: str

    async def fetch_resource(self, resource: str) -> dict[str, Any]: ...

    def normalize_notification(self, payload: dict[str, Any]) -> RawEvent: ...
