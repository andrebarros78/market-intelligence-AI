from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from market_intelligence.core.event_loop import psycopg_compatible_loop
from market_intelligence.intelligence.radar.unit import run_unit_cycle, run_unit_forever


def _database_url() -> str:
    value = os.getenv("MI_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("MI_DATABASE_URL_missing")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Radar Universal Sovereign Unit")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status-path", default="runtime/radar-unit/status.json")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    database_url = _database_url()
    status_path = Path(args.status_path)
    if not status_path.is_absolute():
        status_path = Path(__file__).resolve().parents[1] / status_path
    with asyncio.Runner(loop_factory=psycopg_compatible_loop) as runner:
        if args.once:
            report = runner.run(run_unit_cycle(database_url))
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return 0 if report["radar_health"] == "PASS" else 1
        runner.run(
            run_unit_forever(
                database_url,
                status_path=status_path,
                interval_seconds=args.interval_seconds,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
