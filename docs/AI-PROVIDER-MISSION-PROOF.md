# Gemini — prova de conexão do sistema e dos agentes

## Escopo

Esta etapa prova somente a conectividade autenticada das duas credenciais Gemini do API ML:

- `system`: IA responsável pelo sistema;
- `agents`: IA exclusiva dos agentes/workers.

Não executa inferência, não envia dados de negócio e não altera o Mercado Livre.

## Gate técnico

O workflow `.github/workflows/ai-provider-connectivity.yml` usa o Environment GitHub `INTELIGENCI DE MERCADO API` e executa uma matriz com os papéis `system` e `agents`.

Cada papel chama apenas `GET https://generativelanguage.googleapis.com/v1beta/models` através de `scripts/probe_ai_provider.py`.

A execução é aprovada somente quando os dois papéis retornarem:

- `authenticated=true`;
- `model_available=true`;
- `inference_executed=false`;
- `business_data_sent=false`.

## Segurança

- as chaves entram somente pelo contexto `secrets` do Environment;
- os nomes esperados são `MI_AI_SYSTEM_API_KEY` e `MI_AI_AGENTS_API_KEY`;
- a chave do papel `agents` nunca herda a chave do `system`;
- o probe não imprime nenhuma credencial;
- redirects ficam desabilitados;
- o driver Gemini aceita somente HTTPS, host `generativelanguage.googleapis.com` e base `/v1beta`;
- não há chamada de geração de conteúdo nesta etapa.

## Critério MISSION_PROVEN

`MISSION_PROVEN` exige, cumulativamente:

1. CI sintético completo verde;
2. merge pelo head verde exato;
3. CI pós-merge verde;
4. workflow autenticado no `main` com `system` verde;
5. workflow autenticado no `main` com `agents` verde;
6. ausência de chave em logs/artefatos;
7. documentação final registrando os SHAs e runs aprovados.
