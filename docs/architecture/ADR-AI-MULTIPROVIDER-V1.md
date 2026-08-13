# ADR — Arquitetura Multi-API de IA V1

**Data:** 13/08/2026
**Estado:** APROVADO TECNICAMENTE PARA IMPLEMENTAÇÃO
**Escopo:** agentes internos do Market Intelligence IA

## Decisão

O Market Intelligence IA terá **uma única API/contrato interno de IA**, estável e independente de fornecedor. Os agentes nunca chamarão Groq, Z.AI, SiliconFlow, Moonshot/Kimi ou DeepSeek diretamente.

A topologia aprovada é:

```text
AGENTES
   |
   v
AI ROUTER / GATEWAY INTERNO
   |
   +--> PRINCIPAL-RÁPIDO: Groq
   +--> PRINCIPAL-PROFUNDO: Z.AI / GLM
   +--> RESERVA: SiliconFlow / Qwen
   +--> ESPECIALISTA-LONGO: DeepSeek
   +--> ESPECIALISTA-MULTIMODAL: Kimi
```

A API do sistema permanece única. Provedor e modelo são decisões do roteador e podem mudar sem alterar o contrato dos agentes.

## Correção de nomenclatura

`Groq/GLM` não é tratado como um único par provedor/modelo. Groq e Z.AI são provedores distintos. GLM é família de modelos Z.AI. Groq permanece no pool principal por baixa latência; GLM permanece no pool principal por capacidade de raciocínio/engenharia de longa duração.

## Perfis lógicos aprovados

### `fast_agent`

- Primário: Groq `openai/gpt-oss-120b`.
- Finalidade: loops rápidos, classificação, sumarização operacional, transformação de contratos, preparação de chamadas de ferramenta e tarefas de baixa/média complexidade.
- Regra: ferramentas executam no nosso runtime; não delegar efeitos externos a ferramenta server-side do provedor.

### `deep_agent`

- Primário: Z.AI família GLM.
- Padrão econômico: `glm-4.7`.
- Escalada crítica/long-horizon: `glm-5.1`.
- Finalidade: arquitetura, depuração complexa, investigação causal, planejamento longo, revisão técnica e decisões de alta complexidade.

### `reserve_agent`

- Provedor: SiliconFlow.
- Família: Qwen.
- O modelo físico é resolvido por um registry versionado e deve passar benchmark/contrato antes da promoção. Não colocar IDs de preview/deprecados diretamente nos agentes.
- Finalidade: failover independente e capacidade adicional de engenharia/código.

### `long_context_specialist`

- Primário: DeepSeek `deepseek-v4-pro`.
- Finalidade: contexto muito longo, análise histórica ampla, matemática/raciocínio profundo e grandes bases de código/documentos.

### `multimodal_specialist`

- Primário: Moonshot/Kimi `kimi-k2.6`.
- Finalidade: imagem, vídeo, documentos visuais, frontend, análise multimodal e tarefas agentic long-horizon em que visão agrega valor.

## Regra de roteamento

O agente solicita uma **capacidade**, nunca um fornecedor:

```text
FAST
DEEP_REASONING
LONG_CONTEXT
MULTIMODAL
CODING
STRUCTURED_OUTPUT
TOOL_USE
```

O roteador seleciona o provedor/modelo conforme:

1. capacidade exigida;
2. classificação de dados;
3. saúde do provedor;
4. limite de contexto;
5. latência;
6. custo máximo da tarefa;
7. histórico de qualidade do modelo para aquele perfil.

## Failover

Failover automático é permitido somente para falhas técnicas transitórias:

- timeout;
- conexão indisponível;
- HTTP 429;
- HTTP 5xx;
- modelo temporariamente indisponível;
- circuit breaker aberto.

Não executar failover automático para:

- 400 por contrato inválido;
- 401/403 de credencial/permissão;
- violação de política;
- recusa de segurança;
- erro de validação de ferramenta;
- operação externa cujo efeito possa ter ocorrido e ainda não tenha sido reconciliado.

