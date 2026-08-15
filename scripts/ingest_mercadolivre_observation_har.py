from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.marketplaces.mercadolivre.observation_lab import analyze_har
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.postgresql import PostgresRawEventRepository, database_healthcheck


def _policy() -> None:
    if os.getenv("MI_READ_ONLY", "true").strip().lower() != "true":
        raise RuntimeError("observation_lab_requires_read_only")
    if os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").strip().lower() != "false":
        raise RuntimeError("observation_lab_forbids_marketplace_writes")


async def ingest(path: Path, database_url: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = analyze_har(payload)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    inserted = 0
    try:
        if not await database_healthcheck(sessions):
            raise RuntimeError("observation_lab_database_health_failed")
        repository = PostgresRawEventRepository(sessions)
        observed_at = datetime.now(UTC)
        for observation in report.observations:
            safe = observation.as_safe_payload()
            event = build_raw_event(
                source="mercadolivre_observation_lab",
                event_type="har_surface",
                external_id=observation.surface_key,
                resource=observation.path_template,
                occurred_at=observed_at,
                received_at=observed_at,
                payload=safe,
            )
            inserted += int(await repository.append_if_new(event))
        return {
            "source_file": path.name,
            "entries_total": report.entries_total,
            "entries_in_scope": report.entries_in_scope,
            "entries_skipped": report.entries_skipped,
            "unique_surfaces": report.unique_surfaces,
            "new_surface_events": inserted,
            "methods": report.methods,
            "credential_headers_observed": report.credential_headers_observed,
            "values_persisted": False,
            "network_requests_executed": 0,
            "marketplace_writes": 0,
        }
    finally:
        await engine.dispose()


def main() -> int:
    _policy()
    parser = argparse.ArgumentParser()
    parser.add_argument("har", type=Path)
    args = parser.parse_args()
    if not args.har.is_file():
        raise SystemExit("HAR file not found")
    database_url = (os.getenv("MI_DATABASE_URL") or "").strip()
    if not database_url:
        raise SystemExit("MI_DATABASE_URL is required")
    result = asyncio.run(ingest(args.har, database_url))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
