from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from market_intelligence.marketplaces.mercadolivre.webhook_surface_probe import schema_only_observation


_MAX_ENTRIES = 10000
_MAX_JSON_TEXT_BYTES = 2 * 1024 * 1024
_SAFE_HOST_SUFFIXES = (".mercadolivre.com.br", ".mercadolibre.com")
_SAFE_HOSTS = {"api.mercadolibre.com", "www.mercadolivre.com.br", "www.mercadolibre.com"}
_IDENTIFIER_LIKE = re.compile(r"^(?:[A-Z]{2,6}[A-Z0-9_-]{5,}|[0-9]{5,}|[0-9a-fA-F]{16,}|[A-Za-z0-9_-]{24,})$")
_SAFE_PATH_WORD = re.compile(r"^[a-z][a-z0-9_-]{0,48}$")
_SECRET_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
}
_SECRET_FIELD_NAMES = {
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "password",
    "cookie",
    "set-cookie",
    "api_key",
    "apikey",
}
_SECRET_PATH_TOKEN = re.compile(
    r"(?i)(?P<prefix>\.|\[\])(?:access_token|refresh_token|client_secret|authorization|password|cookie|set-cookie|api_key|apikey)(?P<suffix>:|\.|\[|$)"
)


def _allowed_host(host: str) -> bool:
    normalized = host.strip().lower().rstrip(".")
    return normalized in _SAFE_HOSTS or any(normalized.endswith(suffix) for suffix in _SAFE_HOST_SUFFIXES)


def _path_template(path: str) -> str:
    segments: list[str] = []
    for raw in [segment for segment in path.split("/") if segment][:12]:
        if _IDENTIFIER_LIKE.fullmatch(raw):
            segments.append("{id}")
        elif _SAFE_PATH_WORD.fullmatch(raw):
            segments.append(raw)
        else:
            segments.append("{segment}")
    return "/" + "/".join(segments) if segments else "/"


def _header_summary(headers: Any) -> dict[str, Any]:
    if not isinstance(headers, list):
        return {"header_count": 0, "credential_header_present": False}
    names: list[str] = []
    credential = False
    for item in headers:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if not name:
            continue
        if name in _SECRET_HEADER_NAMES or name.endswith(("-token", "-secret")):
            credential = True
            continue
        names.append(name)
    return {
        "header_count": len(headers),
        "non_secret_header_names": sorted(set(names))[:128],
        "credential_header_present": credential,
    }


def _secret_field_name(name: str) -> bool:
    normalized = name.strip().lower()
    return (
        normalized in _SECRET_FIELD_NAMES
        or normalized.endswith(("_token", "_secret", "_password"))
        or normalized.startswith(("token_", "secret_", "password_"))
    )


def _mask_schema_metadata(schema: dict[str, Any]) -> dict[str, Any]:
    paths = [str(item) for item in schema.get("schema_paths") or []]
    fields = [str(item) for item in schema.get("top_level_fields") or []]
    secret_present = any(_secret_field_name(field) for field in fields) or any(
        _SECRET_PATH_TOKEN.search(path) is not None for path in paths
    )
    masked_paths = [
        _SECRET_PATH_TOKEN.sub(
            lambda match: f"{match.group('prefix')}[SECRET_FIELD]{match.group('suffix')}",
            path,
        )
        for path in paths
    ]
    masked_fields = ["[SECRET_FIELD]" if _secret_field_name(field) else field for field in fields]
    result = dict(schema)
    result["schema_paths"] = list(dict.fromkeys(masked_paths))[:512]
    result["top_level_fields"] = sorted(set(masked_fields))[:256]
    result["secret_field_present"] = secret_present
    return result


def _json_schema_only(text: Any) -> dict[str, Any] | None:
    if not isinstance(text, str) or not text:
        return None
    if len(text.encode("utf-8", errors="ignore")) > _MAX_JSON_TEXT_BYTES:
        return {"json_too_large": True}
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return {"json_root_type": type(payload).__name__}
    return _mask_schema_metadata(schema_only_observation(payload))


