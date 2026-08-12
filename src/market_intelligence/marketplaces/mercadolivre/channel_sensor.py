from __future__ import annotations

from datetime import UTC, datetime
from typing import Mapping

from pydantic import BaseModel, Field


_ALLOWED_HEADERS = {
    "retry-after",
    "x-request-id",
    "x-content-missing",
    "content-length",
    "content-type",
    "cache-control",
    "age",
    "etag",
    "last-modified",
}


class ChannelTelemetry(BaseModel):
    direction: str
    endpoint: str
    observed_at: datetime
    status_code: int | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    attempts: int = Field(default=1, ge=1)
    request_id: str | None = None
    retry_after: str | None = None
    partial_content: bool = False
    operational_headers: dict[str, str] = Field(default_factory=dict)


def sanitize_operational_headers(headers: Mapping[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for name, value in headers.items():
        lower = name.lower().strip()
        if lower in {"authorization", "proxy-authorization", "cookie", "set-cookie"}:
            continue
        if lower in _ALLOWED_HEADERS:
            sanitized[lower] = str(value)[:2048]
    return sanitized


def build_channel_telemetry(*, direction: str, endpoint: str, headers: Mapping[str, str] | None = None, status_code: int | None = None, latency_ms: float | None = None, attempts: int = 1) -> ChannelTelemetry:
    safe_headers = sanitize_operational_headers(headers or {})
    return ChannelTelemetry(
        direction=direction,
        endpoint=endpoint,
        observed_at=datetime.now(UTC),
        status_code=status_code,
        latency_ms=latency_ms,
        attempts=attempts,
        request_id=safe_headers.get("x-request-id"),
        retry_after=safe_headers.get("retry-after"),
        partial_content=status_code == 206 or "x-content-missing" in safe_headers,
        operational_headers=safe_headers,
    )
