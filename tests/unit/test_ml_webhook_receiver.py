from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from market_intelligence.api.mercadolivre_webhooks import build_mercadolivre_webhook_router
from market_intelligence.ingestion.events import RawEvent

APP_ID = "2767330231710080"


class MemoryRawEventSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.events: list[RawEvent] = []
        self._keys: set[tuple[str, str | None, str | None, str]] = set()
        self.fail = fail

    async def append_if_new(self, event: RawEvent) -> bool:
        if self.fail:
            raise RuntimeError("database unavailable")
        key = (event.event_type, event.external_id, event.resource, event.payload_hash)
        if key in self._keys:
            return False
        self._keys.add(key)
        self.events.append(event)
        return True


def _app(sink: MemoryRawEventSink, *, max_body_bytes: int = 1024 * 1024) -> FastAPI:
    app = FastAPI()
    app.include_router(
        build_mercadolivre_webhook_router(
            sink,
            application_id=APP_ID,
            max_body_bytes=max_body_bytes,
        )
    )
    return app


def _payload(**changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "_id": "f9f08571-1f65-4c46-9e0a-c0f43faa1557e",
        "resource": "/items/MLB1234567890",
        "user_id": 123456789,
        "topic": "items",
        "application_id": int(APP_ID),
        "attempts": 1,
        "sent": "2026-08-14T20:20:30.123Z",
        "received": "2026-08-14T20:20:30.100Z",
    }
    payload.update(changes)
    return payload


@pytest.mark.asyncio
async def test_valid_notification_is_acknowledged_and_preserved() -> None:
    sink = MemoryRawEventSink()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(sink)),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/webhooks/mercadolivre", json=_payload())

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.source == "mercadolivre_webhook"
    assert event.event_type == "items"
    assert event.resource == "/items/MLB1234567890"
    assert event.external_id == "f9f08571-1f65-4c46-9e0a-c0f43faa1557e"
    assert event.payload["application_id"] == int(APP_ID)


@pytest.mark.asyncio
async def test_duplicate_notification_is_idempotently_acknowledged() -> None:
    sink = MemoryRawEventSink()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(sink)),
        base_url="http://test",
    ) as client:
        first = await client.post("/v1/webhooks/mercadolivre", json=_payload())
        second = await client.post("/v1/webhooks/mercadolivre", json=_payload())

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(sink.events) == 1


@pytest.mark.asyncio
async def test_application_id_mismatch_is_rejected() -> None:
    sink = MemoryRawEventSink()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(sink)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/webhooks/mercadolivre",
            json=_payload(application_id=999),
        )

    assert response.status_code == 403
    assert sink.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resource",
    [
        "https://evil.example/orders/1",
        "//evil.example/orders/1",
        "/orders/../secrets",
        "\\\\evil.example\\share",
        "/orders/1?access_token=secret",
    ],
)
async def test_unsafe_resource_is_rejected(resource: str) -> None:
    sink = MemoryRawEventSink()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(sink)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/webhooks/mercadolivre",
            json=_payload(resource=resource),
        )

    assert response.status_code == 400
    assert sink.events == []


@pytest.mark.asyncio
async def test_relative_resource_used_by_some_topics_is_accepted() -> None:
    sink = MemoryRawEventSink()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(sink)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/webhooks/mercadolivre",
            json=_payload(topic="messages", resource="3f6da1e35ac84f70a24af7360d24c7bc"),
        )

    assert response.status_code == 200
    assert sink.events[0].resource == "3f6da1e35ac84f70a24af7360d24c7bc"


@pytest.mark.asyncio
async def test_malformed_or_non_json_requests_are_rejected() -> None:
    sink = MemoryRawEventSink()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(sink)),
        base_url="http://test",
    ) as client:
        malformed = await client.post(
            "/v1/webhooks/mercadolivre",
            content=b"{broken",
            headers={"content-type": "application/json"},
        )
        wrong_type = await client.post(
            "/v1/webhooks/mercadolivre",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )

    assert malformed.status_code == 400
    assert wrong_type.status_code == 415
    assert sink.events == []


@pytest.mark.asyncio
async def test_oversized_notification_is_rejected_before_persistence() -> None:
    sink = MemoryRawEventSink()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(sink, max_body_bytes=128)),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/webhooks/mercadolivre", json=_payload(extra="x" * 500))

    assert response.status_code == 413
    assert sink.events == []


@pytest.mark.asyncio
async def test_persistence_failure_returns_retryable_error_instead_of_false_ack() -> None:
    sink = MemoryRawEventSink(fail=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(sink)),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/webhooks/mercadolivre", json=_payload())

    assert response.status_code == 503
