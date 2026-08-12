from __future__ import annotations

from typing import Any

_SECRET_KEYS = {
    "state",
    "code",
    "authorization_code",
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "code_verifier",
}


def sanitize_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in _SECRET_KEYS or key.lower().endswith(("_token", "_secret")):
                clean[key] = "[REDACTED]"
            else:
                clean[key] = sanitize_mapping(item)
        return clean
    if isinstance(value, list):
        return [sanitize_mapping(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_mapping(item) for item in value)
    return value


def contains_secret_marker(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key.lower() in _SECRET_KEYS or key.lower().endswith(("_token", "_secret"))
            for key in value
        )
    return False
