from __future__ import annotations

import asyncio

import httpx
import pytest

from market_intelligence.api.app import create_app
from market_intelligence.core.config import Settings
from market_intelligence.core.security import OperationalSecurityViolation
from market_intelligence.marketplaces.mercadolivre.http_client import (
    MercadoLivreReadError,
    MercadoLivreReadOnlyAdapter,
)

TOKEN = "synthetic-r120-token-never-send-outside-mock"


def test_app_refuses_unsafe_module01_runtime_configuration() -> None:
    with pytest.raises(OperationalSecurityViolation) as not_read_only:
        create_app(Settings(read_only=False, allow_marketplace_writes=False))
    assert not_read_only.value.code == "module01_read_only_policy_violation"

    with pytest.raises(OperationalSecurityViolation) as write_flag:
        create_app(Settings(read_only=True, allow_marketplace_writes=True))
    assert write_flag.value.code == "module01_read_only_policy_violation"


def test_capabilities_report_locked_security_posture_truthfully() -> None:
    async def scenario() -> None:
        app = create_app(Settings())
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            ready = (await client.get("/ready")).json()
            assert ready["read_only"] is True
            assert ready["marketplace_writes"] is False
            assert ready["module01_security_policy"] == "module01-security@1.0.0"

            capabilities = (await client.get("/v1/system/capabilities")).json()
            security = capabilities["operational_security"]
            assert security["policy_version"] == "module01-security@1.0.0"
            assert security["module01_read_only_runtime_locked"] is True
            assert security["unsafe_write_configuration_rejected_at_startup"] is True
            assert security["mercadolivre_allowed_methods"] == ["GET"]
            assert security["mercadolivre_allowed_host"] == "api.mercadolibre.com"
            assert security["mercadolivre_https_required"] is True
            assert security["authorization_override_blocked"] is True
            assert security["resource_path_traversal_blocked"] is True
            assert security["sensitive_query_parameters_blocked"] is True
            assert security["scraping_fallback_enabled"] is False
            assert security["real_marketplace_network_enabled"] is False

    asyncio.run(scenario())


@pytest.mark.asyncio
async def test_authorization_header_override_is_rejected_before_transport() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"ok": True})

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(MercadoLivreReadError) as caught:
            await adapter._read(
                "/items/MLB1",
                headers={"Authorization": "Bearer attacker-value"},
            )
        assert caught.value.code == "mercadolivre_forbidden_request_header"
        assert called is False
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_path_identifier_query_and_header_secret_echo_are_rejected_before_transport() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"ok": True})

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(MercadoLivreReadError) as traversal:
            await adapter.fetch_resource("/items/%252e%252e/orders/1")
        assert traversal.value.code == "mercadolivre_invalid_resource_path"

        with pytest.raises(MercadoLivreReadError) as identifier:
            await adapter.read_listing("MLB1/../../orders/1")
        assert identifier.value.code == "mercadolivre_invalid_resource_identifier"

        with pytest.raises(MercadoLivreReadError) as query:
            await adapter._read("/items/MLB1", params={"access_token": "attacker"})
        assert query.value.code == "mercadolivre_forbidden_query_parameter"

        with pytest.raises(MercadoLivreReadError) as token_query_echo:
            await adapter._read("/visits/items", params={"ids": TOKEN})
        assert token_query_echo.value.code == "mercadolivre_forbidden_query_parameter"

        with pytest.raises(MercadoLivreReadError) as token_path_echo:
            await adapter.fetch_resource(f"/items/{TOKEN}")
        assert token_path_echo.value.code == "mercadolivre_credential_echo_blocked"

        with pytest.raises(MercadoLivreReadError) as token_header_echo:
            await adapter._read(
                "/items/MLB1",
                headers={"Accept": f"application/json; debug={TOKEN}"},
            )
        assert token_header_echo.value.code == "mercadolivre_credential_echo_blocked"
        assert called is False
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_normal_read_is_get_https_official_host_and_system_owned_authorization() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["scheme"] = request.url.scheme
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"id": "MLB1", "status": "active"})

    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await adapter.read_listing("MLB1")
        assert result.payload["id"] == "MLB1"
        assert seen == {
            "method": "GET",
            "scheme": "https",
            "host": "api.mercadolibre.com",
            "path": "/items/MLB1",
            "authorization": f"Bearer {TOKEN}",
        }
    finally:
        await adapter.aclose()


class _UntrustedCustomTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.called = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.called = True
        return httpx.Response(200, request=request, json={"ok": True})


@pytest.mark.asyncio
async def test_arbitrary_custom_transport_cannot_bypass_default_network_block() -> None:
    transport = _UntrustedCustomTransport()
    adapter = MercadoLivreReadOnlyAdapter(
        access_token=TOKEN,
        transport=transport,
        network_allowed=False,
    )
    try:
        with pytest.raises(MercadoLivreReadError) as caught:
            await adapter.read_listing("MLB1")
        assert caught.value.code == "mercadolivre_network_blocked"
        assert transport.called is False
    finally:
        await adapter.aclose()


def test_adapter_subclass_cannot_redirect_base_url_to_other_host() -> None:
    class EvilHostAdapter(MercadoLivreReadOnlyAdapter):
        base_url = "https://evil.example"

    with pytest.raises(MercadoLivreReadError) as caught:
        EvilHostAdapter(
            access_token=TOKEN,
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        )
    assert caught.value.code == "mercadolivre_base_url_policy_violation"
