# ADR — Arquitetura Multi-IA e Controle de Custo V1

**Data:** 13/08/2026
**Estado:** APROVADO EM PRINCÍPIO; RANKING DE MODELOS PENDENTE DE BENCHMARK
**Escopo:** inteligência principal, agentes internos e runtime automatizado do Market Intelligence IA

## Decisão soberana

O **ChatGPT/Pipo permanece como inteligência principal e orquestradora do sistema**.

As APIs externas de IA não substituem essa autoridade. Elas formam um pool de capacidade para os agentes e para o runtime automatizado quando uma tarefa precisar ser executada sem depender de uma conversa interativa aberta.

O Market Intelligence IA terá **uma única API/contrato interno de IA**, estável e independente de fornecedor. Nenhum agente chama diretamente OpenAI, Groq, Z.AI/GLM, SiliconFlow/Qwen, DeepSeek ou Moonshot/Kimi.

```text
PROPRIETÁRIO
    |
CHATGPT / PIPO
inteligência principal + direção técnica
    |
    v
AGENTES ESPECIALIZADOS
    |
    v
AI ROUTER / GATEWAY INTERNO
    |
    +--> OpenAI API
    +--> Groq
    +--> Z.AI / GLM
    +--> SiliconFlow / Qwen
    +--> DeepSeek
    +--> Moonshot / Kimi
```

Todos os provedores acima podem ser usados. **Isso não significa enviar cada tarefa para todos eles.** O roteador escolhe o menor custo capaz de cumprir o critério de qualidade e escala somente quando necessário.

## Separação ChatGPT x API

- `ChatGPT/Pipo`: cérebro principal, coordenação, decisão técnica, síntese, supervisão dos agentes e interação com o proprietário.
- `OpenAI API`: um dos motores programáticos disponíveis para execução automática pelo software.
- demais APIs: motores auxiliares, reservas ou especialistas conforme benchmark.

A assinatura do ChatGPT não deve ser tratada como franquia de API. Custos de API são controlados separadamente.

## Nenhum ranking definitivo agora

A classificação anterior de “Groq primeiro”, “GLM segundo”, “DeepSeek contexto longo” etc. fica **suspensa como decisão fixa**.

Essas hipóteses serão testadas. O ranking final será produzido por evidência para cada função de agente.

Exemplo:

```text
Agente de segurança
  qualidade técnica
  aderência a instruções
  taxa de falso negativo
  latência
  custo por tarefa aprovada
        -> ranking próprio

Agente de triagem
  precisão suficiente
  baixa latência
  baixo custo
        -> ranking diferente
```

Não existe obrigação de o melhor modelo de arquitetura ser também o melhor para classificação, SQL, resumo, código, visão ou análise de mercado.

## Regra econômica central

A unidade de decisão não será “preço por milhão de tokens” isoladamente.

Será:

```text
CUSTO EFETIVO POR TAREFA APROVADA
=
(tokens + ferramentas + retries + falhas + escaladas)
/
resultado que passou no critério de qualidade
```

Um modelo barato que exige três tentativas pode ser mais caro que um modelo superior que resolve de primeira.

Um modelo excelente e caro não deve ser usado para trabalho trivial.

## Política de roteamento econômico

Para cada tarefa o roteador considera:

1. função do agente;
2. criticidade;
3. capacidade necessária;
4. classificação/sensibilidade dos dados;
5. qualidade histórica por tipo de tarefa;
6. taxa de sucesso na primeira tentativa;
7. latência;
8. tokens de entrada e saída;
9. cache disponível;
10. custo estimado total;
11. disponibilidade/saúde do provedor;
12. orçamento restante do período.

A política padrão é **economic-first com quality floor**:

```text
escolher o modelo mais econômico
QUE já tenha demonstrado qualidade mínima
para aquela função
```

Se o resultado não atingir o critério:

```text
modelo econômico
    -> validação
        -> insuficiente
            -> modelo intermediário
                -> validação
                    -> crítico/complexo
                        -> modelo de maior capacidade
```

## Perfis lógicos, não fornecedores fixos

Os agentes pedem capacidades:

```text
FAST
STANDARD_REASONING
DEEP_REASONING
LONG_CONTEXT
MULTIMODAL
CODING
DATA_ANALYSIS
STRUCTURED_OUTPUT
TOOL_USE
HIGH_ASSURANCE
```

O mapping físico fica em registry versionado e pode mudar sem alterar os agentes.

## Pool aprovado para avaliação e uso

### OpenAI

Papel: candidato natural ao pool principal por integração com ChatGPT/Pipo, modelos agentic e família com diferentes faixas de custo/capacidade.

Não fixar o modelo mais caro como default. O registry deve permitir níveis econômico, equilibrado e crítico.

### Groq

Papel: candidato forte para baixa latência e alto volume.

Deve ser avaliado por custo efetivo e qualidade por tarefa; velocidade sozinha não determina prioridade.

### Z.AI / GLM

Papel: candidato para raciocínio, engenharia e agentes complexos.

