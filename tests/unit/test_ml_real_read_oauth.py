from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from market_intelligence.marketplaces.mercadolivre.oauth.real_read import (
    MercadoLivreRealOAuthClient,
    RealReadOAuthError,
    RealReadOAuthSettings,
)


@pytest.fixture
def settings() -> RealReadOAuthSettings:
    return RealReadOAuthSettings(
        app_id="2767330231710080",
        client_secret=SecretStr("super-secret-value"),
        redirect_uri="https://example.test/v1/oauth/mercadolivre/callback",
        real_read_enabled=False,
    )


def test_real_read_settings_are_fail_closed_by_default(settings: RealReadOAuthSettings) -> None:
    settings.validate_configuration()
    with pytest.raises(PermissionError, match="mercadolivre_real_read_disabled"):
        settings.assert_enabled()


def test_real_read_redirect_must_be_static_https() -> None:
    with pytest.raises(ValueError, match="redirect_uri_invalid"):
        RealReadOAuthSettings(
            app_id="2767330231710080",
            client_secret=SecretStr("secret"),
            redirect_uri="http://localhost/callback",
        ).validate_configuration()
    with pytest.raises(ValueError, match="redirect_uri_invalid"):
        RealReadOAuthSettings(
            app_id="2767330231710080",
            client_secret=SecretStr("secret"),
            redirect_uri="https://example.test/callback?code=dynamic",
        ).validate_configuration()


@pytest.mark.asyncio
async def test_authorization_url_uses_state_pkce_and_never_client_secret(
    settings: RealReadOAuthSettings,
) -> None:
    client = MercadoLivreRealOAuthClient(
        settings,
        transport=httpx.MockTransport(lambda request: None),
    )
    try:
        url = client.authorization_url(state="state-value", code_challenge="challenge-value")
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        assert parsed.scheme == "https"
        assert parsed.netloc == "auth.mercadolivre.com.br"
        assert parsed.path == "/authorization"
        assert query["response_type"] == ["code"]
        assert query["client_id"] == [settings.app_id]
        assert query["redirect_uri"] == [settings.redirect_uri]
        assert query["state"] == ["state-value"]
        assert query["code_challenge"] == ["challenge-value"]
        assert query["code_challenge_method"] == ["S256"]
        assert settings.client_secret.get_secret_value() not in url
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_exchange_is_the_only_oauth_post_and_users_me_is_get(
    settings: RealReadOAuthSettings,
) -> None:
    seen: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8", errors="ignore")
        seen.append((request.method, request.url.path, body))
        if request.url.path == "/oauth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "real-access-token",
                    "refresh_token": "real-refresh-token",
                    "expires_in": 21600,
                    "scope": "read offline_access",
                },
            )
        if request.url.path == "/users/me":
            assert request.headers["Authorization"] == "Bearer real-access-token"
            return httpx.Response(
                200,
                headers={"x-request-id": "req-real-read-01"},
                json={
                    "id": 9876543210,
                    "nickname": "seller-test",
                    "site_id": "MLB",
                    "status": "active",
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = MercadoLivreRealOAuthClient(settings, transport=httpx.MockTransport(handler))
    try:
        tokens = await client.exchange(code="authorization-code", verifier="pkce-verifier")
        assert tokens.access_token == "real-access-token"
        assert tokens.refresh_token == "real-refresh-token"
        assert tokens.scopes == ("offline_access", "read")
        identity = await client.read_users_me(tokens.access_token)
        assert identity.payload["id"] == 9876543210
        assert identity.telemetry.status_code == 200
        assert identity.telemetry.request_id == "req-real-read-01"
        assert [entry[:2] for entry in seen] == [
            ("POST", "/oauth/token"),
            ("GET", "/users/me"),
        ]
        assert "super-secret-value" in seen[0][2]
        assert "real-access-token" not in seen[0][2]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_write_scope_is_rejected_before_any_business_read(
    settings: RealReadOAuthSettings,
) -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/oauth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "must-not-be-used",
                    "refresh_token": "must-not-be-stored",
                    "expires_in": 21600,
                    "scope": "read write offline_access",
                },
            )
        raise AssertionError("business read must not happen after write scope")

    client = MercadoLivreRealOAuthClient(settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RealReadOAuthError) as caught:
            await client.exchange(code="authorization-code", verifier="pkce-verifier")
        assert caught.value.code == "mercadolivre_real_oauth_write_scope_rejected"
        assert seen == [("POST", "/oauth/token")]
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [None, "", "offline_access"])
async def test_missing_read_scope_is_rejected_fail_closed(
    settings: RealReadOAuthSettings,
    scope: str | None,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload: dict[str, object] = {
            "access_token": "must-not-be-used",
            "refresh_token": "must-not-be-stored",
            "expires_in": 21600,
        }
        if scope is not None:
            payload["scope"] = scope
        return httpx.Response(200, json=payload)

    client = MercadoLivreRealOAuthClient(settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RealReadOAuthError) as caught:
            await client.exchange(code="authorization-code", verifier="pkce-verifier")
        assert caught.value.code == "mercadolivre_real_oauth_read_scope_missing"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_exchange_error_never_echoes_external_payload_or_secret(
    settings: RealReadOAuthSettings,
) -> None:
    secret = settings.client_secret.get_secret_value()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad", "client_secret": secret})

    client = MercadoLivreRealOAuthClient(settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RealReadOAuthError) as caught:
            await client.exchange(code="sensitive-code", verifier="sensitive-verifier")
        rendered = repr(caught.value)
        assert secret not in rendered
        assert "sensitive-code" not in rendered
        assert "sensitive-verifier" not in rendered
        assert caught.value.code == "mercadolivre_real_oauth_exchange_rejected"
        assert caught.value.status_code == 400
    finally:
        await client.aclose()
