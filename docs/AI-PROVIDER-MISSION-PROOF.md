# GPT do sistema + Z.AI/GLM dos agentes — prova de conexão

## Estado

**MISSION_PROVEN** para a missão de conexão das APIs de IA ao Market Intelligence AI.

Esta conclusão se refere exclusivamente à conexão autenticada das IAs. Não significa conclusão integral do Market Intelligence AI nem ativação de escrita no Mercado Livre.

## Arquitetura comprovada

O Market Intelligence AI mantém dois papéis de IA independentes por meio do `ProviderManager`:

- `system`: OpenAI/GPT, responsável pela inteligência do sistema;
- `agents`: Z.AI/GLM, exclusivo dos agentes/workers.

Credenciais:

- `MI_AI_SYSTEM_API_KEY`: OpenAI/GPT;
- `MI_AI_AGENTS_API_KEY`: Z.AI/GLM.

Os agentes não herdam a credencial do sistema. Gemini permanece apenas como provider opcional na abstração e não é o provider atual dos agentes.

## Configuração validada

### Sistema

- provider: `openai`;
- modelo: `gpt-5-mini`;
- endpoint: `https://api.openai.com/v1`;
- probe: `GET /v1/models`;
- autenticação: Bearer.

### Agentes

- provider: `zai`;
- modelo: `glm-5.1`;
- endpoint: `https://api.z.ai/api/paas/v4`;
- probe: `GET /api/paas/v4/models`;
- autenticação: Bearer.

## Evidência técnica

### Implementação Z.AI

- PR #44: `GPT sistema + Z.AI GLM agentes — conexão autenticada`;
- head validado: `9bef2042c02952df1cf9efd909a0dc91e18f5886`;
- CI de branch #181 / run `31812167894`: sucesso integral;
- merge PR #44: `5b7d74f6e85e430191ff12bdb42ee113d2763ed3`.

O primeiro gate autenticado após esse merge provou que:

- a chave Z.AI já autenticava e o job `agents-zai` passava;
- a chave OpenAI também autenticava, mas o valor antigo de `MI_AI_SYSTEM_MODEL` armazenado como Secret apontava para modelo indisponível;
- a falha era de configuração de modelo, não da chave OpenAI.

### Correção do modelo

- PR #45: `Corrigir configuração pública dos modelos de IA`;
- head validado: `57cfa77f10521fef1a42e3461e1c0cbb369d1ce0`;
- CI de branch #183 / run `31812535546`: sucesso integral;
- merge PR #45: `9528c3f896a7ebb889342d3d876966a5490a1df6`.

Modelos deixaram de ser tratados como Secrets. O gate passou a usar configuração pública explícita:

- `gpt-5-mini` para `system`;
- `glm-5.1` para `agents`.

### Gate autenticado final

Workflow: `AI Provider Connectivity`

- run #3;
- run id: `31812722075`;
- SHA testado: `9528c3f896a7ebb889342d3d876966a5490a1df6`;
- conclusão global: `success`.

Resultado `system-gpt`:

- `provider=openai`;
- `model=gpt-5-mini`;
- `authenticated=true`;
- `model_available=true`;
- `endpoint_host=api.openai.com`;
- `inference_executed=false`;
- `business_data_sent=false`;
- `status=ok`.

Resultado `agents-zai`:

- `provider=zai`;
- `model=glm-5.1`;
- `authenticated=true`;
- `model_available=true`;
- `endpoint_host=api.z.ai`;
- `inference_executed=false`;
- `business_data_sent=false`;
- `status=ok`.

### Regressão pós-merge

Workflow `Validate Market Intelligence Base`:

- run #184;
- run id: `31812722077`;
- SHA testado: `9528c3f896a7ebb889342d3d876966a5490a1df6`;
- Install: success;
- Compile: success;
- PostgreSQL migration: success;
- migration drift: success;
- migration rollback: success;
- suíte de testes: success;
- conclusão global: success.

## Segurança comprovada

- nenhuma chave foi versionada;
- Secrets apareceram mascarados nos logs do GitHub Actions;
- nenhum valor de chave foi impresso pelo probe;
- os probes não executaram inferência;
- nenhum dado de negócio do Market Intelligence AI/Mercado Livre foi enviado aos provedores;
- redirects ficam desabilitados;
- drivers aceitam somente HTTPS, host e base URL oficiais configurados para cada provider;
- nenhuma escrita no Mercado Livre foi ativada por esta missão.

## Critério MISSION_PROVEN

Todos os gates desta missão foram satisfeitos:

1. Provider Manager desacoplado: **aprovado**;
2. GPT/OpenAI exclusivo do papel `system`: **aprovado**;
3. Z.AI/GLM exclusivo do papel `agents`: **aprovado**;
4. credenciais separadas: **aprovado**;
5. CI de implementação: **aprovado**;
6. OpenAI autenticado e modelo disponível: **aprovado**;
7. Z.AI autenticado e modelo disponível: **aprovado**;
8. nenhuma inferência no probe: **aprovado**;
9. nenhum dado de negócio no probe: **aprovado**;
10. regressão integral pós-merge: **aprovado**.

**Estado: MISSION_PROVEN.**
