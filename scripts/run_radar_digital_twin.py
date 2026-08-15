from __future__ import annotations

import asyncio
import json
import os

from market_intelligence.core.event_loop import psycopg_compatible_loop
from market_intelligence.digital_twin import run_radar_v1_digital_twin


async def _run() -> int:
    database_url = (os.getenv("MI_DATABASE_URL") or os.getenv("TEST_DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("digital_twin_database_configuration_missing")
    report = await run_radar_v1_digital_twin(database_url)
    print(json.dumps(report.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))
    return 0 if report.sandbox_passed else 1


def main() -> int:
    with asyncio.Runner(loop_factory=psycopg_compatible_loop) as runner:
        return runner.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
