# Checkpoint — BASE-03

**Projeto:** Market Intelligence IA  
**Fase:** BASE-03 — Temporal  
**Data:** 12/08/2026  
**Estado:** EM VALIDAÇÃO

## Objetivo

Implantar orquestração durável sem transformar PostgreSQL em fila. O workflow coordena; efeitos externos e persistência executam somente em Activities.

## Entrega planejada

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
- teste integrado Temporal + PostgreSQL;
- teste de retry sintético da leitura;
- nenhuma chamada real ao Mercado Livre.

## Segurança

- Temporal desabilitado por padrão no runtime (`MI_TEMPORAL_ENABLED=false`);
- nenhuma credencial real adicionada;
- nenhuma Activity de escrita em marketplace;
- política global read-only/fail-closed preservada.
