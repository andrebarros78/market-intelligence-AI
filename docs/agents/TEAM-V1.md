# Equipe de Agentes V1 — Market Intelligence IA

A equipe foi desenhada em duas camadas: engenharia do software e operação de Market Intelligence. As duas camadas permanecem separadas.

## Equipe de engenharia

| Agente | Responsabilidade principal |
|---|---|
| Pipo Chief Engineer | Orquestração, prioridade, integração e decisão técnica |
| Architecture Guardian | Contratos, fronteiras e arquitetura multi-marketplace |
| Marketplace Integration Specialist | Adapters, notificações, Sensor do Canal e normalização |
| Temporal Workflows Specialist | Workflows duráveis, retries, replay e recuperação |
| Data Persistence Specialist | PostgreSQL, Alembic, integridade e histórico |
| Radar ML Specialist | Detecção de anomalias e inteligência quantitativa |
| Security OAuth Guardian | OAuth/PKCE, segredos, autorização e fail-closed |
| QA Independent Verifier | Verificação independente e testes adversariais |
| Platform Observability Specialist | CI, health, métricas, Higress e operação |
| API Panel Integration Specialist | FastAPI, contratos e integração com painel |
| Market Intelligence Domain Specialist | Valor comercial, alertas, evidência e semântica |

Fluxo: Pipo define critério → especialista implementa → Security/Architecture revisam quando aplicável → QA verifica → Pipo integra apenas com evidência.

## Equipe operacional do produto

Os perfis abaixo estão instalados em `src/market_intelligence/agents/runtime.py`:

1. Intelligence Supervisor
2. Market Analyst
3. Competitor Intelligence
4. Data/BI Analyst
5. Product & Category Analyst
6. Pricing & Revenue Analyst
7. Economics Analyst
8. Statistics Analyst
9. Demand Forecast Analyst
10. Inventory & Replenishment Analyst
11. Marketing & Ads Analyst
12. Customer Voice Analyst
13. Finance & Reconciliation Analyst
14. Logistics & Fulfillment Analyst
15. Risk & Anomaly Investigator
16. Evidence Auditor
17. Compliance & Governance Analyst
18. Data Collection Specialist
19. Research Intelligence Specialist
20. Executive Reporting Analyst

Todos são `read_only`, provider-neutral e usam exclusivamente o plano de IA `agents`.

## Duas IAs

- **IA do sistema**: `role=system`, fila `market-intelligence-ai-system-v1`.
- **IA dos agentes**: `role=agents`, fila `market-intelligence-ai-agents-v1`.

O Provider Manager/Router escolhe o modelo físico. Agentes não carregam provider/modelo em seus perfis e não podem usar a IA do sistema.

## Almoxarifado externo

Os 19 recursos externos recrutados em `agents/warehouse/recruits.json` continuam inativos até promoção individual por origem/licença/ref/hash/inspeção/sandbox/testes/QA. Armazenar ou recrutar não concede autoridade de execução.

## Estado operacional

Os 11 perfis de engenharia existem para Codex/GitHub. Os 20 perfis operacionais existem no runtime Python do produto. Criar ou registrar perfil não inicia consumo de API. Qualquer execução real continua subordinada aos workers, ao AI Data Gateway, ao AI Router, às políticas de custo e às permissões do sistema.
