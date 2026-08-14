# Cofre de IA — 5 perfis completos e independentes

## Objetivo

O API ML possui capacidade fixa de **5 perfis de IA**. Cada perfil é uma ficha completa e independente para um provedor/modelo. O sistema não compartilha credenciais entre perfis e não assume que todos os provedores usam o mesmo método de autenticação.

Os perfis são nomeados de forma uniforme:

- `MI_AI_PROFILE_1_*`
- `MI_AI_PROFILE_2_*`
- `MI_AI_PROFILE_3_*`
- `MI_AI_PROFILE_4_*`
- `MI_AI_PROFILE_5_*`

Para os testes atuais:

- perfil 1: OpenAI / GPT / sistema;
- perfil 2: Z.AI / GLM / agentes;
- perfis 3, 4 e 5: disponíveis e desativados até configuração futura.

A seleção operacional é feita por:

- `MI_AI_SYSTEM_PROFILE=1`
- `MI_AI_AGENTS_PROFILE=2`

Esses seletores podem apontar para qualquer slot de 1 a 5 sem reconstruir o sistema.

## Campos públicos — Environment variables

Cada um dos cinco perfis possui os mesmos campos públicos. Substitua `N` por `1`, `2`, `3`, `4` ou `5`:

- `MI_AI_PROFILE_N_ENABLED`
- `MI_AI_PROFILE_N_NAME`
- `MI_AI_PROFILE_N_PROVIDER`
- `MI_AI_PROFILE_N_MODEL`
- `MI_AI_PROFILE_N_BASE_URL`
- `MI_AI_PROFILE_N_PROTOCOL`
- `MI_AI_PROFILE_N_AUTH_TYPE`
- `MI_AI_PROFILE_N_AUTH_HEADER`
- `MI_AI_PROFILE_N_API_VERSION`
- `MI_AI_PROFILE_N_ORGANIZATION`
- `MI_AI_PROFILE_N_PROJECT`
- `MI_AI_PROFILE_N_TENANT`
- `MI_AI_PROFILE_N_REGION`
- `MI_AI_PROFILE_N_DEPLOYMENT`
- `MI_AI_PROFILE_N_CLIENT_ID`
- `MI_AI_PROFILE_N_TIMEOUT_SECONDS`
- `MI_AI_PROFILE_N_RETRIES`
- `MI_AI_PROFILE_N_MAX_OUTPUT_TOKENS`
- `MI_AI_PROFILE_N_TEMPERATURE`
- `MI_AI_PROFILE_N_STORE`
- `MI_AI_PROFILE_N_EXTRA_CONFIG_JSON`

`EXTRA_CONFIG_JSON` é a extensão para parâmetros públicos que um provedor futuro possa exigir sem obrigar uma alteração imediata do formato do cofre.

## Campos confidenciais — Environment secrets

Cada um dos cinco perfis possui os mesmos campos confidenciais. Substitua `N` por `1`, `2`, `3`, `4` ou `5`:

- `MI_AI_PROFILE_N_API_KEY`
- `MI_AI_PROFILE_N_BEARER_TOKEN`
- `MI_AI_PROFILE_N_CLIENT_SECRET`
- `MI_AI_PROFILE_N_ACCESS_TOKEN`
- `MI_AI_PROFILE_N_REFRESH_TOKEN`
- `MI_AI_PROFILE_N_PRIVATE_KEY`
- `MI_AI_PROFILE_N_SERVICE_ACCOUNT_JSON`
- `MI_AI_PROFILE_N_EXTRA_SECRET_JSON`

`EXTRA_SECRET_JSON` é reservado para material confidencial específico de um provedor futuro. Seu conteúdo permanece selado; não é enviado automaticamente para nenhuma API.

## Regras de segurança

1. Cada perfil possui credenciais próprias.
2. Nenhuma credencial é herdada de outro perfil.
3. O status público informa apenas `*_configured=true/false`; nunca retorna o valor secreto.
4. `SecretStr` mantém valores confidenciais mascarados em representações e logs.
5. Um provedor desconhecido pode ser cadastrado no cofre, mas não pode executar rede até existir um adapter explícito para ele.
6. O adapter do provedor recebe apenas os campos que declara suportar; `EXTRA_SECRET_JSON`, tokens OAuth, private keys e service accounts não são encaminhados genericamente.
7. Perfis desativados falham fechados quando selecionados para execução.
8. O cofre não executa fallback automático entre perfis.

## Compatibilidade com a configuração já comprovada

Durante a migração, se `PROFILE_1` e `PROFILE_2` ainda não estiverem preenchidos, o runtime cria uma ponte somente em memória a partir dos nomes já utilizados:

- `MI_AI_SYSTEM_*` → perfil 1;
- `MI_AI_AGENTS_*` → perfil 2.

Isso preserva as conexões autenticadas já comprovadas de GPT e Z.AI enquanto o Environment é migrado gradualmente para o formato de cinco perfis.

Quando os novos campos forem preenchidos, eles passam a ter precedência e a ponte antiga deixa de ser usada naquele slot.

## Estado inicial recomendado

### Perfil 1 — Sistema

- `ENABLED=true`
- `NAME=System GPT`
- `PROVIDER=openai`
- `MODEL=gpt-5-mini`
- `BASE_URL=https://api.openai.com/v1`
- `PROTOCOL=openai-compatible`
- `AUTH_TYPE=api_key`
- `API_KEY=<GitHub Environment Secret>`

### Perfil 2 — Agentes

- `ENABLED=true`
- `NAME=Agents GLM`
- `PROVIDER=zai`
- `MODEL=glm-5.1`
- `BASE_URL=https://api.z.ai/api/paas/v4`
- `PROTOCOL=openai-compatible`
- `AUTH_TYPE=api_key`
- `API_KEY=<GitHub Environment Secret>`

### Perfis 3, 4 e 5

- `ENABLED=false`
- demais campos podem ficar vazios até a escolha de um novo provedor/modelo.

## Critério de aceitação

O cofre de cinco perfis é aprovado quando:

- existem exatamente 5 slots;
- todos expõem o mesmo conjunto de campos;
- sistema e agentes podem selecionar slots diferentes;
- perfis não compartilham segredos;
- dados confidenciais não aparecem no status público;
- a configuração antiga de GPT/Z.AI continua funcionando durante a migração;
- CI integral permanece verde.
