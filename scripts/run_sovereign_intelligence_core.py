from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from market_intelligence.intelligence.sovereign.runtime import run_forever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-path", type=Path, default=Path("runtime/sovereign-core/status.json"))
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--max-records", type=int, default=32)
    args = parser.parse_args()

    database_url = os.getenv("MI_DATABASE_URL")
    if not database_url:
        raise SystemExit("MI_DATABASE_URL is required")
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(
        run_forever(
            database_url,
            status_path=args.status_path,
            interval_seconds=args.interval_seconds,
            max_records=args.max_records,
        )
    )


if __name__ == "__main__":
    main()
