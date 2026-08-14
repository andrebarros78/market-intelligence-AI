from __future__ import annotations

import argparse
import asyncio
import json
import sys

from market_intelligence.ai import AIProviderConfig, ProviderConfigurationError, ProviderManager


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe an AI provider without inference or business data.")
    parser.add_argument("--role", choices=("system", "agents"), default="system")
    return parser


async def _run(role: str) -> int:
    try:
        config = AIProviderConfig.from_env(role=role)
        driver = ProviderManager().build(config)
        result = await driver.probe()
    except ProviderConfigurationError as exc:
        print(json.dumps({"status": "failed", "role": role, "code": exc.code}, sort_keys=True))
        return 2

    payload = result.model_dump(mode="json")
    payload["status"] = "ok" if result.model_available else "model_unavailable"
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.authenticated and result.model_available else 3


if __name__ == "__main__":
    args = _parser().parse_args()
    sys.exit(asyncio.run(_run(args.role)))
