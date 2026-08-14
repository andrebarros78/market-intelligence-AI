from __future__ import annotations

import asyncio

from market_intelligence.core import event_loop as event_loop_module


def test_psycopg_compatible_loop_uses_selector_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(event_loop_module.sys, "platform", "win32")

    loop = event_loop_module.psycopg_compatible_loop(use_subprocess=False)
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()


def test_psycopg_compatible_loop_uses_platform_default_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(event_loop_module.sys, "platform", "linux")

    loop = event_loop_module.psycopg_compatible_loop(use_subprocess=False)
    try:
        assert isinstance(loop, asyncio.AbstractEventLoop)
    finally:
        loop.close()
