# Conexão das APIs de IA ao API ML via GitHub

## Objetivo

O API ML consome IA por contrato estável através do `ProviderManager`. GitHub guarda código, CI e segredos; não é barramento de runtime.

O projeto possui dois papéis de IA independentes:

1. `system`: inteligência responsável pelo próprio sistema API ML — OpenAI/GPT;
2. `agents`: capacidade de IA utilizada pelos agentes/workers autorizados — Google/Gemini.

As credenciais são independentes e nunca são compartilhadas entre os dois papéis.

## Configuração atual

### Sistema

- provider: `openai`;
- modelo padrão: `gpt-5-mini`;
- base URL: `https://api.openai.com/v1`;
- secret: `MI_AI_SYSTEM_API_KEY`;
- probe: `GET /v1/models` com `Authorization: Bearer`.

### Agentes

- provider: `gemini`;
- modelo padrão: `gemini-3.6-flash`;
- base URL: `https://generativelanguage.googleapis.com/v1beta`;
- secret: `MI_AI_AGENTS_API_KEY`;
- probe: `GET /v1beta/models` com `x-goog-api-key`.

A escolha continua protegida por uma camada de provider. A aplicação não depende estruturalmente de um único fornecedor; a separação atual é uma configuração de produto: GPT para o sistema e Gemini para os agentes.

## Variáveis previstas

Configurações não secretas:

- `MI_AI_SYSTEM_PROVIDER=openai`
- `MI_AI_SYSTEM_MODEL=gpt-5-mini`
- `MI_AI_SYSTEM_BASE_URL=https://api.openai.com/v1`
- `MI_AI_AGENTS_PROVIDER=gemini`
- `MI_AI_AGENTS_MODEL=gemini-3.6-flash`
- `MI_AI_AGENTS_BASE_URL=https://generativelanguage.googleapis.com/v1beta`

Secrets:

- `MI_AI_SYSTEM_API_KEY`
- `MI_AI_AGENTS_API_KEY`

Compatibilidade temporária: `MI_AI_API_KEY`, `MI_AI_MODEL`, `MI_AI_BASE_URL`, `MI_AI_RETRIES`, `MI_AI_TIMEOUT_SECONDS` e `MI_AI_STORE` podem atuar somente como fallback do papel `system`. O antigo `MI_AI_PROVIDER` não pode trocar silenciosamente o sistema para outro provedor. O papel `agents` nunca herda chave ou configuração secreta do sistema.

## Implementação

- `ProviderManager`: seleção de driver por configuração;
- `OpenAIResponsesDriver`: driver atual do papel `system`;
- `GeminiDriver`: driver atual do papel `agents`;
- `AIProviderConfig.from_env(role="system"|"agents")`: configuração isolada por papel;
- `scripts/probe_ai_provider.py --role system|agents`: prova de conectividade por papel;
- `market_intelligence.ai.status`: status não secreto de runtime.

## Probes seguros

### Sistema GPT

A prova usa somente `GET https://api.openai.com/v1/models`.

Ela comprova autenticação e disponibilidade do modelo configurado sem executar inferência e sem enviar dados de negócio.

### Agentes Gemini

A prova usa somente `GET https://generativelanguage.googleapis.com/v1beta/models`.

Ela comprova autenticação e disponibilidade do modelo configurado sem executar inferência e sem enviar dados de negócio.

## Segurança

Os dois drivers:

- recusam host arbitrário;
- exigem HTTPS e base URL oficial;
- não seguem redirects;
- não imprimem credencial;
- não enviam anúncios, pedidos, métricas ou dados pessoais no probe;
- retornam somente resultado sanitizado.

A chave dos agentes nunca herda `MI_AI_SYSTEM_API_KEY` nem `MI_AI_API_KEY`.

## GitHub Actions

O Environment usado é `INTELIGENCI DE MERCADO API`.

O workflow autenticado possui dois jobs independentes:

- `system-gpt`;
- `agents-gemini`.

Isso permite provar e diagnosticar cada credencial sem misturar fornecedores ou privilégios.

## Critério para conexão real comprovada

Cada papel só será marcado como conectado quando:

1. seu Secret estiver configurado no GitHub;
2. o probe correspondente rodar no Environment autenticado;
3. `authenticated=true`;
4. `model_available=true`;
5. `inference_executed=false` durante o probe;
6. `business_data_sent=false` durante o probe;
7. nenhuma credencial aparecer em log ou artefato.
