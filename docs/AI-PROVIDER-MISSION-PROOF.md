# GPT do sistema + Gemini dos agentes — prova de conexão

## Escopo

Esta etapa prova a conectividade autenticada de duas credenciais independentes do API ML:

- `system`: OpenAI/GPT, responsável pela inteligência do sistema;
- `agents`: Google/Gemini, exclusivo dos agentes/workers.

Não executa inferência, não envia dados de negócio e não altera o Mercado Livre.

## Gate técnico

O workflow `.github/workflows/ai-provider-connectivity.yml` usa o Environment GitHub `INTELIGENCI DE MERCADO API` e executa dois jobs independentes:

- `system-gpt`: chama somente `GET https://api.openai.com/v1/models`;
- `agents-gemini`: chama somente `GET https://generativelanguage.googleapis.com/v1beta/models`.

A execução é aprovada somente quando os dois papéis retornarem:

- `authenticated=true`;
- `model_available=true`;
- `inference_executed=false`;
- `business_data_sent=false`.

## Segurança

- as chaves entram somente pelo contexto `secrets` do Environment;
- os nomes esperados são `MI_AI_SYSTEM_API_KEY` e `MI_AI_AGENTS_API_KEY`;
- a chave dos agentes nunca herda a chave do sistema;
- o probe não imprime nenhuma credencial;
- redirects ficam desabilitados;
- OpenAI aceita somente HTTPS + `api.openai.com` + `/v1`;
- Gemini aceita somente HTTPS + `generativelanguage.googleapis.com` + `/v1beta`;
- não há chamada de geração de conteúdo nesta etapa.

## Critério MISSION_PROVEN

`MISSION_PROVEN` exige, cumulativamente:

1. CI sintético completo verde no head final;
2. merge pelo head verde exato;
3. CI pós-merge verde;
4. workflow autenticado no `main` com `system-gpt` verde;
5. workflow autenticado no `main` com `agents-gemini` verde;
6. ausência de chave em logs/artefatos;
7. documentação final registrando os SHAs e runs aprovados.
