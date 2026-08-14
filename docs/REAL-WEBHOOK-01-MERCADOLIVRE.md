# REAL-WEBHOOK-01 — Notificações reais do Mercado Livre

## Objetivo

Receber notificações reais do Mercado Livre em uma rota separada do OAuth, preservar o evento bruto de forma idempotente e responder rapidamente sem liberar qualquer escrita no marketplace.

Rota pública planejada:

`https://vendas.tail7ad8aa.ts.net/v1/webhooks/mercadolivre`

Destino local:

`http://127.0.0.1:8772/v1/webhooks/mercadolivre`

A exposição HTTPS é uma etapa operacional separada. O processo local permanece bindado somente em loopback.

## Contrato implementado

`POST /v1/webhooks/mercadolivre`

O receptor:

- aceita somente `application/json`;
- limita o corpo a 1 MiB;
- exige `application_id` igual a `MI_ML_APP_ID`;
- valida `user_id`, `topic` e `resource`;
- rejeita `resource` absoluto, host externo, traversal, backslash, query e fragmento;
- aceita recursos relativos usados por alguns tópicos do Mercado Livre;
- preserva o payload bruto em `raw_events` via `PostgresRawEventRepository`;
- usa `_id` ou `id` quando disponível para reforçar idempotência;
- devolve `200` também para duplicatas já persistidas;
- devolve `503` se a persistência falhar, evitando falso ACK;
- não consulta a API do Mercado Livre dentro do request;
- não executa POST/PUT/PATCH/DELETE no marketplace;
- não registra o corpo da notificação em logs de acesso.

## Segurança e processamento posterior

A notificação é tratada apenas como aviso. Ela não é fonte de verdade para alterar estado de negócio.

Depois do ACK, o processamento assíncrono poderá consultar o `resource` pela API oficial usando `GET`, sujeito ao mesmo gate read-only do projeto. A validação de `resource` existe para impedir que um valor recebido seja transformado em acesso a host arbitrário.

Não foi inventado um header de assinatura para o webhook. Qualquer validação criptográfica futura só será implementada quando o contrato oficial aplicável ao endpoint padrão estiver identificado de forma inequívoca.

## Runtime local

Variáveis mínimas:

- `MI_READ_ONLY=true`
- `MI_ALLOW_MARKETPLACE_WRITES=false`
- `MI_DATABASE_URL=<PostgreSQL protegido>`
- `MI_ML_APP_ID=2767330231710080`
- `MI_ML_WEBHOOK_LOCAL_PORT=8772` (opcional)

Execução:

`python scripts/run_mercadolivre_webhooks.py`

O Uvicorn inicia em `127.0.0.1:8772`, com access log desligado.

## Provas obrigatórias antes de declarar operacional

1. CI completo verde.
2. POST sintético local retorna `HTTP 200` e cria exatamente um `raw_event`.
3. Replay do mesmo evento retorna `HTTP 200` sem duplicar persistência.
4. Entrada HTTPS pública responde pela rota exata e não expõe outras portas locais.
5. Uma notificação realmente emitida pelo Mercado Livre aparece em `raw_events` com `application_id`, `topic`, `resource`, `user_id`, `attempts` e timestamps observados.
6. Depois do OAuth real, o `resource` recebido é confirmado por `GET` oficial antes de qualquer uso como verdade de negócio.

Enquanto os itens 4 e 5 não forem comprovados, `REAL-WEBHOOK-01` permanece preparado, mas não deve ser declarado operacional em produção.