## Ferramentas e ações

Modelos podem **propor** tool calls. A execução pertence ao Market Intelligence IA.

Fluxo obrigatório:

```text
modelo propõe ferramenta
      |
validação de schema
      |
policy / autorização / escopo
      |
idempotência
      |
executor interno
      |
readback / evidência
      |
resultado volta ao modelo
```

Nenhum provedor de IA recebe autoridade direta para escrever no Mercado Livre, banco crítico, cofre, GitHub ou infraestrutura.

## Segurança de dados

Nunca enviar aos provedores:

- Client Secret do Mercado Livre;
- access token ou refresh token;
- código OAuth;
- Authorization header;
- chave de banco/cofre;
- segredo de outro provedor;
- PII de comprador sem necessidade e política específica.

Preferir contratos normalizados, dados minimizados, IDs internos e amostras sanitizadas.

## Registry de modelos

Os agentes usam aliases lógicos. O mapping físico fica em registry versionado, por exemplo:

```text
fast_agent             -> groq/openai-gpt-oss-120b
deep_agent              -> zai/glm-4.7
deep_agent_critical     -> zai/glm-5.1
reserve_agent           -> siliconflow/qwen-approved
long_context_specialist -> deepseek/deepseek-v4-pro
multimodal_specialist   -> moonshot/kimi-k2.6
```

Trocar modelo exige somente alterar o registry após benchmark e CI. Não exige alterar cada agente.

## Observabilidade obrigatória

Cada chamada deve registrar, sem conteúdo sensível:

- correlation_id;
- agent_id;
- profile solicitado;
- provider escolhido;
- model_id resolvido;
- motivo da rota;
- latência;
- tokens de entrada/saída;
- cache quando informado;
- custo estimado;
- retries/failover;
- tool calls propostas/executadas;
- status final.

## Circuit breaker e saúde

Manter estado por `provider + model`:

```text
HEALTHY
DEGRADED
OPEN
RECOVERING
DISABLED
```

Falhas de um provedor não derrubam a API interna. O roteador usa fallback aprovado e registra a mudança.

## Controle de custo

Todo perfil possui orçamento por tarefa. O roteador deve evitar usar modelos de maior custo quando um modelo aprovado de classe inferior atende ao critério de qualidade.

GLM-5.1, Kimi K2.6 e DeepSeek V4-Pro são escaladas por capacidade, não defaults universais.

## Critérios para ativar um modelo/provider

Antes de entrar no pool ativo:

1. API compatível/adaptador implementado;
2. tool calling testado quando necessário;
3. JSON/schema testado;
4. latência medida;
5. custo medido;
6. contexto confirmado;
7. política de dados revisada;
8. testes de segredo aprovados;
9. failover testado;
10. benchmark mínimo por função do agente.

## Política para SiliconFlow

SiliconFlow é aprovado como **provedor-reserva e agregador**, não como dependência única. A disponibilidade de modelos muda com frequência; por isso os IDs físicos não ficam embutidos nos agentes. O registry deve fixar a versão aprovada e possuir teste de disponibilidade/depreciação.

## Política para Codex local

Codex local continua sendo o executor de engenharia quando houver acesso à máquina. As APIs descritas neste ADR servem aos agentes/runtime do Market Intelligence IA e a tarefas distribuídas; não substituem o Codex local nem o GitHub como memória operacional.

## Resultado arquitetural

```text
API DO SISTEMA       = única e estável
AGENTES              = independentes de fornecedor
MODELOS              = substituíveis
PROVEDORES            = redundantes
SEGREDOS              = isolados
TOOL EXECUTION        = interno e governado
FAILOVER              = controlado
CUSTO                 = observável
QUALIDADE             = benchmark por função
```

## Próxima implementação autorizada pela arquitetura

Criar o `AI Router`, adapters OpenAI-compatible, registry de modelos, health/circuit breaker, telemetria de custo/latência e testes sintéticos. Nenhuma chave real deve entrar no Git e nenhum plano pago deve ser contratado automaticamente.
