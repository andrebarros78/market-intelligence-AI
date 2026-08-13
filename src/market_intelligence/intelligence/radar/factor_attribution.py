from __future__ import annotations
import statistics
from pydantic import ValidationError
from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.factor_math import change_scale,differences,pearson,slope
from market_intelligence.intelligence.radar.factor_models import AttributedFactor,FactorAttribution,FactorAttributionRequest
from market_intelligence.intelligence.radar.models import DetectorResult,RadarObservation
from market_intelligence.intelligence.radar.time_series import find_seasonal_reference
class FactorAttributionEngine:
    version='factor-attribution@1.0.0'
    def __init__(self,min_history=8,min_association=.60,min_current_signal=.75,min_target_change_ratio=.10,max_factors=6): self.min_history=min_history; self.min_association=min_association; self.min_current_signal=min_current_signal; self.min_target_change_ratio=min_target_change_ratio; self.max_factors=max_factors
    def request(self,o):
        raw=o.context.get('factor_attribution')
        if not isinstance(raw,dict):return None
        try:return FactorAttributionRequest.model_validate(raw)
        except ValidationError:return None
    def expected(self,o,r):
        if r.expected is not None:return float(r.expected),'explicit_expected'
        seasonal=find_seasonal_reference(o,r.metric)
        if seasonal is not None:return float(seasonal.expected),f'seasonal:{seasonal.period}'
        h=o.history.get(r.metric,[])
        return (float(statistics.median(h)),'history_median') if len(h)>=self.min_history else None
    def analyze(self,o:RadarObservation)->FactorAttribution|None:
        r=self.request(o)
        if r is None or r.metric not in o.metrics:return None
        th=o.history.get(r.metric,[])
        if len(th)<self.min_history:return None
        er=self.expected(o,r)
        if er is None:return None
        expected,source=er; observed=float(o.metrics[r.metric]); delta=observed-expected; denom=max(abs(expected),float(statistics.median(abs(v) for v in th)),1e-9)
        if abs(delta)/denom<self.min_target_change_ratio:return None
        excluded={}; accepted=[]
        def reject(k):excluded[k]=excluded.get(k,0)+1
        for f in r.factors:
            if not f.eligible:reject('declared_ineligible');continue
            overlap=min(len(th),len(f.history))
            if overlap<self.min_history:reject('insufficient_history');continue
            tw=[float(v) for v in th[-overlap:]]; fw=[float(v) for v in f.history[-overlap:]]; td,fd=differences(tw),differences(fw); assoc=pearson(fd,td); sl=slope(fd,td)
            if assoc is None or sl is None:reject('unstable_history');continue
            if abs(assoc)<self.min_association:reject('weak_association');continue
            cur=float(f.current)-fw[-1]; sc=change_scale(fd)
            if sc<=0:reject('unstable_history');continue
            signal=abs(cur)/sc
            if signal<self.min_current_signal:reject('insufficient_current_movement');continue
            raw=sl*cur
            if abs(raw)<=1e-12:reject('negligible_contribution');continue
            if delta*raw<=0:reject('direction_mismatch');continue
            accepted.append(AttributedFactor(name=f.name,source=f.source,association=assoc,slope=sl,current_delta=cur,raw_contribution=raw,contribution=raw,historical_points=overlap,attributes={**f.attributes,'current_signal':signal,'fit_uses_current_target':False,'causal_claim':False}))
        accepted.sort(key=lambda i:(-abs(i.raw_contribution)*abs(i.association),i.name)); accepted=accepted[:self.max_factors]; raw_total=sum(abs(i.raw_contribution) for i in accepted); alloc=min(1.0,abs(delta)/raw_total) if raw_total>1e-12 else 1.0; allocated=[i.model_copy(update={'contribution':i.raw_contribution*alloc}) for i in accepted]; explained=sum(i.contribution for i in allocated); residual=delta-explained
        return FactorAttribution(metric=r.metric,expected=expected,observed=observed,observed_delta=delta,factors=allocated,explained_delta=explained,unexplained_residual=residual,explained_fraction=min(1.0,abs(explained)/max(abs(delta),1e-9)),reference_source=source,excluded=excluded,version=self.version,attributes={**r.attributes,'allocation_scale':alloc})
class ObservableFactorAttributionDetector:
    name='factor_attribution_v1'; version='factor-attribution@1.0.0'
    def __init__(self,engine=None):self.engine=engine or FactorAttributionEngine()
    def evaluate(self,o):
        a=self.engine.analyze(o)
        if a is None or not a.factors:return None
        assoc=statistics.fmean(abs(i.association) for i in a.factors); score=min(.59,.40+.10*a.explained_fraction+.09*assoc)
        return DetectorResult(detector=self.name,score=score,level=EvidenceLevel.INFERENCE,summary=f'Observable factors associated with {a.metric} explain an estimated {a.explained_fraction:.1%} of the observed change; no causal claim',attributes={'pattern':'observable_factor_attribution','metric':a.metric,'observable_causes':[i.name for i in a.factors],'factor_attribution':a.model_dump(mode='json'),'explained_delta':a.explained_delta,'unexplained_residual':a.unexplained_residual,'cause_status':'associated_not_causal','causal_claim':False,'fit_uses_current_target':False,'detector_version':self.version})
