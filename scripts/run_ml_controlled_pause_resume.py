from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

API_BASE = "https://api.mercadolibre.com"
EXPECTED_APP_ID = "3438551912770538"
APPROVAL_PHRASE = "pause-resume-1-item"
PROOF_DIR = Path("runtime/controlled-proof")
REACTIVATION_ATTEMPTS = 3
REACTIVATION_DELAY_SECONDS = 1.0


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
    proof_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    proof_root = PROOF_DIR / proof_id

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
        paused_confirmed = False
        active: dict[str, Any] | None = None
        primary_error: Exception | None = None
        try:
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
            paused_confirmed = True
            _write_json(
                proof_root / "radar_snapshot_paused.json",
                {**base_evidence, "paused": _sanitize_item(paused), "paused_confirmed": True},
            )
        except Exception as exc:
            primary_error = exc
        finally:
            if pause_write_accepted:
                active = await _ensure_active(client, token=token, item_id=candidate.item_id)
                _write_json(
                    proof_root / "radar_snapshot_after.json",
                    {
                        **base_evidence,
                        "after": _sanitize_item(active),
                        "pause_confirmed": paused_confirmed,
                        "reactivation_confirmed": active.get("status") == "active",
                        "webhook_validation": "PENDING_DB_CORRELATION",
                        "skill_feed_status": "BLOCKED_UNTIL_WEBHOOK_VALIDATED",
                    },
                )

        if primary_error is not None:
            raise primary_error
        if not paused_confirmed or active is None or active.get("status") != "active":
            raise ControlledProofError("controlled_cycle_not_confirmed")

        final = {
            **base_evidence,
            "after": _sanitize_item(active),
            "pause_confirmed": True,
            "reactivation_confirmed": True,
            "webhook_validation": "PENDING_DB_CORRELATION",
            "skill_feed_status": "BLOCKED_UNTIL_WEBHOOK_VALIDATED",
        }
        print(json.dumps(final, ensure_ascii=False, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
