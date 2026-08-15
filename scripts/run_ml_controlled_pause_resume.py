from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import RawEventRecord
from market_intelligence.skills.evidence_feed import build_validated_status_cycle_evidence

API_BASE = "https://api.mercadolibre.com"
EXPECTED_APP_ID = "3438551912770538"
APPROVAL_PHRASE = "pause-resume-1-item"
PROOF_DIR = Path("runtime/controlled-proof")
REACTIVATION_ATTEMPTS = 3
REACTIVATION_DELAY_SECONDS = 1.0
WEBHOOK_TIMEOUT_SECONDS = 60.0
WEBHOOK_POLL_SECONDS = 0.5


class ControlledProofError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Candidate:
    item_id: str
    sold_quantity: int
    visits: int
    available_quantity: int
    title: str

    @property
    def risk_key(self) -> tuple[int, int, int, str]:
        return (self.sold_quantity, self.visits, -self.available_quantity, self.item_id)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ControlledProofError(f"missing_env:{name}")
    return value


def _safe_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sanitize_item(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "id",
        "site_id",
        "title",
        "status",
        "price",
        "available_quantity",
        "sold_quantity",
        "catalog_listing",
        "permalink",
        "date_created",
        "last_updated",
    }
    return {key: payload.get(key) for key in sorted(allowed) if key in payload}


def _serialize_dataclass(value: object) -> dict[str, Any]:
    raw = asdict(value)  # type: ignore[arg-type]
    observed_at = raw.get("observed_at")
    if isinstance(observed_at, datetime):
        raw["observed_at"] = observed_at.isoformat()
    return raw


async def _request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    token: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    if method not in {"GET", "PUT"}:
        raise ControlledProofError("forbidden_method")
    if method == "PUT":
        if not path.startswith("/items/") or path.count("/") != 2:
            raise ControlledProofError("forbidden_write_path")
        if json_body not in ({"status": "paused"}, {"status": "active"}):
            raise ControlledProofError("forbidden_write_payload")
    return await client.request(
        method,
        path,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        json=json_body,
        params=params,
    )


