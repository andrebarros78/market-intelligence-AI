from __future__ import annotations

from urllib.parse import urlsplit

from market_intelligence.ai.providers import AIProviderConfig


def role_status(role: str) -> dict[str, object]:
    config = AIProviderConfig.from_env(role=role)
    return {
        "role": config.role,
        "provider": config.provider,
        "model": config.model,
        "endpoint_host": urlsplit(config.base_url).hostname,
        "configured": config.api_key is not None,
        "credential_exposed": False,
        "inference_enabled": False,
        "store_enabled": config.store,
        "retries": config.retries,
    }


def runtime_ai_status() -> dict[str, dict[str, object]]:
    return {
        "system": role_status("system"),
        "agents": role_status("agents"),
    }
