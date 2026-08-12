from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class RawEvent(BaseModel):
    source: str
    event_type: str
    resource: str | None = None
    occurred_at: datetime | None = None
    received_at: datetime
    payload_hash: str
    payload: dict[str, Any] = Field(default_factory=dict)


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_raw_event(*, source: str, event_type: str, payload: dict[str, Any], resource: str | None = None, occurred_at: datetime | None = None, received_at: datetime | None = None) -> RawEvent:
    return RawEvent(
        source=source,
        event_type=event_type,
        resource=resource,
        occurred_at=occurred_at,
        received_at=received_at or datetime.now(UTC),
        payload_hash=canonical_payload_hash(payload),
        payload=payload,
    )
