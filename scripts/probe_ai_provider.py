from __future__ import annotations

import asyncio
import json
import sys

from market_intelligence.ai import AIProviderConfig, ProviderConfigurationError, ProviderManager


async def _run() -> int:
    try:
        config = AIProviderConfig.from_env()
        driver = ProviderManager().build(config)
        result = await driver.probe()
    except ProviderConfigurationError as exc:
        print(json.dumps({"status": "failed", "code": exc.code}, sort_keys=True))
        return 2

    payload = result.model_dump(mode="json")
    payload["status"] = "ok" if result.model_available else "model_unavailable"
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.authenticated and result.model_available else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
