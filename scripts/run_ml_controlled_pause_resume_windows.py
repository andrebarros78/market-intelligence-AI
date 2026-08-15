from __future__ import annotations

import asyncio
import os

from scripts.run_ml_controlled_pause_resume import main


def _run() -> int:
    if os.name == "nt":
        policy_factory = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if policy_factory is None:
            raise RuntimeError("windows_selector_event_loop_policy_unavailable")
        asyncio.set_event_loop_policy(policy_factory())
    return asyncio.run(main())


if __name__ == "__main__":
    raise SystemExit(_run())
