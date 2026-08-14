from __future__ import annotations

import argparse
import asyncio
import os

from temporalio.client import Client

from market_intelligence.workflows.ai_worker import build_ai_temporal_worker


async def _run(*, role: str) -> None:
    address = os.getenv("MI_TEMPORAL_ADDRESS", "localhost:7233").strip()
    namespace = os.getenv("MI_TEMPORAL_NAMESPACE", "default").strip()
    if not address or not namespace:
        raise RuntimeError("temporal_configuration_missing")

    client = await Client.connect(address, namespace=namespace)
    worker = build_ai_temporal_worker(client, role=role)
    await worker.run()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the dedicated API ML Temporal AI worker.")
    parser.add_argument("--role", choices=("system", "agents"), required=True)
    args = parser.parse_args()
    asyncio.run(_run(role=args.role))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
