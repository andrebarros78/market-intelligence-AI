from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from market_intelligence.ai.data_gateway import AI_DATA_GATEWAY, AIDataGateway
from market_intelligence.ai.temporal_queue import build_minimized_ai_job


AGENT_AI_ROLE: Literal["agents"] = "agents"


class AgentProfile(BaseModel):
    """Provider-neutral operational worker. Agents never select a commercial model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str = Field(min_length=1)
    function: str = Field(min_length=1)
    description: str = Field(min_length=1)
    ai_role: Literal["agents"] = "agents"
    requested_capabilities: tuple[str, ...] = ()
    authority: Literal["read_only"] = "read_only"
    active: bool = True


class AgentRuntimeRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, AgentProfile] = {}

    def install(self, profile: AgentProfile) -> None:
        if profile.agent_id in self._profiles:
            raise ValueError("agent_already_installed")
        if profile.ai_role != AGENT_AI_ROLE:
            raise ValueError("agent_must_use_agents_ai_role")
        self._profiles[profile.agent_id] = profile

    def require_active(self, agent_id: str) -> AgentProfile:
        try:
            profile = self._profiles[agent_id]
        except KeyError as exc:
            raise KeyError("agent_not_installed") from exc
        if not profile.active:
            raise RuntimeError("agent_not_active")
        return profile

    def installed(self) -> tuple[AgentProfile, ...]:
        return tuple(sorted(self._profiles.values(), key=lambda item: item.agent_id))


INSTALLED_OPERATIONAL_AGENTS: tuple[AgentProfile, ...] = (
    AgentProfile(
        agent_id="intelligence-supervisor",
        function="supervision",
        description="Prioriza investigacoes e coordena especialistas sem alterar fatos.",
        requested_capabilities=("DEEP_REASONING", "STRUCTURED_OUTPUT", "TOOL_USE"),
    ),
    AgentProfile(
        agent_id="market-analyst",
        function="market_analysis",
        description="Analisa mercado, categorias, demanda e movimentos competitivos.",
        requested_capabilities=("STANDARD_REASONING", "DATA_ANALYSIS", "STRUCTURED_OUTPUT"),
    ),
    AgentProfile(
        agent_id="competitor-intelligence",
        function="competition",
        description="Investiga concorrentes, ofertas, posicionamento e mudancas observadas.",
        requested_capabilities=("STANDARD_REASONING", "LONG_CONTEXT", "TOOL_USE"),
    ),
    AgentProfile(
        agent_id="data-bi-analyst",
        function="data_bi",
        description="Explora metricas e evidencia estruturada para apoiar os demais agentes.",
        requested_capabilities=("DATA_ANALYSIS", "STRUCTURED_OUTPUT"),
    ),
    AgentProfile(
        agent_id="product-category-analyst",
        function="product_category",
        description="Analisa produto, catalogo, categoria, atributos e posicionamento.",
        requested_capabilities=("STANDARD_REASONING", "DATA_ANALYSIS"),
    ),
    AgentProfile(
        agent_id="pricing-revenue-analyst",
        function="pricing",
        description="Interpreta preco, elasticidade e cenarios calculados pelo motor deterministico.",
        requested_capabilities=("DATA_ANALYSIS", "STRUCTURED_OUTPUT"),
    ),
    AgentProfile(
        agent_id="economics-analyst",
        function="economics",
        description="Interpreta sinais economicos e efeitos externos relevantes ao marketplace.",
        requested_capabilities=("DEEP_REASONING", "DATA_ANALYSIS", "LONG_CONTEXT"),
    ),
    AgentProfile(
        agent_id="statistics-analyst",
        function="statistics",
        description="Valida leitura estatistica sem substituir motores matematicos deterministas.",
        requested_capabilities=("DATA_ANALYSIS", "HIGH_ASSURANCE"),
    ),
    AgentProfile(
        agent_id="demand-forecast-analyst",
        function="forecasting",
        description="Interpreta previsoes, incerteza e mudancas de demanda.",
        requested_capabilities=("DATA_ANALYSIS", "STANDARD_REASONING"),
    ),
    AgentProfile(
        agent_id="inventory-replenishment-analyst",
        function="inventory",
        description="Analisa estoque, ruptura, cobertura e reposicao recomendada.",
        requested_capabilities=("DATA_ANALYSIS", "STRUCTURED_OUTPUT"),
    ),
    AgentProfile(
        agent_id="marketing-ads-analyst",
        function="marketing_ads",
        description="Analisa publicidade, campanhas, funil, eficiencia e oportunidades.",
        requested_capabilities=("DATA_ANALYSIS", "STANDARD_REASONING"),
    ),
    AgentProfile(
        agent_id="customer-voice-analyst",
        function="customer_voice",
        description="Sintetiza reviews, reclamacoes e sinais de voz do cliente.",
        requested_capabilities=("LONG_CONTEXT", "STANDARD_REASONING", "STRUCTURED_OUTPUT"),
    ),
    AgentProfile(
        agent_id="finance-reconciliation-analyst",
        function="finance",
        description="Interpreta margem, taxas, recebimentos e conciliacao calculados pelo sistema.",
        requested_capabilities=("DATA_ANALYSIS", "HIGH_ASSURANCE", "STRUCTURED_OUTPUT"),
    ),
    AgentProfile(
        agent_id="logistics-fulfillment-analyst",
        function="logistics",
        description="Analisa frete, fulfillment, atrasos, devolucoes e desempenho logistico.",
        requested_capabilities=("DATA_ANALYSIS", "STANDARD_REASONING"),
    ),
    AgentProfile(
        agent_id="risk-anomaly-investigator",
        function="risk_anomaly",
        description="Investiga anomalias levantadas pelo Radar preservando fato, inferencia e hipotese.",
        requested_capabilities=("DEEP_REASONING", "HIGH_ASSURANCE", "STRUCTURED_OUTPUT"),
    ),
    AgentProfile(
        agent_id="evidence-auditor",
        function="evidence_audit",
        description="Verifica proveniencia, confianca, contradicoes e suficiência de evidencias.",
        requested_capabilities=("HIGH_ASSURANCE", "LONG_CONTEXT", "STRUCTURED_OUTPUT"),
    ),
    AgentProfile(
        agent_id="compliance-governance-analyst",
        function="compliance",
        description="Verifica politicas, limites, licencas e regras de uso sem conceder autoridade.",
        requested_capabilities=("HIGH_ASSURANCE", "STANDARD_REASONING"),
    ),
    AgentProfile(
        agent_id="data-collection-specialist",
        function="data_collection",
        description="Planeja coleta e cobertura de dados via adapters governados e read-only.",
        requested_capabilities=("TOOL_USE", "STRUCTURED_OUTPUT"),
    ),
    AgentProfile(
        agent_id="research-intelligence-specialist",
        function="research",
        description="Pesquisa sinais externos e organiza fontes para o nucleo de inteligencia.",
        requested_capabilities=("LONG_CONTEXT", "TOOL_USE", "STANDARD_REASONING"),
    ),
    AgentProfile(
        agent_id="executive-reporting-analyst",
        function="reporting",
        description="Transforma evidencia aprovada em sintese executiva rastreavel.",
        requested_capabilities=("STRUCTURED_OUTPUT", "STANDARD_REASONING"),
    ),
)


AGENT_RUNTIME = AgentRuntimeRegistry()
for _profile in INSTALLED_OPERATIONAL_AGENTS:
    AGENT_RUNTIME.install(_profile)


def build_agent_inference_job(
    *,
    agent_id: str,
    request_id: str,
    purpose: str,
    data: Mapping[str, Any],
    gateway: AIDataGateway = AI_DATA_GATEWAY,
) -> dict[str, Any]:
    """Dispatch an operational agent only through the dedicated agents AI plane."""

    profile = AGENT_RUNTIME.require_active(agent_id)
    job = build_minimized_ai_job(
        request_id=f"{profile.agent_id}:{request_id}",
        role=AGENT_AI_ROLE,
        purpose=purpose,
        data=data,
        gateway=gateway,
    )
    return {
        "agent_id": profile.agent_id,
        "function": profile.function,
        "authority": profile.authority,
        "requested_capabilities": profile.requested_capabilities,
        "ai_job": job,
    }
