# CHECKPOINT — BASE V1 RECONSTRUÍDA

**Data:** 12/08/2026  
**Estado:** BASE V1 CONCLUÍDA E VALIDADA

## Encerramento da recuperação

A recuperação física do Git antigo foi encerrada após análise dos inventários, índices históricos e dangling blobs. Os 46 arquivos avançados perdidos não foram restauráveis pelo Git local e passam a ser tratados como capacidades a reconstruir na arquitetura nova.

## Base limpa criada

A Base V1 foi construída sem importar segredos ou código recuperado sensível. Ela contém:

- projeto Python empacotável;
- política fail-closed/read-only;
- contratos de evidência, alerta e entidade;
- eventos brutos com SHA-256 determinístico;
- deduplicação de sandbox;
- boundary para adapters de marketplace;
- contratos read-only do Mercado Livre;
- Sensor do Canal com allowlist e exclusão de Authorization/cookies;
- contratos de persistência;
- contrato de workflows e engine em processo somente para sandbox;
- Radar plugável;
- detector de regra conhecida;
- detector estatístico robusto inicial;
- API FastAPI com `/health`, `/ready`, `/v1/system/capabilities` e `/v1/radar/evaluate`;
- testes unitários;
- GitHub Actions para instalação, compilação e testes.

## Evidência

Validação isolada antes do envio:

- `python -m compileall -q src tests`: aprovado;
- `pytest -q`: 8 testes aprovados.

Validação GitHub Actions da Base V1:

- checkout: success;
- setup Python 3.12: success;
- instalação: success;
- compilação: success;
- testes: success.

Workflow run: `31636211477`.
Commit de fechamento da Base V1: `da3360d855e682962a99534134965b11299a3c35`.

## Limites deliberados

Ainda não estão implementados e não devem ser considerados prontos:

- PostgreSQL/Alembic operacional;
- Temporal de produção;
- OAuth Mercado Livre real;
- notificações reais;
- chamadas reais ao Mercado Livre;
- writes em marketplace;
- PyOD ensemble;
- anomalia temporal/multivariada;
- mudança de regime;
- contrafactual;
- resíduo não explicado;
- Higress integrado ao núcleo;
- Digital Twin integral.

## Próxima fase técnica

**FASE BASE-02 — Persistência Operacional**

Objetivo: implementar PostgreSQL + Alembic com contratos versionados para raw events, snapshots, entidades, evidências, alertas e estado OAuth sintético, com idempotência e testes de integração. Temporal entra na fase seguinte, usando o banco como estado persistente e não como fila improvisada.
