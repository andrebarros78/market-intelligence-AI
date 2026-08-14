from __future__ import annotations

import argparse
import asyncio
import json

from market_intelligence.ai import AIVault, ProviderConfigurationError, ProviderManager


async def _run(role: str) -> int:
    try:
        config = AIVault.from_env().resolve(role=role)
        driver = ProviderManager().build(config)
        sandbox_infer = getattr(driver, "sandbox_infer", None)
        if sandbox_infer is None:
            raise ProviderConfigurationError("ai_provider_sandbox_inference_not_supported")
        result = await sandbox_infer()
        payload = result.model_dump(mode="json")
        payload["status"] = "ok" if result.expected_output_match else "mismatch"
        print(json.dumps(payload, sort_keys=True))
        return 0 if result.expected_output_match else 2
    except ProviderConfigurationError as exc:
        print(json.dumps({"status": "error", "error": exc.code, "role": role}, sort_keys=True))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run exactly one fixed synthetic AI sandbox inference for a configured role."
    )
    parser.add_argument("--role", choices=("system", "agents"), required=True)
    args = parser.parse_args()
    return asyncio.run(_run(args.role))


if __name__ == "__main__":
    raise SystemExit(main())
