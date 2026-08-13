from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Mapping

import httpx
from pydantic import SecretStr

from market_intelligence.marketplaces.base import MarketplaceAdapter
from market_intelligence.marketplaces.mercadolivre.channel_sensor import (
    ChannelTelemetry,
    build_channel_telemetry,
)
from market_intelligence.marketplaces.mercadolivre.schema import schema_fingerprint


@dataclass(frozen=True, slots=True)
class MercadoLivreReadResult:
    payload: dict[str, Any]
    telemetry: ChannelTelemetry
    schema_fingerprint: str
    missing_fields: tuple[str, ...] = ()

    @property
    def degraded(self) -> bool:
        return self.telemetry.partial_content or bool(self.missing_fields)


class MercadoLivreReadError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after: str | None = None,
        telemetry: ChannelTelemetry | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
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
        self._token = (
            access_token
            if isinstance(access_token, SecretStr)
            else SecretStr(access_token) if access_token else None
        )
        self._network_allowed = network_allowed
        self._synthetic_transport = transport is not None
        self._client: httpx.AsyncClient | None = None
        if transport is not None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                transport=transport,
                timeout=timeout_seconds,
            )
        elif network_allowed:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_seconds)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    def _require_transport(self) -> httpx.AsyncClient:
        if self._client is None:
            raise MercadoLivreReadError("mercadolivre_network_blocked", retryable=False)
        if not self._network_allowed and not self._synthetic_transport:
            raise MercadoLivreReadError("mercadolivre_network_blocked", retryable=False)
        return self._client

    def _authorization_headers(self) -> dict[str, str]:
        if self._token is None:
            raise MercadoLivreReadError("mercadolivre_credential_missing", retryable=False)
        return {"Authorization": f"Bearer {self._token.get_secret_value()}"}

    async def _read(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        attempt: int = 1,
    ) -> MercadoLivreReadResult:
        if not path.startswith("/") or path.startswith("//"):
            raise MercadoLivreReadError("mercadolivre_invalid_resource_path", retryable=False)
        client = self._require_transport()
        request_headers = self._authorization_headers()
        request_headers.update(dict(headers or {}))
        started = monotonic()
        try:
            response = await client.get(path, params=params, headers=request_headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            telemetry = build_channel_telemetry(
                direction="outbound",
                endpoint=path,
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
            endpoint=path,
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
        if response.status_code >= 400:
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
        missing_header = telemetry.operational_headers.get("x-content-missing", "")
        missing_fields = tuple(
            item.strip() for item in missing_header.split(",") if item.strip()
        )
        return MercadoLivreReadResult(
            payload=payload,
            telemetry=telemetry,
            schema_fingerprint=schema_fingerprint(payload),
            missing_fields=missing_fields,
        )

    async def read_listing(self, listing_id: str) -> MercadoLivreReadResult:
        return await self._read(f"/items/{listing_id}")

    async def read_order(self, order_id: str) -> MercadoLivreReadResult:
        return await self._read(f"/orders/{order_id}")

    async def read_shipment(self, shipment_id: str) -> MercadoLivreReadResult:
        return await self._read(
            f"/shipments/{shipment_id}", headers={"x-format-new": "true"}
        )

    async def read_catalog_competition(self, item_id: str) -> MercadoLivreReadResult:
        return await self._read(
            f"/items/{item_id}/price_to_win", params={"version": "v2"}
        )

    async def read_visits(self, item_id: str) -> MercadoLivreReadResult:
        return await self._read("/visits/items", params={"ids": item_id})

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

    async def fetch_resource(self, resource: str) -> dict[str, Any]:
        return (await self._read(resource)).payload

    def normalize_notification(self, payload: dict[str, Any]) -> Any:
        raise NotImplementedError("notification normalization belongs to ingestion")
