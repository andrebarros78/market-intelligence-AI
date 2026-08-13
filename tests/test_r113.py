from datetime import UTC,datetime
from market_intelligence.intelligence.radar.factor_attribution import FactorAttributionEngine,ObservableFactorAttributionDetector
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.residual import UnexplainedResidualDetector
TARGET=[100,110,105,115,110,120,115,125,120,130]
GOOD=[50,55,52.5,57.5,55,60,57.5,62.5,60,65]
BAD=[1,9,2,8,3,7,4,6,5,5]
def obs(current=110,factor_current=55):
 return RadarObservation(entity_id='T',observed_at=datetime.now(UTC),metrics={'visits':current},history={'visits':TARGET},context={'factor_attribution':{'metric':'visits','expected':130,'factors':[{'name':'competition','current':factor_current,'history':GOOD,'source':'market'},{'name':'noise','current':9,'history':BAD}]}})
def test_engine_selects_associated_factor_without_current_target_fit():
 a=FactorAttributionEngine().analyze(obs()); assert a; assert [f.name for f in a.factors]==['competition']; assert a.fit_uses_current_target is False; assert a.causal_claim is False; assert a.explained_delta<0
def test_fit_invariant_to_current_target():
 a=FactorAttributionEngine().analyze(obs(110)); b=FactorAttributionEngine().analyze(obs(100)); assert a and b; assert a.factors[0].association==b.factors[0].association; assert a.factors[0].slope==b.factors[0].slope
def test_direction_mismatch_rejected():
 o=RadarObservation(entity_id='T',observed_at=datetime.now(UTC),metrics={'visits':110},history={'visits':TARGET},context={'factor_attribution':{'metric':'visits','expected':130,'factors':[{'name':'competition','current':75,'history':GOOD}]}}); a=FactorAttributionEngine().analyze(o); assert a and not a.factors; assert a.excluded['direction_mismatch']==1
def test_detector_is_inference_and_cannot_trigger_alert_alone():
 r=ObservableFactorAttributionDetector().evaluate(obs()); assert r; assert r.level.value=='inference'; assert r.score<.60; assert r.attributes['causal_claim'] is False
def test_residual_auto_consumes_factor_attribution():
 r=UnexplainedResidualDetector().evaluate(obs(80,60)); assert r; assert r.attributes['analysis_attributes']['automatic_factor_attribution'] is True; assert r.attributes['observable_causes']==['competition']; assert r.attributes['unexplained_residual']<0
def test_explanation_is_capped_to_observed_delta():
 o=RadarObservation(entity_id='T',observed_at=datetime.now(UTC),metrics={'visits':110},history={'visits':TARGET},context={'factor_attribution':{'metric':'visits','expected':130,'factors':[{'name':'a','current':55,'history':GOOD},{'name':'b','current':55,'history':GOOD}]}}); a=FactorAttributionEngine().analyze(o); assert a; assert abs(a.explained_delta)<=20.0000001
