# IA-08 — Ponte Radar → IA Minimizada

Data: 2026-08-14

## Objetivo

Conectar o resultado analítico do Radar ao pipeline IA-07 sem criar prompt livre, sem enviar o identificador real da entidade e sem transportar `context` ou payload bruto do Mercado Livre.

## Fluxo

```text
RadarObservation
+ RadarFinding
-> radar_finding_to_ai_data
-> alias SHA-256 da entidade
-> seleção determinística de métricas e evidência
-> AIDataGateway IA-04
-> contrato IA-05
-> Temporal IA-07
-> runtime/auditoria IA-06
```

## Dados deliberadamente excluídos

A ponte não exporta:

- `entity_id` real;
- `RadarObservation.context`;
- payload bruto de marketplace;
- e-mail, telefone, comprador ou vendedor;
- credenciais/tokens;
- `summary` textual dos detectores;
- prompt fornecido pelo chamador.

## Dados permitidos

A ponte deriva somente:

- `entity_type=marketplace_entity`;
- `entity_alias` por SHA-256 irreversível para finalidade operacional;
- período observado;
- `anomaly_detected` / `no_anomaly`;
- classe epistemológica;
- severidade e confiança;
- nomes internos seguros dos detectores;
- hipóteses internas identificadas pelo detector;
- uma métrica primária, valor observado, baseline histórico, desvio e tamanho da amostra quando disponíveis.

Todo esse objeto ainda passa obrigatoriamente pela allowlist da IA-04 antes de entrar no histórico do Temporal.

## Disciplina epistemológica

A classificação é conservadora:

1. qualquer detector `HYPOTHESIS` torna o envelope `HIPOTESE`;
2. sem hipótese, qualquer `INFERENCE` torna o envelope `INFERENCIA`;
3. somente resultados exclusivamente factuais permanecem `FATO`.

A IA-05 impede que a resposta altere essa classificação e exige `causal_claim=false`.

## Despacho

`start_radar_ai_explanation(...)` chama exclusivamente `start_minimized_ai_job(...)` da IA-07.

Não existe argumento `prompt` na interface da ponte.

## Gate IA-08

A fase somente é aprovada se o CI provar:

1. `entity_id` real não atravessa a ponte;
2. `context`, dados pessoais e credenciais não atravessam;
3. summaries livres dos detectores não atravessam;
4. hipótese nunca é elevada para inferência/fato;
5. saída da ponte é aceita pelo Gateway IA-04;
6. despacho usa somente o caminho IA-07 minimizado;
7. nenhuma chamada externa real ocorre no CI.
