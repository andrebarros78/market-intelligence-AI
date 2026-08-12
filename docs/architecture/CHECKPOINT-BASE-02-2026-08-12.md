# Checkpoint — BASE-02

**Projeto:** Market Intelligence IA  
**Fase:** BASE-02 — Persistência Operacional  
**Data:** 12/08/2026  
**Estado:** CONCLUÍDA E VALIDADA

## Entrega

- esquema PostgreSQL inicial;
- Alembic configurado e migration `0001_base02`;
- SQLAlchemy models;
- AsyncEngine/AsyncSession com Psycopg 3;
- repositório idempotente de eventos brutos;
- upsert de entidades;
- snapshots por mudança;
- gravação transacional de alerta + evidências;
- estado OAuth com hash, envelope binário e consumo atômico único;
- CI com PostgreSQL real;
- testes unitários e integração.

## Correção realizada durante o ciclo

O primeiro CI revelou que `rowcount` não era uma evidência confiável para distinguir inserção real de conflito no fluxo assíncrono com Psycopg. A implementação foi corrigida para usar `INSERT ... ON CONFLICT DO NOTHING RETURNING id`, preservando idempotência verificável pelo próprio PostgreSQL.

O gate também foi endurecido para incluir `alembic check`, downgrade completo + novo upgrade e consumo concorrente do estado OAuth, exigindo exatamente um vencedor.

## Evidência final

- PR: `#1 — BASE-02 — Persistência Operacional`;
- commit de merge no `main`: `823ec1f157e1c080a17722382605c3554c069984`;
- workflow pós-merge: `31638992647`;
- PostgreSQL 18.3: saudável;
- compilação: aprovada;
- `alembic upgrade head`: aprovado;
- `alembic check`: aprovado, sem drift;
- `alembic downgrade base` + `upgrade head`: aprovado;
- suíte: 15 testes aprovados;
- resultado final do job no `main`: `success`.

## Segurança

- nenhuma credencial real foi adicionada;
- password usada no CI é somente do PostgreSQL descartável do job;
- tabela OAuth não contém colunas `state`, `access_token`, `refresh_token` ou `client_secret`;
- marketplace permanece read-only/fail-closed;
- nenhuma chamada real ou escrita no Mercado Livre foi executada.

## Próximo passo

BASE-03 — Temporal, preservando PostgreSQL como fonte de estado/histórico e deixando retries/orquestração durável para o workflow engine.
