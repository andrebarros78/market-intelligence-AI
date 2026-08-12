# Checkpoint — BASE-03

**Projeto:** Market Intelligence IA  
**Fase:** BASE-03 — Temporal  
**Data:** 12/08/2026  
**Estado:** TECNICAMENTE APROVADA — AGUARDANDO MERGE

## Objetivo

Implantar orquestração durável sem transformar PostgreSQL em fila. O workflow coordena; efeitos externos e persistência executam somente em Activities.

## Entrega

- Temporal Python SDK `1.31.0`;
- workflow durável de ingestão;
- Activity para persistência idempotente do evento bruto;
- Activity read-only para recuperação do recurso no marketplace;
- Activity de upsert + snapshot por mudança;
- Activity opcional para avaliação do Radar atual;
- retries controlados por tipo de Activity;
- workflow ID determinístico por chave de idempotência;
- política `REJECT_DUPLICATE`;
- worker com PostgreSQL e registro explícito de adapters;
- configuração de target/namespace/task queue/TLS, com Temporal desabilitado por padrão;
- teste integrado Temporal + PostgreSQL;
- retry sintético de leitura comprovado: duas falhas transitórias e sucesso na 3ª tentativa;
- histórico Temporal recuperado e não vazio;
- replay do histórico pelo `Replayer` aprovado, comprovando determinismo do workflow;
- nenhuma chamada real ao Mercado Livre.

## Evidência

- PR: `#2 — BASE-03 — Temporal Durable Workflows`;
- branch: `base-03-temporal`;
- commit funcional inicial: `5e9fe99386c5e5ebf0860ab35e8146fc52a3ef7d`;
- commit do gate de replay: `727a47f7bc3252604faff553b8ad5b53164de566`;
- workflow CI inicial: `31642057489` — `success`;
- workflow CI com replay: `31642265945` — `success`;
- PostgreSQL 18.3: saudável;
- Temporal SDK `1.31.0`: instalado e executado;
- compilação: aprovada;
- `alembic upgrade head`: aprovado;
- `alembic check`: aprovado, sem drift;
- rollback `downgrade base` + reaplicação: aprovado;
- suíte final: `19 passed`;
- retry read-only do adapter: 3 tentativas, conforme esperado;
- replay de workflow: aprovado.

## Segurança

- Temporal desabilitado por padrão no runtime (`MI_TEMPORAL_ENABLED=false`);
- nenhuma credencial real adicionada;
- nenhuma Activity de escrita em marketplace;
- política global read-only/fail-closed preservada;
- o teste de marketplace usa adapter sintético, sem rede Mercado Livre;
- nenhuma chamada real ou escrita no Mercado Livre foi executada.

## Gate pendente

O código está tecnicamente aprovado no PR #2. Como o repositório é público, o merge no `main` exige autorização explícita antes da publicação final desta fase.
