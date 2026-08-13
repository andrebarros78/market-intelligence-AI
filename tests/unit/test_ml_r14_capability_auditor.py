from __future__ import annotations

import httpx
import pytest

from market_intelligence.marketplaces.mercadolivre.capability_auditor import (
    CapabilityState,
    CapabilityTargets,
    MercadoLivreCapabilityAuditor,
)
from market_intelligence.marketplaces.mercadolivre.http_client import MercadoLivreReadOnlyAdapter

TOKEN = "synthetic-auditor-token"


@pytest.mark.asyncio
async def test_capability_auditor_classifies_observed_channel_states_without_causal_claims() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/items/MLB1":
            return httpx.Response(200, json={"id": "MLB1", "status": "active"})
        if path == "/orders/O1":
            return httpx.Response(
                206,
                headers={"X-Content-Missing": "buyer"},
                json={"id": "O1", "status": "paid"},
            )
        if path == "/shipments/S1":
            assert request.headers["x-format-new"] == "true"
            return httpx.Response(200, json={"id": "S1", "status": "ready_to_ship"})
        if path == "/visits/items":
            return httpx.Response(429, headers={"Retry-After": "5"}, json={"error": "rate_limit"})
        if path == "/items/MLB1/price_to_win":
            return httpx.Response(404, json={"error": "not_found"})
        raise AssertionError(path)

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN, transport=httpx.MockTransport(handler)
    )
    try:
        auditor = MercadoLivreCapabilityAuditor(adapter)
        probes = await auditor.audit(
            CapabilityTargets(
                listing_id="MLB1",
                order_id="O1",
                shipment_id="S1",
                visits_item_id="MLB1",
                catalog_item_id="MLB1",
            )
        )
    finally:
        await adapter.aclose()

    by_name = {probe.capability: probe for probe in probes}
    assert by_name["listing"].state == CapabilityState.AVAILABLE
    assert by_name["order"].state == CapabilityState.DEGRADED
    assert by_name["order"].missing_fields == ("buyer",)
    assert by_name["shipment"].state == CapabilityState.AVAILABLE
    assert by_name["visits"].state == CapabilityState.UNKNOWN
    assert by_name["visits"].reason == "mercadolivre_rate_limited"
    assert by_name["catalog_competition"].state == CapabilityState.UNAVAILABLE
    assert by_name["catalog_competition"].reason == "mercadolivre_request_rejected"


@pytest.mark.asyncio
async def test_capability_auditor_marks_schema_drift_as_degraded() -> None:
    current = [{"id": "MLB1", "status": "active"}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=current[0])

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN, transport=httpx.MockTransport(handler)
    )
    try:
        auditor = MercadoLivreCapabilityAuditor(adapter)
        first = await auditor.audit(CapabilityTargets(listing_id="MLB1"))
        assert first[0].state == CapabilityState.AVAILABLE

        current[0] = {"id": "MLB1", "status": "active", "new_platform_field": True}
        second = await auditor.audit(CapabilityTargets(listing_id="MLB1"))
        assert second[0].state == CapabilityState.DEGRADED
        assert second[0].schema_drift is not None
        assert second[0].schema_drift.changed is True
        assert second[0].reason == "partial_or_schema_drift"
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_missing_probe_target_is_unknown_without_network_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN, transport=httpx.MockTransport(handler)
    )
    try:
        probes = await MercadoLivreCapabilityAuditor(adapter).audit(CapabilityTargets())
    finally:
        await adapter.aclose()

    assert calls == 0
    assert all(probe.state == CapabilityState.UNKNOWN for probe in probes)
    assert all(probe.reason == "target_missing" for probe in probes)