def _post_data_schema(post_data: Any) -> dict[str, Any]:
    if not isinstance(post_data, dict):
        return {"body_present": False}
    mime_type = str(post_data.get("mimeType") or "").split(";", 1)[0].strip().lower()
    result: dict[str, Any] = {
        "body_present": bool(post_data.get("text") or post_data.get("params")),
        "mime_type": mime_type,
    }
    if mime_type == "application/json":
        schema = _json_schema_only(post_data.get("text"))
        if schema is not None:
            result["json_schema"] = schema
    elif isinstance(post_data.get("params"), list):
        names = []
        secret_present = False
        for item in post_data["params"]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            if _secret_field_name(name):
                secret_present = True
                continue
            names.append(name)
        result["form_field_names"] = sorted(set(names))[:128]
        result["secret_form_field_present"] = secret_present
    return result


def _response_schema(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {"status": None, "body_present": False}
    content = response.get("content") if isinstance(response.get("content"), dict) else {}
    mime_type = str(content.get("mimeType") or "").split(";", 1)[0].strip().lower()
    result: dict[str, Any] = {
        "status": response.get("status") if isinstance(response.get("status"), int) else None,
        "mime_type": mime_type,
        "body_present": bool(content.get("text")),
        **_header_summary(response.get("headers")),
    }
    if "json" in mime_type:
        schema = _json_schema_only(content.get("text"))
        if schema is not None:
            result["json_schema"] = schema
    return result


def _query_keys(query: Any) -> tuple[str, ...]:
    if not isinstance(query, list):
        return ()
    keys = []
    for item in query:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or _secret_field_name(name):
            continue
        keys.append(name)
    return tuple(sorted(set(keys))[:128])


@dataclass(frozen=True, slots=True)
class HarSurfaceObservation:
    surface_key: str
    host: str
    method: str
    path_template: str
    status: int | None
    request_query_keys: tuple[str, ...]
    request_metadata: dict[str, Any]
    request_body_schema: dict[str, Any]
    response_metadata: dict[str, Any]

    def as_safe_payload(self) -> dict[str, Any]:
        return {
            "surface_key": self.surface_key,
            "host": self.host,
            "method": self.method,
            "path_template": self.path_template,
            "status": self.status,
            "request_query_keys": list(self.request_query_keys),
            "request_metadata": self.request_metadata,
            "request_body_schema": self.request_body_schema,
            "response_metadata": self.response_metadata,
            "values_persisted": False,
            "capture_mode": "har_schema_metadata_only",
        }


@dataclass(frozen=True, slots=True)
class HarObservationReport:
    entries_total: int
    entries_in_scope: int
    entries_skipped: int
    unique_surfaces: int
    methods: dict[str, int]
    credential_headers_observed: int
    observations: tuple[HarSurfaceObservation, ...]


def analyze_har(har: dict[str, Any]) -> HarObservationReport:
    log = har.get("log") if isinstance(har, dict) else None
    entries = log.get("entries") if isinstance(log, dict) else None
    if not isinstance(entries, list):
        raise ValueError("invalid_har_entries")
    if len(entries) > _MAX_ENTRIES:
        raise ValueError("har_entry_limit_exceeded")

    methods: Counter[str] = Counter()
    credential_headers_observed = 0
    in_scope = skipped = 0
    by_key: dict[str, HarSurfaceObservation] = {}

    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
        url = str(request.get("url") or "")
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() != "https" or not host or not _allowed_host(host):
            skipped += 1
            continue

        method = str(request.get("method") or "GET").upper()
        if not re.fullmatch(r"[A-Z]{3,12}", method):
            skipped += 1
            continue
        template = _path_template(parsed.path)
        request_metadata = _header_summary(request.get("headers"))
        response_metadata = _response_schema(entry.get("response"))
        credential_headers_observed += int(
            request_metadata.get("credential_header_present") is True
        )
        methods[method] += 1
        in_scope += 1

        key_material = f"{host}|{method}|{template}"
        key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
        observation = HarSurfaceObservation(
            surface_key=key,
            host=host,
            method=method,
            path_template=template,
            status=response_metadata.get("status"),
            request_query_keys=_query_keys(request.get("queryString")),
            request_metadata=request_metadata,
            request_body_schema=_post_data_schema(request.get("postData")),
            response_metadata=response_metadata,
        )
        by_key[key] = observation

    return HarObservationReport(
        entries_total=len(entries),
        entries_in_scope=in_scope,
        entries_skipped=skipped,
        unique_surfaces=len(by_key),
        methods=dict(sorted(methods.items())),
        credential_headers_observed=credential_headers_observed,
        observations=tuple(by_key[key] for key in sorted(by_key)),
    )
