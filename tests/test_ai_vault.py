from __future__ import annotations

import pytest

from market_intelligence.ai import AIVault, AIVaultProfile, ProviderConfigurationError


def _clear_vault_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for slot in range(1, 6):
        prefix = f"MI_AI_PROFILE_{slot}"
        for suffix in (
            "ENABLED",
            "NAME",
            "PROVIDER",
            "MODEL",
            "BASE_URL",
            "PROTOCOL",
            "AUTH_TYPE",
            "AUTH_HEADER",
            "API_VERSION",
            "ORGANIZATION",
            "PROJECT",
            "TENANT",
            "REGION",
            "DEPLOYMENT",
            "CLIENT_ID",
            "TIMEOUT_SECONDS",
            "RETRIES",
            "MAX_OUTPUT_TOKENS",
            "TEMPERATURE",
            "STORE",
            "EXTRA_CONFIG_JSON",
            "API_KEY",
            "BEARER_TOKEN",
            "CLIENT_SECRET",
            "ACCESS_TOKEN",
            "REFRESH_TOKEN",
            "PRIVATE_KEY",
            "SERVICE_ACCOUNT_JSON",
            "EXTRA_SECRET_JSON",
        ):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    monkeypatch.delenv("MI_AI_SYSTEM_PROFILE", raising=False)
    monkeypatch.delenv("MI_AI_AGENTS_PROFILE", raising=False)


def test_vault_has_exactly_five_slots_and_legacy_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_vault_env(monkeypatch)
    monkeypatch.setenv("MI_AI_SYSTEM_PROVIDER", "openai")
    monkeypatch.setenv("MI_AI_SYSTEM_MODEL", "gpt-5-mini")
    monkeypatch.setenv("MI_AI_SYSTEM_API_KEY", "system-key")
    monkeypatch.setenv("MI_AI_AGENTS_PROVIDER", "zai")
    monkeypatch.setenv("MI_AI_AGENTS_MODEL", "glm-4.7-flash")
    monkeypatch.setenv("MI_AI_AGENTS_API_KEY", "agents-key")

    vault = AIVault.from_env()

    assert len(vault.profiles) == 5
    assert vault.profile(1).provider == "openai"
    assert vault.profile(2).provider == "zai"
    assert vault.profile(3).enabled is False
    assert vault.profile(4).enabled is False
    assert vault.profile(5).enabled is False


