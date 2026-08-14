from __future__ import annotations

import argparse
import asyncio
import json
import sys

from market_intelligence.ai import AIVault, ProviderConfigurationError, ProviderManager
from market_intelligence.ai.probe_policy import classify_probe_result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe an AI provider without inference or business data.")
    parser.add_argument("--role", choices=("system", "agents"), default="system")
    parser.add_argument(
        "--allow-model-unlisted",
        action="store_true",
        help=(
            "Treat authenticated access as a successful connectivity gate even when "
            "the provider catalog does not list the configured model. The JSON output "
            "still reports model_available=false."
        ),
    )
    return parser


async def _run(role: str, *, allow_model_unlisted: bool = False) -> int:
    try:
        config = AIVault.from_env().resolve(role=role)
        driver = ProviderManager().build(config)
        result = await driver.probe()
    except ProviderConfigurationError as exc:
        print(json.dumps({"status": "failed", "role": role, "code": exc.code}, sort_keys=True))
        return 2

    decision = classify_probe_result(
        authenticated=result.authenticated,
        model_available=result.model_available,
        allow_model_unlisted=allow_model_unlisted,
    )
    payload = result.model_dump(mode="json")
    payload["status"] = decision.status
    payload["model_listing_advisory"] = bool(
        allow_model_unlisted and result.authenticated and not result.model_available
    )
    print(json.dumps(payload, sort_keys=True))
    return decision.exit_code


if __name__ == "__main__":
    args = _parser().parse_args()
    sys.exit(
        asyncio.run(
            _run(
                args.role,
                allow_model_unlisted=args.allow_model_unlisted,
            )
        )
    )
