from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Mapping

import httpx
from pydantic import SecretStr

from market_intelligence.core.security import (
    MODULE01_SECURITY_POLICY,
    OperationalSecurityViolation,
)
from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.ingestion.events import RawEvent
from market_intelligence.marketplaces.base import (
    MarketplaceAdapter,
    MarketplaceFetchResult,
    MarketplaceReadError,
)
from market_intelligence.marketplaces.mercadolivre.channel_sensor import (
    ChannelTelemetry,
    build_channel_telemetry,
)
from market_intelligence.marketplaces.mercadolivre.schema import schema_fingerprint

_CREDENTIAL_FIELDS = {
    "authorization",
    "access_token",
    "refresh_token",
    "client_secret",
}


def _sanitize_credential_echo(value: Any, *, token: str) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in _CREDENTIAL_FIELDS or lowered.endswith(("_token", "_secret")):
                clean[key] = "[REDACTED]"
            else:
                clean[key] = _sanitize_credential_echo(item, token=token)
        return clean
    if isinstance(value, list):
        return [_sanitize_credential_echo(item, token=token) for item in value]
    if isinstance(value, str) and value == token:
        return "[REDACTED]"
    return value


def _channel_event(telemetry: ChannelTelemetry) -> ChannelEvent:
    attributes: dict[str, Any] = {
        "partial_content": telemetry.partial_content,
        "operational_headers": telemetry.operational_headers,
    }
    if telemetry.retry_after is not None:
        attributes["retry_after"] = telemetry.retry_after
    return ChannelEvent(
        marketplace="mercadolivre",
        direction="outbound",
        operation=telemetry.endpoint,
        observed_at=telemetry.observed_at,
        status_code=telemetry.status_code,
        latency_ms=telemetry.latency_ms,
        attempt=telemetry.attempts,
        request_id=telemetry.request_id,
        attributes=attributes,
    )


@dataclass(frozen=True, slots=True)
class MercadoLivreReadResult:
    payload: dict[str, Any]
    telemetry: ChannelTelemetry
    schema_fingerprint: str
    missing_fields: tuple[str, ...] = ()

    @property
    def degraded(self) -> bool:
        return self.telemetry.partial_content or bool(self.missing_fields)


class MercadoLivreReadError(MarketplaceReadError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after: str | None = None,
        telemetry: ChannelTelemetry | None = None,
    ) -> None:
        super().__init__(
            code,
            status_code=status_code,
            retryable=retryable,
            channel_event=_channel_event(telemetry) if telemetry is not None else None,
        )
        self.retry_after = retry_after
        self.telemetry = telemetry


