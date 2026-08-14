from __future__ import annotations

import asyncio

import uvicorn

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


def test_uvicorn_imports_psycopg_compatible_loop_factory(monkeypatch) -> None:
    monkeypatch.setattr(event_loop_module.sys, "platform", "win32")

    config = uvicorn.Config(
        "market_intelligence.api.webhook_server:create_mercadolivre_webhook_app_from_env",
        factory=True,
        loop="market_intelligence.core.event_loop:psycopg_compatible_loop",
    )
    factory = config.get_loop_factory()
    assert factory is not None

    loop = factory()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()
