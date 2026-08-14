from __future__ import annotations

import argparse
import asyncio
import os

from temporalio.client import Client

from market_intelligence.persistence.ai_audit import PostgresAIInferenceAuditRepository
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.workflows.ai_worker import build_ai_temporal_worker


async def _run(*, role: str) -> None:
    address = os.getenv("MI_TEMPORAL_ADDRESS", "localhost:7233").strip()
    namespace = os.getenv("MI_TEMPORAL_NAMESPACE", "default").strip()
    database_url = (os.getenv("MI_DATABASE_URL") or "").strip()
    if not address or not namespace:
        raise RuntimeError("temporal_configuration_missing")
    if not database_url:
        raise RuntimeError("ai_audit_database_configuration_missing")

    temporal = await Client.connect(address, namespace=namespace)
    database = create_database_engine(database_url)
    sessions = create_session_factory(database)
    audit_repo = PostgresAIInferenceAuditRepository(sessions)
    try:
        worker = build_ai_temporal_worker(temporal, role=role, audit_repo=audit_repo)
        await worker.run()
    finally:
        await database.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the dedicated API ML Temporal AI worker.")
    parser.add_argument("--role", choices=("system", "agents"), required=True)
    args = parser.parse_args()
    asyncio.run(_run(role=args.role))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
