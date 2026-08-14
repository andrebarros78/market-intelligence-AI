# Runtime de Agentes Operacionais V1

**Data:** 14/08/2026  
**Estado:** INSTALADO EM BRANCH / AGUARDANDO CI  
**Runtime:** `src/market_intelligence/agents/runtime.py`

## Separação de equipes

O projeto possui duas equipes diferentes:

1. **Agentes de engenharia** — perfis Codex/GitHub usados para construir, revisar e testar o software.
2. **Agentes operacionais de Market Intelligence** — trabalhadores do produto que analisam evidências, mercado e operação.

Nenhum agente operacional escolhe provedor de IA. Todos usam o plano `agents` do AI Router/Temporal.

## Agentes operacionais instalados

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

## Autoridade

Todos os perfis são `read_only`.

Eles podem:

- analisar dados minimizados;
- solicitar capacidades lógicas de IA;
- produzir inferências/hipóteses separadas de fatos;
- solicitar ferramentas governadas quando a fase permitir;
- recomendar ações.

Eles não podem:

- escrever em marketplace;
- escolher ou trocar provedor diretamente;
- usar a IA do sistema;
- aumentar orçamento;
- acessar segredos;
- executar código de skill em quarentena;
- transformar estimativa em fato.

## IA dos agentes

```text
AgentProfile
   -> build_agent_inference_job
   -> AI Data Gateway
   -> role=agents
   -> task_queue=market-intelligence-ai-agents-v1
   -> AI Router/Provider Manager
```

O campo `ai_role` do perfil aceita exclusivamente `agents`. Uma tentativa de criar perfil com `system` falha na validação.

## IA do sistema

A IA soberana continua no plano separado:

```text
role=system
-> task_queue=market-intelligence-ai-system-v1
```

Sistema e agentes podem usar provedores físicos diferentes. A separação é por contrato e fila; o código dos agentes não contém `provider`, `model` ou endpoint comercial.

## Skills

Skills são resolvidas por `SkillRegistry` e continuam subordinadas ao agente e às políticas do sistema. Apenas skills internas/open-source com estado `APPROVED_ACTIVE` podem executar.

Skills proprietárias ou em quarentena permanecem `REFERENCE_ONLY`. Isso inclui a coleção Nexscope enquanto sua licença/uso executável não estiver aprovado.

## Gate

A instalação só é considerada integrada após:

- teste de quantidade/perfis;
- teste de `read_only`;
- teste de impossibilidade de `ai_role=system` em agente;
- teste de filas distintas;
- teste de minimização do payload;
- regressão completa do projeto verde.