async def _json_ok(response: httpx.Response, expected: frozenset[int] = frozenset({200})) -> dict[str, Any]:
    if response.status_code not in expected:
        raise ControlledProofError(f"http_{response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ControlledProofError("unexpected_payload")
    return payload


async def _get_item(client: httpx.AsyncClient, *, token: str, item_id: str) -> dict[str, Any]:
    return await _json_ok(await _request(client, "GET", f"/items/{item_id}", token=token))


async def _select_candidate(client: httpx.AsyncClient, *, token: str, user_id: str) -> Candidate:
    search = await _request(
        client,
        "GET",
        f"/users/{user_id}/items/search",
        token=token,
        params={"status": "active", "limit": "50"},
    )
    payload = await _json_ok(search)
    ids = payload.get("results")
    if not isinstance(ids, list) or not ids:
        raise ControlledProofError("no_active_items")

    candidates: list[Candidate] = []
    for raw_id in ids[:30]:
        item_id = str(raw_id)
        item = await _get_item(client, token=token, item_id=item_id)
        if item.get("status") != "active":
            continue
        available = int(item.get("available_quantity") or 0)
        if available <= 0:
            continue
        visits_payload = await _json_ok(
            await _request(client, "GET", "/visits/items", token=token, params={"ids": item_id})
        )
        visits = int(visits_payload.get(item_id) or 0)
        candidates.append(
            Candidate(
                item_id=item_id,
                sold_quantity=int(item.get("sold_quantity") or 0),
                visits=visits,
                available_quantity=available,
                title=str(item.get("title") or ""),
            )
        )
    if not candidates:
        raise ControlledProofError("no_low_risk_candidate")
    return min(candidates, key=lambda item: item.risk_key)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


async def _ensure_active(
    client: httpx.AsyncClient,
    *,
    token: str,
    item_id: str,
    attempts: int = REACTIVATION_ATTEMPTS,
    delay_seconds: float = REACTIVATION_DELAY_SECONDS,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            current = await _get_item(client, token=token, item_id=item_id)
            if current.get("status") == "active":
                return current
            response = await _request(
                client,
                "PUT",
                f"/items/{item_id}",
                token=token,
                json_body={"status": "active"},
            )
            await _json_ok(response)
            current = await _get_item(client, token=token, item_id=item_id)
            if current.get("status") == "active":
                return current
            last_error = ControlledProofError(f"reactivation_not_confirmed_attempt_{attempt}")
        except Exception as exc:  # bounded recovery must survive transient HTTP/network errors
            last_error = exc
        if attempt < attempts:
            await asyncio.sleep(delay_seconds)
    raise ControlledProofError("CRITICAL_REACTIVATION_FAILED") from last_error


def _matching_webhook(record: RawEventRecord, *, item_id: str, user_id: str) -> bool:
    if record.source != "mercadolivre_webhook" or record.event_type != "items":
        return False
    if record.resource != f"/items/{item_id}":
        return False
    payload = record.payload if isinstance(record.payload, dict) else {}
    return (
        str(payload.get("application_id") or "") == EXPECTED_APP_ID
        and str(payload.get("user_id") or "") == user_id
    )


async def _wait_for_item_webhook(
    sessions: async_sessionmaker[AsyncSession],
    *,
    item_id: str,
    user_id: str,
    after: datetime,
    timeout_seconds: float = WEBHOOK_TIMEOUT_SECONDS,
    poll_seconds: float = WEBHOOK_POLL_SECONDS,
) -> dict[str, Any]:
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        async with sessions() as session:
            result = await session.execute(
                select(RawEventRecord)
                .where(
                    RawEventRecord.source == "mercadolivre_webhook",
                    RawEventRecord.event_type == "items",
                    RawEventRecord.resource == f"/items/{item_id}",
                    RawEventRecord.received_at >= after,
                )
                .order_by(RawEventRecord.received_at.asc())
                .limit(10)
            )
            for record in result.scalars():
                if _matching_webhook(record, item_id=item_id, user_id=user_id):
                    return {
                        "event_id": str(record.id),
                        "event_type": record.event_type,
                        "resource": record.resource,
                        "payload_hash": record.payload_hash,
                        "occurred_at": record.occurred_at.isoformat() if record.occurred_at else None,
                        "received_at": record.received_at.isoformat(),
                        "application_id_validated": True,
                        "user_id_validated": True,
                    }
        await asyncio.sleep(poll_seconds)
    raise ControlledProofError("real_items_webhook_not_observed")


async def main() -> int:
    if _require_env("MI_CONTROLLED_WRITE_TEST_APPROVED") != APPROVAL_PHRASE:
        raise ControlledProofError("approval_phrase_mismatch")
    if _require_env("MI_ML_APP_ID") != EXPECTED_APP_ID:
        raise ControlledProofError("application_id_mismatch")
    if os.environ.get("MI_READ_ONLY", "true").lower() != "true":
        raise ControlledProofError("permanent_read_only_must_remain_true")
    if os.environ.get("MI_ALLOW_MARKETPLACE_WRITES", "false").lower() != "false":
        raise ControlledProofError("permanent_write_gate_must_remain_false")

    token = _require_env("MI_ML_TEMP_WRITE_TOKEN")
    database_url = _require_env("MI_DATABASE_URL")
    proof_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    proof_root = PROOF_DIR / proof_id
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)

    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=20.0, follow_redirects=False) as client:
            me = await _json_ok(await _request(client, "GET", "/users/me", token=token))
            user_id = str(me.get("id") or "")
            if not user_id:
                raise ControlledProofError("users_me_missing_id")

            candidate = await _select_candidate(client, token=token, user_id=user_id)
            before = await _get_item(client, token=token, item_id=candidate.item_id)
            if before.get("status") != "active":
                raise ControlledProofError("candidate_not_active_before")

            base_evidence = {
                "proof_id": proof_id,
                "marketplace": "mercadolivre",
                "application_id": EXPECTED_APP_ID,
                "account_hash": _safe_hash(user_id),
                "item_id": candidate.item_id,
                "selection": {
                    "sold_quantity": candidate.sold_quantity,
                    "visits": candidate.visits,
                    "available_quantity": candidate.available_quantity,
                    "criterion": "min(sold_quantity, visits, -available_quantity, item_id)",
                },
                "before": _sanitize_item(before),
            }
            _write_json(proof_root / "radar_snapshot_before.json", base_evidence)

            pause_write_accepted = False
            reactivation_confirmed = False
            active: dict[str, Any] | None = None
            primary_error: Exception | None = None
            pause_webhook: dict[str, Any] | None = None
            active_webhook: dict[str, Any] | None = None
            try:
                pause_started = datetime.now(timezone.utc)
                paused_response = await _request(
                    client,
                    "PUT",
                    f"/items/{candidate.item_id}",
                    token=token,
                    json_body={"status": "paused"},
                )
                await _json_ok(paused_response)
                pause_write_accepted = True

                paused = await _get_item(client, token=token, item_id=candidate.item_id)
                if paused.get("status") != "paused":
                    raise ControlledProofError("pause_not_confirmed")

                pause_webhook = await _wait_for_item_webhook(
                    sessions,
                    item_id=candidate.item_id,
                    user_id=user_id,
                    after=pause_started,
                )
                paused_after_webhook = await _get_item(client, token=token, item_id=candidate.item_id)
                if paused_after_webhook.get("status") != "paused":
                    raise ControlledProofError("pause_webhook_not_validated_by_official_get")

                _write_json(
                    proof_root / "radar_snapshot_paused.json",
                    {
                        **base_evidence,
                        "paused": _sanitize_item(paused_after_webhook),
                        "paused_confirmed": True,
                        "webhook": pause_webhook,
                        "official_get_after_webhook": True,
                    },
                )

                active_started = datetime.now(timezone.utc)
                active = await _ensure_active(client, token=token, item_id=candidate.item_id)
                reactivation_confirmed = active.get("status") == "active"
                if not reactivation_confirmed:
                    raise ControlledProofError("reactivation_not_confirmed")

                active_webhook = await _wait_for_item_webhook(
                    sessions,
                    item_id=candidate.item_id,
                    user_id=user_id,
                    after=active_started,
                )
                active_after_webhook = await _get_item(client, token=token, item_id=candidate.item_id)
                if active_after_webhook.get("status") != "active":
                    raise ControlledProofError("active_webhook_not_validated_by_official_get")
                active = active_after_webhook
            except Exception as exc:
                primary_error = exc
            finally:
                if pause_write_accepted and not reactivation_confirmed:
                    active = await _ensure_active(client, token=token, item_id=candidate.item_id)
                    reactivation_confirmed = active.get("status") == "active"
                if pause_write_accepted:
                    _write_json(
                        proof_root / "radar_snapshot_after.json",
                        {
                            **base_evidence,
                            "after": _sanitize_item(active or {}),
                            "reactivation_confirmed": reactivation_confirmed,
                            "pause_webhook": pause_webhook,
                            "active_webhook": active_webhook,
                            "skill_feed_status": (
                                "READY" if pause_webhook and active_webhook and reactivation_confirmed else "BLOCKED"
                            ),
                        },
                    )

            if primary_error is not None:
                raise primary_error
            if not (pause_webhook and active_webhook and reactivation_confirmed and active):
                raise ControlledProofError("controlled_cycle_not_fully_validated")

            observed_at = datetime.now(timezone.utc)
            skill_evidence = build_validated_status_cycle_evidence(
                item_id=candidate.item_id,
                observed_at=observed_at,
                before_status="active",
                paused_status="paused",
                after_status="active",
                webhook_validated=True,
                official_get_validated=True,
                proof_id=proof_id,
            )
            skill_payload = _serialize_dataclass(skill_evidence)
            _write_json(proof_root / "skills_validated_evidence.json", skill_payload)

            final = {
                **base_evidence,
                "after": _sanitize_item(active),
                "pause_confirmed": True,
                "reactivation_confirmed": True,
                "pause_webhook_validated": True,
                "active_webhook_validated": True,
                "official_get_validated": True,
                "radar": "VALIDATED",
                "skills": "VALIDATED_FACT_ONLY",
                "permanent_read_only": True,
                "permanent_marketplace_writes": False,
                "mission": "MISSION_PROVEN",
            }
            _write_json(proof_root / "MISSION_PROVEN.json", final)
            print(json.dumps(final, ensure_ascii=False, sort_keys=True))
    finally:
        await engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
