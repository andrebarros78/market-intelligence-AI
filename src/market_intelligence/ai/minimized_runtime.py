from __future__ import annotations

import hashlib
from time import perf_counter
from typing import Any

from pydantic import BaseModel

from market_intelligence.ai.data_gateway import AIDataGatewayResult
from market_intelligence.ai.inference_contract import (
    AIAnalysisResponse,
    AIInferencePromptEnvelope,
    build_minimized_inference_prompt,
    parse_minimized_ai_response,
)
from market_intelligence.ai.providers import (
    AIProviderConfig,
    OpenAIResponsesDriver,
    ProviderConfigurationError,
    ZAIDriver as BaseZAIDriver,
    _extract_openai_output_text,
    _extract_zai_output_text,
    _optional_int,
)
from market_intelligence.ai.rate_limited_providers import ProviderManager


class AIMinimizedInferenceResult(BaseModel):
    role: str
    provider: str
    model: str
    endpoint_host: str
    purpose: str
    gateway_policy_version: str
    gateway_output_sha256: str
    contract_version: str
    prompt_sha256: str
    output_sha256: str
    output_length_chars: int
    analysis: AIAnalysisResponse
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int
    store_enabled: bool = False
    business_data_minimized: bool = True
    credential_exposed: bool = False
    pii_exposed: bool = False


async def execute_minimized_inference(
    config: AIProviderConfig,
    gateway_result: AIDataGatewayResult,
    *,
    driver: Any | None = None,
) -> AIMinimizedInferenceResult:
    """Execute one bounded inference from an attested minimized envelope.

    This function deliberately has no raw-prompt parameter. Callers can supply
    only an AIDataGatewayResult, which is transformed into the fixed IA-05
    contract before the provider adapter is invoked.
    """

    if config.store:
        raise ProviderConfigurationError("ai_minimized_store_must_be_false")
    envelope = build_minimized_inference_prompt(gateway_result)
    selected = driver or ProviderManager().build(config)

    if config.provider == "openai":
        if not isinstance(selected, OpenAIResponsesDriver):
            raise ProviderConfigurationError("ai_provider_driver_mismatch")
        raw_text, usage, endpoint_host, latency_ms = await _execute_openai(
            selected, envelope
        )
    elif config.provider == "zai":
        if not isinstance(selected, BaseZAIDriver):
            raise ProviderConfigurationError("ai_provider_driver_mismatch")
        raw_text, usage, endpoint_host, latency_ms = await _execute_zai(selected, envelope)
    else:
        raise ProviderConfigurationError("ai_minimized_provider_not_supported")

    analysis = parse_minimized_ai_response(raw_text, source_gateway=gateway_result)
    normalized_output = raw_text.strip()
    return AIMinimizedInferenceResult(
        role=config.role,
        provider=config.provider,
        model=config.model,
        endpoint_host=endpoint_host,
        purpose=gateway_result.purpose,
        gateway_policy_version=gateway_result.policy_version,
        gateway_output_sha256=gateway_result.output_sha256,
        contract_version=envelope.contract_version,
        prompt_sha256=envelope.prompt_sha256,
        output_sha256=hashlib.sha256(normalized_output.encode("utf-8")).hexdigest(),
        output_length_chars=len(normalized_output),
        analysis=analysis,
        input_tokens=usage[0],
        output_tokens=usage[1],
        total_tokens=usage[2],
        latency_ms=latency_ms,
        store_enabled=False,
        business_data_minimized=True,
        credential_exposed=False,
        pii_exposed=False,
    )


async def _execute_openai(
    driver: OpenAIResponsesDriver,
    envelope: AIInferencePromptEnvelope,
) -> tuple[str, tuple[int | None, int | None, int | None], str, int]:
    api_key = driver._api_key_value()
    started = perf_counter()
    response = await driver._request(
        method="POST",
        path="responses",
        headers={"Authorization": f"Bearer {api_key}"},
        json_body={
            "model": driver._config.model,
            "input": envelope.prompt,
            "max_output_tokens": envelope.max_output_tokens,
            "store": False,
        },
    )
    latency_ms = max(0, round((perf_counter() - started) * 1000))
    driver._check_response_status(response, operation="inference")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderConfigurationError("ai_provider_invalid_inference_response") from exc
    if not isinstance(payload, dict):
        raise ProviderConfigurationError("ai_provider_invalid_inference_response")
    raw_text = _extract_openai_output_text(payload)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return (
        raw_text,
        (
            _optional_int(usage.get("input_tokens")),
            _optional_int(usage.get("output_tokens")),
            _optional_int(usage.get("total_tokens")),
        ),
        driver.allowed_host,
        latency_ms,
    )


async def _execute_zai(
    driver: BaseZAIDriver,
    envelope: AIInferencePromptEnvelope,
) -> tuple[str, tuple[int | None, int | None, int | None], str, int]:
    api_key = driver._api_key_value()
    started = perf_counter()
    response = await driver._request(
        method="POST",
        path="chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json_body={
            "model": driver._config.model,
            "messages": [{"role": "user", "content": envelope.prompt}],
            "thinking": {"type": "disabled"},
            "stream": False,
            "max_tokens": envelope.max_output_tokens,
            "temperature": envelope.temperature,
        },
    )
    latency_ms = max(0, round((perf_counter() - started) * 1000))
    driver._check_response_status(response, operation="inference")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderConfigurationError("ai_provider_invalid_inference_response") from exc
    if not isinstance(payload, dict):
        raise ProviderConfigurationError("ai_provider_invalid_inference_response")
    raw_text = _extract_zai_output_text(payload)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return (
        raw_text,
        (
            _optional_int(usage.get("prompt_tokens")),
            _optional_int(usage.get("completion_tokens")),
            _optional_int(usage.get("total_tokens")),
        ),
        driver.allowed_host,
        latency_ms,
    )
