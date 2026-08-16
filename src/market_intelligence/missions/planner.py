from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict

from market_intelligence.missions.models import MissionCreate


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


FAMILY_MARKERS: dict[str, tuple[str, ...]] = {
    "sales": ("venda", "vendas", "faturamento", "sold", "conversao", "conversion"),
    "demand": ("demanda", "procura", "intencao", "interest"),
    "visits": ("visita", "visitas", "trafego", "traffic"),
    "price": ("preco", "precos", "price"),
    "competition": ("competitiv", "concorr", "competition"),
    "catalog": ("catalog", "categoria", "atributo"),
    "exposure": ("exposicao", "visibilidade", "ranking", "impressao", "distribution"),
    "stock": ("estoque", "stock", "available_quantity"),
    "questions": ("pergunta", "perguntas", "question"),
    "orders": ("pedido", "pedidos", "order"),
    "payments": ("pagamento", "pagamentos", "payment"),
    "logistics": ("logistica", "envio", "frete", "shipping", "delivery"),
    "post_sale": ("pos-venda", "pos venda", "claim", "reclamacao", "devolucao"),
    "reputation": ("reputacao", "reputation", "qualidade"),
    "promotions": ("promoc", "campanha", "campaign", "discount"),
    "channel": ("canal", "latencia", "webhook", "notific", "http", "rate limit"),
    "schema": ("schema", "campo", "endpoint", "surface", "superficie"),
}

FAMILY_QUESTIONS: dict[str, tuple[str, ...]] = {
    "sales": (
        "As vendas realmente mudaram no periodo solicitado?",
        "Quando a mudanca comecou e quais entidades concentram o efeito?",
        "A mudanca e localizada ou aparece em varias entidades comparaveis?",
    ),
    "demand": ("Ha mudanca observavel de demanda ou intencao?",),
    "visits": ("Visitas ou sinais de trafego mudaram antes ou junto do resultado?",),
    "price": ("Preco proprio ou sinais de preco competitivo mudaram?",),
    "competition": ("A competitividade observavel mudou no mesmo periodo?",),
    "catalog": ("Catalogo, categoria, atributos ou elegibilidade observavel mudaram?",),
    "exposure": ("Ha evidencias de mudanca de exposicao ou distribuicao?",),
    "stock": ("Disponibilidade ou estoque observavel limitou a operacao?",),
    "questions": ("Perguntas ou outros sinais de intencao mudaram?",),
    "orders": ("Pedidos mudaram de volume, composicao ou estado observavel?",),
    "payments": ("Sinais de pagamento legitimamente observaveis mudaram?",),
    "logistics": ("Promessa, frete, prazo ou outro sinal logistico mudou?",),
    "post_sale": ("Claims, devolucoes ou pos-venda observavel mudaram?",),
    "reputation": ("Reputacao ou indicadores de qualidade observaveis mudaram?",),
    "promotions": ("Promocoes ou campanhas observaveis mudaram?",),
    "channel": ("Canal, notificacoes, latencia, erros ou limites mudaram?",),
    "schema": ("Schema, campos, endpoints ou superficies observaveis mudaram?",),
}

FAMILY_TERMS: dict[str, tuple[str, ...]] = {
    "sales": ("sold", "sale", "order", "conversion", "venda"),
    "demand": ("demand", "question", "visit", "interest", "demanda"),
    "visits": ("visit", "traffic", "visita"),
    "price": ("price", "preco"),
    "competition": ("competition", "compet", "concorr"),
    "catalog": ("catalog", "category", "attribute", "catalogo"),
    "exposure": ("exposure", "distribution", "ranking", "visibility", "exposicao"),
    "stock": ("stock", "available_quantity", "inventory", "estoque"),
    "questions": ("question", "pergunta"),
    "orders": ("order", "pedido"),
    "payments": ("payment", "pagamento"),
    "logistics": ("shipping", "delivery", "logistic", "frete"),
    "post_sale": ("claim", "return", "refund", "reclam"),
    "reputation": ("reputation", "quality", "reput"),
    "promotions": ("promotion", "campaign", "discount", "promoc"),
    "channel": ("channel", "webhook", "latency", "http", "notification", "rate"),
    "schema": ("schema", "surface", "field", "endpoint"),
}

BROAD_MARKERS = (
    "baseline",
    "todo historico",
    "todo o historico",
    "toda operacao",
    "varredura soberana",
    "mudancas, anomalias",
)


class InvestigationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_version: str = "cognitive-mission-planner@1.0.0"
    objective_original: str
    main_question: str
    secondary_questions: list[str]
    temporal_window: dict[str, Any]
    relevant_entities: list[str]
    marketplaces: list[str]
    signal_families: list[str]
    signal_terms: list[str]
    available_data: dict[str, int]
    missing_data: list[str]
    initial_hypotheses: list[dict[str, Any]]
    validation_criteria: list[str]
    rejection_criteria: list[str]
    minimum_evidence: dict[str, Any]
    safety_limits: list[str]
    stop_condition: list[str]
    priority: int
    possible_deepenings: list[str]
    mode: str = "standard"


