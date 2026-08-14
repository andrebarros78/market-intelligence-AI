from __future__ import annotations

import httpx
import pytest

from market_intelligence.core.config import Settings
from market_intelligence.core.security import (
    MODULE01_SECURITY_POLICY,
    OperationalSecurityViolation,
)


def test_module01_runtime_policy_accepts_only_read_only_settings() -> None:
    Settings().assert_module01_operational_security()

    with pytest.raises(OperationalSecurityViolation) as not_read_only:
        Settings(read_only=False).assert_module01_operational_security()
    assert not_read_only.value.code == "module01_read_only_policy_violation"

    with pytest.raises(OperationalSecurityViolation) as writes_enabled:
        Settings(allow_marketplace_writes=True).assert_module01_operational_security()
    assert writes_enabled.value.code == "module01_read_only_policy_violation"

    with pytest.raises(OperationalSecurityViolation):
        Settings(read_only=False, allow_marketplace_writes=True).assert_module01_operational_security()


def test_resource_path_guard_rejects_host_escape_query_fragment_and_traversal() -> None:
    policy = MODULE01_SECURITY_POLICY
    assert policy.validate_resource_path("/items/MLB1") == "/items/MLB1"

    invalid = [
        "https://evil.example/items/MLB1",
        "//evil.example/items/MLB1",
        "items/MLB1",
        "/items/MLB1?access_token=secret",
        "/items/MLB1#fragment",
        "/items/../orders/1",
        "/items/%2e%2e/orders/1",
        "/items/%252e%252e/orders/1",
        "/items\\..\\orders\\1",
        "/items/MLB1\r\nX-Evil: yes",
    ]
    for resource in invalid:
        with pytest.raises(OperationalSecurityViolation) as caught:
            policy.validate_resource_path(resource)
        assert caught.value.code == "mercadolivre_invalid_resource_path"


def test_identifier_guard_blocks_path_and_query_injection() -> None:
    policy = MODULE01_SECURITY_POLICY
    assert policy.validate_identifier("MLB123-ABC") == "MLB123-ABC"
    for value in ["", "..", "MLB1/../../orders/1", "MLB1?x=1", "MLB1#x", " MLB1", "MLB1%2F1"]:
        with pytest.raises(OperationalSecurityViolation) as caught:
            policy.validate_identifier(value)
        assert caught.value.code == "mercadolivre_invalid_resource_identifier"


def test_additional_header_allowlist_blocks_authorization_host_cookie_and_unknown_headers() -> None:
    policy = MODULE01_SECURITY_POLICY
    assert policy.validate_additional_headers({"X-Format-New": "true"}) == {
        "x-format-new": "true"
    }
    assert policy.validate_additional_headers({"Accept": "application/json"}) == {
        "accept": "application/json"
    }

    for name in ["Authorization", "Host", "Cookie", "Proxy-Authorization", "X-Forwarded-Host", "X-Arbitrary"]:
        with pytest.raises(OperationalSecurityViolation) as caught:
            policy.validate_additional_headers({name: "attacker-controlled"})
        assert caught.value.code == "mercadolivre_forbidden_request_header"


def test_query_guard_blocks_secret_keys_and_credential_echo() -> None:
    policy = MODULE01_SECURITY_POLICY
    token = "synthetic-r120-token"
    assert policy.validate_query_params({"ids": "MLB1", "version": "v2"}, access_token=token) == {
        "ids": "MLB1",
        "version": "v2",
    }

    for params in [
        {"access_token": "secret"},
        {"refresh_token": "secret"},
        {"client_secret": "secret"},
        {"custom_token": "secret"},
        {"ids": token},
    ]:
        with pytest.raises(OperationalSecurityViolation) as caught:
            policy.validate_query_params(params, access_token=token)
        assert caught.value.code == "mercadolivre_forbidden_query_parameter"


def test_outbound_request_guard_rejects_non_get_and_wrong_host() -> None:
    policy = MODULE01_SECURITY_POLICY
    policy.validate_outbound_request(
        httpx.Request("GET", "https://api.mercadolibre.com/items/MLB1")
    )

    with pytest.raises(OperationalSecurityViolation) as method:
        policy.validate_outbound_request(
            httpx.Request("POST", "https://api.mercadolibre.com/items/MLB1")
        )
    assert method.value.code == "module01_non_read_request_blocked"

    with pytest.raises(OperationalSecurityViolation) as host:
        policy.validate_outbound_request(
            httpx.Request("GET", "https://evil.example/items/MLB1")
        )
    assert host.value.code == "mercadolivre_outbound_host_policy_violation"

    with pytest.raises(OperationalSecurityViolation) as scheme:
        policy.validate_outbound_request(
            httpx.Request("GET", "http://api.mercadolibre.com/items/MLB1")
        )
    assert scheme.value.code == "mercadolivre_outbound_host_policy_violation"
