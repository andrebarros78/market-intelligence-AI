from __future__ import annotations

from urllib.parse import urlsplit

from market_intelligence.ai.vault import AIVault


def role_status(role: str, *, vault: AIVault | None = None) -> dict[str, object]:
    resolved_vault = vault or AIVault.from_env()
    normalized_role = role.strip().lower()
    if normalized_role == "system":
        slot = resolved_vault.system_profile_slot
    elif normalized_role == "agents":
        slot = resolved_vault.agents_profile_slot
    else:
        # Delegate validation/error contract to the vault resolver.
        resolved_vault.resolve(role=normalized_role)
        raise AssertionError("unreachable")

    profile = resolved_vault.profile(slot)
    config = resolved_vault.resolve(role=normalized_role)
    return {
        "role": config.role,
        "profile_slot": slot,
        "profile_name": profile.name,
        "profile_enabled": profile.enabled,
        "provider": config.provider,
        "model": config.model,
        "endpoint_host": urlsplit(config.base_url).hostname,
        "configured": config.api_key is not None,
        "credential_exposed": False,
        "inference_enabled": False,
        "store_enabled": config.store,
        "retries": config.retries,
    }


def runtime_ai_status(vault: AIVault | None = None) -> dict[str, dict[str, object]]:
    resolved_vault = vault or AIVault.from_env()
    return {
        "system": role_status("system", vault=resolved_vault),
        "agents": role_status("agents", vault=resolved_vault),
    }
