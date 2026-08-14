# Conexão das APIs de IA ao API ML via GitHub

## Objetivo

O API ML consome IA por contrato estável através do `ProviderManager`. GitHub guarda código, CI e segredos; não é barramento de runtime.

O projeto possui dois papéis de IA independentes:

1. `system`: inteligência responsável pelo próprio sistema API ML;
2. `agents`: capacidade de IA utilizada pelos agentes/workers autorizados.

Os dois papéis podem usar Gemini, mas não compartilham a mesma credencial.

## Configuração atual

### Sistema

- provider: `gemini`;
- modelo padrão: `gemini-3.6-flash`;
- base URL: `https://generativelanguage.googleapis.com/v1beta`;
- secret: `MI_AI_SYSTEM_API_KEY`.

### Agentes

- provider: `gemini`;
- modelo padrão: `gemini-3.6-flash`;
- base URL: `https://generativelanguage.googleapis.com/v1beta`;
- secret: `MI_AI_AGENTS_API_KEY`.

A escolha do provedor e do modelo permanece configurável. OpenAI continua disponível como driver alternativo; não é dependência fixa da aplicação.

## Variáveis previstas

Configurações não secretas:

- `MI_AI_SYSTEM_PROVIDER=gemini`
- `MI_AI_SYSTEM_MODEL=gemini-3.6-flash`
- `MI_AI_SYSTEM_BASE_URL=https://generativelanguage.googleapis.com/v1beta`
- `MI_AI_AGENTS_PROVIDER=gemini`
- `MI_AI_AGENTS_MODEL=gemini-3.6-flash`
- `MI_AI_AGENTS_BASE_URL=https://generativelanguage.googleapis.com/v1beta`

Secrets:

- `MI_AI_SYSTEM_API_KEY`
- `MI_AI_AGENTS_API_KEY`

Compatibilidade temporária: os antigos `MI_AI_PROVIDER`, `MI_AI_MODEL`, `MI_AI_BASE_URL` e `MI_AI_API_KEY` podem ser usados apenas como fallback do papel `system`. O papel `agents` nunca reutiliza a chave do sistema nem a chave legada.

## Implementação

- `ProviderManager`: seleção de driver por configuração;
- `GeminiDriver`: driver Gemini atual;
- `OpenAIResponsesDriver`: alternativa preservada;
- `AIProviderConfig.from_env(role="system"|"agents")`: configuração isolada por papel;
- `scripts/probe_ai_provider.py --role system|agents`: prova de conectividade por papel.

## Probe seguro Gemini

A prova inicial usa somente `GET /v1beta/models` com o header `x-goog-api-key`.

Ela comprova:

1. aceitação da credencial;
2. resposta do host oficial;
3. disponibilidade do modelo configurado para a credencial.

Ela não:

- executa inferência;
- envia anúncios, pedidos, métricas ou qualquer dado de negócio;
- imprime a credencial;
- segue redirects;
- aceita host arbitrário para o driver Gemini.

O driver recusa base URL diferente de HTTPS + `generativelanguage.googleapis.com` + `/v1beta`, reduzindo risco de exfiltração de credenciais por configuração maliciosa.

## Separação de credenciais

A chave do sistema é exclusiva do papel `system`.

A chave dos agentes é exclusiva do papel `agents`.

Se `MI_AI_AGENTS_API_KEY` estiver ausente, o papel de agentes falha fechado: ele não herda `MI_AI_SYSTEM_API_KEY` nem `MI_AI_API_KEY`.

## GitHub Actions

O conector disponível nesta sessão permite confirmar a existência do ambiente GitHub, mas não possui permissão para listar os nomes/valores dos Environment Secrets. O workflow autenticado que referencia Secrets também não deve ser criado por bypass de baixo nível se a camada de segurança do conector bloquear essa escrita.

## Critério para conexão real comprovada

Cada papel só será marcado como conectado quando:

1. seu Secret estiver configurado no GitHub;
2. o probe correspondente rodar em ambiente autenticado;
3. `authenticated=true`;
4. `model_available=true`;
5. `inference_executed=false` durante o probe;
6. `business_data_sent=false` durante o probe;
7. nenhuma credencial aparecer em log ou artefato.
