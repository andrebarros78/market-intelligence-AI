from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from typing import Any

import httpx

MODEL = "glm-4.7-flash"
ENDPOINT = "https://api.z.ai/api/paas/v4/chat/completions"
PROMPT = "Synthetic API ML diagnostic. Reply with exactly SANDBOX_OK and no other text."
_SAFE_CODE = re.compile(r"^[0-9]{4}$")


def _safe_numeric_code(payload: Any) -> str | None:
    """Extract only a four-digit provider code; never return provider messages."""
    candidates: list[Any] = []
    if isinstance(payload, dict):
        candidates.extend([payload.get("code"), payload.get("código")])
        for key in ("error", "erro"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                candidates.extend([nested.get("code"), nested.get("código")])
    for value in candidates:
        if isinstance(value, int):
            text = str(value)
        elif isinstance(value, str):
            text = value.strip()
        else:
            continue
        if _SAFE_CODE.fullmatch(text):
            return text
    return None


async def _run() -> int:
    api_key = os.getenv("MI_AI_AGENTS_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({"status": "missing_secret"}, sort_keys=True))
        return 2

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "thinking": {"type": "disabled"},
        "stream": False,
        "max_tokens": 32,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            response = await client.post(ENDPOINT, headers=headers, json=body)
    except (httpx.TimeoutException, httpx.TransportError):
        print(json.dumps({"status": "transport_error"}, sort_keys=True))
        return 3

    if response.status_code >= 400:
        try:
            payload: Any = response.json()
        except ValueError:
            payload = None
        print(
            json.dumps(
                {
                    "status": "provider_error",
                    "http_status": response.status_code,
                    "zai_code": _safe_numeric_code(payload) or "unknown",
                    "model": MODEL,
                    "business_data_sent": False,
                },
                sort_keys=True,
            )
        )
        return 1

    try:
        payload = response.json()
    except ValueError:
        print(json.dumps({"status": "invalid_success_response"}, sort_keys=True))
        return 4

    choices = payload.get("choices") if isinstance(payload, dict) else None
    usage = payload.get("usage") if isinstance(payload, dict) else None
    output_present = isinstance(choices, list) and bool(choices)
    safe_usage: dict[str, int] = {}
    if isinstance(usage, dict):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                safe_usage[key] = value

    print(
        json.dumps(
            {
                "status": "success" if output_present else "empty_success_response",
                "http_status": response.status_code,
                "authenticated": True,
                "model": MODEL,
                "inference_executed": True,
                "synthetic_data_only": True,
                "business_data_sent": False,
                "output_present": output_present,
                "usage": safe_usage,
            },
            sort_keys=True,
        )
    )
    return 0 if output_present else 5


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
