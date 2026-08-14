from __future__ import annotations

import os

from market_intelligence.ai import AIProviderConfig


def _safe_status(role: str) -> dict[str, object]:
    config = AIProviderConfig.from_env(role=role)
    return {
        "role": config.role,
        "provider": config.provider,
        "model": config.model,
        "configured": config.api_key is not None,
        "credential_exposed": False,
        "inference_enabled": False,
    }


def test_system_and_agents_runtime_status_never_exposes_secret(monkeypatch) -> None:
    monkeypatch.setenv("MI_AI_SYSTEM_API_KEY", "system-super-secret")
    monkeypatch.setenv("MI_AI_AGENTS_API_KEY", "agents-super-secret")
    monkeypatch.setenv("MI_AI_SYSTEM_PROVIDER", "gemini")
    monkeypatch.setenv("MI_AI_AGENTS_PROVIDER", "gemini")

    system = _safe_status("system")
    agents = _safe_status("agents")

    rendered = repr({"system": system, "agents": agents})
    assert system["configured"] is True
    assert agents["configured"] is True
    assert system["credential_exposed"] is False
    assert agents["credential_exposed"] is False
    assert system["inference_enabled"] is False
    assert agents["inference_enabled"] is False
    assert os.environ["MI_AI_SYSTEM_API_KEY"] not in rendered
    assert os.environ["MI_AI_AGENTS_API_KEY"] not in rendered
