from __future__ import annotations

import pytest

from market_intelligence.intelligence.radar.runtime import _assert_read_only_policy


def test_radar_runtime_accepts_permanent_read_only_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MI_READ_ONLY", "true")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "false")
    _assert_read_only_policy()


def test_radar_runtime_rejects_read_only_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MI_READ_ONLY", "false")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "false")
    with pytest.raises(RuntimeError, match="radar_runtime_requires_read_only"):
        _assert_read_only_policy()


def test_radar_runtime_rejects_marketplace_writes_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MI_READ_ONLY", "true")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "true")
    with pytest.raises(RuntimeError, match="radar_runtime_forbids_marketplace_writes"):
        _assert_read_only_policy()