A família e versão escolhidas dependem de benchmark; não assumir que o maior modelo é o melhor custo-benefício.

### SiliconFlow / Qwen

Papel: agregador/reserva e família chinesa de alta importância estratégica.

Também pode oferecer rotas alternativas para outras famílias. IDs físicos ficam no registry, nunca embutidos nos agentes.

### DeepSeek

Papel: candidato para raciocínio/código/análise, condicionado a benchmark real do perfil.

A expressão “especialista de contexto” não é decisão arquitetural. Contexto máximo é apenas uma característica; o papel será comprovado nos testes.

### Moonshot / Kimi

Papel: candidato para multimodalidade, documentos extensos e tarefas complexas, condicionado a benchmark e custo efetivo.

## Benchmark obrigatório por agente

Antes de definir 1º, 2º e 3º lugar, cada função relevante terá um conjunto de tarefas representativas.

Métricas mínimas:

```text
qualidade / acerto
aderência ao contrato
aderência às políticas
sucesso de tool calling
taxa de primeira tentativa
latência p50 / p95
input tokens
output tokens
cache
custo por execução
custo por tarefa aprovada
falhas / 429 / 5xx
consistência em repetição
```

Para agentes críticos incluir:

```text
falso positivo
falso negativo
capacidade de explicar evidência
não inventar fatos
não atravessar autorização
```

## Controle de orçamento

O AI Router deverá ter:

- orçamento máximo por tarefa;
- orçamento por agente;
- orçamento diário e mensal;
- alerta em 50%, 75%, 90% e 100%;
- bloqueio ou degradação controlada quando o teto for atingido;
- limite de retries;
- limite de escaladas;
- limite de saída;
- contabilização de cache e ferramentas;
- relatório de custo por resultado útil.

Nenhum agente tem permissão para aumentar orçamento por conta própria.

## Estratégia de economia

Prioridades:

1. não enviar contexto desnecessário;
2. usar recuperação seletiva de contexto;
3. resumir histórico quando seguro;
4. aproveitar cache de prompt quando disponível;
5. limitar saída ao necessário;
6. escolher modelo proporcional à dificuldade;
7. evitar chamadas duplicadas;
8. benchmark antes de escalar modelo;
9. usar processamento em lote somente onde não houver requisito de tempo real;
10. medir custo real, não estimativa teórica apenas.

## Failover

Failover automático é permitido para falhas técnicas transitórias:

- timeout;
- conexão indisponível;
- HTTP 429;
- HTTP 5xx;
- modelo temporariamente indisponível;
- circuit breaker aberto.

Não fazer failover automático em:

- contrato inválido;
- 401/403;
- violação de política;
- recusa de segurança;
- validação de ferramenta falha;
- operação externa cujo efeito possa ter ocorrido e ainda não tenha sido reconciliado.

## Ferramentas e efeitos externos

Modelos podem propor chamadas. A execução pertence ao Market Intelligence IA:

```text
modelo propõe
   -> schema
   -> policy/autorização
   -> idempotência
   -> executor interno
   -> readback/evidência
   -> resultado ao modelo
```

Nenhuma API de IA recebe autoridade direta sobre Mercado Livre, banco crítico, cofre, GitHub ou infraestrutura.

## Segurança de dados

Nunca enviar a provedores:

- Client Secret;
- access token;
- refresh token;
- código OAuth;
- Authorization header;
- chaves de banco/cofre;
- segredo de outro provedor;
- PII sem finalidade e política específica.

Preferir dados minimizados, contratos normalizados e IDs internos.

## Observabilidade

Toda chamada registra sem conteúdo sensível:

- correlation_id;
- agent_id;
- capacidade solicitada;
- provider/model escolhidos;
- razão da rota;
- latência;
- tokens;
- cache;
- custo estimado e real quando disponível;
- retries;
- escaladas/failover;
- avaliação de qualidade;
- status final.

## Codex local

Codex local permanece executor principal de engenharia quando houver acesso à máquina. Não é substituído por este pool de APIs.

## Estado arquitetural final desta revisão

```text
IA PRINCIPAL / ORQUESTRADOR     = ChatGPT / Pipo
API INTERNA DE IA               = única e estável
POOL DE PROVEDORES              = OpenAI + Groq + Z.AI + SiliconFlow + DeepSeek + Kimi
RANKING FIXO                    = NÃO DEFINIDO
SELEÇÃO                         = benchmark por agente + custo-benefício
POLÍTICA                        = economic-first com quality floor
MODELO CARO COMO DEFAULT        = PROIBIDO
CONTROLE DE ORÇAMENTO           = obrigatório
TOOL EXECUTION                  = interno e governado
CODEX LOCAL                     = engenharia local
GITHUB                          = memória operacional
```

## Próximo passo

Antes de implementar prioridades definitivas, criar a **Matriz de Benchmark de IAs por Agente V1** e o esqueleto do AI Router com registry neutro.

Nenhuma chave real, recarga, contratação ou gasto novo é autorizado por este ADR.
