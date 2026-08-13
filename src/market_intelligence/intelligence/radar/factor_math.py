from __future__ import annotations
import math, statistics
def differences(values:list[float])->list[float]: return [float(r)-float(l) for l,r in zip(values,values[1:])]
def pearson(left:list[float],right:list[float])->float|None:
    if len(left)!=len(right) or len(left)<2:return None
    lm,rm=statistics.fmean(left),statistics.fmean(right); lc=[v-lm for v in left]; rc=[v-rm for v in right]; ls=sum(v*v for v in lc); rs=sum(v*v for v in rc)
    if ls<=1e-18 or rs<=1e-18:return None
    return max(-1.0,min(1.0,float(sum(a*b for a,b in zip(lc,rc))/math.sqrt(ls*rs))))
def slope(x:list[float],y:list[float])->float|None:
    if len(x)!=len(y) or len(x)<2:return None
    mx,my=statistics.fmean(x),statistics.fmean(y); den=sum((v-mx)**2 for v in x)
    if den<=1e-18:return None
    return float(sum((a-mx)*(b-my) for a,b in zip(x,y))/den)
def change_scale(values:list[float])->float:
    vals=[abs(v) for v in values if abs(v)>1e-12]; return max(float(statistics.median(vals)),1e-12) if vals else 0.0
