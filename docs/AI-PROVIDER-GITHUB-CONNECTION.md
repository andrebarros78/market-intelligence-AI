# Conexão das APIs de IA ao API ML via GitHub

## Objetivo

O API ML consome IA por contrato estável através do `ProviderManager`. GitHub guarda código, CI e segredos; não é barramento de runtime.

O projeto possui dois papéis de IA independentes:

1. `system`: inteligência responsável pelo próprio sistema API ML — OpenAI/GPT;
2. `agents`: capacidade de IA utilizada pelos agentes/workers autorizados — Z.AI/GLM.

As credenciais são independentes e nunca são compartilhadas entre os dois papéis.

## Configuração atual

### Sistema

- provider: `openai`;
- modelo padrão: `gpt-5-mini`;
- base URL: `https://api.openai.com/v1`;
- secret: `MI_AI_SYSTEM_API_KEY`;
- probe: `GET /v1/models` com `Authorization: Bearer`.

### Agentes

- provider: `zai`;
- modelo padrão: `glm-5.1`;
- base URL: `https://api.z.ai/api/paas/v4`;
- secret: `MI_AI_AGENTS_API_KEY`;
- autenticação: `Authorization: Bearer`;
- protocolo: OpenAI-compatible.

A escolha continua protegida pela camada de provider. A aplicação não depende estruturalmente de um único fornecedor; a configuração de produto atual é GPT para o sistema e GLM/Z.AI para os agentes.

## Variáveis previstas

Configurações não secretas:

- `MI_AI_SYSTEM_PROVIDER=openai`
- `MI_AI_SYSTEM_MODEL=gpt-5-mini`
- `MI_AI_SYSTEM_BASE_URL=https://api.openai.com/v1`
- `MI_AI_AGENTS_PROVIDER=zai`
- `MI_AI_AGENTS_MODEL=glm-5.1`
- `MI_AI_AGENTS_BASE_URL=https://api.z.ai/api/paas/v4`

Secrets:

- `MI_AI_SYSTEM_API_KEY`
- `MI_AI_AGENTS_API_KEY`

Compatibilidade temporária: `MI_AI_API_KEY`, `MI_AI_MODEL`, `MI_AI_BASE_URL`, `MI_AI_RETRIES`, `MI_AI_TIMEOUT_SECONDS` e `MI_AI_STORE` podem atuar somente como fallback do papel `system`. O antigo `MI_AI_PROVIDER` não pode trocar silenciosamente o sistema para outro provedor. O papel `agents` nunca herda chave ou configuração secreta do sistema.

## Implementação

- `ProviderManager`: seleção de driver por configuração;
- `OpenAIResponsesDriver`: driver do papel `system`;
- `ZAIDriver`: driver do papel `agents`;
- `GeminiDriver`: alternativa preservada, não padrão atual;
- `AIProviderConfig.from_env(role="system"|"agents")`: configuração isolada por papel;
- `scripts/probe_ai_provider.py --role system|agents`: prova de conectividade por papel;
- `market_intelligence.ai.status`: status não secreto de runtime.

## Probes seguros

### Sistema GPT

A prova usa somente `GET https://api.openai.com/v1/models`.

### Agentes Z.AI

A Z.AI documenta endpoint geral `https://api.z.ai/api/paas/v4`, autenticação HTTP Bearer e compatibilidade com protocolo OpenAI. O probe utiliza o recurso de listagem de modelos do protocolo compatível e não executa geração de conteúdo.

Os probes não enviam anúncios, pedidos, métricas ou outros dados de negócio e mantêm `inference_executed=false`.

## Segurança

Os drivers:

- recusam host arbitrário;
- exigem HTTPS e base URL oficial de cada provedor;
- não seguem redirects;
- não imprimem credencial;
- retornam somente resultado sanitizado.

A chave dos agentes nunca herda `MI_AI_SYSTEM_API_KEY` nem `MI_AI_API_KEY`.

## GitHub Actions

O Environment usado é `INTELIGENCI DE MERCADO API`.

O workflow autenticado possui dois jobs independentes:

- `system-gpt`;
- `agents-zai`.

## Critério para conexão real comprovada

Cada papel só será marcado como conectado quando:

1. seu Secret estiver configurado no GitHub;
2. o probe correspondente rodar no Environment autenticado;
3. `authenticated=true`;
4. `model_available=true`;
5. `inference_executed=false` durante o probe;
6. `business_data_sent=false` durante o probe;
7. nenhuma credencial aparecer em log ou artefato.
