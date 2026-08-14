# IA-07 — Execução Minimizada no Temporal

Data: 2026-08-14

## Objetivo

Colocar o runtime IA-06 dentro da fila durável IA-03 sem permitir que dados brutos ou prompt livre entrem no histórico do Temporal.

## Fluxo obrigatório

```text
objeto analítico interno
-> AIDataGateway.minimize (fora do Temporal)
-> validação IA-05
-> start_workflow com envelope minimizado
-> AIMinimizedInferenceWorkflow
-> Activity mi.ai.minimized_infer
-> revalidação do Gateway
-> AIVault / ProviderManager
-> execute_minimized_inference
-> auditoria PostgreSQL
-> resposta estruturada validada
```

## Barreiras contra bypass

1. O despachante `start_minimized_ai_job` recebe o objeto interno e executa o Gateway antes do `Client.start_workflow`.
2. O prompt determinístico é validado antes do despacho, mas **não é armazenado no payload do Workflow**.
3. O Workflow aceita somente `mode=minimized`, política `ai-data-gateway@1.0.0`, payload minimizado e atestações seguras.
4. A Activity reconstrói `AIDataGatewayResult` e executa novamente a allowlist e a varredura de conteúdo sensível sobre o payload presente no histórico.
5. Se o conteúdo revalidado não produzir exatamente o mesmo payload/hash de saída, a chamada falha antes da rede.

Assim, um chamador que tente contornar o despachante e acionar o Temporal diretamente não consegue transformar o Workflow em rota de prompt livre ou de dados brutos.

## Persistência e idempotência

- Workflow ID continua determinístico e `REJECT_DUPLICATE`;
- `request_key` continua SHA-256 sem o request id original no histórico;
- antes da inferência, a Activity consulta `ai_inference_audits`;
- se já existir auditoria concluída, retorna a resposta validada persistida e não chama o provedor novamente;
- após resposta externa válida, a Activity persiste a auditoria antes de concluir.

### Janela crítica

Se o provedor responder com sucesso e a gravação PostgreSQL falhar imediatamente depois, a Activity falha de forma **não retryable**. Essa decisão é deliberada: é preferível interromper e exigir reconciliação a executar uma segunda inferência possivelmente cobrável sem saber se a primeira já foi processada.

## Rate limit e retry

Falhas conhecidas de conectividade e `rate_limited` continuam retryable no Temporal. Erros de configuração, autenticação, Gateway, schema ou persistência após uma resposta de provedor são não retryable.

As Task Queues continuam com limite inicial de 1 atividade concorrente e 1 atividade/s, além do gate local Z.AI.

## Worker

`scripts/run_ai_worker.py` passa a exigir:

- Temporal configurado;
- `MI_DATABASE_URL` para auditoria PostgreSQL.

O worker registra simultaneamente os workflows `sandbox` e `minimized` nas filas separadas de `system` e `agents`.

## Gate IA-07

A fase somente é aprovada se o CI provar:

1. dados sensíveis são removidos antes de `start_workflow`;
2. o request id original não entra no histórico;
3. tentativa direta de forjar envelope é recusada antes da inferência;
4. auditoria existente evita nova chamada;
5. worker mantém limites server-side/local;
6. workflows sandbox e minimized coexistem;
7. nenhuma chamada externa real ocorre no CI.
