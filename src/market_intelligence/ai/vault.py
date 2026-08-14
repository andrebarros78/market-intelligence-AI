from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from pydantic import SecretStr

from market_intelligence.ai.providers import AIProviderConfig, ProviderConfigurationError

AI_VAULT_PROFILE_COUNT = 5
AI_VAULT_SLOTS = tuple(range(1, AI_VAULT_PROFILE_COUNT + 1))


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ProviderConfigurationError("ai_vault_invalid_boolean_config")


def _parse_optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ProviderConfigurationError("ai_vault_invalid_numeric_config") from exc
    if parsed < 0:
        raise ProviderConfigurationError("ai_vault_invalid_numeric_config")
    return parsed


def _parse_optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ProviderConfigurationError("ai_vault_invalid_numeric_config") from exc


def _parse_json_object(value: str | None) -> dict[str, Any]:
    if value is None or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProviderConfigurationError("ai_vault_invalid_json_config") from exc
    if not isinstance(parsed, dict):
        raise ProviderConfigurationError("ai_vault_invalid_json_config")
    return parsed


def _secret(value: str | None) -> SecretStr | None:
    if value is None or not value.strip():
        return None
    return SecretStr(value)


def _profile_prefix(slot: int) -> str:
    if slot not in AI_VAULT_SLOTS:
        raise ProviderConfigurationError("ai_vault_profile_slot_out_of_range")
    return f"MI_AI_PROFILE_{slot}"


@dataclass(frozen=True, slots=True)
class AIVaultProfile:
    """Provider-neutral vault record for one AI model/profile.

    The vault can retain provider-specific metadata and secrets without automatically
    forwarding them to a network endpoint. Runtime adapters receive only fields they
    explicitly support.
    """

    slot: int
    enabled: bool = False
    name: str = ""
    provider: str = ""
    model: str = ""
    base_url: str = ""
    protocol: str = ""
    auth_type: str = "api_key"
    auth_header: str = ""
    api_version: str = ""
    organization: str = ""
    project: str = ""
    tenant: str = ""
    region: str = ""
    deployment: str = ""
    client_id: str = ""
    timeout_seconds: float = 20.0
    retries: int = 0
    max_output_tokens: int | None = None
    temperature: float | None = None
    store: bool = False
    extra_config: dict[str, Any] = field(default_factory=dict)

    api_key: SecretStr | None = None
    bearer_token: SecretStr | None = None
    client_secret: SecretStr | None = None
    access_token: SecretStr | None = None
    refresh_token: SecretStr | None = None
    private_key: SecretStr | None = None
    service_account_json: SecretStr | None = None
    extra_secret_json: SecretStr | None = None

    @classmethod
    def from_env(cls, slot: int) -> "AIVaultProfile":
        prefix = _profile_prefix(slot)

        raw_timeout = os.getenv(f"{prefix}_TIMEOUT_SECONDS") or "20"
        raw_retries = os.getenv(f"{prefix}_RETRIES") or "0"
        try:
            timeout_seconds = float(raw_timeout)
            retries = int(raw_retries)
        except ValueError as exc:
            raise ProviderConfigurationError("ai_vault_invalid_numeric_config") from exc
        if timeout_seconds <= 0 or retries < 0:
            raise ProviderConfigurationError("ai_vault_invalid_numeric_config")

        return cls(
            slot=slot,
            enabled=_parse_bool(os.getenv(f"{prefix}_ENABLED"), default=False),
            name=(os.getenv(f"{prefix}_NAME") or "").strip(),
            provider=(os.getenv(f"{prefix}_PROVIDER") or "").strip().lower(),
            model=(os.getenv(f"{prefix}_MODEL") or "").strip(),
            base_url=(os.getenv(f"{prefix}_BASE_URL") or "").strip(),
            protocol=(os.getenv(f"{prefix}_PROTOCOL") or "").strip().lower(),
            auth_type=(os.getenv(f"{prefix}_AUTH_TYPE") or "api_key").strip().lower(),
            auth_header=(os.getenv(f"{prefix}_AUTH_HEADER") or "").strip(),
            api_version=(os.getenv(f"{prefix}_API_VERSION") or "").strip(),
            organization=(os.getenv(f"{prefix}_ORGANIZATION") or "").strip(),
            project=(os.getenv(f"{prefix}_PROJECT") or "").strip(),
            tenant=(os.getenv(f"{prefix}_TENANT") or "").strip(),
            region=(os.getenv(f"{prefix}_REGION") or "").strip(),
            deployment=(os.getenv(f"{prefix}_DEPLOYMENT") or "").strip(),
            client_id=(os.getenv(f"{prefix}_CLIENT_ID") or "").strip(),
            timeout_seconds=timeout_seconds,
            retries=retries,
            max_output_tokens=_parse_optional_int(os.getenv(f"{prefix}_MAX_OUTPUT_TOKENS")),
            temperature=_parse_optional_float(os.getenv(f"{prefix}_TEMPERATURE")),
            store=_parse_bool(os.getenv(f"{prefix}_STORE"), default=False),
            extra_config=_parse_json_object(os.getenv(f"{prefix}_EXTRA_CONFIG_JSON")),
            api_key=_secret(os.getenv(f"{prefix}_API_KEY")),
            bearer_token=_secret(os.getenv(f"{prefix}_BEARER_TOKEN")),
            client_secret=_secret(os.getenv(f"{prefix}_CLIENT_SECRET")),
            access_token=_secret(os.getenv(f"{prefix}_ACCESS_TOKEN")),
            refresh_token=_secret(os.getenv(f"{prefix}_REFRESH_TOKEN")),
            private_key=_secret(os.getenv(f"{prefix}_PRIVATE_KEY")),
            service_account_json=_secret(os.getenv(f"{prefix}_SERVICE_ACCOUNT_JSON")),
            extra_secret_json=_secret(os.getenv(f"{prefix}_EXTRA_SECRET_JSON")),
        )

    def to_provider_config(self, *, role: str) -> AIProviderConfig:
        if not self.enabled:
            raise ProviderConfigurationError("ai_vault_profile_disabled")
        if not self.provider:
            raise ProviderConfigurationError("ai_provider_not_supported")
        if not self.model:
            raise ProviderConfigurationError("ai_provider_model_missing")
        if not self.base_url:
            raise ProviderConfigurationError("ai_provider_base_url_missing")

        # Existing adapters explicitly consume API_KEY only. Other stored secret
        # material remains sealed until a provider-specific adapter declares support.
        return AIProviderConfig(
            role=role,
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            store=self.store,
            retries=self.retries,
            timeout_seconds=self.timeout_seconds,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
        )

    def public_status(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "enabled": self.enabled,
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "protocol": self.protocol,
            "auth_type": self.auth_type,
            "api_version": self.api_version,
            "organization": self.organization,
            "project": self.project,
            "tenant": self.tenant,
            "region": self.region,
            "deployment": self.deployment,
            "client_id_configured": bool(self.client_id),
            "api_key_configured": self.api_key is not None,
            "bearer_token_configured": self.bearer_token is not None,
            "client_secret_configured": self.client_secret is not None,
            "access_token_configured": self.access_token is not None,
            "refresh_token_configured": self.refresh_token is not None,
            "private_key_configured": self.private_key is not None,
            "service_account_configured": self.service_account_json is not None,
            "extra_secret_configured": self.extra_secret_json is not None,
        }


