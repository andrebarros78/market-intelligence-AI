# BASE-02 — Persistência Operacional

**Estado alvo da fase:** PostgreSQL e Alembic como fundação persistente, sem qualquer escrita em marketplace.

## Objetivo

Substituir persistência temporária de sandbox por contratos e implementação operacional reproduzível. PostgreSQL guarda estado, histórico, evidência e idempotência. Ele não é usado como substituto de Temporal.

## Esquema inicial

- `raw_events`: evento bruto, payload, SHA-256, ID externo opcional e chave de deduplicação.
- `entities`: estado corrente normalizado por marketplace/tipo/id.
- `snapshots`: somente mudanças de estado, preservadas por hash.
- `alerts`: alerta operacional e inteligência priorizada.
- `evidence`: fatos, inferências e hipóteses associados ao alerta.
- `oauth_states`: estado OAuth sintético/operacional com apenas `state_hash`; nunca guarda state, token ou client secret em texto aberto.

## Garantias

1. evento bruto é persistido antes da interpretação;
2. retries do mesmo evento são idempotentes no banco;
3. quando houver ID externo de notificação, ele tem precedência na chave de deduplicação;
4. entidade usa chave natural `(marketplace, entity_type, entity_id)`;
5. snapshot idêntico não é duplicado;
6. alerta + evidências são gravados dentro da mesma transação;
7. estado OAuth é consumido no máximo uma vez e somente antes do vencimento;
8. migrations são versionadas pelo Alembic;
9. nenhum segredo real faz parte de migrations, testes ou configuração versionada;
10. política de marketplace continua fail-closed e read-only.

## Dependências adotadas nesta fase

- SQLAlchemy 2.0.52;
- Alembic 1.19.1;
- Psycopg 3.3.4;
- PostgreSQL 18.3 no CI de integração.

## Critério de aprovação

A BASE-02 só é aprovada se:

- `compileall` passar;
- migration `upgrade head` passar em PostgreSQL real de CI;
- teste de deduplicação provar `insert` único;
- upsert de entidade for comprovado;
- snapshots aceitarem mudança e rejeitarem duplicata;
- OAuth state aceitar apenas um consumo;
- alerta e evidência forem persistidos;
- testes anteriores da BASE-01 continuarem verdes;
- nenhuma escrita externa ou OAuth real ocorrer.

## Próximo gate

BASE-03: Temporal para workflows duráveis de ingestão, fetch de recurso, retry, atualização de snapshot e investigação.
