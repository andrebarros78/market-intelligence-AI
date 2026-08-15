from __future__ import annotations

import httpx
import pytest

from scripts.run_ml_controlled_pause_resume import (
    ControlledProofError,
    _ensure_active,
    _request,
)


@pytest.mark.asyncio
async def test_request_rejects_any_method_outside_get_put() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as client:
        with pytest.raises(ControlledProofError, match="forbidden_method"):
            await _request(client, "POST", "/items/MLB1", token="secret")


@pytest.mark.asyncio
async def test_request_rejects_write_outside_item_status_endpoint() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as client:
        with pytest.raises(ControlledProofError, match="forbidden_write_path"):
            await _request(client, "PUT", "/users/1", token="secret", json_body={"status": "active"})


@pytest.mark.asyncio
async def test_request_rejects_closed_and_other_write_payloads() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as client:
        with pytest.raises(ControlledProofError, match="forbidden_write_payload"):
            await _request(client, "PUT", "/items/MLB1", token="secret", json_body={"status": "closed"})
        with pytest.raises(ControlledProofError, match="forbidden_write_payload"):
            await _request(client, "PUT", "/items/MLB1", token="secret", json_body={"price": 1})


@pytest.mark.asyncio
async def test_ensure_active_recovers_after_transient_failure() -> None:
    state = {"get": 0, "put": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            state["get"] += 1
            status = "paused" if state["get"] < 3 else "active"
            return httpx.Response(200, json={"id": "MLB1", "status": status})
        if request.method == "PUT":
            state["put"] += 1
            if state["put"] == 1:
                return httpx.Response(503, json={"message": "temporary"})
            return httpx.Response(200, json={"id": "MLB1", "status": "active"})
        raise AssertionError(request.method)

    async with httpx.AsyncClient(base_url="https://api.mercadolibre.com", transport=httpx.MockTransport(handler)) as client:
        item = await _ensure_active(client, token="secret", item_id="MLB1", attempts=3, delay_seconds=0)

    assert item["status"] == "active"
    assert state["put"] == 2


@pytest.mark.asyncio
async def test_ensure_active_fails_closed_when_reactivation_never_confirms() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"id": "MLB1", "status": "paused"})
        if request.method == "PUT":
            return httpx.Response(200, json={"id": "MLB1", "status": "paused"})
        raise AssertionError(request.method)

    async with httpx.AsyncClient(base_url="https://api.mercadolibre.com", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ControlledProofError, match="CRITICAL_REACTIVATION_FAILED"):
            await _ensure_active(client, token="secret", item_id="MLB1", attempts=2, delay_seconds=0)
