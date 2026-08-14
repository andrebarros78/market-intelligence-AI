from __future__ import annotations

import asyncio
from typing import Any, Callable

import httpx

from market_intelligence.ai.providers import (
    AIProviderConfig,
    AIProviderDriver,
    ProviderConfigurationError,
    ProviderManager as BaseProviderManager,
    ZAIDriver as BaseZAIDriver,
)
from market_intelligence.ai.rate_control import ZAI_RETRY_POLICY, ZAI_TRAFFIC_GATE


class RateLimitedZAIDriver(BaseZAIDriver):
    """Z.AI adapter with one-process queueing and bounded backoff.

    The gate serializes local requests, honors Retry-After when present, and
    preserves a short cooldown after HTTP 429. It never inspects or logs the
    provider response body while deciding whether to retry.
    """

    async def _request(
        self,
        *,
        method: str,
        path: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        timeout = httpx.Timeout(self._config.timeout_seconds)
        async with httpx.AsyncClient(
            base_url=self._config.base_url.rstrip("/"),
            transport=self._transport,
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            for attempt in range(self._config.retries + 1):
                await ZAI_TRAFFIC_GATE.acquire()
                try:
                    try:
                        response = await client.request(
                            method,
                            path,
                            headers=headers,
                            json=json_body,
                        )
                    except (httpx.TimeoutException, httpx.TransportError) as exc:
                        if attempt < self._config.retries:
                            delay = ZAI_RETRY_POLICY.delay_seconds(attempt=attempt)
                            await asyncio.sleep(delay)
                            continue
                        raise ProviderConfigurationError(
                            "ai_provider_connectivity_failure"
                        ) from exc
                finally:
                    ZAI_TRAFFIC_GATE.release()

                if response.status_code == 429:
                    delay = ZAI_RETRY_POLICY.delay_seconds(
                        attempt=attempt,
                        retry_after=response.headers.get("Retry-After"),
                    )
                    ZAI_TRAFFIC_GATE.defer(delay)
                    if attempt < self._config.retries:
                        await asyncio.sleep(delay)
                        continue
                    return response

                if response.status_code in {500, 502, 503, 504} and attempt < self._config.retries:
                    delay = ZAI_RETRY_POLICY.delay_seconds(
                        attempt=attempt,
                        retry_after=response.headers.get("Retry-After"),
                    )
                    await asyncio.sleep(delay)
                    continue
                return response
        raise AssertionError("unreachable")


DriverFactory = Callable[[AIProviderConfig], AIProviderDriver]


class ProviderManager(BaseProviderManager):
    """Provider manager with the guarded Z.AI adapter installed by default."""

    def __init__(self, factories: dict[str, DriverFactory] | None = None) -> None:
        guarded_factories: dict[str, DriverFactory] = {
            "zai": lambda config: RateLimitedZAIDriver(config),
        }
        if factories:
            guarded_factories.update(factories)
        super().__init__(guarded_factories)
