from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from market_intelligence.core.contracts import Alert, EntityRef
from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.ingestion.events import RawEvent


class RawEventRepository(Protocol):
    async def append_if_new(self, event: RawEvent) -> bool: ...


class ChannelEventRepository(Protocol):
    async def append_if_new(self, event: ChannelEvent) -> bool: ...


class EntityRepository(Protocol):
    async def upsert(self, entity: EntityRef, payload: dict[str, Any], observed_at: datetime) -> None: ...


class SnapshotRepository(Protocol):
    async def append_if_changed(
        self, entity: EntityRef, payload: dict[str, Any], captured_at: datetime
    ) -> bool: ...


class AlertRepository(Protocol):
    async def save(self, alert: Alert) -> None: ...
    async def save_if_new(self, alert: Alert) -> bool: ...


class OAuthStateRepository(Protocol):
    async def create(
        self,
        *,
        marketplace: str,
        state_hash: str,
        expires_at: datetime,
        verifier_envelope: bytes | None = None,
        redirect_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
        synthetic: bool = True,
        created_at: datetime | None = None,
    ) -> None: ...

    async def consume(self, *, state_hash: str, consumed_at: datetime | None = None) -> bool: ...
