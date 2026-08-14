# IA-06 — Execução Minimizada e Proveniência Persistente

Data: 2026-08-14

## Objetivo

Conectar o contrato IA-05 aos adapters reais sem introduzir prompt livre e registrar evidência operacional suficiente para auditoria/reprodução.

## Caminho de execução

```text
AIDataGatewayResult
-> build_minimized_inference_prompt
-> adapter permitido pelo ProviderManager
-> OpenAI Responses ou Z.AI chat/completions
-> parse_minimized_ai_response
-> AIMinimizedInferenceResult
-> ai_inference_audits (PostgreSQL)
```

O runtime não possui argumento `prompt`. A única entrada de negócio é um `AIDataGatewayResult` já atestado.

## Provedores inicialmente executáveis

- OpenAI/GPT para `system`;
- Z.AI/GLM para `agents`.

Outros perfis continuam armazenáveis no cofre, mas falham fechados até existir adapter explicitamente aprovado.

## Segurança de entrada e saída

- `store=true` é rejeitado;
- endpoint e host continuam validados pelo adapter;
- credencial continua encapsulada no adapter e não entra no resultado;
- saída bruta é parseada imediatamente e não é persistida;
- o parser IA-05 exige JSON exato e `causal_claim=false`;
- mudança de `FATO`/`INFERENCIA`/`HIPOTESE` é rejeitada;
- e-mail/Bearer/prefixos de segredo na saída são rejeitados.

## Auditoria PostgreSQL

A tabela `ai_inference_audits` guarda somente:

- chave idempotente SHA-256 da solicitação;
- papel, provedor, modelo e host;
- finalidade;
- versão/hash do Gateway;
- versão/hash do contrato/prompt;
- hash da saída bruta validada;
- resposta JSON já validada;
- tokens;
- latência;
- data de criação.

Não guarda:

- API key/token;
- Authorization header;
- prompt bruto externo (não existe);
- objeto bruto do marketplace;
- resposta bruta do provedor.

A chave `request_key` é única, tornando o registro final idempotente.

## Gate

A IA-06 é aprovada somente se:

1. OpenAI e Z.AI passarem por MockTransport com payload minimizado;
2. material removido pelo Gateway não aparecer na requisição;
3. saída sensível for bloqueada;
4. migration 0007 subir, passar `alembic check` e reverter/reaplicar;
5. persistência PostgreSQL for idempotente;
6. nenhum teste exigir chamada externa real.
