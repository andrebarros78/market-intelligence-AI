from __future__ import annotations

import asyncio
import sys


def psycopg_compatible_loop(*, use_subprocess: bool = False) -> asyncio.AbstractEventLoop:
    """Return an event loop compatible with psycopg async connections.

    Psycopg async mode is incompatible with Windows' default ProactorEventLoop.
    Uvicorn calls custom loop factories with ``use_subprocess``; the webhook
    runtime does not spawn subprocesses, so the argument is intentionally
    ignored and a SelectorEventLoop is used on Windows.
    """
    del use_subprocess
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()
