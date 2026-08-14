from __future__ import annotations

import os

from market_intelligence.ai.status import runtime_ai_status


def _clear_profile_env(monkeypatch) -> None:
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
            "API_KEY",
        ):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    monkeypatch.delenv("MI_AI_SYSTEM_PROFILE", raising=False)
    monkeypatch.delenv("MI_AI_AGENTS_PROFILE", raising=False)


def test_system_and_agents_runtime_status_never_exposes_secret(monkeypatch) -> None:
    _clear_profile_env(monkeypatch)
    monkeypatch.setenv("MI_AI_SYSTEM_API_KEY", "system-super-secret")
    monkeypatch.setenv("MI_AI_AGENTS_API_KEY", "agents-super-secret")
    monkeypatch.setenv("MI_AI_SYSTEM_PROVIDER", "openai")
    monkeypatch.setenv("MI_AI_SYSTEM_MODEL", "gpt-5-mini")
    monkeypatch.setenv("MI_AI_AGENTS_PROVIDER", "zai")
    monkeypatch.setenv("MI_AI_AGENTS_MODEL", "glm-5.1")

    status = runtime_ai_status()
    system = status["system"]
    agents = status["agents"]

    rendered = repr(status)
    assert system["configured"] is True
    assert agents["configured"] is True
    assert system["profile_slot"] == 1
    assert agents["profile_slot"] == 2
    assert system["provider"] == "openai"
    assert agents["provider"] == "zai"
    assert system["credential_exposed"] is False
    assert agents["credential_exposed"] is False
    assert system["inference_enabled"] is False
    assert agents["inference_enabled"] is False
    assert system["endpoint_host"] == "api.openai.com"
    assert agents["endpoint_host"] == "api.z.ai"
    assert os.environ["MI_AI_SYSTEM_API_KEY"] not in rendered
    assert os.environ["MI_AI_AGENTS_API_KEY"] not in rendered


def test_runtime_status_uses_explicit_profile_1_and_2_over_legacy(monkeypatch) -> None:
    _clear_profile_env(monkeypatch)
    monkeypatch.setenv("MI_AI_SYSTEM_API_KEY", "legacy-system-secret")
    monkeypatch.setenv("MI_AI_AGENTS_API_KEY", "legacy-agents-secret")

    profile_1 = "MI_AI_PROFILE_1"
    monkeypatch.setenv(f"{profile_1}_ENABLED", "true")
    monkeypatch.setenv(f"{profile_1}_NAME", "System GPT Profile")
    monkeypatch.setenv(f"{profile_1}_PROVIDER", "openai")
    monkeypatch.setenv(f"{profile_1}_MODEL", "gpt-5-mini")
    monkeypatch.setenv(f"{profile_1}_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv(f"{profile_1}_API_KEY", "profile-system-secret")

    profile_2 = "MI_AI_PROFILE_2"
    monkeypatch.setenv(f"{profile_2}_ENABLED", "true")
    monkeypatch.setenv(f"{profile_2}_NAME", "Agents GLM Profile")
    monkeypatch.setenv(f"{profile_2}_PROVIDER", "zai")
    monkeypatch.setenv(f"{profile_2}_MODEL", "glm-5.1")
    monkeypatch.setenv(f"{profile_2}_BASE_URL", "https://api.z.ai/api/paas/v4")
    monkeypatch.setenv(f"{profile_2}_API_KEY", "profile-agents-secret")
    monkeypatch.setenv("MI_AI_SYSTEM_PROFILE", "1")
    monkeypatch.setenv("MI_AI_AGENTS_PROFILE", "2")

    status = runtime_ai_status()
    rendered = repr(status)

    assert status["system"]["profile_slot"] == 1
    assert status["system"]["profile_name"] == "System GPT Profile"
    assert status["agents"]["profile_slot"] == 2
    assert status["agents"]["profile_name"] == "Agents GLM Profile"
    assert "profile-system-secret" not in rendered
    assert "profile-agents-secret" not in rendered
    assert "legacy-system-secret" not in rendered
    assert "legacy-agents-secret" not in rendered


def test_missing_agent_key_is_reported_without_falling_back(monkeypatch) -> None:
    _clear_profile_env(monkeypatch)
    monkeypatch.setenv("MI_AI_SYSTEM_API_KEY", "system-super-secret")
    monkeypatch.setenv("MI_AI_SYSTEM_PROVIDER", "openai")
    monkeypatch.delenv("MI_AI_AGENTS_API_KEY", raising=False)
    monkeypatch.delenv("MI_AI_API_KEY", raising=False)

    status = runtime_ai_status()
    assert status["system"]["configured"] is True
    assert status["agents"]["configured"] is False
    assert status["agents"]["provider"] == "zai"
