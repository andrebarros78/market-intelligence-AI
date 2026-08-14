from __future__ import annotations

import os

from market_intelligence.ai.status import runtime_ai_status


def test_system_and_agents_runtime_status_never_exposes_secret(monkeypatch) -> None:
    monkeypatch.setenv("MI_AI_SYSTEM_API_KEY", "system-super-secret")
    monkeypatch.setenv("MI_AI_AGENTS_API_KEY", "agents-super-secret")
    monkeypatch.setenv("MI_AI_SYSTEM_PROVIDER", "openai")
    monkeypatch.setenv("MI_AI_SYSTEM_MODEL", "gpt-5-mini")
    monkeypatch.setenv("MI_AI_AGENTS_PROVIDER", "gemini")
    monkeypatch.setenv("MI_AI_AGENTS_MODEL", "gemini-3.6-flash")

    status = runtime_ai_status()
    system = status["system"]
    agents = status["agents"]

    rendered = repr(status)
    assert system["configured"] is True
    assert agents["configured"] is True
    assert system["provider"] == "openai"
    assert agents["provider"] == "gemini"
    assert system["credential_exposed"] is False
    assert agents["credential_exposed"] is False
    assert system["inference_enabled"] is False
    assert agents["inference_enabled"] is False
    assert system["endpoint_host"] == "api.openai.com"
    assert agents["endpoint_host"] == "generativelanguage.googleapis.com"
    assert os.environ["MI_AI_SYSTEM_API_KEY"] not in rendered
    assert os.environ["MI_AI_AGENTS_API_KEY"] not in rendered


def test_missing_agent_key_is_reported_without_falling_back(monkeypatch) -> None:
    monkeypatch.setenv("MI_AI_SYSTEM_API_KEY", "system-super-secret")
    monkeypatch.setenv("MI_AI_SYSTEM_PROVIDER", "openai")
    monkeypatch.delenv("MI_AI_AGENTS_API_KEY", raising=False)
    monkeypatch.delenv("MI_AI_API_KEY", raising=False)

    status = runtime_ai_status()
    assert status["system"]["configured"] is True
    assert status["agents"]["configured"] is False
