from __future__ import annotations

import httpx
import pytest

from market_intelligence.marketplaces.mercadolivre.http_client import (
    MercadoLivreReadError,
    MercadoLivreReadOnlyAdapter,
)

TOKEN = "synthetic-r14-token-never-log"


@pytest.mark.asyncio
async def test_real_network_is_blocked_by_default() -> None:
    adapter = MercadoLivreReadOnlyAdapter(access_token=TOKEN)
    with pytest.raises(MercadoLivreReadError) as caught:
        await adapter.read_listing("MLB1")
    assert caught.value.code == "mercadolivre_network_blocked"
    assert caught.value.retryable is False
    assert TOKEN not in repr(caught.value)


@pytest.mark.asyncio
async def test_synthetic_transport_still_requires_explicit_credential() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"id": "MLB1"})

    adapter = MercadoLivreReadOnlyAdapter(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(MercadoLivreReadError) as caught:
            await adapter.read_listing("MLB1")
        assert caught.value.code == "mercadolivre_credential_missing"
        assert called is False
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_200_read_sanitizes_credential_echo_and_operational_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(
            200,
            headers={
                "X-Request-Id": "req-123",
                "ETag": "etag-1",
                "Authorization": f"Bearer {TOKEN}",
                "Set-Cookie": "secret=cookie",
            },
            json={
                "id": "MLB1",
                "status": "active",
                "access_token": TOKEN,
                "nested": {"value": TOKEN},
            },
        )

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN, transport=httpx.MockTransport(handler)
    )
    try:
        result = await adapter.read_listing("MLB1")
        assert result.payload["access_token"] == "[REDACTED]"
        assert result.payload["nested"]["value"] == "[REDACTED]"
        assert result.telemetry.request_id == "req-123"
        assert "authorization" not in result.telemetry.operational_headers
        assert "set-cookie" not in result.telemetry.operational_headers
        rendered = repr(result)
        assert TOKEN not in rendered
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_order_206_is_successful_but_degraded_with_missing_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            206,
            headers={"X-Content-Missing": "buyer, feedback", "X-Request-Id": "order-req"},
            json={"id": 123, "status": "paid", "buyer": {}},
        )

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN, transport=httpx.MockTransport(handler)
    )
    try:
        result = await adapter.read_order("123")
        assert result.payload["status"] == "paid"
        assert result.telemetry.status_code == 206
        assert result.telemetry.partial_content is True
        assert result.missing_fields == ("buyer", "feedback")
        assert result.degraded is True
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_resource_specific_read_contracts_send_expected_paths_headers_and_queries() -> None:
    seen: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.path,
                str(request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query),
                request.headers.get("x-format-new"),
            )
        )
        return httpx.Response(200, json={"ok": True})

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN, transport=httpx.MockTransport(handler)
    )
    try:
        await adapter.read_listing("MLB1")
        await adapter.read_order("O1")
        await adapter.read_shipment("S1")
        await adapter.read_visits("MLB1")
        await adapter.read_catalog_competition("MLB1")
    finally:
        await adapter.aclose()

    assert seen[0] == ("/items/MLB1", "", None)
    assert seen[1] == ("/orders/O1", "", None)
    assert seen[2] == ("/shipments/S1", "", "true")
    assert seen[3][0] == "/visits/items" and "ids=MLB1" in seen[3][1]
    assert seen[4][0] == "/items/MLB1/price_to_win" and "version=v2" in seen[4][1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (429, "mercadolivre_rate_limited", True),
        (500, "mercadolivre_server_failure", True),
        (503, "mercadolivre_server_failure", True),
        (404, "mercadolivre_request_rejected", False),
        (302, "mercadolivre_request_rejected", False),
    ],
)
async def test_http_failures_are_classified_without_leaking_response_body(
    status_code: int, expected_code: str, retryable: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"Retry-After": "7"} if status_code == 429 else {}
        return httpx.Response(
            status_code,
            headers=headers,
            json={"message": TOKEN, "access_token": TOKEN},
        )

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN, transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(MercadoLivreReadError) as caught:
            await adapter.read_listing("MLB1")
        error = caught.value
        assert error.code == expected_code
        assert error.status_code == status_code
        assert error.retryable is retryable
        assert TOKEN not in repr(error)
        if status_code == 429:
            assert error.retry_after == "7"
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_absolute_or_scheme_relative_resource_paths_are_rejected_before_transport() -> None:
    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )
    try:
        for resource in ["https://evil.example/data", "//evil.example/data", "items/MLB1"]:
            with pytest.raises(MercadoLivreReadError) as caught:
                await adapter.fetch_resource(resource)
            assert caught.value.code == "mercadolivre_invalid_resource_path"
    finally:
        await adapter.aclose()
