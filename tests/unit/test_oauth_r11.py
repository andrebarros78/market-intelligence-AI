from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

import pytest
from cryptography.exceptions import InvalidTag

from market_intelligence.marketplaces.mercadolivre.oauth.crypto import EnvelopeCrypto, generate_pkce, state_digest
from market_intelligence.marketplaces.mercadolivre.oauth.sanitize import sanitize_mapping
from market_intelligence.marketplaces.mercadolivre.oauth.settings import OAuthRuntimeSettings
from market_intelligence.marketplaces.mercadolivre.oauth.synthetic_client import SyntheticOAuthClient, SyntheticOAuthError


def test_r11_fail_closed_defaults() -> None:
    settings = OAuthRuntimeSettings()
    settings.validate_for_r11()
    assert settings.synthetic_only is True and settings.network_blocked is True and settings.writes_blocked is True


def test_r11_rejects_network_open() -> None:
    with pytest.raises(PermissionError): OAuthRuntimeSettings(network_blocked=False).validate_for_r11()


def test_r11_rejects_writes_open() -> None:
    with pytest.raises(PermissionError): OAuthRuntimeSettings(writes_blocked=False).validate_for_r11()


def test_r11_real_network_guard() -> None:
    with pytest.raises(PermissionError): OAuthRuntimeSettings().assert_real_network_allowed()


def test_r11_write_guard() -> None:
    with pytest.raises(PermissionError): OAuthRuntimeSettings().assert_marketplace_write_allowed()


def test_pkce_s256_matches_expected() -> None:
    material = generate_pkce()
    expected = base64.urlsafe_b64encode(hashlib.sha256(material.verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    assert material.challenge == expected and material.state_hash == state_digest(material.state)
    assert len(material.verifier) >= 43


def test_state_digest_does_not_equal_state() -> None:
    state = "synthetic-sensitive-state"
    assert state_digest(state) != state and len(state_digest(state)) == 64


def test_envelope_round_trip_and_context_binding() -> None:
    crypto = EnvelopeCrypto(b"x" * 32)
    envelope = crypto.seal("synthetic-secret", context="ctx-a")
    assert b"synthetic-secret" not in envelope
    assert crypto.open(envelope, context="ctx-a") == "synthetic-secret"
    with pytest.raises(InvalidTag): crypto.open(envelope, context="ctx-b")


def test_envelope_tamper_is_rejected() -> None:
    crypto = EnvelopeCrypto(b"y" * 32)
    envelope = bytearray(crypto.seal("synthetic-secret", context="ctx")); envelope[-1] ^= 1
    with pytest.raises(InvalidTag): crypto.open(bytes(envelope), context="ctx")


def test_audit_sanitizer_redacts_secret_keys() -> None:
    value = sanitize_mapping({"state":"s","code":"c","access_token":"a","nested":{"refresh_token":"r","safe":"ok"}})
    assert value["state"] == value["code"] == value["access_token"] == "[REDACTED]"
    assert value["nested"]["refresh_token"] == "[REDACTED]" and value["nested"]["safe"] == "ok"


@pytest.mark.asyncio
async def test_synthetic_client_has_no_real_network_and_issues_tokens() -> None:
    fixed = datetime(2026, 8, 12, tzinfo=UTC); client = SyntheticOAuthClient(clock=lambda: fixed)
    tokens = await client.exchange(code="synthetic-code", verifier="synthetic-verifier")
    assert tokens.access_token.startswith("syn_at_") and tokens.refresh_token.startswith("syn_rt_")
    assert client.exchange_calls == 1


@pytest.mark.asyncio
async def test_synthetic_exchange_failure_has_safe_reason() -> None:
    client = SyntheticOAuthClient(fail_exchange=True)
    with pytest.raises(SyntheticOAuthError, match="synthetic_exchange_rejected"):
        await client.exchange(code="do-not-echo-this-code", verifier="do-not-echo-this-verifier")


@pytest.mark.asyncio
async def test_synthetic_refresh_failure_has_safe_reason() -> None:
    client = SyntheticOAuthClient(fail_refresh=True)
    with pytest.raises(SyntheticOAuthError, match="synthetic_refresh_rejected"):
        await client.refresh(refresh_token="do-not-echo-this-token")
