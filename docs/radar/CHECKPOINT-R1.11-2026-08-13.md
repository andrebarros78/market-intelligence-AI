# CHECKPOINT R1.11 — 2026-08-13

## Fase

R1.11 — Séries Temporais Timestampadas + Sazonalidade Real.

## Estado integrado

PR #30 integrado ao `main` no commit `f4911ad5fa6de081a36fe2bc34d938e4f10cf296`.

## Entregas

- `timestamped_history` com timestamps timezone-aware;
- compatibilidade preservada com `history` numérico legado;
- ordenação determinística e rejeição de timestamps duplicados;
- referências sazonais para hora do dia, dia da semana, dia do mês e mês do ano;
- detector `seasonality@1.0.0`;
- classificação `seasonal_expected` e `seasonal_deviation`;
- supressão restrita de falsos positivos univariados para sazonalidade esperada;
- integração com `unexplained-residual@1.0.0` usando baseline sazonal antes da mediana global;
- API `/v1/radar/evaluate`, fábrica compartilhada e `RadarActivities` do Temporal cobertos por testes;
- persistência PostgreSQL e deduplicação de alerta cobertas por teste;
- serializer JSON estrito no banco para impedir falhas por `NaN`/`Infinity` em evidências legadas;
- versão do pacote: `0.14.0`.

## Falha encontrada e corrigida

O primeiro CI da R1.11 revelou uma dívida anterior: `RobustZScoreDetector` podia produzir `Infinity` quando o histórico tinha dispersão zero. JSONB do PostgreSQL rejeita valores não finitos. A correção foi aplicada no limite de persistência, normalizando JSON antes do banco e preservando um marcador explícito do valor não finito.

## Limitações conhecidas

- não há decomposição STL/ETS automática nesta fase;
- feriados e promoções ainda não são calendários automáticos;
- alinhamento timestampado multivariado entre métricas diferentes será aprofundado depois;
- a seleção sazonal é associação temporal observada, não evidência causal;
- a metadata/capability literal em `api/app.py` não foi alterada nesta fase porque o conector bloqueou repetidamente a substituição desse arquivo; o endpoint funcional `/v1/radar/evaluate` usa a fábrica compartilhada e foi testado com `timestamped_history`.

## Segurança e custo

- sem OAuth real;
- sem chamada real ao Mercado Livre;
- sem escrita externa;
- sem IA paga;
- política read-only/fail-closed preservada.

## Gate final

Executar novamente o workflow `Validate Market Intelligence Base` no estado publicado do `main`: compilação, PostgreSQL, Alembic upgrade/check/downgrade/upgrade e suíte completa.