@dataclass(frozen=True, slots=True)
class AIVault:
    profiles: tuple[AIVaultProfile, ...]
    system_profile_slot: int = 1
    agents_profile_slot: int = 2

    @classmethod
    def from_env(cls) -> "AIVault":
        profiles = [AIVaultProfile.from_env(slot) for slot in AI_VAULT_SLOTS]

        # Migration bridge: keep the two already-proven role credentials working
        # until the operator chooses to populate PROFILE_1 / PROFILE_2 explicitly.
        if not _profile_has_any_env(1):
            profiles[0] = _legacy_profile(role="system", slot=1)
        if not _profile_has_any_env(2):
            profiles[1] = _legacy_profile(role="agents", slot=2)

        system_slot = _selected_slot("MI_AI_SYSTEM_PROFILE", default=1)
        agents_slot = _selected_slot("MI_AI_AGENTS_PROFILE", default=2)
        return cls(
            profiles=tuple(profiles),
            system_profile_slot=system_slot,
            agents_profile_slot=agents_slot,
        )

    def profile(self, slot: int) -> AIVaultProfile:
        if slot not in AI_VAULT_SLOTS:
            raise ProviderConfigurationError("ai_vault_profile_slot_out_of_range")
        return self.profiles[slot - 1]

    def resolve(self, *, role: str) -> AIProviderConfig:
        normalized_role = role.strip().lower()
        if normalized_role == "system":
            slot = self.system_profile_slot
        elif normalized_role == "agents":
            slot = self.agents_profile_slot
        else:
            raise ProviderConfigurationError("ai_provider_role_not_supported")
        return self.profile(slot).to_provider_config(role=normalized_role)

    def public_status(self) -> dict[str, Any]:
        return {
            "capacity": AI_VAULT_PROFILE_COUNT,
            "system_profile_slot": self.system_profile_slot,
            "agents_profile_slot": self.agents_profile_slot,
            "profiles": [profile.public_status() for profile in self.profiles],
        }


def _selected_slot(env_name: str, *, default: int) -> int:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        return default
    try:
        slot = int(raw)
    except ValueError as exc:
        raise ProviderConfigurationError("ai_vault_profile_slot_out_of_range") from exc
    if slot not in AI_VAULT_SLOTS:
        raise ProviderConfigurationError("ai_vault_profile_slot_out_of_range")
    return slot


def _profile_has_any_env(slot: int) -> bool:
    prefix = f"{_profile_prefix(slot)}_"
    return any(name.startswith(prefix) for name in os.environ)


def _legacy_profile(*, role: str, slot: int) -> AIVaultProfile:
    config = AIProviderConfig.from_env(role=role)
    return AIVaultProfile(
        slot=slot,
        enabled=True,
        name="System GPT" if role == "system" else "Agents GLM",
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        protocol="openai-compatible" if config.provider in {"openai", "zai"} else config.provider,
        auth_type="api_key",
        timeout_seconds=config.timeout_seconds,
        retries=config.retries,
        max_output_tokens=config.max_output_tokens,
        temperature=config.temperature,
        store=config.store,
        api_key=config.api_key,
    )
