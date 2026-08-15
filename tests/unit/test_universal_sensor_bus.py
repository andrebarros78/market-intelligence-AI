from __future__ import annotations
from datetime import UTC,datetime
import pytest
from market_intelligence.marketplaces.canonical import EvidenceKind
from market_intelligence.sensors import SensorSignal,SensorSignalKind,UniversalSensorBus
@pytest.mark.asyncio
async def test_validated_fact_passes_bus():
    bus=UniversalSensorBus(); seen=[]
    async def handler(signal):seen.append(signal)
    bus.subscribe(handler)
    signal=SensorSignal(marketplace="mercadolivre",kind=SensorSignalKind.BUSINESS_EVENT,evidence_kind=EvidenceKind.FACT,source="official_api_get:/items/X",observed_at=datetime.now(UTC),payload={"status":"active"},validated=True)
    await bus.publish(signal)
    assert bus.observed_count==1 and bus.rejected_count==0 and seen==[signal]
    assert signal.permanent_fact_eligible is True
@pytest.mark.asyncio
async def test_secret_key_is_rejected():
    bus=UniversalSensorBus()
    signal=SensorSignal(marketplace="mercadolivre",kind=SensorSignalKind.CHANNEL_TELEMETRY,evidence_kind=EvidenceKind.FACT,source="channel",observed_at=datetime.now(UTC),payload={"authorization":"redacted"},validated=True)
    with pytest.raises(ValueError,match="sensor_signal_contains_secret"):await bus.publish(signal)
@pytest.mark.asyncio
async def test_hypothesis_cannot_be_promoted_as_validated_fact():
    bus=UniversalSensorBus()
    signal=SensorSignal(marketplace="mercadolivre",kind=SensorSignalKind.DERIVED,evidence_kind=EvidenceKind.HYPOTHESIS,source="radar",observed_at=datetime.now(UTC),payload={"candidate":"ranking change"},validated=True)
    with pytest.raises(ValueError,match="non_fact_signal_cannot_be_validated_as_fact"):await bus.publish(signal)
