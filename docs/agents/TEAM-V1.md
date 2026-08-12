# Equipe de Agentes V1 — Market Intelligence IA

A equipe foi desenhada para permitir especialização e verificação independente.

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

## Fluxo de uma tarefa
Pipo define critério → especialista implementa → Security/Architecture revisam quando aplicável → QA verifica → Pipo integra apenas com evidência.

## Estado operacional
Os perfis existem para GitHub Copilot custom agents. Criar os perfis não inicia sessões nem gera consumo de agente. A execução por Copilot cloud agent depende de o recurso estar habilitado na conta/repositório e de autorização para eventual consumo/custo.
