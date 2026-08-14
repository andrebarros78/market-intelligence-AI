from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import unquote, urlsplit

import httpx


class OperationalSecurityViolation(PermissionError):
    """Fail-closed policy violation with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_SENSITIVE_QUERY_KEYS = {
    "authorization",
    "access_token",
    "refresh_token",
    "client_secret",
    "client_id_secret",
    "code_verifier",
    "password",
    "api_key",
    "apikey",
}

_BLOCKED_REQUEST_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "host",
    "x-forwarded-host",
    "x-forwarded-for",
    "x-real-ip",
}

_ALLOWED_ADDITIONAL_HEADERS = {
    "accept",
    "x-format-new",
}


def _contains_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _decode_for_validation(value: str) -> str:
    current = value
    for _ in range(3):
        decoded = unquote(current)
        if decoded == current:
            break
        current = decoded
    return current


@dataclass(frozen=True, slots=True)
class Module01SecurityPolicy:
    version: str = "module01-security@1.0.0"
    marketplace_host: str = "api.mercadolibre.com"
    max_resource_length: int = 2048
    max_identifier_length: int = 256

    @property
    def allowed_additional_headers(self) -> tuple[str, ...]:
        return tuple(sorted(_ALLOWED_ADDITIONAL_HEADERS))

    def assert_runtime_settings(
        self,
        *,
        read_only: bool,
        allow_marketplace_writes: bool,
    ) -> None:
        if not read_only or allow_marketplace_writes:
            raise OperationalSecurityViolation("module01_read_only_policy_violation")

    def validate_base_url(self, base_url: str) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme.lower() != "https"
            or (parsed.hostname or "").lower() != self.marketplace_host
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise OperationalSecurityViolation("mercadolivre_base_url_policy_violation")

    def validate_resource_path(self, resource: str) -> str:
        if not isinstance(resource, str) or not resource or len(resource) > self.max_resource_length:
            raise OperationalSecurityViolation("mercadolivre_invalid_resource_path")
        if _contains_control(resource) or "\\" in resource:
            raise OperationalSecurityViolation("mercadolivre_invalid_resource_path")

        parsed = urlsplit(resource)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise OperationalSecurityViolation("mercadolivre_invalid_resource_path")
        if not parsed.path.startswith("/") or parsed.path.startswith("//"):
            raise OperationalSecurityViolation("mercadolivre_invalid_resource_path")

        decoded = _decode_for_validation(parsed.path)
        if _contains_control(decoded) or "\\" in decoded or decoded.startswith("//"):
            raise OperationalSecurityViolation("mercadolivre_invalid_resource_path")
        segments = decoded.split("/")
        if any(segment in {".", ".."} for segment in segments):
            raise OperationalSecurityViolation("mercadolivre_invalid_resource_path")
        return parsed.path

    def validate_identifier(self, value: str) -> str:
        if not isinstance(value, str) or not value or len(value) > self.max_identifier_length:
            raise OperationalSecurityViolation("mercadolivre_invalid_resource_identifier")
        if value != value.strip() or _contains_control(value):
            raise OperationalSecurityViolation("mercadolivre_invalid_resource_identifier")
        if value in {".", ".."} or any(char in value for char in "/\\?#%"):
            raise OperationalSecurityViolation("mercadolivre_invalid_resource_identifier")
        return value

    def validate_additional_headers(
        self,
        headers: Mapping[str, str] | None,
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_name, raw_value in (headers or {}).items():
            name = str(raw_name).strip().lower()
            value = str(raw_value)
            if not name or _contains_control(name) or _contains_control(value):
                raise OperationalSecurityViolation("mercadolivre_forbidden_request_header")
            if name in _BLOCKED_REQUEST_HEADERS or name not in _ALLOWED_ADDITIONAL_HEADERS:
                raise OperationalSecurityViolation("mercadolivre_forbidden_request_header")
            normalized[name] = value
        return normalized

    def validate_query_params(
        self,
        params: Mapping[str, str] | None,
        *,
        access_token: str | None = None,
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_value in (params or {}).items():
            key = str(raw_key).strip()
            value = str(raw_value)
            lowered = key.lower()
            if not key or _contains_control(key) or _contains_control(value):
                raise OperationalSecurityViolation("mercadolivre_forbidden_query_parameter")
            if (
                lowered in _SENSITIVE_QUERY_KEYS
                or lowered.endswith(("_token", "_secret"))
                or (access_token and access_token in value)
            ):
                raise OperationalSecurityViolation("mercadolivre_forbidden_query_parameter")
            normalized[key] = value
        return normalized

    def validate_outbound_request(self, request: httpx.Request) -> None:
        if request.method.upper() != "GET":
            raise OperationalSecurityViolation("module01_non_read_request_blocked")

        parsed = urlsplit(str(request.url))
        if (
            parsed.scheme.lower() != "https"
            or (parsed.hostname or "").lower() != self.marketplace_host
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise OperationalSecurityViolation("mercadolivre_outbound_host_policy_violation")

        self.validate_resource_path(parsed.path)


MODULE01_SECURITY_POLICY = Module01SecurityPolicy()
