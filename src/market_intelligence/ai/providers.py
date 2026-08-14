from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, SecretStr


class ProviderConfigurationError(RuntimeError):
    """Stable fail-closed error that never embeds credential material."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


AI_ROLES = {"system", "agents"}
SANDBOX_EXPECTED_OUTPUT = "SANDBOX_OK"
SANDBOX_PROMPT = (
    "Synthetic Market Intelligence AI sandbox test. Reply with exactly SANDBOX_OK and no other text."
)
SANDBOX_MAX_OUTPUT_TOKENS_LIMIT = 256

_PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "openai": ("gpt-5-mini", "https://api.openai.com/v1"),
    "gemini": ("gemini-3.6-flash", "https://generativelanguage.googleapis.com/v1beta"),
    "zai": ("glm-4.7-flash", "https://api.z.ai/api/paas/v4"),
}


@dataclass(frozen=True, slots=True)
class AIProviderConfig:
    role: str = "system"
    provider: str = "openai"
    model: str = "gpt-5-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr | None = None
    store: bool = False
    retries: int = 0
    timeout_seconds: float = 20.0
    max_output_tokens: int | None = None
    temperature: float | None = None

    @classmethod
    def from_env(cls, *, role: str = "system") -> "AIProviderConfig":
        normalized_role = role.strip().lower()
        if normalized_role not in AI_ROLES:
            raise ProviderConfigurationError("ai_provider_role_not_supported")

        role_prefix = f"MI_AI_{normalized_role.upper()}"
        is_system = normalized_role == "system"
        default_provider = "openai" if is_system else "zai"
        provider = (os.getenv(f"{role_prefix}_PROVIDER") or default_provider).strip().lower()

        defaults = _PROVIDER_DEFAULTS.get(provider)
        if defaults is None:
            default_model = ""
            default_base_url = ""
        else:
            default_model, default_base_url = defaults

        model = (
            os.getenv(f"{role_prefix}_MODEL")
            or (os.getenv("MI_AI_MODEL") if is_system else None)
            or default_model
        ).strip()
        base_url = (
            os.getenv(f"{role_prefix}_BASE_URL")
            or (os.getenv("MI_AI_BASE_URL") if is_system else None)
            or default_base_url
        ).strip()
        raw_key = os.getenv(f"{role_prefix}_API_KEY") or (
            os.getenv("MI_AI_API_KEY") if is_system else None
        )
        raw_retries = (
            os.getenv(f"{role_prefix}_RETRIES")
            or (os.getenv("MI_AI_RETRIES") if is_system else None)
            or "0"
        )
        raw_timeout = (
            os.getenv(f"{role_prefix}_TIMEOUT_SECONDS")
            or (os.getenv("MI_AI_TIMEOUT_SECONDS") if is_system else None)
            or "20"
        )
        raw_store = (
            os.getenv(f"{role_prefix}_STORE")
            or (os.getenv("MI_AI_STORE") if is_system else None)
            or "false"
        )
        raw_max_output_tokens = os.getenv(f"{role_prefix}_MAX_OUTPUT_TOKENS") or (
            os.getenv("MI_AI_MAX_OUTPUT_TOKENS") if is_system else None
        )
        raw_temperature = os.getenv(f"{role_prefix}_TEMPERATURE") or (
            os.getenv("MI_AI_TEMPERATURE") if is_system else None
        )

        try:
            retries = int(raw_retries)
            timeout_seconds = float(raw_timeout)
            max_output_tokens = (
                int(raw_max_output_tokens) if raw_max_output_tokens is not None else None
            )
            temperature = float(raw_temperature) if raw_temperature is not None else None
        except ValueError as exc:
            raise ProviderConfigurationError("ai_provider_invalid_numeric_config") from exc
        if (
            retries < 0
            or timeout_seconds <= 0
            or (max_output_tokens is not None and max_output_tokens <= 0)
        ):
            raise ProviderConfigurationError("ai_provider_invalid_numeric_config")

        return cls(
            role=normalized_role,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=SecretStr(raw_key) if raw_key else None,
            store=raw_store.strip().lower() == "true",
            retries=retries,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )


class AIProviderProbeResult(BaseModel):
    role: str
    provider: str
    model: str
    authenticated: bool
    model_available: bool
    endpoint_host: str
    inference_executed: bool = False
    business_data_sent: bool = False


class AIProviderInferenceResult(BaseModel):
    role: str
    provider: str
    model: str
    endpoint_host: str
    authenticated: bool
    inference_executed: bool
    synthetic_data_only: bool
    business_data_sent: bool
    store_enabled: bool
    expected_output_match: bool
    output_sha256: str
    output_length_chars: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    max_output_tokens: int
    latency_ms: int


class AIProviderDriver(Protocol):
    async def probe(self) -> AIProviderProbeResult: ...


class SandboxInferenceDriver(Protocol):
    async def sandbox_infer(self) -> AIProviderInferenceResult: ...


class _CredentialBoundDriver:
    def __init__(self, config: AIProviderConfig) -> None:
        self._config = config

    def _api_key_value(self) -> str:
        if self._config.api_key is None:
            raise ProviderConfigurationError("ai_provider_api_key_missing")
        value = self._config.api_key.get_secret_value()
        if not value.strip():
            raise ProviderConfigurationError("ai_provider_api_key_missing")
        return value

    def _sandbox_token_limit(self, *, default: int) -> int:
        value = self._config.max_output_tokens or default
        if value < 1 or value > SANDBOX_MAX_OUTPUT_TOKENS_LIMIT:
            raise ProviderConfigurationError("ai_provider_sandbox_token_limit_invalid")
        if self._config.store:
            raise ProviderConfigurationError("ai_provider_sandbox_store_must_be_false")
        if self._config.retries > 1:
            raise ProviderConfigurationError("ai_provider_sandbox_retries_exceeded")
        return value

    @staticmethod
    def _sandbox_result(
        *,
        config: AIProviderConfig,
        endpoint_host: str,
        output_text: str,
        input_tokens: int | None,
        output_tokens: int | None,
        total_tokens: int | None,
        max_output_tokens: int,
        latency_ms: int,
    ) -> AIProviderInferenceResult:
        normalized_output = output_text.strip()
        return AIProviderInferenceResult(
            role=config.role,
            provider=config.provider,
            model=config.model,
            endpoint_host=endpoint_host,
            authenticated=True,
            inference_executed=True,
            synthetic_data_only=True,
            business_data_sent=False,
            store_enabled=False,
            expected_output_match=normalized_output == SANDBOX_EXPECTED_OUTPUT,
            output_sha256=hashlib.sha256(normalized_output.encode("utf-8")).hexdigest(),
            output_length_chars=len(normalized_output),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            max_output_tokens=max_output_tokens,
            latency_ms=latency_ms,
        )


class _OpenAICompatibleModelsDriver(_CredentialBoundDriver):
    provider_name: str
    allowed_host: str
    allowed_base_path: str
    policy_error: str

    def __init__(
        self,
        config: AIProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(config)
        self._transport = transport
        self._validate_config()

    def _validate_config(self) -> None:
        if self._config.provider != self.provider_name:
            raise ProviderConfigurationError("ai_provider_driver_mismatch")
        if not self._config.model:
            raise ProviderConfigurationError("ai_provider_model_missing")
        parsed = urlsplit(self._config.base_url)
        if (
            parsed.scheme.lower() != "https"
            or (parsed.hostname or "").lower() != self.allowed_host
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != self.allowed_base_path
        ):
            raise ProviderConfigurationError(self.policy_error)

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
                try:
                    response = await client.request(
                        method,
                        path,
                        headers=headers,
                        json=json_body,
                    )
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt < self._config.retries:
                        continue
                    raise ProviderConfigurationError("ai_provider_connectivity_failure") from exc
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self._config.retries:
                    continue
                return response
        raise AssertionError("unreachable")

    @staticmethod
    def _check_response_status(response: httpx.Response, *, operation: str) -> None:
        if response.status_code in {400, 401, 403}:
            code = (
                "ai_provider_authentication_failed"
                if response.status_code in {401, 403}
                else f"ai_provider_{operation}_failed"
            )
            raise ProviderConfigurationError(code)
        if response.status_code == 429:
            raise ProviderConfigurationError("ai_provider_rate_limited")
        if response.status_code >= 400:
            raise ProviderConfigurationError(f"ai_provider_{operation}_failed")

    async def probe(self) -> AIProviderProbeResult:
        api_key = self._api_key_value()
        response = await self._request(
            method="GET",
            path="models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._check_response_status(response, operation="probe")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderConfigurationError("ai_provider_invalid_probe_response") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ProviderConfigurationError("ai_provider_invalid_probe_response")
        model_ids = {
            item.get("id")
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        return AIProviderProbeResult(
            role=self._config.role,
            provider=self._config.provider,
            model=self._config.model,
            authenticated=True,
            model_available=self._config.model.lower() in {item.lower() for item in model_ids},
            endpoint_host=self.allowed_host,
            inference_executed=False,
            business_data_sent=False,
        )


class OpenAIResponsesDriver(_OpenAICompatibleModelsDriver):
    """OpenAI boundary. Real inference is restricted to the fixed synthetic sandbox probe."""

    provider_name = "openai"
    allowed_host = "api.openai.com"
    allowed_base_path = "/v1"
    policy_error = "openai_base_url_policy_violation"

    async def sandbox_infer(self) -> AIProviderInferenceResult:
        api_key = self._api_key_value()
        max_output_tokens = self._sandbox_token_limit(default=128)
        started = perf_counter()
        response = await self._request(
            method="POST",
            path="responses",
            headers={"Authorization": f"Bearer {api_key}"},
            json_body={
                "model": self._config.model,
                "input": SANDBOX_PROMPT,
                "max_output_tokens": max_output_tokens,
                "store": False,
            },
        )
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        self._check_response_status(response, operation="inference")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderConfigurationError("ai_provider_invalid_inference_response") from exc
        if not isinstance(payload, dict):
            raise ProviderConfigurationError("ai_provider_invalid_inference_response")

        output_text = _extract_openai_output_text(payload)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return self._sandbox_result(
            config=self._config,
            endpoint_host=self.allowed_host,
            output_text=output_text,
            input_tokens=_optional_int(usage.get("input_tokens")),
            output_tokens=_optional_int(usage.get("output_tokens")),
            total_tokens=_optional_int(usage.get("total_tokens")),
            max_output_tokens=max_output_tokens,
            latency_ms=latency_ms,
        )


class ZAIDriver(_OpenAICompatibleModelsDriver):
    """Z.AI boundary. Sandbox inference disables thinking and sends synthetic text only."""

    provider_name = "zai"
    allowed_host = "api.z.ai"
    allowed_base_path = "/api/paas/v4"
    policy_error = "zai_base_url_policy_violation"

    async def sandbox_infer(self) -> AIProviderInferenceResult:
        api_key = self._api_key_value()
        max_output_tokens = self._sandbox_token_limit(default=64)
        started = perf_counter()
        response = await self._request(
            method="POST",
            path="chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json_body={
                "model": self._config.model,
                "messages": [{"role": "user", "content": SANDBOX_PROMPT}],
                "thinking": {"type": "disabled"},
                "stream": False,
                "max_tokens": max_output_tokens,
                "temperature": 0.0,
            },
        )
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        self._check_response_status(response, operation="inference")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderConfigurationError("ai_provider_invalid_inference_response") from exc
        if not isinstance(payload, dict):
            raise ProviderConfigurationError("ai_provider_invalid_inference_response")

        output_text = _extract_zai_output_text(payload)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return self._sandbox_result(
            config=self._config,
            endpoint_host=self.allowed_host,
            output_text=output_text,
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
            total_tokens=_optional_int(usage.get("total_tokens")),
            max_output_tokens=max_output_tokens,
            latency_ms=latency_ms,
        )


class GeminiDriver(_CredentialBoundDriver):
    """Gemini boundary retained as an optional provider, not the agent default."""

    provider_name = "gemini"
    allowed_host = "generativelanguage.googleapis.com"
    allowed_base_path = "/v1beta"

    def __init__(
        self,
        config: AIProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(config)
        self._transport = transport
        self._validate_config()

    def _validate_config(self) -> None:
        if self._config.provider != self.provider_name:
            raise ProviderConfigurationError("ai_provider_driver_mismatch")
        if not self._config.model:
            raise ProviderConfigurationError("ai_provider_model_missing")
        parsed = urlsplit(self._config.base_url)
        if (
            parsed.scheme.lower() != "https"
            or (parsed.hostname or "").lower() != self.allowed_host
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != self.allowed_base_path
        ):
            raise ProviderConfigurationError("gemini_base_url_policy_violation")

    async def probe(self) -> AIProviderProbeResult:
        api_key = self._api_key_value()
        timeout = httpx.Timeout(self._config.timeout_seconds)
        async with httpx.AsyncClient(
            base_url=self._config.base_url.rstrip("/"),
            transport=self._transport,
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            try:
                response = await client.get("models", headers={"x-goog-api-key": api_key})
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise ProviderConfigurationError("ai_provider_connectivity_failure") from exc

        if response.status_code in {400, 401, 403}:
            raise ProviderConfigurationError("ai_provider_authentication_failed")
        if response.status_code >= 400:
            raise ProviderConfigurationError("ai_provider_probe_failed")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderConfigurationError("ai_provider_invalid_probe_response") from exc
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise ProviderConfigurationError("ai_provider_invalid_probe_response")
        model_ids: set[str] = set()
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            base_model_id = item.get("baseModelId")
            if isinstance(name, str):
                model_ids.add(name.removeprefix("models/"))
            if isinstance(base_model_id, str):
                model_ids.add(base_model_id)
        return AIProviderProbeResult(
            role=self._config.role,
            provider=self._config.provider,
            model=self._config.model,
            authenticated=True,
            model_available=self._config.model in model_ids,
            endpoint_host=self.allowed_host,
            inference_executed=False,
            business_data_sent=False,
        )

    async def sandbox_infer(self) -> AIProviderInferenceResult:
        raise ProviderConfigurationError("ai_provider_sandbox_inference_not_supported")


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _extract_openai_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    output = payload.get("output")
    if not isinstance(output, list):
        raise ProviderConfigurationError("ai_provider_invalid_inference_response")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if part.get("type") == "output_text" and isinstance(text, str):
                parts.append(text)
    if not parts:
        raise ProviderConfigurationError("ai_provider_invalid_inference_response")
    return "".join(parts)


def _extract_zai_output_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderConfigurationError("ai_provider_invalid_inference_response")
    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderConfigurationError("ai_provider_invalid_inference_response")
    message = first.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ProviderConfigurationError("ai_provider_invalid_inference_response")
    return message["content"]


DriverFactory = Callable[[AIProviderConfig], AIProviderDriver]


class ProviderManager:
    """Stable provider contract; system and agent credentials stay isolated by role."""

    def __init__(self, factories: dict[str, DriverFactory] | None = None) -> None:
        self._factories: dict[str, DriverFactory] = {
            "gemini": lambda config: GeminiDriver(config),
            "openai": lambda config: OpenAIResponsesDriver(config),
            "zai": lambda config: ZAIDriver(config),
        }
        if factories:
            self._factories.update(factories)

    @property
    def supported_providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def build(self, config: AIProviderConfig) -> AIProviderDriver:
        factory = self._factories.get(config.provider)
        if factory is None:
            raise ProviderConfigurationError("ai_provider_not_supported")
        return factory(config)
