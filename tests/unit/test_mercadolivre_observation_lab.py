from __future__ import annotations

import json

import pytest

from market_intelligence.marketplaces.mercadolivre.observation_lab import analyze_har


def _har() -> dict:
    return {
        "log": {
            "entries": [
                {
                    "request": {
                        "method": "POST",
                        "url": "https://www.mercadolivre.com.br/internal/track/123456789?session=private&access_token=do-not-store",
                        "headers": [
                            {"name": "Authorization", "value": "Bearer SUPERSECRET"},
                            {"name": "Content-Type", "value": "application/json"},
                        ],
                        "queryString": [
                            {"name": "session", "value": "private"},
                            {"name": "access_token", "value": "do-not-store"},
                        ],
                        "postData": {
                            "mimeType": "application/json",
                            "text": json.dumps(
                                {
                                    "seller_id": 123456789,
                                    "event": "edit_price",
                                    "email": "private@example.com",
                                    "access_token": "SUPERSECRET",
                                }
                            ),
                        },
                    },
                    "response": {
                        "status": 200,
                        "headers": [{"name": "Set-Cookie", "value": "SESSION=SECRET"}],
                        "content": {
                            "mimeType": "application/json",
                            "text": json.dumps(
                                {
                                    "ok": True,
                                    "decision": {"score": 0.93, "reason": "internal"},
                                    "customer_email": "private@example.com",
                                }
                            ),
                        },
                    },
                },
                {
                    "request": {
                        "method": "GET",
                        "url": "https://evil.example/private?token=steal",
                        "headers": [],
                    },
                    "response": {
                        "status": 200,
                        "headers": [],
                        "content": {"mimeType": "text/plain", "text": "bad"},
                    },
                },
            ]
        }
    }


def test_har_analysis_keeps_structure_not_secret_or_pii_values() -> None:
    report = analyze_har(_har())
    assert report.entries_total == 2
    assert report.entries_in_scope == 1
    assert report.entries_skipped == 1
    assert report.unique_surfaces == 1
    assert report.methods == {"POST": 1}
    assert report.credential_headers_observed == 1

    payload = report.observations[0].as_safe_payload()
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    for forbidden in (
        "SUPERSECRET",
        "private@example.com",
        "do-not-store",
        "SESSION=SECRET",
        "seller_id\": 123456789",
        "0.93",
        "$.access_token:str",
    ):
        assert forbidden not in encoded

    assert payload["path_template"] == "/internal/track/{id}"
    assert payload["request_query_keys"] == ["session"]
    assert payload["request_metadata"]["credential_header_present"] is True
    request_schema = payload["request_body_schema"]["json_schema"]
    assert "$.event:str" in request_schema["schema_paths"]
    assert "$.[SECRET_FIELD]:str" in request_schema["schema_paths"]
    assert request_schema["secret_field_present"] is True
    assert "[SECRET_FIELD]" in request_schema["top_level_fields"]
    assert "$.decision.score:float" in payload["response_metadata"]["json_schema"]["schema_paths"]
    assert payload["values_persisted"] is False


def test_har_rejects_invalid_or_excessive_entries() -> None:
    with pytest.raises(ValueError, match="invalid_har_entries"):
        analyze_har({})
    with pytest.raises(ValueError, match="har_entry_limit_exceeded"):
        analyze_har({"log": {"entries": [{}] * 10001}})
