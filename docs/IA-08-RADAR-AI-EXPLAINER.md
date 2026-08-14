# IA-08 — Radar → IA explicativa

Data: 2026-08-14

## Objetivo

Permitir que o Radar peça uma explicação estruturada à IA sem transferir para o modelo autoridade sobre fatos, classe de evidência ou ações no Mercado Livre.

## Contrato

```text
Radar Alert soberano
-> pseudonimização da entidade
-> contrato analítico reduzido
-> AIDataGateway
-> Temporal minimized workflow
-> ProviderManager
-> parser IA-05
-> auditoria PostgreSQL
-> análise explicativa anexa
```

A IA não é detector, não altera o `Alert`, não cria FATO e não executa ações.

## Proteções

- `entity_id` real nunca entra no contrato de IA;
- atributos brutos das evidências nunca são encaminhados;
- somente os campos analíticos necessários são derivados do alerta;
- `FATO`, `INFERENCIA` e `HIPOTESE` são preservados;
- `control_comparison` é reduzido a representação canônica limitada;
- request id é hash determinístico e não contém o identificador real;
- despacho usa exclusivamente `start_minimized_ai_job`;
- não existe parâmetro de prompt livre;
- qualquer PII/segredo ainda presente é bloqueado pelo AIDataGateway;
- a saída segue o contrato IA-05 com `causal_claim=false`;
- nenhuma chamada externa real faz parte do gate deste PR.

## Gate

A IA-08 é aprovada quando o CI comprovar pseudonimização, preservação epistemológica, ausência de payload bruto e uso exclusivo do pipeline minimizado, com todos os gates anteriores verdes.
