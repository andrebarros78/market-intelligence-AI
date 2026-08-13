# CHECKPOINT — R1.13 — 2026-08-13

## Estado

R1.13 — Atribuição Automática de Fatores Observáveis: concluída e integrada ao `main`.

## Entregue

- `FactorAttributionEngine` versionado como `factor-attribution@1.0.0`;
- `ObservableFactorAttributionDetector` integrado ao Radar;
- fatores candidatos estruturados e auditáveis;
- relação estimada somente com histórico anterior;
- nenhuma utilização do valor atual do alvo para ajustar associação ou inclinação;
- associação histórica explicitamente separada de causalidade;
- fatores com movimento insuficiente, associação fraca, instabilidade ou direção incompatível são rejeitados;
- contribuição total limitada à mudança observada;
- integração automática com `UnexplainedResidualDetector`;
- compatibilidade com `residual_analysis` explícito preservada;
- API, Temporal, PostgreSQL e deduplicação cobertos.

## Evidências

- PR #32 integrado.
- Head funcional: `714dc2f17355f088db6eee59d21524601bc7b498`.
- Merge commit: `00dfdbb2f3c8c5f6634ce3d985ef05f895d31da1`.
- CI final da branch: run #99 — sucesso.
- CI pós-merge do `main`: run #100 — sucesso.

## Segurança e limites

- `EvidenceLevel.INFERENCE` para atribuição;
- `causal_claim=false`;
- associação não é apresentada como causa comprovada;
- nenhuma chamada real ao Mercado Livre;
- nenhuma escrita externa;
- nenhuma credencial real;
- nenhuma infraestrutura paga.

## Próximo passo técnico

R1.14 — Contrafactual Operacional: usar controles automaticamente selecionados para construir uma trajetória operacional esperada sem usar o valor atual do alvo no ajuste, medir o gap observado e manter contrafactual causal completo desabilitado.
