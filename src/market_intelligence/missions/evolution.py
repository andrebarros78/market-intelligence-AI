from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.missions.models import MissionCreate, MissionOrigin, MissionType
from market_intelligence.missions.persistence import PostgresMissionRepository, stable_hash

QUESTION_STATES_OPEN = ("OPEN", "REOPENED")
KNOWLEDGE_REVALIDATION_HOURS = 6


def _family(value: str) -> str:
    key = (value or "").lower()
    if "price_to_win" in key or "competition" in key:
        return "PRICE_TO_WIN"
    if "visit" in key:
        return "VISITS"
    if "order" in key:
        return "ORDERS"
    if "claim" in key or "post-purchase" in key:
        return "CLAIMS"
    if "question" in key:
        return "QUESTIONS"
    if "promotion" in key or "offer" in key or "candidate" in key:
        return "PROMOTIONS"
    if "stock" in key or "inventory" in key:
        return "STOCK"
    if "catalog" in key:
        return "CATALOG"
    if "item" in key or "listing" in key:
        return "ITEMS"
    if "webhook" in key or "notification" in key:
        return "WEBHOOK"
    if "account" in key or "users/me" in key:
        return "ACCOUNT"
    return "UNKNOWN"


def _meaning(family: str) -> tuple[str, str, str]:
    known = {
        "ORDERS": "Estado comercial de pedidos autorizado da propria conta.",
        "ITEMS": "Estado observado dos anuncios e itens da propria conta.",
        "VISITS": "Valor de visitas observado por item e janela quando retornado pela API oficial.",
        "PRICE_TO_WIN": "Estado observavel de competicao/preco para ganhar exposicao de catalogo; nao prova causalidade de vendas.",
        "CLAIMS": "Estado observavel de reclamacoes/pos-venda; zero so e fato quando o endpoint oficial confirma total zero.",
        "QUESTIONS": "Perguntas pre-venda observadas na conta.",
        "PROMOTIONS": "Ofertas/candidaturas promocionais legitimamente retornadas para a conta.",
        "STOCK": "Quantidade/disponibilidade observavel dos itens e estruturas de estoque autorizadas.",
        "CATALOG": "Sinais de catalogo, associacao e superficie de produto observaveis.",
        "ACCOUNT": "Identidade e capacidades observaveis da conta autenticada.",
        "WEBHOOK": "Evento recebido do marketplace; e gatilho e deve ser reconciliado com o recurso oficial.",
        "UNKNOWN": "Familia ainda sem semantica operacional suficiente.",
    }
    unknown = {
        "PRICE_TO_WIN": "Nao se conhece por este sinal isolado a causa de mudanca de vendas, ranking ou exposicao.",
        "VISITS": "A janela e a semantica exata devem permanecer ligadas ao contrato observado.",
        "ORDERS": "Custos e margem completa exigem componentes financeiros adicionais.",
        "UNKNOWN": "Significado de negocio ainda precisa ser investigado antes de promocao de conhecimento.",
    }
    relevance = {
        "ORDERS": "vendas_receita_demanda",
        "ITEMS": "preco_estoque_status_exposicao",
        "VISITS": "trafego_conversao_observavel",
        "PRICE_TO_WIN": "competitividade_catalogo",
        "CLAIMS": "reputacao_pos_venda",
        "QUESTIONS": "demanda_friccao_pre_venda",
        "PROMOTIONS": "oportunidade_preco_promocao",
        "STOCK": "ruptura_disponibilidade",
        "CATALOG": "exposicao_competicao",
        "WEBHOOK": "mudanca_evento",
        "ACCOUNT": "capacidade_restricao",
        "UNKNOWN": "desconhecida",
    }
    return known.get(family, known["UNKNOWN"]), unknown.get(family, "Limites e causalidade ainda precisam de validacao."), relevance.get(family, "desconhecida")


def _question_priority(statement: str, *, evidence_available: float = 0.8, recurrence: float = 0.8, novelty: float = 0.7) -> tuple[int, float, dict[str, float]]:
    s = statement.casefold()
    impact = 1.0 if any(x in s for x in ("venda", "pedido", "receita", "competitiv", "visita", "estoque", "claim", "reclam")) else 0.7
    uncertainty = 0.9 if any(x in s for x in ("por que", "qual", "pode", "hipot", "ainda", "antecede")) else 0.7
    actionability = 0.9 if any(x in s for x in ("perda", "queda", "ganho", "risco", "oportun", "antecede")) else 0.7
    factors = {
        "business_impact": impact,
        "uncertainty": uncertainty,
        "evidence_availability": max(0.1, min(1.0, evidence_available)),
        "recurrence": max(0.1, min(1.0, recurrence)),
        "actionability_future": actionability,
        "novelty": max(0.1, min(1.0, novelty)),
    }
    value = math.prod(factors.values())
    return min(100, max(1, round(100 * value))), value, factors


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


