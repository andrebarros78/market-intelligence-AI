from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def contract_from_prediction(prediction: dict[str, Any], *, entity_id: str, observed_at: datetime) -> dict[str, Any] | None:
    metric = prediction.get("target_metric") or prediction.get("metric")
    operator = prediction.get("operator")
    baseline = prediction.get("baseline_value")
    expected = prediction.get("expected_value")
    if not metric or not operator:
        return None
    op = str(operator).upper()
    if op in {"DECREASE", "INCREASE"} and baseline is None:
        return None
    if op not in {"DECREASE", "INCREASE"} and expected is None:
        return None
    return {
        "target_entity": str(prediction.get("target_entity") or entity_id),
        "target_metric": str(metric),
        "operator": op,
        "expected_value": jsonable(expected),
        "expected_direction": str(prediction.get("expected_direction") or ("DOWN" if op == "DECREASE" else "UP" if op == "INCREASE" else "")) or None,
        "baseline_value": jsonable(baseline),
        "tolerance": float(prediction.get("tolerance") or 0.0),
        "evaluation_window": prediction.get("evaluation_window") if isinstance(prediction.get("evaluation_window"), dict) else {"start_at": observed_at.isoformat()},
        "evidence_source": str(prediction.get("evidence_source") or "official_read_snapshots"),
    }


def compare(*, operator: str, observed: Any, expected: Any, baseline: Any, tolerance: float) -> tuple[str, float | None]:
    op = operator.upper(); on = num(observed); en = num(expected); bn = num(baseline)
    if op == "DECREASE" and on is not None and bn is not None:
        if on < bn - tolerance: return "EVALUATED_CORRECT", 1.0
        if abs(on - bn) <= tolerance: return "EVALUATED_PARTIAL", 0.5
        return "EVALUATED_INCORRECT", 0.0
    if op == "INCREASE" and on is not None and bn is not None:
        if on > bn + tolerance: return "EVALUATED_CORRECT", 1.0
        if abs(on - bn) <= tolerance: return "EVALUATED_PARTIAL", 0.5
        return "EVALUATED_INCORRECT", 0.0
    if op in {"GREATER_THAN", "GT"} and on is not None and en is not None:
        return (("EVALUATED_CORRECT", 1.0) if on > en + tolerance else ("EVALUATED_INCORRECT", 0.0))
    if op in {"LESS_THAN", "LT"} and on is not None and en is not None:
        return (("EVALUATED_CORRECT", 1.0) if on < en - tolerance else ("EVALUATED_INCORRECT", 0.0))
    if op in {"AT_LEAST", "GTE"} and on is not None and en is not None:
        return (("EVALUATED_CORRECT", 1.0) if on + tolerance >= en else ("EVALUATED_INCORRECT", 0.0))
    if op in {"AT_MOST", "LTE"} and on is not None and en is not None:
        return (("EVALUATED_CORRECT", 1.0) if on - tolerance <= en else ("EVALUATED_INCORRECT", 0.0))
    if op in {"EQUALS", "EQ"}:
        if on is not None and en is not None:
            return (("EVALUATED_CORRECT", 1.0) if abs(on - en) <= tolerance else ("EVALUATED_INCORRECT", 0.0))
        return (("EVALUATED_CORRECT", 1.0) if observed == expected else ("EVALUATED_INCORRECT", 0.0))
    if op in {"NOT_EQUALS", "NE"}:
        return (("EVALUATED_CORRECT", 1.0) if observed != expected else ("EVALUATED_INCORRECT", 0.0))
    return "NOT_EVALUABLE", None


async def observe(session: AsyncSession, row: dict[str, Any]) -> dict[str, Any] | None:
    metric = str(row.get("target_metric") or "").lower(); entity = str(row.get("target_entity") or "")
    expected = row.get("expected_observation") if isinstance(row.get("expected_observation"), dict) else {}
    window = row.get("evaluation_window") if isinstance(row.get("evaluation_window"), dict) else {}
    after = parse_dt(window.get("start_at")) or parse_dt(expected.get("after")) or row["created_at"]
    now = datetime.now(UTC)
    requested_end = parse_dt(window.get("end_at")) or parse_dt(row.get("evaluation_due_at"))
    before = min(now, requested_end) if requested_end is not None else now
    if metric in {"orders", "order_count"}:
        count = int((await session.execute(text("""
            SELECT count(*) FROM snapshots
            WHERE entity_type='order' AND captured_at>:after AND captured_at<=:before
              AND EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(payload->'order_items','[]'::jsonb)) oi WHERE oi->>'item_id'=:entity)
        """), {"after":after,"before":before,"entity":entity})).scalar_one())
        return {"value":count,"metric":"orders","source":"snapshots:order","observed_at":before.isoformat()} if count else None
    source = {
        "visits":"visits", "stock":"listing", "available_quantity":"listing", "price":"listing", "listing_price":"listing",
        "current_price":"catalog_competition", "price_to_win":"catalog_competition", "competition":"catalog_competition",
        "competition_status":"catalog_competition", "visit_share":"catalog_competition", "claims":"claim", "claim_count":"claim",
    }.get(metric)
    if not source:
        return None
    snap = (await session.execute(text("""
        SELECT payload,captured_at FROM snapshots
        WHERE entity_type=:etype AND entity_id=:entity AND captured_at>:after AND captured_at<=:before
        ORDER BY captured_at DESC LIMIT 1
    """), {"etype":source,"entity":entity,"after":after,"before":before})).mappings().first()
    if not snap:
        return None
    payload = snap["payload"] if isinstance(snap["payload"], dict) else {}
    if metric == "visits": value = payload.get("visits", payload.get(entity))
    elif metric == "stock": value = payload.get("available_quantity")
    elif metric in {"listing_price", "price"}: value = payload.get("price")
    elif metric in {"competition", "competition_status"}: value = payload.get("status")
    else: value = payload.get(metric)
    if value is None:
        return None
    return {"value":value,"metric":metric,"source":f"snapshots:{source}","observed_at":snap["captured_at"].isoformat()}
