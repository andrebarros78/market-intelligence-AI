from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChannelEvent(BaseModel):
    marketplace: str = Field(min_length=1, max_length=64)
    direction: Literal["inbound", "outbound"]
    operation: str = Field(min_length=1, max_length=160)
    observed_at: datetime
    status_code: int | None = Field(default=None, ge=100, le=599)
    latency_ms: float | None = Field(default=None, ge=0)
    attempt: int = Field(default=1, ge=1)
    correlation_id: str | None = Field(default=None, max_length=160)
    request_id: str | None = Field(default=None, max_length=160)
    attributes: dict[str, Any] = Field(default_factory=dict)
