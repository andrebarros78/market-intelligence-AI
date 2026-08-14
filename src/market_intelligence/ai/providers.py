from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, SecretStr


class ProviderConfigurationError(RuntimeError):
    """Stable fail-closed error that never embeds credential material."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class AIProviderConfig:
    provider: str = "openai"
    model: str = "gpt-5-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr | None = None
    store: bool = False
    retries: int = 0
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> "AIProviderConfig":
        raw_key = os.getenv("MI_AI_API_KEY") or None
        raw_retries = os.getenv("MI_AI_RETRIES", "0")
        raw_timeout = os.getenv("MI_AI_TIMEOUT_SECONDS", "20")
        try:
            retries = int(raw_retries)
            timeout_seconds = float(raw_timeout)
        except ValueError as exc:
            raise ProviderConfigurationError("ai_provider_invalid_numeric_config") from exc
        if retries < 0 or timeout_seconds <= 0:
            raise ProviderConfigurationError("ai_provider_invalid_numeric_config")
        return cls(
            provider=(os.getenv("MI_AI_PROVIDER") or "openai").strip().lower(),
            model=(os.getenv("MI_AI_MODEL") or "gpt-5-mini").strip(),
            base_url=(os.getenv("MI_AI_BASE_URL") or "https://api.openai.com/v1").strip(),
            api_key=SecretStr(raw_key) if raw_key else None,
            store=(os.getenv("MI_AI_STORE", "false").strip().lower() == "true"),
            retries=retries,
            timeout_seconds=timeout_seconds,
        )


class AIProviderProbeResult(BaseModel):
    provider: str
    model: str
    authenticated: bool
    model_available: bool
    endpoint_host: str
    inference_executed: bool = False
    business_data_sent: bool = False


class AIProviderDriver(Protocol):
    async def probe(self) -> AIProviderProbeResult: ...


class OpenAIResponsesDriver:
    """OpenAI Responses provider boundary.

    The connectivity probe deliberately calls only GET /v1/models. It validates the
    credential and configured model without executing inference or sending business data.
    """

    provider_name = "openai"
    allowed_scheme = "https"
    allowed_host = "api.openai.com"
    allowed_base_path = "/v1"

    def __init__(
        self,
        config: AIProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._validate_config()

    def _validate_config(self) -> None:
        if self._config.provider != self.provider_name:
            raise ProviderConfigurationError("ai_provider_driver_mismatch")
        if not self._config.model:
            raise ProviderConfigurationError("ai_provider_model_missing")
        parsed = urlsplit(self._config.base_url)
        if (
            parsed.scheme.lower() != self.allowed_scheme
            or (parsed.hostname or "").lower() != self.allowed_host
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != self.allowed_base_path
        ):
            raise ProviderConfigurationError("openai_base_url_policy_violation")

    def _api_key_value(self) -> str:
        if self._config.api_key is None:
            raise ProviderConfigurationError("ai_provider_api_key_missing")
        value = self._config.api_key.get_secret_value()
        if not value.strip():
            raise ProviderConfigurationError("ai_provider_api_key_missing")
        return value

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
                response = await client.get(
                    "/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise ProviderConfigurationError("ai_provider_connectivity_failure") from exc

        if response.status_code in {401, 403}:
            raise ProviderConfigurationError("ai_provider_authentication_failed")
        if response.status_code >= 400:
            raise ProviderConfigurationError("ai_provider_probe_failed")
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
            provider=self._config.provider,
            model=self._config.model,
            authenticated=True,
            model_available=self._config.model in model_ids,
            endpoint_host=self.allowed_host,
            inference_executed=False,
            business_data_sent=False,
        )


DriverFactory = Callable[[AIProviderConfig], AIProviderDriver]


class ProviderManager:
    """Stable provider contract; provider selection is configuration, not application coupling."""

    def __init__(self, factories: dict[str, DriverFactory] | None = None) -> None:
        self._factories: dict[str, DriverFactory] = {
            "openai": lambda config: OpenAIResponsesDriver(config),
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
