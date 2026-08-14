import httpx
import pytest
from pydantic import SecretStr

from market_intelligence.ai import AIProviderConfig, ProviderManager, ZAIDriver
from market_intelligence.ai.rate_limited_providers import RateLimitedZAIDriver


@pytest.mark.asyncio
async def test_zai_adapter_honors_retry_after_and_retries_once() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                request=request,
                headers={"Retry-After": "0"},
                json={"error": {"code": "1305"}},
            )
        return httpx.Response(
            200,
            request=request,
            json={"data": [{"id": "glm-4.7-flash"}]},
        )

    config = AIProviderConfig(
        role="agents",
        provider="zai",
        model="glm-4.7-flash",
        base_url="https://api.z.ai/api/paas/v4",
        api_key=SecretStr("synthetic-zai-key"),
        retries=1,
        timeout_seconds=5,
    )
    result = await RateLimitedZAIDriver(
        config,
        transport=httpx.MockTransport(handler),
    ).probe()

    assert calls == 2
    assert result.authenticated is True
    assert result.model_available is True
    assert result.business_data_sent is False


def test_default_provider_manager_installs_guarded_zai_driver() -> None:
    config = AIProviderConfig(
        role="agents",
        provider="zai",
        model="glm-4.7-flash",
        base_url="https://api.z.ai/api/paas/v4",
        api_key=SecretStr("synthetic-zai-key"),
    )

    driver = ProviderManager().build(config)

    assert isinstance(driver, RateLimitedZAIDriver)
    assert isinstance(driver, ZAIDriver)
