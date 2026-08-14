from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, status

from market_intelligence.ingestion.events import RawEvent, build_raw_event

_MAX_BODY_BYTES = 1024 * 1024
_SAFE_TOPIC = re.compile(r"^[a-z0-9._-]{1,128}$")


class RawEventSink(Protocol):
    async def append_if_new(self, event: RawEvent) -> bool: ...


def _identifier(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int)):
        normalized = str(value).strip()
        return normalized or None
    return None


def _external_id(payload: dict[str, object]) -> str | None:
    value = _identifier(payload.get("_id")) or _identifier(payload.get("id"))
    if value is None:
        return None
    if len(value) <= 160:
        return value
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _parse_sent(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _validated_resource(value: object) -> str:
    if not isinstance(value, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_resource")
    resource = value.strip()
    if not resource or len(resource) > 2048:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_resource")
    if "\\" in resource or "\x00" in resource or "?" in resource or "#" in resource:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_resource")

    parsed = urlsplit(resource)
    if parsed.scheme or parsed.netloc or resource.startswith("//"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_resource")
    if any(segment in {".", ".."} for segment in parsed.path.split("/")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_resource")
    return resource


def build_mercadolivre_webhook_router(
    sink: RawEventSink,
    *,
    application_id: str,
    max_body_bytes: int = _MAX_BODY_BYTES,
) -> APIRouter:
    expected_application_id = application_id.strip()
    if not expected_application_id:
        raise ValueError("application_id is required")
    if max_body_bytes < 1:
        raise ValueError("max_body_bytes must be positive")

    router = APIRouter(tags=["mercadolivre-webhooks"])

    @router.post("/v1/webhooks/mercadolivre")
    async def receive_mercadolivre_notification(request: Request) -> dict[str, bool]:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise HTTPException(status_code=415, detail="application_json_required")

        raw_content_length = request.headers.get("content-length")
        if raw_content_length:
            try:
                content_length = int(raw_content_length)
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_content_length") from None
            if content_length > max_body_bytes:
                raise HTTPException(status_code=413, detail="notification_too_large")

        body = await request.body()
        if len(body) > max_body_bytes:
            raise HTTPException(status_code=413, detail="notification_too_large")

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_json") from None
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="notification_must_be_object")

        observed_application_id = _identifier(payload.get("application_id"))
        if observed_application_id != expected_application_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="application_id_mismatch")

        user_id = _identifier(payload.get("user_id"))
        if user_id is None or not user_id.isdigit() or int(user_id) <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_user_id")

        topic_value = payload.get("topic")
        if not isinstance(topic_value, str):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_topic")
        topic = topic_value.strip()
        if not _SAFE_TOPIC.fullmatch(topic):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_topic")

        resource = _validated_resource(payload.get("resource"))
        event = build_raw_event(
            source="mercadolivre_webhook",
            event_type=topic,
            external_id=_external_id(payload),
            resource=resource,
            occurred_at=_parse_sent(payload.get("sent")),
            received_at=datetime.now(UTC),
            payload=payload,
        )

        try:
            await sink.append_if_new(event)
        except Exception:
            # Fail closed without acknowledging data that was not durably accepted.
            # The request body is intentionally never logged here.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="notification_persistence_unavailable",
            ) from None

        # Duplicate notifications are intentionally acknowledged with 200 as well.
        return {"ok": True}

    return router
