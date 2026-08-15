from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from market_intelligence.marketplaces.mercadolivre.full_read_collector import MercadoLivreFullReadCollector


class _FakeReadOnlyAdapter:
    async def read_user_me(self):
        return SimpleNamespace(payload={"id": 123})

    async def read_user_items(self, user_id: str, *, status: str = "active", limit: int = 50):
        return SimpleNamespace(payload={"results": []})

    async def read_orders_search(self, seller_id: str, *, limit: int = 20):
        return SimpleNamespace(payload={"results": []}, telemetry=SimpleNamespace(observed_at=datetime.now(UTC)))

    async def read_questions_search(self, seller_id: str, *, limit: int = 50):
        return SimpleNamespace(
            payload={
                "total": 1,
                "limit": limit,
                "questions": [
                    {
                        "id": 10,
                        "item_id": "MLB1",
                        "status": "ANSWERED",
                        "answer": {"status": "ACTIVE", "date_created": "2026-08-15T00:00:00Z"},
                    }
                ],
            }
        )

    async def read_open_claims(self, *, limit: int = 30):
        return SimpleNamespace(payload={"data": []})

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_full_read_collector_sanitizes_questions_without_name_shadowing() -> None:
    collector = object.__new__(MercadoLivreFullReadCollector)
    collector.max_items_per_cycle = 20
    adapter = _FakeReadOnlyAdapter()
    collector._new_adapter = lambda token=None: adapter
    collector._persist_result = AsyncMock(return_value=(False, False))

    report = await collector.collect_once()

    assert report.success is True
    assert report.account_id == "123"
    assert report.questions_seen == 1
    assert report.claims_seen == 0
    assert report.errors == ()
