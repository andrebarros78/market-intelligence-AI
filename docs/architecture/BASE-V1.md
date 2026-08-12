# Base V1 — Market Intelligence IA

**Estado:** base limpa reconstruída.  
**Princípio:** preservar capacidades válidas do projeto antigo sem reproduzir sua arquitetura quebrada.

## Objetivo desta base

Criar um núcleo pequeno, seguro, executável e testável sobre o qual o projeto possa evoluir em Loop Engineering. Esta base não faz OAuth real, não chama o Mercado Livre e não escreve em marketplace.

## Fluxo alvo

```text
Marketplace
  -> Sensor do Canal / notificações / API
  -> evento bruto imutável + hash
  -> deduplicação
  -> normalização e snapshots
  -> PostgreSQL
  -> workflows duráveis (Temporal)
  -> analytics (DuckDB/Polars)
  -> Radar
  -> investigação: fato / inferência / hipótese
  -> impacto + recomendação
  -> API interna / Higress / painel
```

## Estrutura do código

- `core`: políticas, contratos e configuração.
- `marketplaces`: adapters por marketplace; Mercado Livre é o primeiro.
- `ingestion`: captura bruta, hashing, deduplicação e futuramente normalização.
- `persistence`: contratos de repositório; PostgreSQL será a implementação operacional.
- `workflows`: contrato de workflow; Temporal será a implementação de produção.
- `intelligence/radar`: detectores e agregação de evidências.
- `api`: superfície interna controlada para painel/IA.

## Regras arquiteturais congeladas

1. read-only por padrão;
2. segredo nunca entra em telemetria ou evidência;
3. evento bruto preservado antes da interpretação;
4. deduplicação antes do processamento;
5. workflows duráveis não serão reinventados em SQLite/PostgreSQL;
6. PostgreSQL guarda estado e histórico, não substitui Temporal;
7. o Radar separa fato, inferência e hipótese;
8. nenhuma anomalia implica causa conhecida automaticamente;
9. NocoBase continua fora deste repositório;
10. adapters futuros não contaminam o domínio central.

## O que já funciona nesta V1

- aplicação FastAPI;
- `/health` e `/ready`;
- política de escrita bloqueada por padrão;
- contrato canônico de alertas/evidências;
- evento bruto com SHA-256 determinístico;
- deduplicação em memória para sandbox;
- Sensor do Canal ML com allowlist e exclusão de Authorization/cookies;
- contratos de Mercado Livre, persistência e workflows;
- engine em processo apenas para sandbox;
- Radar com regra conhecida + baseline estatístico robusto simples;
- endpoint de avaliação do Radar;
- endpoint de capabilities que declara explicitamente o que ainda não existe.

## Próximas fases

1. PostgreSQL + Alembic: raw events, snapshots, entities, alerts, evidence, OAuth state.
2. Temporal: ingestão, fetch de recurso, retry, atualização de snapshot e investigação.
3. Mercado Livre sandbox: OAuth sintético, notificações sintéticas e client read-only.
4. Sensor do Canal persistente.
5. Radar PyOD/ensemble + benchmark TSB-AD/TSB-AutoAD.
6. temporal/multivariate/regime/counterfactual/unexplained residual.
7. Higress e API para IA/painel.
8. Digital Twin completo antes de qualquer conexão real.

## Critério para avançar

Uma fase só avança quando compila, passa testes, tem evidência e não reintroduz escrita externa ou segredo.
