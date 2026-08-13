# CHECKPOINT — R1.12 — 2026-08-13

## Estado

R1.12 — Seleção Automática de Controles: concluída e integrada ao `main`.

## Entregue

- `AutomaticControlSelector` versionado como `auto-control-selector@1.0.0`;
- novo contrato `context.control_candidates` sem similaridade pré-calculada;
- preservação integral do contrato legado `context.controls`;
- similaridade baseada apenas no histórico anterior ao ponto atual;
- nenhuma utilização do valor atual do alvo/candidato para escolher controles;
- filtros auditáveis para auto-referência, inelegibilidade declarada, contaminação declarada, métrica ausente, histórico insuficiente, baixa similaridade e limite excedido;
- ordenação determinística e limite padrão de oito controles;
- modos `legacy`, `automatic` e `hybrid`;
- detector relacional elevado para `relational-control@2.0.0` mantendo o nome de integração `relational_control_v1`;
- evidência de seleção incorporada a `control_comparison`;
- API compartilhada validada com seleção automática;
- caminho Temporal preservado pelo mesmo detector compartilhado e regressão existente;
- persistência PostgreSQL e deduplicação de alerta com seleção automática comprovadas;
- documento de desenho `docs/radar/R1.12-AUTO-CONTROL-SELECTION-DESIGN.md`.

## Evidências

- PR #31 integrado por squash.
- Commit funcional no `main`: `ac39c5057f72e1534d4db3a76767b600ca2de8c4`.
- CI final da branch: run #88 — sucesso.
- CI pós-merge do `main`: run #89 (`31713225734`) — sucesso.
- Gates aprovados: instalação, compilação, PostgreSQL 18.3, migrations, drift, rollback/re-upgrade e suíte completa de testes.

## Falhas encontradas e corrigidas

O primeiro CI da R1.12 falhou somente porque dois testes do R1.9 ainda esperavam `relational-control@1.0.0`. As expectativas foram atualizadas para `2.0.0`; nenhum comportamento legado foi removido.

## Segurança e limites

- sem rede externa;
- sem chamada real ao Mercado Livre;
- sem escrita em marketplace;
- sem IA paga;
- sem nova migration;
- `contaminated=true` é um atributo declarado, não uma inferência causal;
- similaridade V1 usa alinhamento numérico pela janela histórica comum; alinhamento timestampado entre entidades ainda é evolução futura;
- a seleção automática não prova causalidade;
- a versão literal do pacote permaneceu `0.14.0` porque a alteração de `pyproject.toml` foi bloqueada pelo conector; isso não altera o comportamento executado;
- `api/app.py` ainda possui metadados de capabilities antigos por bloqueios anteriores do conector.

## Próximo passo técnico recomendado

R1.13 — Atribuição automática de fatores observáveis: estruturar fatores mensuráveis, separar explicação observada de hipótese, estimar contribuição sem declarar causalidade indevida e preparar o caminho para contrafactual operacional.
