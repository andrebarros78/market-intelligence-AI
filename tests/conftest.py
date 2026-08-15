from __future__ import annotations

import asyncio
import os


def pytest_configure() -> None:
    """Use the psycopg-compatible event loop policy for Windows test processes."""
    if os.name != "nt":
        return
    policy_factory = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_factory is None:
        raise RuntimeError("windows_selector_event_loop_policy_unavailable")
    asyncio.set_event_loop_policy(policy_factory())
