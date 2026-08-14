# IA-03 — Fila persistente Temporal para IA

Data: 2026-08-14

## Objetivo

Colocar toda execução de IA atrás de uma fila durável e controlada antes de liberar dados reais de negócio.

## Arquitetura

- `system` usa `market-intelligence-ai-system-v1`;
- `agents` usa `market-intelligence-ai-agents-v1`;
- cada fila inicia com 1 atividade concorrente;
- cada worker inicia limitado a 1 atividade por segundo;
- a Task Queue também inicia limitada no servidor a 1 atividade por segundo;
- eager activity execution fica desabilitada, impedindo bypass do limite da fila;
- o adapter Z.AI continua com seu gate local, `Retry-After`, cooldown e backoff como segunda defesa.

## Persistência e recuperação

O Workflow Temporal registra somente metadados sanitizados. A chamada externa ocorre em Activity, nunca dentro do Workflow. Se o processo cair, o Temporal pode reagendar a Activity de acordo com a política de retry.

A IA-03 usa:

- timeout por tentativa: 60 segundos;
- janela total da Activity: 20 minutos;
- retry persistente: no máximo 3 tentativas;
- intervalo inicial: 30 segundos;
- backoff 2x;
- intervalo máximo: 5 minutos.

Erros de autenticação/configuração são marcados como não-retryable. Rate limit e falha transitória de conectividade são retryable.

## Idempotência

O chamador fornece `request_id`, mas ele não é colocado no histórico Temporal. O sistema gera SHA-256 de `role:request_id` e usa essa chave no payload e no Workflow ID.

O despacho usa `WorkflowIDReusePolicy.REJECT_DUPLICATE`. Assim, o mesmo `request_id` para o mesmo papel não pode executar duas vezes, inclusive depois de uma execução concluída.

## Proteção de dados

Nesta fase o único modo aceito é `sandbox`.

Não existe campo de prompt no payload. O Workflow e a Activity rejeitam qualquer modo diferente com `ai_data_gateway_required`. Portanto, nenhum dado real do Mercado Livre deve alcançar a IA antes da IA-04.

O histórico não recebe:

- prompt;
- texto retornado pelo provedor;
- API key/token;
- header Authorization;
- request id original;
- dados de negócio.

## Escala futura

O cofre continua com 5 perfis. A fila é separada por papel (`system`/`agents`), não por fabricante, para permitir trocar provedores por configuração sem reconstruir a orquestração.

Os limites conservadores deverão ser calibrados somente depois de evidência real de capacidade, custo e rate limit dos provedores.

## Gate IA-03

A fase somente é aprovada se:

1. CI integral ficar verde;
2. filas system/agents forem diferentes;
3. Worker aplicar limite local e server-side;
4. eager activity execution estiver desabilitada;
5. Workflow for durável e a chamada externa estiver isolada em Activity;
6. retry distinguir falha transitória de configuração permanente;
7. idempotência usar Workflow ID determinístico com rejeição de duplicidade;
8. nenhum prompt/dado real puder entrar antes da IA-04.