class ContinuousEvolutionEngine:
    version = "sovereign-continuous-evolution@1.0.0"

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        mission_repository: PostgresMissionRepository,
        runtime_root: Path,
        *,
        interval_seconds: int = 300,
    ) -> None:
        self.sessions = sessions
        self.missions = mission_repository
        self.runtime_root = runtime_root
        self.interval_seconds = max(60, int(interval_seconds))

    @staticmethod
    def assert_security() -> None:
        if os.getenv("MI_READ_ONLY", "true").strip().lower() != "true":
            raise RuntimeError("continuous_evolution_requires_read_only")
        if os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").strip().lower() != "false":
            raise RuntimeError("continuous_evolution_forbids_marketplace_writes")
        if os.getenv("MARKETPLACE_WRITES", "0").strip() != "0":
            raise RuntimeError("continuous_evolution_marketplace_writes_nonzero")

    async def run_due(self, *, force: bool = False) -> dict[str, Any]:
        self.assert_security()
        now = datetime.now(UTC)
        bucket = int(now.timestamp()) // self.interval_seconds
        cycle_key = stable_hash({"engine": self.version, "bucket": bucket if not force else f"force-{now.isoformat()}"})
        async with self.sessions() as session:
            if not force:
                locked = bool(
                    (
                        await session.execute(
                            text("SELECT pg_try_advisory_xact_lock(hashtext('sovereign-continuous-evolution'))")
                        )
                    ).scalar_one()
                )
                if not locked:
                    await session.rollback()
                    return {"status": "SKIPPED_COOLDOWN", "marketplace_writes": 0}
                recent = (
                    await session.execute(
                        text("""
                        SELECT 1 FROM evolution_cycles
                        WHERE started_at >= :cutoff
                          AND status IN ('RUNNING','COMPLETED')
                        ORDER BY started_at DESC LIMIT 1
                        """),
                        {"cutoff": now - timedelta(seconds=self.interval_seconds)},
                    )
                ).scalar_one_or_none()
                if recent is not None:
                    await session.rollback()
                    return {"status": "SKIPPED_COOLDOWN", "marketplace_writes": 0}
            inserted = (
                await session.execute(
                    text("""
                    INSERT INTO evolution_cycles(cycle_id,cycle_key,status,summary_json,marketplace_writes)
                    VALUES(:id,:key,'RUNNING','{}'::jsonb,0)
                    ON CONFLICT(cycle_key) DO NOTHING RETURNING cycle_id
                    """),
                    {"id": uuid4(), "key": cycle_key},
                )
            ).scalar_one_or_none()
            await session.commit()
        if inserted is None:
            return {"status": "SKIPPED_COOLDOWN", "marketplace_writes": 0}
        try:
            summary = {
                "signal_dictionary": await self.refresh_signal_dictionary(),
                "commercial_baseline": await self.refresh_commercial_baselines(),
                "questions": await self.refresh_questions(),
                "predictions": await self.refresh_predictions(),
                "prediction_evaluation": await self.evaluate_due_predictions(),
                "knowledge_revalidation": await self.refresh_knowledge_lifecycle(),
                "drift": await self.detect_drift(),
                "leading_signals": await self.research_leading_signals(),
                "rejected_hypotheses": await self.learn_from_rejections(),
            }
            summary["question_outcomes"] = await self.refresh_question_outcomes()
            summary["autonomous_investigation"] = await self.open_highest_value_question()
            summary["metrics"] = await self.persist_metrics()
            summary["marketplace_writes"] = 0
            await self._finish_cycle(inserted, "COMPLETED", summary)
            await self.write_report(summary)
            return {"status": "COMPLETED", **summary}
        except Exception as exc:
            await self._finish_cycle(inserted, "FAILED", {"error": type(exc).__name__, "marketplace_writes": 0})
            raise

    async def _finish_cycle(self, cycle_id: Any, status: str, summary: dict[str, Any]) -> None:
        async with self.sessions() as session:
            await session.execute(
                text("UPDATE evolution_cycles SET status=:s,summary_json=CAST(:j AS jsonb),completed_at=now(),marketplace_writes=0 WHERE cycle_id=:id"),
                {"s": status, "j": json.dumps(summary, ensure_ascii=False, default=str), "id": cycle_id},
            )
            await session.commit()

    async def refresh_signal_dictionary(self) -> dict[str, int]:
        rows: list[dict[str, Any]] = []
        async with self.sessions() as session:
            channels = (await session.execute(text("""
                SELECT operation,min(observed_at) first_seen,max(observed_at) last_seen,count(*) n,
                       array_remove(array_agg(DISTINCT status_code),NULL) statuses
                FROM channel_events GROUP BY operation ORDER BY operation
            """))).mappings().all()
            for item in channels:
                family = _family(str(item["operation"]))
                known, unknown, _ = _meaning(family)
                span = max(0.0, (item["last_seen"] - item["first_seen"]).total_seconds())
                rows.append({
                    "marketplace":"mercadolivre","family":family,"source":"universal_sensor_channel",
                    "who":"collector","collector":True,"endpoint":str(item["operation"]),
                    "requested":"Leitura/polling executado pelo proprio coletor.",
                    "returned":"Telemetria HTTP da chamada; nao e resultado comercial por si so.",
                    "fields":["status_code","latency_ms","attempt"],"entity_type":"channel_operation",
                    "temporal":{"observations":int(item["n"]),"average_interval_seconds":span/max(1,int(item["n"])-1),"statuses":list(item["statuses"] or [])},
                    "known":known,"unknown":unknown,"relevance":"instrumentation_only","related":[],"confidence":1.0,
                    "first":item["first_seen"],"last":item["last_seen"],"validated":item["last_seen"],
                })
            stats = {str(r["entity_type"]):dict(r) for r in (await session.execute(text("""
                SELECT entity_type,min(captured_at) first_seen,max(captured_at) last_seen,count(*) n
                FROM snapshots GROUP BY entity_type
            """))).mappings().all()}
            samples = (await session.execute(text("""
                SELECT DISTINCT ON(entity_type) entity_type,payload,captured_at
                FROM snapshots ORDER BY entity_type,captured_at DESC
            """))).mappings().all()
            for sample in samples:
                etype=str(sample["entity_type"]); stat=stats[etype]; family=_family(etype)
                known,unknown,relevance=_meaning(family); payload=sample["payload"] if isinstance(sample["payload"],dict) else {}
                rows.append({
                    "marketplace":"mercadolivre","family":family,"source":"universal_sensor_snapshot",
                    "who":"collector_read","collector":False,"endpoint":etype,
                    "requested":f"Estado oficial de {etype} da propria conta.",
                    "returned":f"Snapshot sanitizado de {etype} retornado pelo marketplace.",
                    "fields":sorted(str(k) for k in payload)[:80],"entity_type":etype,
                    "temporal":{"observations":int(stat["n"]),"first_seen_at":stat["first_seen"].isoformat(),"last_seen_at":stat["last_seen"].isoformat()},
                    "known":known,"unknown":unknown,"relevance":relevance,"related":[],
                    "confidence":0.9 if family!="UNKNOWN" else 0.5,"first":stat["first_seen"],"last":stat["last_seen"],
                    "validated":stat["last_seen"] if family!="UNKNOWN" else None,
                })
            raw = (await session.execute(text("""
                SELECT source,event_type,min(received_at) first_seen,max(received_at) last_seen,count(*) n,max(resource) resource
                FROM raw_events GROUP BY source,event_type ORDER BY source,event_type
            """))).mappings().all()
            for item in raw:
                family=_family(str(item["event_type"])+" "+str(item["resource"] or "")); known,unknown,relevance=_meaning(family)
                rows.append({
                    "marketplace":"mercadolivre","family":family,"source":str(item["source"]),
                    "who":"marketplace_notification_or_authorized_probe","collector":False,
                    "endpoint":str(item["resource"] or item["event_type"]),
                    "requested":"Recurso/superficie legitimamente observado apos evento autorizado.",
                    "returned":"Schema/metadados sanitizados ou recurso oficial permitido.","fields":[],"entity_type":"surface",
                    "temporal":{"observations":int(item["n"]),"first_seen_at":item["first_seen"].isoformat(),"last_seen_at":item["last_seen"].isoformat()},
                    "known":known,"unknown":unknown,"relevance":relevance,"related":[],
                    "confidence":0.75 if family!="UNKNOWN" else 0.4,"first":item["first_seen"],"last":item["last_seen"],
                    "validated":item["last_seen"] if family!="UNKNOWN" else None,
                })
            for row in rows:
                await session.execute(text("""
                    INSERT INTO signal_dictionary(id,marketplace,signal_family,source,who_triggered_it,collector_generated,
                        endpoint_or_topic,what_we_requested,what_marketplace_returned,important_fields,entity_type,
                        temporal_behavior,known_meaning,unknown_meaning,business_relevance,related_signals,confidence,
                        first_seen_at,last_seen_at,last_validated_at)
                    VALUES(:id,:marketplace,:family,:source,:who,:collector,:endpoint,:requested,:returned,CAST(:fields AS jsonb),
                        :entity_type,CAST(:temporal AS jsonb),:known,:unknown,:relevance,CAST(:related AS jsonb),:confidence,:first,:last,:validated)
                    ON CONFLICT(marketplace,signal_family,source,endpoint_or_topic) DO UPDATE SET
                        who_triggered_it=EXCLUDED.who_triggered_it,collector_generated=EXCLUDED.collector_generated,
                        what_we_requested=EXCLUDED.what_we_requested,what_marketplace_returned=EXCLUDED.what_marketplace_returned,
                        important_fields=EXCLUDED.important_fields,entity_type=EXCLUDED.entity_type,temporal_behavior=EXCLUDED.temporal_behavior,
                        known_meaning=EXCLUDED.known_meaning,unknown_meaning=EXCLUDED.unknown_meaning,business_relevance=EXCLUDED.business_relevance,
                        related_signals=EXCLUDED.related_signals,confidence=EXCLUDED.confidence,
                        first_seen_at=LEAST(signal_dictionary.first_seen_at,EXCLUDED.first_seen_at),
                        last_seen_at=GREATEST(signal_dictionary.last_seen_at,EXCLUDED.last_seen_at),last_validated_at=EXCLUDED.last_validated_at,updated_at=now()
                """),{**row,"id":uuid4(),"fields":json.dumps(row["fields"]),"temporal":json.dumps(row["temporal"],default=str),"related":json.dumps(row["related"])})
            await session.commit()
        return {"rows":len(rows),"understood":sum(1 for r in rows if r["family"]!="UNKNOWN" and not r["collector"]),"unknown":sum(1 for r in rows if r["family"]=="UNKNOWN" and not r["collector"]),"collector_instrumentation":sum(1 for r in rows if r["collector"])}

    @staticmethod
    def _metric_value(entity_type: str, entity_id: str, payload: dict[str, Any], metric: str) -> Any:
        if metric == "visits":
            direct=payload.get("visits")
            if _num(direct) is not None:
                return direct
            keyed=payload.get(entity_id)
            return keyed if _num(keyed) is not None else None
        return payload.get(metric)

    async def refresh_commercial_baselines(self) -> dict[str,int]:
        metrics={"listing":("price","available_quantity","sold_quantity","status"),"visits":("visits",),"catalog_competition":("current_price","price_to_win","status","visit_share"),"order":("total_amount","paid_amount","status")}
        async with self.sessions() as session:
            snapshots=(await session.execute(text("""
                SELECT entity_type,entity_id,captured_at,payload FROM snapshots
                WHERE entity_type IN ('listing','visits','catalog_competition','order')
                ORDER BY entity_type,entity_id,captured_at,id
            """))).mappings().all()
            series:dict[tuple[str,str,str],list[tuple[datetime,Any]]]=defaultdict(list)
            daily:dict[str,dict[str,float]]=defaultdict(lambda:{"orders":0.0,"revenue":0.0,"units":0.0})
            for row in snapshots:
                etype=str(row["entity_type"]); eid=str(row["entity_id"]); payload=row["payload"] if isinstance(row["payload"],dict) else {}
                for metric in metrics.get(etype,()):
                    value=self._metric_value(etype,eid,payload,metric)
                    if value is not None and isinstance(value,(str,int,float,bool)):
                        series[(etype,eid,metric)].append((row["captured_at"],value))
                if etype=="order":
                    created=_parse_dt(payload.get("date_created"))
                    if created:
                        day=created.astimezone(UTC).date().isoformat(); daily[day]["orders"]+=1
                        daily[day]["revenue"]+=_num(payload.get("paid_amount")) or _num(payload.get("total_amount")) or 0.0
                        daily[day]["units"]+=sum(float(x.get("quantity") or 0) for x in payload.get("order_items") or [] if isinstance(x,dict))
            for day,values in daily.items():
                dt=datetime.fromisoformat(day).replace(tzinfo=UTC)
                for metric,value in values.items(): series[("operation","orders_daily",metric)].append((dt,value))
            count=0
            for (etype,eid,metric),values in series.items():
                if not values: continue
                values.sort(key=lambda x:x[0]); raw=[v for _,v in values]; numeric=[float(v) for v in raw if _num(v) is not None]
                transitions=sum(1 for a,b in pairwise(raw) if a!=b)
                if numeric:
                    split=max(1,len(numeric)//2)
                    baseline={"first":numeric[0],"median_early":median(numeric[:split]),"min":min(numeric),"max":max(numeric),"transitions":transitions}
                    current={"value":numeric[-1],"median_late":median(numeric[split:] or numeric[-1:]),"transitions":transitions}
                else:
                    baseline={"first":raw[0],"values":list(dict.fromkeys(str(v) for v in raw))[:20],"transitions":transitions}; current={"value":raw[-1],"transitions":transitions}
                confidence=min(0.95,0.45+0.1*min(5,len(values)))
                await session.execute(text("""
                    INSERT INTO commercial_baselines(baseline_id,marketplace,entity_type,entity_id,metric,baseline_json,current_json,sample_count,first_observed_at,last_observed_at,source,confidence)
                    VALUES(:id,'mercadolivre',:etype,:eid,:metric,CAST(:baseline AS jsonb),CAST(:current AS jsonb),:n,:first,:last,'official_read_snapshots',:confidence)
                    ON CONFLICT(marketplace,entity_type,entity_id,metric) DO UPDATE SET baseline_json=EXCLUDED.baseline_json,current_json=EXCLUDED.current_json,
                    sample_count=EXCLUDED.sample_count,first_observed_at=EXCLUDED.first_observed_at,last_observed_at=EXCLUDED.last_observed_at,source=EXCLUDED.source,confidence=EXCLUDED.confidence,updated_at=now()
                """),{"id":uuid4(),"etype":etype,"eid":eid,"metric":metric,"baseline":json.dumps(baseline),"current":json.dumps(current),"n":len(values),"first":values[0][0],"last":values[-1][0],"confidence":confidence})
                count+=1
            await session.commit()
        return {"baseline_metrics":count,"entities":len({(k[0],k[1]) for k in series}),"order_days":len(daily)}

    async def _upsert_question(self, statement:str, source:str, *, entities:list[str]|None=None, signals:list[str]|None=None, evidence:list[str]|None=None, evidence_available:float=0.8, recurrence:float=0.8, novelty:float=0.7) -> bool:
        priority,value,factors=_question_priority(statement,evidence_available=evidence_available,recurrence=recurrence,novelty=novelty)
        key=stable_hash({"statement":statement.strip().casefold(),"source":source})
        async with self.sessions() as session:
            row=(await session.execute(text("""
                INSERT INTO cognitive_questions(question_id,dedupe_key,statement,source,priority,expected_value,priority_factors,status,related_entities,related_signals,evidence_required)
                VALUES(:id,:key,:statement,:source,:priority,:value,CAST(:factors AS jsonb),'OPEN',CAST(:entities AS jsonb),CAST(:signals AS jsonb),CAST(:evidence AS jsonb))
                ON CONFLICT(dedupe_key) DO UPDATE SET priority=EXCLUDED.priority,expected_value=EXCLUDED.expected_value,priority_factors=EXCLUDED.priority_factors,
                    related_entities=EXCLUDED.related_entities,related_signals=EXCLUDED.related_signals,evidence_required=EXCLUDED.evidence_required,
                    status=CASE WHEN cognitive_questions.status IN ('REJECTED','ANSWERED') THEN cognitive_questions.status ELSE cognitive_questions.status END,
                    last_reviewed_at=now(),updated_at=now() RETURNING (xmax=0) AS inserted
            """),{"id":uuid4(),"key":key,"statement":statement,"source":source,"priority":priority,"value":value,"factors":json.dumps(factors),
                   "entities":json.dumps(entities or []),"signals":json.dumps(signals or []),"evidence":json.dumps(evidence or [])})).scalar_one()
            await session.commit(); return bool(row)

    async def refresh_questions(self) -> dict[str,int]:
        seed=[
            ("Que sinais legitimamente observaveis antecedem pedidos ou aumento de vendas?",["ORDERS","VISITS","PRICE_TO_WIN","ITEMS"]),
            ("Que sinais antecedem perda ou ganho de competitividade sem confundir correlacao com causalidade?",["PRICE_TO_WIN","VISITS","ORDERS"]),
            ("Que sinais antecedem queda de visitas e o padrao se repete entre anuncios comparaveis?",["VISITS","ITEMS","PRICE_TO_WIN"]),
            ("O que pode anteceder reclamacao real quando houver claims observaveis?",["CLAIMS","ORDERS","ITEMS"]),
            ("O comportamento sharing_first_place para winning e retorno de MLB3936072281 coincide com mudanca de pedidos, visitas, preco ou estoque e se repete em outros anuncios?",["PRICE_TO_WIN","ORDERS","VISITS","ITEMS"]),
            ("No MLB5043378730, qual campo mudou de R$53,25 para R$78,90, qual sua semantica correta e que resultados comerciais ocorreram antes e depois?",["PRICE_TO_WIN","ORDERS","VISITS","ITEMS"]),
            ("Quais familias de sinais ainda estao semanticamente desconhecidas e qual delas possui maior valor comercial potencial?",["UNKNOWN"]),
            ("Qual conhecimento validado esta envelhecendo ou contradito e precisa ser revalidado agora?",["KNOWLEDGE_REVALIDATION"]),
        ]
        inserted=0
        for statement,signals in seed:
            inserted+=int(await self._upsert_question(statement,"continuous_evolution_seed",signals=signals,evidence=["historical_snapshots","validated_non_collector_intelligence"]))
        async with self.sessions() as session:
            iterations=(await session.execute(text("SELECT iteration_json FROM mission_iterations ORDER BY completed_at DESC LIMIT 100"))).scalars().all()
            unknown=(await session.execute(text("SELECT signal_family,endpoint_or_topic FROM signal_dictionary WHERE collector_generated=false AND signal_family='UNKNOWN' ORDER BY updated_at DESC LIMIT 30"))).mappings().all()
        for payload in iterations:
            if not isinstance(payload,dict): continue
            for q in payload.get("open_questions") or []:
                if isinstance(q,str) and len(q)>=8:
                    inserted+=int(await self._upsert_question(q,"instigator_or_counterintelligence",evidence=["mission_evidence"],novelty=0.8))
        for row in unknown:
            statement=f"O que significa operacionalmente o sinal {row['endpoint_or_topic']} e qual relevancia de negocio pode ser validada?"
            inserted+=int(await self._upsert_question(statement,"unknown_signal_family",signals=[str(row["signal_family"])],evidence=["official_read","repetition","counterexample"],novelty=1.0))
        async with self.sessions() as session:
            counts={str(r["status"]):int(r["n"]) for r in (await session.execute(text("SELECT status,count(*) n FROM cognitive_questions GROUP BY status"))).mappings().all()}
        return {"inserted":inserted,"open":counts.get("OPEN",0)+counts.get("REOPENED",0),"investigating":counts.get("INVESTIGATING",0),"answered":counts.get("ANSWERED",0),"inconclusive":counts.get("INCONCLUSIVE",0)}

    async def refresh_predictions(self) -> dict[str,int]:
        now=datetime.now(UTC); inserted=0
        async with self.sessions() as session:
            rows=(await session.execute(text("""
                SELECT id,entity_type,entity_id,signal_kind,confidence,observed_at,report_json
                FROM sovereign_intelligence
                WHERE knowledge_state NOT IN ('rejected','quarantined')
                  AND COALESCE(report_json#>>'{signal,source}','') <> 'universal_sensor_channel'
                ORDER BY observed_at DESC LIMIT 1500
            """))).mappings().all()
            for row in rows:
                report=row["report_json"] if isinstance(row["report_json"],dict) else {}; pred=report.get("prediction") if isinstance(report.get("prediction"),dict) else {}
                statement=str(pred.get("statement") or "").strip()
                if not statement: continue
                conf=max(0.0,min(1.0,float(pred.get("confidence") or row["confidence"] or 0.0)))
                key=stable_hash({"source":str(row["id"]),"statement":statement})
                due=row["observed_at"]+timedelta(hours=6)
                result=await session.execute(text("""
                    INSERT INTO prediction_evaluations(prediction_id,dedupe_key,source_intelligence_id,statement,target,time_horizon,confidence_before,expected_observation,evaluation_due_at,observed_result,correct_or_incorrect,confidence_after,status,marketplace_writes)
                    VALUES(:id,:key,:sid,:statement,:target,:horizon,:conf,CAST(:expected AS jsonb),:due,'{}'::jsonb,'PENDING',:conf,'PENDING',0)
                    ON CONFLICT(dedupe_key) DO NOTHING RETURNING prediction_id
                """),{"id":uuid4(),"key":key,"sid":row["id"],"statement":statement,"target":f"{row['entity_type']}:{row['entity_id']}:{row['signal_kind']}",
                       "horizon":str(pred.get("horizon") or "proxima_janela_observacional"),"conf":conf,"expected":json.dumps({"entity_type":row["entity_type"],"entity_id":row["entity_id"],"signal_kind":row["signal_kind"],"after":row["observed_at"].isoformat()}),"due":due})
                inserted+=int(result.scalar_one_or_none() is not None)
            await session.commit()
            total=int((await session.execute(text("SELECT count(*) FROM prediction_evaluations"))).scalar_one())
        return {"inserted":inserted,"total":total,"generated_at":now.isoformat()}

    async def evaluate_due_predictions(self) -> dict[str,Any]:
        now=datetime.now(UTC); evaluated=correct=incorrect=0; errors:list[float]=[]
        async with self.sessions() as session:
            due=(await session.execute(text("SELECT * FROM prediction_evaluations WHERE status='PENDING' AND evaluation_due_at<=:now ORDER BY evaluation_due_at LIMIT 500"),{"now":now})).mappings().all()
            for row in due:
                expected=row["expected_observation"] if isinstance(row["expected_observation"],dict) else {}; after=_parse_dt(expected.get("after")) or row["created_at"]
                match=(await session.execute(text("""
                    SELECT id,observed_at,knowledge_state FROM sovereign_intelligence
                    WHERE entity_type=:etype AND entity_id=:eid AND signal_kind=:kind AND observed_at>:after
                      AND COALESCE(report_json#>>'{signal,source}','') <> 'universal_sensor_channel'
                    ORDER BY observed_at ASC LIMIT 1
                """),{"etype":expected.get("entity_type"),"eid":expected.get("entity_id"),"kind":expected.get("signal_kind"),"after":after})).mappings().first()
                outcome=1.0 if match else 0.0; conf=float(row["confidence_before"]); error=abs(conf-outcome); errors.append(error)
                result="CORRECT" if match else "INCORRECT"; new_conf=min(0.99,conf+0.05*(1-conf)) if match else max(0.05,conf*0.75)
                observed={"matched":bool(match),"matched_intelligence_id":str(match["id"]) if match else None,"observed_at":match["observed_at"].isoformat() if match else None}
                await session.execute(text("UPDATE prediction_evaluations SET observed_result=CAST(:obs AS jsonb),correct_or_incorrect=:result,calibration_error=:error,confidence_after=:new,status='EVALUATED',last_evaluated_at=:now WHERE prediction_id=:id"),
                                      {"obs":json.dumps(observed),"result":result,"error":error,"new":new_conf,"now":now,"id":row["prediction_id"]})
                evaluated+=1; correct+=int(bool(match)); incorrect+=int(not match)
                if not match:
                    await self._upsert_question(f"Por que a previsao falhou: {row['statement']}","prediction_error",evidence=["prediction","observed_result","regime_change_check"],novelty=0.9)
            await session.commit()
        return {"evaluated":evaluated,"correct":correct,"incorrect":incorrect,"mean_calibration_error":sum(errors)/len(errors) if errors else 0.0}

    async def refresh_knowledge_lifecycle(self) -> dict[str,int]:
        now=datetime.now(UTC); due=now+timedelta(hours=KNOWLEDGE_REVALIDATION_HOURS)
        async with self.sessions() as session:
            rows=(await session.execute(text("""
                SELECT id,entity_type,entity_id,signal_kind,confidence,observed_at,knowledge_state,report_json
                FROM sovereign_intelligence
                WHERE knowledge_state='validated' AND COALESCE(report_json#>>'{signal,source}','') <> 'universal_sensor_channel'
                ORDER BY observed_at
            """))).mappings().all()
            grouped:dict[tuple[str,str,str],list[dict[str,Any]]]=defaultdict(list)
            for row in rows: grouped[(str(row["entity_type"]),str(row["entity_id"]),str(row["signal_kind"]))].append(dict(row))
            touched=0
            for values in grouped.values():
                latest=values[-1]; first=values[0]; support=len(values); state="VALIDATED" if latest["observed_at"]>=now-timedelta(hours=KNOWLEDGE_REVALIDATION_HOURS) else "REVALIDATION_REQUIRED"
                await session.execute(text("""
                    INSERT INTO knowledge_lifecycle(knowledge_id,source_intelligence_id,validated_at,last_confirmed_at,revalidation_due_at,support_count,contradiction_count,current_confidence,knowledge_version,state,last_reason)
                    VALUES(:id,:sid,:validated,:last,:due,:support,0,:conf,1,:state,:reason)
                    ON CONFLICT(source_intelligence_id) DO UPDATE SET last_confirmed_at=EXCLUDED.last_confirmed_at,revalidation_due_at=EXCLUDED.revalidation_due_at,
                    support_count=EXCLUDED.support_count,current_confidence=EXCLUDED.current_confidence,state=EXCLUDED.state,last_reason=EXCLUDED.last_reason,knowledge_version=knowledge_lifecycle.knowledge_version+1,updated_at=now()
                """),{"id":uuid4(),"sid":latest["id"],"validated":first["observed_at"],"last":latest["observed_at"],"due":max(due,latest["observed_at"]+timedelta(hours=KNOWLEDGE_REVALIDATION_HOURS)),
                       "support":support,"conf":float(latest["confidence"]),"state":state,"reason":"recent_non_collector_validation" if state=="VALIDATED" else "confirmation_window_expired"})
                touched+=1
                if state=="REVALIDATION_REQUIRED": await self._upsert_question(f"Revalidar conhecimento {latest['signal_kind']} para {latest['entity_id']} porque a janela de confirmacao expirou.","knowledge_revalidation",entities=[str(latest["entity_id"])],signals=[_family(str(latest["signal_kind"]))],evidence=["new_official_observation","counterexample"])
            await session.commit()
            counts={str(r["state"]):int(r["n"]) for r in (await session.execute(text("SELECT state,count(*) n FROM knowledge_lifecycle GROUP BY state"))).mappings().all()}
        return {"tracked":touched,"validated":counts.get("VALIDATED",0),"revalidation_required":counts.get("REVALIDATION_REQUIRED",0),"aging":counts.get("AGING",0)}

    async def detect_drift(self) -> dict[str,int]:
        now=datetime.now(UTC); detected=0
        async with self.sessions() as session:
            rows=(await session.execute(text("SELECT * FROM commercial_baselines WHERE sample_count>=2"))).mappings().all()
            for row in rows:
                base=row["baseline_json"] if isinstance(row["baseline_json"],dict) else {}; cur=row["current_json"] if isinstance(row["current_json"],dict) else {}
                a=_num(base.get("median_early")); b=_num(cur.get("median_late")); magnitude=0.0; relevant=False
                if a is not None and b is not None:
                    denom=max(abs(a),1e-9); magnitude=(b-a)/denom; relevant=bool(row["sample_count"]>=3 and abs(magnitude)>=0.20)
                elif base.get("first") is not None and cur.get("value") is not None:
                    relevant=base.get("first")!=cur.get("value") and int(cur.get("transitions") or 0)>=2; magnitude=1.0 if relevant else 0.0
                if not relevant: continue
                family=_family(str(row["metric"])+" "+str(row["entity_type"])); key=stable_hash({"family":family,"etype":row["entity_type"],"eid":row["entity_id"],"metric":row["metric"],"bucket":row["last_observed_at"].date().isoformat()})
                result=await session.execute(text("""
                    INSERT INTO drift_events(drift_id,dedupe_key,signal_family,entity_type,entity_id,metric,baseline_json,current_json,magnitude,confidence,state,detected_at,last_seen_at)
                    VALUES(:id,:key,:family,:etype,:eid,:metric,CAST(:base AS jsonb),CAST(:cur AS jsonb),:mag,:conf,'DETECTED',:now,:last)
                    ON CONFLICT(dedupe_key) DO UPDATE SET current_json=EXCLUDED.current_json,magnitude=EXCLUDED.magnitude,confidence=EXCLUDED.confidence,last_seen_at=EXCLUDED.last_seen_at,updated_at=now()
                    RETURNING (xmax=0) inserted
                """),{"id":uuid4(),"key":key,"family":family,"etype":row["entity_type"],"eid":row["entity_id"],"metric":row["metric"],"base":json.dumps(base),"cur":json.dumps(cur),"mag":magnitude,"conf":float(row["confidence"]),"now":now,"last":row["last_observed_at"]})
                detected+=int(bool(result.scalar_one()))
                await self._upsert_question(f"O que explica o drift em {row['metric']} de {row['entity_type']}:{row['entity_id']} e ele se repete em grupo de controle?","drift_detector",entities=[str(row["entity_id"])],signals=[family],evidence=["baseline_before_after","comparison_group","counterintelligence"],recurrence=0.9)
            await session.commit()
            total=int((await session.execute(text("SELECT count(*) FROM drift_events WHERE state IN ('DETECTED','INVESTIGATING','CONFIRMED')"))).scalar_one())
        return {"new":detected,"active":total}

    async def research_leading_signals(self) -> dict[str,int]:
        async with self.sessions() as session:
            orders=(await session.execute(text("SELECT payload,captured_at FROM snapshots WHERE entity_type='order' ORDER BY captured_at"))).mappings().all()
            signals=(await session.execute(text("SELECT entity_type,entity_id,captured_at,payload FROM snapshots WHERE entity_type IN ('listing','visits','catalog_competition') ORDER BY captured_at"))).mappings().all()
            by_item:dict[str,list[dict[str,Any]]]=defaultdict(list)
            for s in signals: by_item[str(s["entity_id"])].append(dict(s))
            stats:dict[tuple[str,str],list[float]]=defaultdict(list)
            order_items=0
            for order in orders:
                payload=order["payload"] if isinstance(order["payload"],dict) else {}; occurred=_parse_dt(payload.get("date_created")) or order["captured_at"]
                for oi in payload.get("order_items") or []:
                    if not isinstance(oi,dict) or not oi.get("item_id"): continue
                    item=str(oi["item_id"]); order_items+=1
                    candidates=[s for s in by_item.get(item,[]) if timedelta(0)<=(occurred-s["captured_at"])<=timedelta(hours=24)]
                    for s in candidates:
                        stats[(_family(str(s["entity_type"])),"ORDERS")].append((occurred-s["captured_at"]).total_seconds())
            persisted=0
            for (ante,outcome),leads in stats.items():
                support=len(leads); precision=min(1.0,support/max(1,order_items)); state="CANDIDATE" if support>=3 and precision>=0.05 else "INCONCLUSIVE"; conf=min(0.9,0.3+0.05*min(10,support))
                key=stable_hash({"ante":ante,"outcome":outcome,"group":"all_items"})
                await session.execute(text("""
                    INSERT INTO leading_signal_research(research_id,dedupe_key,antecedent_family,outcome_family,entity_group,lead_time_seconds,support,precision,false_positives,false_negatives,confidence,state,evidence_json)
                    VALUES(:id,:key,:ante,:outcome,'all_items',:lead,:support,:precision,0,0,:conf,:state,CAST(:evidence AS jsonb))
                    ON CONFLICT(dedupe_key) DO UPDATE SET lead_time_seconds=EXCLUDED.lead_time_seconds,support=EXCLUDED.support,precision=EXCLUDED.precision,confidence=EXCLUDED.confidence,state=EXCLUDED.state,evidence_json=EXCLUDED.evidence_json,updated_at=now()
                """),{"id":uuid4(),"key":key,"ante":ante,"outcome":outcome,"lead":median(leads),"support":support,"precision":precision,"conf":conf,"state":state,"evidence":json.dumps({"order_items":order_items,"observed_lead_samples":support,"causal_claim":False})})
                persisted+=1
            await session.commit()
        return {"relations":persisted,"order_items_checked":order_items,"candidate_relations":sum(1 for v in stats.values() if len(v)>=3)}

    async def learn_from_rejections(self) -> dict[str,int]:
        inserted=0
        async with self.sessions() as session:
            rows=(await session.execute(text("SELECT mission_id,finding_json FROM mission_findings WHERE knowledge_state='rejected' ORDER BY created_at DESC LIMIT 2000"))).mappings().all()
            for row in rows:
                data=row["finding_json"] if isinstance(row["finding_json"],dict) else {}; report=data.get("report") if isinstance(data.get("report"),dict) else {}; validation=report.get("validation") if isinstance(report.get("validation"),dict) else {}
                statement=str(data.get("summary") or (report.get("intelligence") or {}).get("summary") or data.get("signal_kind") or "rejected finding")
                reason=str(validation.get("reason") or data.get("error_class") or "insufficient_evidence")
                if data.get("collector_generated_pattern") or (report.get("signal") or {}).get("source")=="universal_sensor_channel": error="collector_artifact"
                elif "causal" in reason: error="spurious_correlation"
                elif "schema" in reason: error="schema_change"
                else: error="insufficient_evidence"
                key=stable_hash({"statement":statement,"error":error})
                result=await session.execute(text("""
                    INSERT INTO rejected_hypotheses(rejected_id,dedupe_key,statement,reason,evidence_json,error_class,lesson,source_mission_id)
                    VALUES(:id,:key,:statement,:reason,CAST(:evidence AS jsonb),:error,:lesson,:mid)
                    ON CONFLICT(dedupe_key) DO UPDATE SET reason=EXCLUDED.reason,evidence_json=EXCLUDED.evidence_json,last_seen_at=now() RETURNING (xmax=0) inserted
                """),{"id":uuid4(),"key":key,"statement":statement[:4000],"reason":reason[:4000],"evidence":json.dumps({"finding":data},default=str),"error":error,"lesson":f"Nao promover novamente sem nova evidencia que resolva: {reason}"[:4000],"mid":row["mission_id"]})
                inserted+=int(bool(result.scalar_one()))
            await session.commit()
        return {"new_lessons":inserted,"reviewed":len(rows)}

    async def refresh_question_outcomes(self) -> dict[str,int]:
        answered=inconclusive=rejected=0
        async with self.sessions() as session:
            rows=(await session.execute(text("""
                SELECT q.question_id,q.investigation_id,m.status
                FROM cognitive_questions q JOIN sovereign_missions m ON m.mission_id=q.investigation_id
                WHERE q.status='INVESTIGATING' AND m.status IN ('COMPLETED','FAILED','CANCELLED','BLOCKED')
            """))).mappings().all()
            for row in rows:
                if row["status"]=="COMPLETED":
                    states=[str(x) for x in (await session.execute(text("SELECT knowledge_state FROM mission_findings WHERE mission_id=:mid"),{"mid":row["investigation_id"]})).scalars().all()]
                    if "validated" in states: status="ANSWERED"; answer="VALIDATED"; answered+=1
                    elif states and all(s=="rejected" for s in states): status="REJECTED"; answer="REJECTED"; rejected+=1
                    else: status="INCONCLUSIVE"; answer="INCONCLUSIVE"; inconclusive+=1
                else: status="INCONCLUSIVE"; answer=str(row["status"]); inconclusive+=1
                await session.execute(text("UPDATE cognitive_questions SET status=:status,answer_state=:answer,last_reviewed_at=now(),updated_at=now() WHERE question_id=:id"),{"status":status,"answer":answer,"id":row["question_id"]})
            await session.commit()
        return {"answered":answered,"inconclusive":inconclusive,"rejected":rejected}

    async def open_highest_value_question(self) -> dict[str,Any]:
        if await self.missions.active_autonomous_count()>=4:
            return {"created":False,"reason":"concurrency_limit"}
        async with self.sessions() as session:
            row=(await session.execute(text("""
                SELECT * FROM cognitive_questions WHERE status IN ('OPEN','REOPENED')
                ORDER BY expected_value DESC,priority DESC,created_at ASC LIMIT 1
            """))).mappings().first()
        if not row: return {"created":False,"reason":"no_open_question"}
        request=MissionCreate(objective="Investigacao soberana continua: "+str(row["statement"])+" Use somente evidencia legitima, tente falsificar a conclusao, nao trate correlacao como causa e mantenha escrita externa zero.",origin=MissionOrigin.SYSTEM,mission_type=MissionType.AUTONOMOUS,marketplace_scope=("mercadolivre",),authority="system_read_only",priority=int(row["priority"]),idempotency_key="evolution-"+str(row["question_id"]))
        mission,created=await self.missions.create(request,dedupe_key=stable_hash({"question_id":str(row["question_id"]),"statement":row["statement"]}))
        if created:
            async with self.sessions() as session:
                await session.execute(text("UPDATE cognitive_questions SET status='INVESTIGATING',investigation_id=:mid,last_reviewed_at=now(),updated_at=now() WHERE question_id=:id"),{"mid":mission["mission_id"],"id":row["question_id"]}); await session.commit()
            await self.missions.add_evidence(mission["mission_id"],"continuous_evolution_question","sovereign-continuous-evolution",{"question_id":str(row["question_id"]),"expected_value":float(row["expected_value"]),"priority_factors":row["priority_factors"],"marketplace_writes":0})
        return {"created":created,"mission_id":mission["mission_id"],"question_id":str(row["question_id"]),"expected_value":float(row["expected_value"])}

    async def record_human_hypothesis(self, statement:str, signal_family:str, confidence_initial:float=0.5) -> dict[str,Any]:
        self.assert_security(); confidence=max(0.0,min(1.0,float(confidence_initial))); key=stable_hash({"source":"owner_domain_experience","statement":statement.strip().casefold(),"signal_family":signal_family.upper()})
        async with self.sessions() as session:
            row=(await session.execute(text("""
                INSERT INTO human_domain_hypotheses(hypothesis_id,dedupe_key,source,statement,signal_family,confidence_initial,requires_validation,status)
                VALUES(:id,:key,'owner_domain_experience',:statement,:family,:confidence,true,'OPEN')
                ON CONFLICT(dedupe_key) DO UPDATE SET confidence_initial=EXCLUDED.confidence_initial,updated_at=now() RETURNING hypothesis_id,status
            """),{"id":uuid4(),"key":key,"statement":statement,"family":signal_family.upper(),"confidence":confidence})).mappings().one(); await session.commit()
        await self._upsert_question("Validar experiencia do proprietario: "+statement,"owner_domain_experience",signals=[signal_family.upper()],evidence=["independent_observation","counterexample","counterintelligence"],novelty=0.9)
        return {"hypothesis_id":str(row["hypothesis_id"]),"status":row["status"],"requires_validation":True,"promoted_to_fact":False}

    async def persist_metrics(self) -> dict[str,Any]:
        async with self.sessions() as session:
            def scalar(sql:str)->int: raise RuntimeError("sync_helper_not_used")
            total_signals=int((await session.execute(text("SELECT (SELECT count(*) FROM snapshots)+(SELECT count(*) FROM raw_events)+(SELECT count(*) FROM channel_events)"))).scalar_one())
            understood=int((await session.execute(text("SELECT count(DISTINCT signal_family) FROM signal_dictionary WHERE collector_generated=false AND signal_family<>'UNKNOWN'"))).scalar_one())
            unknown=int((await session.execute(text("SELECT count(DISTINCT endpoint_or_topic) FROM signal_dictionary WHERE collector_generated=false AND signal_family='UNKNOWN'"))).scalar_one())
            qrows={str(r["status"]):int(r["n"]) for r in (await session.execute(text("SELECT status,count(*) n FROM cognitive_questions GROUP BY status"))).mappings().all()}
            validated=int((await session.execute(text("SELECT count(*) FROM knowledge_lifecycle WHERE state='VALIDATED'"))).scalar_one())
            rejected=int((await session.execute(text("SELECT count(*) FROM rejected_hypotheses"))).scalar_one())
            quarantined=int((await session.execute(text("SELECT count(*) FROM sovereign_intelligence WHERE knowledge_state='quarantined'"))).scalar_one())
            stale=int((await session.execute(text("SELECT count(*) FROM knowledge_lifecycle WHERE state IN ('AGING','REVALIDATION_REQUIRED')"))).scalar_one())
            prows={str(r["status"]):int(r["n"]) for r in (await session.execute(text("SELECT status,count(*) n FROM prediction_evaluations GROUP BY status"))).mappings().all()}
            correct=int((await session.execute(text("SELECT count(*) FROM prediction_evaluations WHERE correct_or_incorrect='CORRECT'"))).scalar_one()); incorrect=int((await session.execute(text("SELECT count(*) FROM prediction_evaluations WHERE correct_or_incorrect='INCORRECT'"))).scalar_one())
            cal=float((await session.execute(text("SELECT coalesce(avg(calibration_error),0) FROM prediction_evaluations WHERE status='EVALUATED'"))).scalar_one())
            drift=int((await session.execute(text("SELECT count(*) FROM drift_events WHERE state IN ('DETECTED','INVESTIGATING','CONFIRMED')"))).scalar_one())
            auto=int((await session.execute(text("SELECT count(*) FROM sovereign_missions WHERE mission_type='AUTONOMOUS'"))).scalar_one())
            false_blocked=int((await session.execute(text("SELECT count(*) FROM sovereign_intelligence WHERE report_json->>'collector_generated_pattern'='true'"))).scalar_one())
            human=int((await session.execute(text("SELECT count(*) FROM human_domain_hypotheses"))).scalar_one()); human_valid=int((await session.execute(text("SELECT count(*) FROM human_domain_hypotheses WHERE status='VALIDATED'"))).scalar_one())
            details={"engine":self.version,"false_learning_policy":"collector_generated_pattern_excluded_from_marketplace_knowledge"}
            await session.execute(text("""
                INSERT INTO evolution_metrics(metric_id,observed_at,total_signals,understood_signal_families,unknown_signal_families,open_questions,answered_questions,validated_knowledge,rejected_knowledge,quarantined_knowledge,stale_knowledge,predictions_made,predictions_evaluated,predictions_correct,predictions_incorrect,calibration_error,regime_changes,autonomous_investigations,false_patterns_blocked,human_hypotheses,human_hypotheses_validated,marketplace_writes,details_json)
                VALUES(:id,now(),:signals,:understood,:unknown,:open,:answered,:validated,:rejected,:quarantined,:stale,:pmade,:peval,:pcorrect,:pincorrect,:cal,:drift,:auto,:blocked,:human,:humanv,0,CAST(:details AS jsonb))
            """),{"id":uuid4(),"signals":total_signals,"understood":understood,"unknown":unknown,"open":qrows.get("OPEN",0)+qrows.get("REOPENED",0),"answered":qrows.get("ANSWERED",0),"validated":validated,"rejected":rejected,"quarantined":quarantined,"stale":stale,"pmade":sum(prows.values()),"peval":prows.get("EVALUATED",0),"pcorrect":correct,"pincorrect":incorrect,"cal":cal,"drift":drift,"auto":auto,"blocked":false_blocked,"human":human,"humanv":human_valid,"details":json.dumps(details)}); await session.commit()
        return {"TOTAL_SIGNALS":total_signals,"UNDERSTOOD_SIGNAL_FAMILIES":understood,"UNKNOWN_SIGNAL_FAMILIES":unknown,"OPEN_QUESTIONS":qrows.get("OPEN",0)+qrows.get("REOPENED",0),"ANSWERED_QUESTIONS":qrows.get("ANSWERED",0),"VALIDATED_KNOWLEDGE":validated,"REJECTED_KNOWLEDGE":rejected,"QUARANTINED_KNOWLEDGE":quarantined,"STALE_KNOWLEDGE":stale,"PREDICTIONS_MADE":sum(prows.values()),"PREDICTIONS_EVALUATED":prows.get("EVALUATED",0),"PREDICTIONS_CORRECT":correct,"PREDICTIONS_INCORRECT":incorrect,"CALIBRATION_ERROR":cal,"REGIME_CHANGES":drift,"AUTONOMOUS_INVESTIGATIONS":auto,"FALSE_PATTERNS_BLOCKED":false_blocked,"HUMAN_HYPOTHESES":human,"HUMAN_HYPOTHESES_VALIDATED":human_valid,"MARKETPLACE_WRITES":0}
    async def executive_snapshot(self) -> dict[str, Any]:
        async with self.sessions() as session:
            latest_metrics=(await session.execute(text("SELECT * FROM evolution_metrics ORDER BY observed_at DESC LIMIT 1"))).mappings().first()
            cycle=(await session.execute(text("SELECT cycle_id,status,summary_json,started_at,completed_at FROM evolution_cycles ORDER BY started_at DESC LIMIT 1"))).mappings().first()
            next_q=(await session.execute(text("SELECT question_id,statement,priority,expected_value,status,related_signals FROM cognitive_questions WHERE status IN ('OPEN','REOPENED') ORDER BY expected_value DESC,priority DESC,created_at ASC LIMIT 1"))).mappings().first()
            investigating=[dict(r) for r in (await session.execute(text("SELECT question_id,statement,priority,expected_value,investigation_id FROM cognitive_questions WHERE status='INVESTIGATING' ORDER BY expected_value DESC LIMIT 10"))).mappings().all()]
            top_drift=[dict(r) for r in (await session.execute(text("SELECT drift_id,signal_family,entity_id,metric,magnitude,confidence,state,mission_id,detected_at FROM drift_events WHERE state IN ('DETECTED','INVESTIGATING','CONFIRMED') ORDER BY confidence DESC,magnitude DESC LIMIT 10"))).mappings().all()]
            leading=[dict(r) for r in (await session.execute(text("SELECT antecedent_family,outcome_family,entity_group,lead_time_seconds,support,precision,confidence,state FROM leading_signal_research ORDER BY confidence DESC,support DESC LIMIT 10"))).mappings().all()]
            unknown=[dict(r) for r in (await session.execute(text("SELECT signal_family,source,endpoint_or_topic,unknown_meaning,last_seen_at FROM signal_dictionary WHERE collector_generated=false AND (signal_family='UNKNOWN' OR confidence<0.65) ORDER BY last_seen_at DESC LIMIT 10"))).mappings().all()]
            latest_rejected=[dict(r) for r in (await session.execute(text("SELECT statement,reason,error_class,lesson,last_seen_at FROM rejected_hypotheses ORDER BY last_seen_at DESC LIMIT 10"))).mappings().all()]
            latest_validated=[dict(r) for r in (await session.execute(text("SELECT k.source_intelligence_id,k.current_confidence,k.support_count,k.contradiction_count,k.state,k.last_confirmed_at,s.summary FROM knowledge_lifecycle k JOIN sovereign_intelligence s ON s.id=k.source_intelligence_id WHERE k.state='VALIDATED' ORDER BY k.last_confirmed_at DESC LIMIT 10"))).mappings().all()]
        metrics=dict(latest_metrics) if latest_metrics else {"marketplace_writes":0}
        return {
            "engine": self.version,
            "generated_at": datetime.now(UTC).isoformat(),
            "cycle": dict(cycle) if cycle else None,
            "metrics": metrics,
            "next_question": dict(next_q) if next_q else None,
            "investigating_now": investigating,
            "active_drift": top_drift,
            "leading_signal_candidates": leading,
            "still_unknown": unknown,
            "recent_rejected_hypotheses": latest_rejected,
            "recent_validated_knowledge": latest_validated,
            "marketplace_writes": 0,
        }

    async def write_report(self, cycle_summary: dict[str, Any] | None = None) -> Path:
        snapshot=await self.executive_snapshot()
        metrics=snapshot.get("metrics") or {}
        nq=snapshot.get("next_question") or {}
        def n(key: str) -> int:
            try: return int(metrics.get(key.lower(), metrics.get(key, 0)) or 0)
            except (TypeError, ValueError): return 0
        lines=[
            "# RELAT\u00d3RIO SOBERANO DE EVOLU\u00c7\u00c3O",
            "",
            "Gerado em: "+snapshot["generated_at"],
            "",
            "## 1. O QUE APRENDEMOS",
            f"Conhecimentos validados atualmente: {n('validated_knowledge')}.",
            "",
            "## 2. O QUE DESAPRENDEMOS",
            f"Conhecimentos rejeitados registrados: {n('rejected_knowledge')}. Padr\u00f5es falsos bloqueados: {n('false_patterns_blocked')}.",
            "",
            "## 3. O QUE ESTAVA ERRADO",
            "Hip\u00f3teses rejeitadas permanecem registradas com motivo, evid\u00eancia, classe de erro e li\u00e7\u00e3o; artefatos do coletor n\u00e3o podem ser promovidos a comportamento do marketplace.",
            "",
            "## 4. O QUE MUDOU NO MARKETPLACE",
            f"Mudancas de regime/drift ativas: {n('regime_changes')}.",
            "",
            "## 5. QUAIS SINAIS AGORA ENTENDEMOS",
            f"Fam\u00edlias de sinais entendidas: {n('understood_signal_families')}.",
            "",
            "## 6. QUAIS AINDA N\u00c3O ENTENDEMOS",
            f"Fam\u00edlias/superf\u00edcies ainda desconhecidas: {n('unknown_signal_families')}.",
            "",
            "## 7. QUAIS HIP\u00d3TESES FORAM REJEITADAS",
            json.dumps(snapshot["recent_rejected_hypotheses"],ensure_ascii=False,default=str,indent=2),
            "",
            "## 8. QUAIS CONHECIMENTOS FORAM VALIDADOS",
            json.dumps(snapshot["recent_validated_knowledge"],ensure_ascii=False,default=str,indent=2),
            "",
            "## 9. QUAIS PREVIS\u00d5ES ACERTARAM",
            f"Previs\u00f5es corretas avaliadas: {n('predictions_correct')}.",
            "",
            "## 10. QUAIS PREVIS\u00d5ES ERRARAM",
            f"Previs\u00f5es incorretas avaliadas: {n('predictions_incorrect')}; erro de calibra\u00e7\u00e3o agregado: {metrics.get('calibration_error',0)}.",
            "",
            "## 11. O QUE O INSTIGADOR EST\u00c1 PERGUNTANDO",
            f"Perguntas abertas: {n('open_questions')}.",
            "",
            "## 12. O QUE O INVESTIGADOR EST\u00c1 APURANDO",
            json.dumps(snapshot["investigating_now"],ensure_ascii=False,default=str,indent=2),
            "",
            "## 13. O QUE A CONTRAINTELIG\u00caNCIA DERRUBOU",
            "As conclus\u00f5es rejeitadas e inconclusivas permanecem separadas de conhecimento validado.",
            "",
            "## 14. PRINCIPAIS AMEA\u00c7AS",
            json.dumps(snapshot["active_drift"],ensure_ascii=False,default=str,indent=2),
            "",
            "## 15. PRINCIPAIS OPORTUNIDADES",
            json.dumps(snapshot["leading_signal_candidates"],ensure_ascii=False,default=str,indent=2),
            "",
            "## 16. PR\u00d3XIMA PERGUNTA DE MAIOR VALOR",
            str(nq.get("statement") or "Nenhuma pergunta prioriz\u00e1vel dispon\u00edvel neste ciclo."),
            "",
            "MARKETPLACE_WRITES=0",
        ]
        report="\n".join(lines)+"\n"
        # Source remains ASCII-safe while the resulting report is real UTF-8 Portuguese.
        report=report.encode("utf-8").decode("unicode_escape") if "\\u" in report else report
        root=self.runtime_root/"evolution"; root.mkdir(parents=True,exist_ok=True)
        report_path=root/"RELATORIO_SOBERANO_DE_EVOLUCAO.md"
        snapshot_path=root/"snapshot.json"
        report_path.write_text(report,encoding="utf-8")
        snapshot_path.write_text(json.dumps(snapshot,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
        return report_path
