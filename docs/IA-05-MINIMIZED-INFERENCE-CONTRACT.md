# IA-05 — Contrato de Inferência Minimizada e Proveniência

Data: 2026-08-14

## Objetivo

Eliminar prompt livre e impedir que um adapter de IA receba dados fora do envelope aprovado pela IA-04.

## Fluxo obrigatório

```text
contrato analítico interno
-> AIDataGateway
-> AIDataGatewayResult atestado
-> build_minimized_inference_prompt
-> adapter do provedor
-> resposta JSON
-> parse_minimized_ai_response
-> aplicação
```

## Prompt

O prompt é determinístico e composto por instruções fixas + JSON minimizado. Não aceita texto arbitrário do chamador.

Ele registra somente:

- versão do contrato;
- finalidade;
- hash SHA-256 do envelope minimizado;
- dados que já passaram pelo Gateway.

Configuração obrigatória:

- `store=false`;
- temperatura 0;
- máximo de 384 tokens de saída;
- máximo de 12 KiB de prompt.

## Disciplina epistêmica

A IA não pode elevar ou trocar a classificação da fonte. Quando o Gateway envia `FATO`, `INFERENCIA` ou `HIPOTESE`, a resposta deve manter exatamente a mesma classificação.

`causal_claim` é estruturalmente obrigado a `false` neste contrato. Isso impede que a camada de linguagem transforme correlação, resíduo ou hipótese em uma afirmação causal automática.

## Resposta

Somente JSON com o contrato:

- `summary`;
- `evidence_class`;
- `recommendations` (máximo 5);
- `limitations` (máximo 5);
- `causal_claim=false`.

Campos extras, resposta não JSON, payload excessivo ou conteúdo sensível são rejeitados.

## Segurança

O parser faz uma segunda varredura contra e-mail, Bearer e formatos comuns de segredo na saída do modelo. Isso é defesa adicional; a garantia principal continua sendo o Gateway de entrada e a ausência de credenciais nos dados enviados.

## Estado de execução

A IA-05 não realiza chamada externa. O adapter real será conectado somente depois deste contrato passar no CI. Uma chamada paga de GPT não é necessária para provar esta etapa.
