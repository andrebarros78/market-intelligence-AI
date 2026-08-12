# Checkpoint — BASE-02

**Projeto:** Market Intelligence IA  
**Fase:** BASE-02 — Persistência Operacional  
**Data:** 12/08/2026

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

## Segurança

- nenhuma credencial real foi adicionada;
- password usada no CI é somente do PostgreSQL descartável do job;
- tabela OAuth não contém colunas `state`, `access_token`, `refresh_token` ou `client_secret`;
- marketplace permanece read-only/fail-closed.

## Próximo passo

BASE-03 — Temporal, preservando PostgreSQL como fonte de estado/histórico e deixando retries/orquestração durável para o workflow engine.