class MercadoLivreReadOnlyAdapter(MarketplaceAdapter):
    name = "mercadolivre"
    base_url = "https://api.mercadolibre.com"

    def __init__(
        self,
        *,
        access_token: SecretStr | str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        network_allowed: bool = False,
        timeout_seconds: float = 20.0,
    ) -> None:
        try:
            MODULE01_SECURITY_POLICY.validate_base_url(self.base_url)
        except OperationalSecurityViolation as exc:
            raise MercadoLivreReadError(exc.code, retryable=False) from exc

        self._token = (
            access_token
            if isinstance(access_token, SecretStr)
            else SecretStr(access_token) if access_token else None
        )
        self._network_allowed = network_allowed
        # Only HTTPX MockTransport is implicitly trusted as non-network transport.
        # Any other custom transport requires explicit network_allowed=True.
        self._synthetic_transport = isinstance(transport, httpx.MockTransport)
        self._client: httpx.AsyncClient | None = None
        if transport is not None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                transport=transport,
                timeout=timeout_seconds,
                follow_redirects=False,
            )
        elif network_allowed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout_seconds,
                follow_redirects=False,
            )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    @staticmethod
    def _security_error(exc: OperationalSecurityViolation) -> MercadoLivreReadError:
        return MercadoLivreReadError(exc.code, retryable=False)

    def _safe_identifier(self, value: str) -> str:
        try:
            return MODULE01_SECURITY_POLICY.validate_identifier(value)
        except OperationalSecurityViolation as exc:
            raise self._security_error(exc) from exc

    def _require_transport(self) -> httpx.AsyncClient:
        if self._client is None:
            raise MercadoLivreReadError("mercadolivre_network_blocked", retryable=False)
        if not self._network_allowed and not self._synthetic_transport:
            raise MercadoLivreReadError("mercadolivre_network_blocked", retryable=False)
        return self._client

    def _token_value(self) -> str:
        if self._token is None:
            raise MercadoLivreReadError("mercadolivre_credential_missing", retryable=False)
        return self._token.get_secret_value()

    async def _read(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        attempt: int = 1,
    ) -> MercadoLivreReadResult:
        try:
            safe_path = MODULE01_SECURITY_POLICY.validate_resource_path(path)
            safe_headers = MODULE01_SECURITY_POLICY.validate_additional_headers(headers)
        except OperationalSecurityViolation as exc:
            raise self._security_error(exc) from exc

        client = self._require_transport()
        token = self._token_value()
        try:
            safe_params = MODULE01_SECURITY_POLICY.validate_query_params(
                params,
                access_token=token,
            )
        except OperationalSecurityViolation as exc:
            raise self._security_error(exc) from exc

        # Authorization is written last and cannot be overridden by caller headers.
        request_headers = dict(safe_headers)
        request_headers["Authorization"] = f"Bearer {token}"
        request = client.build_request(
            "GET",
            safe_path,
            params=safe_params or None,
            headers=request_headers,
        )
        try:
            MODULE01_SECURITY_POLICY.validate_outbound_request(request)
        except OperationalSecurityViolation as exc:
            raise self._security_error(exc) from exc

        started = monotonic()
        try:
            response = await client.send(request)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            telemetry = build_channel_telemetry(
                direction="outbound",
                endpoint=safe_path,
                status_code=None,
                latency_ms=(monotonic() - started) * 1000,
                attempts=attempt,
            )
            raise MercadoLivreReadError(
                "mercadolivre_transport_failure",
                retryable=True,
                telemetry=telemetry,
            ) from exc

        telemetry = build_channel_telemetry(
            direction="outbound",
            endpoint=safe_path,
            headers=response.headers,
            status_code=response.status_code,
            latency_ms=(monotonic() - started) * 1000,
            attempts=attempt,
        )
        if response.status_code == 429:
            raise MercadoLivreReadError(
                "mercadolivre_rate_limited",
                status_code=429,
                retryable=True,
                retry_after=telemetry.retry_after,
                telemetry=telemetry,
            )
        if response.status_code >= 500:
            raise MercadoLivreReadError(
                "mercadolivre_server_failure",
                status_code=response.status_code,
                retryable=True,
                telemetry=telemetry,
            )
        if response.status_code >= 300:
            raise MercadoLivreReadError(
                "mercadolivre_request_rejected",
                status_code=response.status_code,
                retryable=False,
                telemetry=telemetry,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise MercadoLivreReadError(
                "mercadolivre_invalid_json",
                status_code=response.status_code,
                retryable=False,
                telemetry=telemetry,
            ) from exc
        if not isinstance(payload, dict):
            raise MercadoLivreReadError(
                "mercadolivre_unexpected_payload_shape",
                status_code=response.status_code,
                retryable=False,
                telemetry=telemetry,
            )
        safe_payload = _sanitize_credential_echo(payload, token=token)
        missing_header = telemetry.operational_headers.get("x-content-missing", "")
        missing_fields = tuple(
            item.strip() for item in missing_header.split(",") if item.strip()
        )
        return MercadoLivreReadResult(
            payload=safe_payload,
            telemetry=telemetry,
            schema_fingerprint=schema_fingerprint(safe_payload),
            missing_fields=missing_fields,
        )

    async def read_listing(self, listing_id: str) -> MercadoLivreReadResult:
        return await self._read(f"/items/{self._safe_identifier(listing_id)}")

    async def read_order(self, order_id: str) -> MercadoLivreReadResult:
        return await self._read(f"/orders/{self._safe_identifier(order_id)}")

    async def read_shipment(self, shipment_id: str) -> MercadoLivreReadResult:
        return await self._read(
            f"/shipments/{self._safe_identifier(shipment_id)}",
            headers={"x-format-new": "true"},
        )

    async def read_catalog_competition(self, item_id: str) -> MercadoLivreReadResult:
        return await self._read(
            f"/items/{self._safe_identifier(item_id)}/price_to_win",
            params={"version": "v2"},
        )

    async def read_visits(self, item_id: str) -> MercadoLivreReadResult:
        return await self._read(
            "/visits/items",
            params={"ids": self._safe_identifier(item_id)},
        )

    async def get_listing(self, listing_id: str) -> dict[str, Any]:
        return (await self.read_listing(listing_id)).payload

    async def get_order(self, order_id: str) -> dict[str, Any]:
        return (await self.read_order(order_id)).payload

    async def get_shipment(self, shipment_id: str) -> dict[str, Any]:
        return (await self.read_shipment(shipment_id)).payload

    async def get_catalog_competition(self, item_id: str) -> dict[str, Any]:
        return (await self.read_catalog_competition(item_id)).payload

    async def get_visits(self, item_id: str) -> dict[str, Any]:
        return (await self.read_visits(item_id)).payload

    async def fetch_resource_observed(
        self, resource: str, *, attempt: int = 1
    ) -> MarketplaceFetchResult:
        result = await self._read(resource, attempt=attempt)
        return MarketplaceFetchResult(
            payload=result.payload,
            channel_event=_channel_event(result.telemetry),
        )

    async def fetch_resource(self, resource: str) -> dict[str, Any]:
        return (await self.fetch_resource_observed(resource)).payload

    def normalize_notification(self, payload: dict[str, Any]) -> RawEvent:
        raise NotImplementedError("notification normalization belongs to ingestion")
