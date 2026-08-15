from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC,datetime,timedelta
from sqlalchemy import func,select
from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker
from market_intelligence.persistence.models import ChannelEventRecord,EvidenceRecord,RawEventRecord,SnapshotRecord
@dataclass(frozen=True,slots=True)
class HistoricalMemorySummary:
    raw_events:int; channel_events:int; snapshots:int; evidence:int; marketplaces:tuple[str,...]; oldest_snapshot_at:datetime|None; newest_snapshot_at:datetime|None
class HistoricalMemoryService:
    def __init__(self,sessions:async_sessionmaker[AsyncSession])->None:self._sessions=sessions
    async def summary(self)->HistoricalMemorySummary:
        async with self._sessions() as s:
            raw=int((await s.execute(select(func.count()).select_from(RawEventRecord))).scalar_one())
            channel=int((await s.execute(select(func.count()).select_from(ChannelEventRecord))).scalar_one())
            snaps=int((await s.execute(select(func.count()).select_from(SnapshotRecord))).scalar_one())
            evidence=int((await s.execute(select(func.count()).select_from(EvidenceRecord))).scalar_one())
            mkts=tuple(sorted(str(x) for x in (await s.execute(select(SnapshotRecord.marketplace).distinct())).scalars().all() if x))
            oldest,newest=(await s.execute(select(func.min(SnapshotRecord.captured_at),func.max(SnapshotRecord.captured_at)))).one()
        return HistoricalMemorySummary(raw,channel,snaps,evidence,mkts,oldest,newest)
    async def is_continuous(self,max_staleness:timedelta=timedelta(hours=24))->bool:
        summary=await self.summary(); newest=summary.newest_snapshot_at
        if newest is None:return False
        if newest.tzinfo is None:newest=newest.replace(tzinfo=UTC)
        return datetime.now(UTC)-newest<=max_staleness
