from __future__ import annotations

from fastapi.testclient import TestClient

from market_intelligence.api.app import create_app


def _configure_two_profiles(monkeypatch) -> None:
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

    monkeypatch.setenv("MI_AI_SYSTEM_PROFILE", "1")
    monkeypatch.setenv("MI_AI_AGENTS_PROFILE", "2")

    monkeypatch.setenv("MI_AI_PROFILE_1_ENABLED", "true")
    monkeypatch.setenv("MI_AI_PROFILE_1_NAME", "System GPT")
    monkeypatch.setenv("MI_AI_PROFILE_1_PROVIDER", "openai")
    monkeypatch.setenv("MI_AI_PROFILE_1_MODEL", "gpt-5-mini")
    monkeypatch.setenv("MI_AI_PROFILE_1_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("MI_AI_PROFILE_1_PROTOCOL", "openai-compatible")
    monkeypatch.setenv("MI_AI_PROFILE_1_AUTH_TYPE", "api_key")
    monkeypatch.setenv("MI_AI_PROFILE_1_API_KEY", "system-profile-secret")

    monkeypatch.setenv("MI_AI_PROFILE_2_ENABLED", "true")
    monkeypatch.setenv("MI_AI_PROFILE_2_NAME", "Agents GLM-4.7-Flash")
    monkeypatch.setenv("MI_AI_PROFILE_2_PROVIDER", "zai")
    monkeypatch.setenv("MI_AI_PROFILE_2_MODEL", "glm-4.7-flash")
    monkeypatch.setenv("MI_AI_PROFILE_2_BASE_URL", "https://api.z.ai/api/paas/v4")
    monkeypatch.setenv("MI_AI_PROFILE_2_PROTOCOL", "openai-compatible")
    monkeypatch.setenv("MI_AI_PROFILE_2_AUTH_TYPE", "api_key")
    monkeypatch.setenv("MI_AI_PROFILE_2_API_KEY", "agents-profile-secret")


def test_ready_reports_selected_ai_profiles_without_enabling_inference(monkeypatch) -> None:
    _configure_two_profiles(monkeypatch)
    client = TestClient(create_app())

    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()

    assert body["ai_vault_capacity"] == 5
    assert body["ai_system_profile_slot"] == 1
    assert body["ai_agents_profile_slot"] == 2
    assert body["ai_system_configured"] is True
    assert body["ai_agents_configured"] is True
    assert body["ai_inference_enabled"] is False


def test_capabilities_exposes_vault_status_but_never_secret_values(monkeypatch) -> None:
    _configure_two_profiles(monkeypatch)
    client = TestClient(create_app())

    response = client.get("/v1/system/capabilities")
    assert response.status_code == 200
    ai = response.json()["ai"]
    rendered = repr(ai)

    assert ai["vault_capacity"] == 5
    assert ai["system_profile_slot"] == 1
    assert ai["agents_profile_slot"] == 2
    assert ai["system"]["provider"] == "openai"
    assert ai["system"]["model"] == "gpt-5-mini"
    assert ai["agents"]["provider"] == "zai"
    assert ai["agents"]["model"] == "glm-4.7-flash"
    assert len(ai["profiles"]) == 5
    assert ai["profiles"][0]["api_key_configured"] is True
    assert ai["profiles"][1]["api_key_configured"] is True
    assert ai["credential_values_exposed"] is False
    assert ai["inference_enabled"] is False
    assert "system-profile-secret" not in rendered
    assert "agents-profile-secret" not in rendered