class CognitiveMissionPlanner:
    version = "cognitive-mission-planner@1.0.0"

    @staticmethod
    def _lookback_hours(text: str) -> int | None:
        value = normalized(text)
        if any(marker in value for marker in BROAD_MARKERS):
            return None
        hour = re.search(r"(?:ultima|ultimas|last)?\s*(\d{1,4})\s*hora", value)
        if hour:
            return max(1, min(24 * 365, int(hour.group(1))))
        day = re.search(r"(?:ultimo|ultimos|last)?\s*(\d{1,4})\s*dia", value)
        if day:
            return max(24, min(24 * 365, int(day.group(1)) * 24))
        if "hoje" in value:
            return 24
        return 24

    def compile(
        self,
        request: MissionCreate,
        *,
        data_inventory: dict[str, int],
        mode: str = "standard",
        inherited_context: dict[str, Any] | None = None,
    ) -> InvestigationPlan:
        text = normalized(request.objective)
        broad = any(marker in text for marker in BROAD_MARKERS)
        families = list(FAMILY_MARKERS) if broad else [
            family
            for family, markers in FAMILY_MARKERS.items()
            if any(marker in text for marker in markers)
        ]
        if not families:
            families = ["channel", "schema", "exposure", "demand"]
        if "sales" in families:
            for extra in (
                "demand", "visits", "price", "competition", "exposure", "stock",
                "questions", "orders", "logistics", "channel",
            ):
                if extra not in families:
                    families.append(extra)
        secondary: list[str] = []
        for family in families:
            secondary.extend(FAMILY_QUESTIONS.get(family, ()))
        secondary.extend(
            (
                "Que evidencia contraria existe para as hipoteses principais?",
                "A mudanca pode ser explicada por alteracao de coleta, schema ou cobertura?",
                "O que ainda nao foi explicado e merece nova investigacao?",
            )
        )
        secondary = list(dict.fromkeys(secondary))[:40]
        terms = list(dict.fromkeys(term for family in families for term in FAMILY_TERMS.get(family, ())))
        missing: list[str] = []
        if data_inventory.get("snapshots", 0) == 0:
            missing.append("snapshots_historicos")
        if data_inventory.get("channel_events", 0) == 0:
            missing.append("telemetria_de_canal")
        if data_inventory.get("raw_events", 0) == 0:
            missing.append("eventos_brutos_sanitizados")
        if data_inventory.get("sovereign_intelligence", 0) == 0:
            missing.append("inteligencia_soberana_persistida")
        hypotheses = [
            {
                "statement": f"A familia de sinais {family} pode estar relacionada ao objetivo, sem causalidade presumida.",
                "status": "initial_hypothesis",
                "causal_claim": False,
                "falsifier": f"Nenhuma evidencia observavel de {family} acompanha ou antecede o fenomeno.",
            }
            for family in families[:12]
        ]
        deepenings = secondary[:10]
        if inherited_context:
            inherited_question = str(inherited_context.get("follow_up_question") or "").strip()
            if inherited_question:
                deepenings.insert(0, inherited_question)
        return InvestigationPlan(
            objective_original=request.objective,
            main_question=request.objective.strip(),
            secondary_questions=secondary,
            temporal_window={"lookback_hours": self._lookback_hours(request.objective), "basis": "objective"},
            relevant_entities=[],
            marketplaces=list(request.marketplace_scope),
            signal_families=families,
            signal_terms=terms,
            available_data=data_inventory,
            missing_data=missing,
            initial_hypotheses=hypotheses,
            validation_criteria=[
                "evidencia_repetida_ou_independente",
                "proveniencia_suficiente",
                "investigacao_progressiva_nao_rejeitada",
                "auditoria_cognitiva_sem_falha_critica",
            ],
            rejection_criteria=[
                "evidencia_contraria_material",
                "mudanca_explica-se_por_coleta_ou_schema",
                "hipotese_nao_se_repete_em_janelas_comparaveis",
            ],
            minimum_evidence={"minimum_distinct_observations": 2, "minimum_confidence_for_validated": 0.80},
            safety_limits=[
                "read_only", "marketplace_writes_zero", "no_auth_bypass",
                "no_pii_generic_collection", "no_causal_claim_without_evidence", "max_iterations_3",
            ],
            stop_condition=[
                "objective_criteria_met", "evidence_saturation", "legitimate_evidence_exhausted",
                "explicitly_inconclusive", "max_safe_iterations",
            ],
            priority=request.priority,
            possible_deepenings=deepenings,
            mode=mode,
        )
