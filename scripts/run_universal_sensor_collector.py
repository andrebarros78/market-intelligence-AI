from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from market_intelligence.core.event_loop import psycopg_compatible_loop
from market_intelligence.marketplaces.mercadolivre.full_read_collector import (
    MercadoLivreFullReadCollector,
)
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import SnapshotRecord
from market_intelligence.sensors.history import HistoricalMemoryService


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=300.0)
    parser.add_argument("--max-items-per-cycle", type=int, default=20)
    parser.add_argument("--status-path", default="runtime/sensors/status.json")
    return parser.parse_args()


def policy() -> None:
    if os.getenv("MI_READ_ONLY", "true").lower() != "true":
        raise RuntimeError("sensor_collector_requires_read_only")
    if os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").lower() != "false":
        raise RuntimeError("sensor_collector_forbids_marketplace_writes")


def write_status(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


async def cycle(db: str, max_items: int) -> dict:
    engine = create_database_engine(db)
    sessions = create_session_factory(engine)
    try:
        report = await MercadoLivreFullReadCollector(
            sessions, max_items_per_cycle=max_items
        ).collect_once()
        memory = await HistoricalMemoryService(sessions).summary()
        async with sessions() as session:
            snapshot_rows = (
                await session.execute(
                    select(SnapshotRecord.entity_type, func.count())
                    .where(SnapshotRecord.marketplace == "mercadolivre")
                    .group_by(SnapshotRecord.entity_type)
                )
            ).all()
        snapshot_totals = {str(entity_type): int(count) for entity_type, count in snapshot_rows}
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "collector_state": "ACTIVE",
            "runtime_scope": "universal_multimarketplace",
            "active_marketplaces": ["mercadolivre"],
            "pending_external_authorization": ["shopee"],
            "mercadolivre_success": report.success,
            "mercadolivre_items_seen": report.items_seen,
            "mercadolivre_item_snapshots": report.item_snapshots,
            "mercadolivre_item_snapshots_new_this_cycle": report.item_snapshots,
            "mercadolivre_order_snapshots": report.order_snapshots,
            "mercadolivre_order_snapshots_new_this_cycle": report.order_snapshots,
            "mercadolivre_snapshot_totals": snapshot_totals,
            "mercadolivre_questions_seen": report.questions_seen,
            "mercadolivre_claims_seen": report.claims_seen,
            "mercadolivre_claims_current_open": report.claims_seen,
            "mercadolivre_channel_events_new": report.channel_events,
            "mercadolivre_errors": list(report.errors),
            "sondador_surface_events_considered": report.surface_events_considered,
            "sondador_surface_resources_fetched": report.surface_resources_fetched,
            "sondador_surface_events_new": report.surface_events_new,
            "sondador_surface_events_skipped_privacy_or_unsupported": report.surface_events_skipped_privacy_or_unsupported,
            "sondador_surface_probe_failures": report.surface_probe_failures,
            "token_refreshed": report.token_refreshed,
            "memory_raw_events": memory.raw_events,
            "memory_channel_events": memory.channel_events,
            "memory_snapshots": memory.snapshots,
            "memory_evidence": memory.evidence,
            "memory_marketplaces": list(memory.marketplaces),
            "memory_oldest_snapshot_at": memory.oldest_snapshot_at.isoformat() if memory.oldest_snapshot_at else None,
            "memory_newest_snapshot_at": memory.newest_snapshot_at.isoformat() if memory.newest_snapshot_at else None,
            "permanent_read_only": True,
            "permanent_marketplace_writes": False,
            "new_marketplace_write_executed": False,
        }
    finally:
        await engine.dispose()


async def run(db: str, status: Path, interval: float, max_items: int, once: bool) -> int:
    while True:
        try:
            data = await cycle(db, max_items)
            write_status(status, data)
            if once:
                print(json.dumps(data, sort_keys=True, separators=(",", ":")))
                return 0
        except Exception as exc:
            data = {
                "timestamp": datetime.now(UTC).isoformat(),
                "collector_state": "DEGRADED_RETRYING",
                "error": type(exc).__name__,
                "runtime_scope": "universal_multimarketplace",
                "permanent_read_only": True,
                "permanent_marketplace_writes": False,
                "new_marketplace_write_executed": False,
            }
            write_status(status, data)
            if once:
                print(json.dumps(data, sort_keys=True, separators=(",", ":")))
                return 1
        await asyncio.sleep(max(30.0, interval))


def main() -> int:
    policy()
    parsed = args()
    database_url = (os.getenv("MI_DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("MI_DATABASE_URL_missing")
    status = Path(parsed.status_path)
    status = status if status.is_absolute() else Path(__file__).resolve().parents[1] / status
    with asyncio.Runner(loop_factory=psycopg_compatible_loop) as runner:
        return runner.run(
            run(
                database_url,
                status,
                parsed.interval_seconds,
                parsed.max_items_per_cycle,
                parsed.once,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