def test_each_profile_reads_its_own_full_field_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_vault_env(monkeypatch)
    prefix = "MI_AI_PROFILE_5"
    monkeypatch.setenv(f"{prefix}_ENABLED", "true")
    monkeypatch.setenv(f"{prefix}_NAME", "Provider Five")
    monkeypatch.setenv(f"{prefix}_PROVIDER", "future-provider")
    monkeypatch.setenv(f"{prefix}_MODEL", "future-model")
    monkeypatch.setenv(f"{prefix}_BASE_URL", "https://ai.example.test/v9")
    monkeypatch.setenv(f"{prefix}_PROTOCOL", "custom")
    monkeypatch.setenv(f"{prefix}_AUTH_TYPE", "oauth2")
    monkeypatch.setenv(f"{prefix}_AUTH_HEADER", "X-Provider-Key")
    monkeypatch.setenv(f"{prefix}_API_VERSION", "2026-08-14")
    monkeypatch.setenv(f"{prefix}_ORGANIZATION", "org-5")
    monkeypatch.setenv(f"{prefix}_PROJECT", "project-5")
    monkeypatch.setenv(f"{prefix}_TENANT", "tenant-5")
    monkeypatch.setenv(f"{prefix}_REGION", "br")
    monkeypatch.setenv(f"{prefix}_DEPLOYMENT", "deployment-5")
    monkeypatch.setenv(f"{prefix}_CLIENT_ID", "client-5")
    monkeypatch.setenv(f"{prefix}_TIMEOUT_SECONDS", "31")
    monkeypatch.setenv(f"{prefix}_RETRIES", "2")
    monkeypatch.setenv(f"{prefix}_MAX_OUTPUT_TOKENS", "4096")
    monkeypatch.setenv(f"{prefix}_TEMPERATURE", "0.25")
    monkeypatch.setenv(f"{prefix}_STORE", "false")
    monkeypatch.setenv(f"{prefix}_EXTRA_CONFIG_JSON", '{"feature":"value"}')
    monkeypatch.setenv(f"{prefix}_API_KEY", "api-secret")
    monkeypatch.setenv(f"{prefix}_BEARER_TOKEN", "bearer-secret")
    monkeypatch.setenv(f"{prefix}_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv(f"{prefix}_ACCESS_TOKEN", "access-secret")
    monkeypatch.setenv(f"{prefix}_REFRESH_TOKEN", "refresh-secret")
    monkeypatch.setenv(f"{prefix}_PRIVATE_KEY", "private-secret")
    monkeypatch.setenv(f"{prefix}_SERVICE_ACCOUNT_JSON", '{"private_key":"service-secret"}')
    monkeypatch.setenv(f"{prefix}_EXTRA_SECRET_JSON", '{"other":"extra-secret"}')

    profile = AIVaultProfile.from_env(5)

    assert profile.slot == 5
    assert profile.enabled is True
    assert profile.name == "Provider Five"
    assert profile.provider == "future-provider"
    assert profile.model == "future-model"
    assert profile.base_url == "https://ai.example.test/v9"
    assert profile.protocol == "custom"
    assert profile.auth_type == "oauth2"
    assert profile.auth_header == "X-Provider-Key"
    assert profile.api_version == "2026-08-14"
    assert profile.organization == "org-5"
    assert profile.project == "project-5"
    assert profile.tenant == "tenant-5"
    assert profile.region == "br"
    assert profile.deployment == "deployment-5"
    assert profile.client_id == "client-5"
    assert profile.timeout_seconds == 31
    assert profile.retries == 2
    assert profile.max_output_tokens == 4096
    assert profile.temperature == 0.25
    assert profile.extra_config == {"feature": "value"}
    assert profile.api_key is not None
    assert profile.bearer_token is not None
    assert profile.client_secret is not None
    assert profile.access_token is not None
    assert profile.refresh_token is not None
    assert profile.private_key is not None
    assert profile.service_account_json is not None
    assert profile.extra_secret_json is not None


def test_system_and_agents_can_select_any_profile_independently(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_vault_env(monkeypatch)
    for slot, provider, model, url, key in (
        (1, "openai", "gpt-5-mini", "https://api.openai.com/v1", "key-one"),
        (2, "zai", "glm-4.7-flash", "https://api.z.ai/api/paas/v4", "key-two"),
    ):
        prefix = f"MI_AI_PROFILE_{slot}"
        monkeypatch.setenv(f"{prefix}_ENABLED", "true")
        monkeypatch.setenv(f"{prefix}_PROVIDER", provider)
        monkeypatch.setenv(f"{prefix}_MODEL", model)
        monkeypatch.setenv(f"{prefix}_BASE_URL", url)
        monkeypatch.setenv(f"{prefix}_API_KEY", key)

    monkeypatch.setenv("MI_AI_SYSTEM_PROFILE", "1")
    monkeypatch.setenv("MI_AI_AGENTS_PROFILE", "2")

    vault = AIVault.from_env()
    system = vault.resolve(role="system")
    agents = vault.resolve(role="agents")

    assert system.provider == "openai"
    assert agents.provider == "zai"
    assert system.api_key is not None
    assert agents.api_key is not None
    assert system.api_key.get_secret_value() == "key-one"
    assert agents.api_key.get_secret_value() == "key-two"


def test_public_status_never_exposes_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_vault_env(monkeypatch)
    prefix = "MI_AI_PROFILE_3"
    monkeypatch.setenv(f"{prefix}_ENABLED", "true")
    monkeypatch.setenv(f"{prefix}_API_KEY", "do-not-expose-api-key")
    monkeypatch.setenv(f"{prefix}_CLIENT_SECRET", "do-not-expose-client-secret")
    monkeypatch.setenv(f"{prefix}_PRIVATE_KEY", "do-not-expose-private-key")

    status = AIVaultProfile.from_env(3).public_status()
    rendered = repr(status)

    assert status["api_key_configured"] is True
    assert status["client_secret_configured"] is True
    assert status["private_key_configured"] is True
    assert "do-not-expose" not in rendered


def test_profile_secrets_are_redacted_from_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_vault_env(monkeypatch)
    monkeypatch.setenv("MI_AI_PROFILE_4_API_KEY", "profile-four-secret")
    rendered = repr(AIVaultProfile.from_env(4))
    assert "profile-four-secret" not in rendered
    assert "**********" in rendered


def test_profile_slot_out_of_range_fails_closed() -> None:
    with pytest.raises(ProviderConfigurationError) as caught:
        AIVaultProfile.from_env(6)
    assert caught.value.code == "ai_vault_profile_slot_out_of_range"


def test_unknown_provider_can_be_stored_but_not_executed_without_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_vault_env(monkeypatch)
    prefix = "MI_AI_PROFILE_3"
    monkeypatch.setenv(f"{prefix}_ENABLED", "true")
    monkeypatch.setenv(f"{prefix}_PROVIDER", "future-provider")
    monkeypatch.setenv(f"{prefix}_MODEL", "future-model")
    monkeypatch.setenv(f"{prefix}_BASE_URL", "https://future.example.test/v1")
    monkeypatch.setenv(f"{prefix}_API_KEY", "future-secret")
    monkeypatch.setenv("MI_AI_SYSTEM_PROFILE", "3")

    config = AIVault.from_env().resolve(role="system")
    assert config.provider == "future-provider"
    assert config.api_key is not None
