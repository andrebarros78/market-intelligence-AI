from __future__ import annotations

import pytest
from temporalio.exceptions import ApplicationError

from market_intelligence.marketplaces.base import MarketplaceReadError
from market_intelligence.workflows.activities import MarketplaceActivities


class FailingAdapter:
    name = "mercadolivre"

    def __init__(self, *, retryable: bool) -> None:
        self.retryable = retryable

    async def fetch_resource(self, resource: str) -> dict:
        raise MarketplaceReadError(
            "synthetic_marketplace_failure",
            status_code=429 if self.retryable else 404,
            retryable=self.retryable,
        )

    def normalize_notification(self, payload: dict):
        raise NotImplementedError


@pytest.mark.asyncio
@pytest.mark.parametrize(("retryable", "non_retryable"), [(True, False), (False, True)])
async def test_marketplace_activity_maps_provider_failure_to_temporal_retry_policy(
    retryable: bool, non_retryable: bool
) -> None:
    activities = MarketplaceActivities(
        {"mercadolivre": FailingAdapter(retryable=retryable)}
    )
    with pytest.raises(ApplicationError) as caught:
        await activities.fetch_resource(
            {"marketplace": "mercadolivre", "resource": "/items/MLB1"}
        )
    assert caught.value.non_retryable is non_retryable
    assert "synthetic_marketplace_failure" in str(caught.value)
