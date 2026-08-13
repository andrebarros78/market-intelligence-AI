# ADR — Política Zero-Cost-First para IA V1

**Data:** 13/08/2026
**Estado:** APROVADO PELO PROPRIETÁRIO
**Relaciona-se com:** `ADR-AI-MULTIPROVIDER-V1.md`

## Decisão soberana

O Market Intelligence IA inicia com **custo adicional de IA igual a zero sempre que tecnicamente possível**.

O **ChatGPT/Pipo permanece como inteligência principal e orquestradora**. As demais capacidades automatizadas devem priorizar modelos, runtimes e ferramentas gratuitos, open-weight ou executáveis localmente, desde que cumpram o critério mínimo de qualidade e segurança da função do agente.

Nenhum agente fica acoplado a um fornecedor/modelo específico.

## Regra econômica inicial

```text
DEFAULT = FREE / LOCAL / OPEN-WEIGHT
PAGO    = DESABILITADO POR PADRÃO
EXCEÇÃO = somente após autorização explícita de orçamento
```

A existência de suporte a um provedor pago não autoriza consumo.

## ChatGPT como principal

ChatGPT/Pipo exerce:

- direção técnica;
- orquestração da equipe;
- síntese e decisão;
- supervisão de agentes;
- aprovação técnica dentro dos limites autorizados.

O uso de ChatGPT não implica habilitar automaticamente chamadas pagas da OpenAI API no backend.

## Pool inicial dos agentes

A primeira rodada de benchmark deve privilegiar:

1. modelos open-weight executados localmente quando o hardware permitir;
2. endpoints gratuitos ou franquias gratuitas verificadas;
3. ferramentas gratuitas que aceitem múltiplos provedores, como OpenCode;
4. provedores pagos somente registrados como adaptadores inativos para uso futuro.

Toda oferta gratuita é considerada **capacidade variável**, não garantia permanente. O registry deve registrar disponibilidade, limite e data de verificação.

## Compatibilidade futura obrigatória

O AI Router deve preservar adapters para múltiplos provedores sem ativá-los:

```text
AI ROUTER
  |
  +-- local/open-weight      [ATIVO por padrão quando aprovado]
  +-- free endpoint          [ATIVO quando custo = 0 e contrato aprovado]
  +-- OpenAI API             [ADAPTER DISPONÍVEL / consumo pago desabilitado]
  +-- Groq                   [ADAPTER DISPONÍVEL]
  +-- Z.AI / GLM             [ADAPTER DISPONÍVEL]
  +-- SiliconFlow / Qwen     [ADAPTER DISPONÍVEL]
  +-- DeepSeek               [ADAPTER DISPONÍVEL]
  +-- Moonshot / Kimi        [ADAPTER DISPONÍVEL]
  +-- futuros provedores     [PLUGÁVEIS]
```

Adicionar ou trocar um provedor deve exigir somente novo adapter/registry e benchmark, não alteração de cada agente.

## Contrato neutro dos agentes

Agentes solicitam capacidades, nunca nomes comerciais:

```text
FAST
STANDARD_REASONING
DEEP_REASONING
CODING
LONG_CONTEXT
MULTIMODAL
DATA_ANALYSIS
STRUCTURED_OUTPUT
TOOL_USE
HIGH_ASSURANCE
```

O roteador resolve `capacidade -> modelo/provider` conforme política vigente.

## Critério de seleção

Enquanto o orçamento pago estiver desabilitado:

1. filtrar somente rotas com custo incremental zero;
2. eliminar rotas que não atinjam o piso de qualidade/segurança;
3. escolher a melhor qualidade entre as rotas gratuitas aprovadas;
4. em empate, escolher menor latência/uso de recursos;
5. se nenhuma rota gratuita cumprir a missão, retornar `PAID_CAPABILITY_REQUIRED` e não gerar gasto automaticamente.

## Política de modelos pagos futuros

Quando houver orçamento e autorização explícita, um modelo pago poderá ser promovido por benchmark.

A promoção exige:

- custo conhecido;
- teto por tarefa/agente/período;
- qualidade superior demonstrada para a função;
- health/failover;
- política de dados aprovada;
- observabilidade de tokens e custo;
- rollback simples para uma rota gratuita ou alternativa.

Nenhum modelo pago será "permanente" ou hard-coded.

## OpenCode

OpenCode é tratado como **ferramenta/host de engenharia multi-provider**, não como um modelo. Pode trabalhar com vários provedores e também com modelos locais. Sua presença não altera o contrato interno do Market Intelligence IA.

## Codex local

Codex local continua sendo o executor principal de engenharia quando a máquina estiver disponível. Ele é independente do pool de inferência do produto.

## Estado de custo

```text
CHATGPT/PIPO               = PRINCIPAL
APIs PAGAS AUTOMÁTICAS     = DESABILITADAS
FREE/OPEN/LOCAL            = PRIORIDADE
GASTO AUTOMÁTICO           = PROIBIDO
ADAPTERS PAGOS             = PODEM EXISTIR INATIVOS
TROCA FUTURA DE MODELO     = SUPORTADA
HARD-CODE DE PROVIDER      = PROIBIDO
```

## Próximo passo técnico

Implementar o esqueleto neutro do AI Router e a Matriz de Benchmark por Agente com um `CostPolicy` que, inicialmente, aceite apenas `incremental_cost == 0`.

Nenhuma recarga, assinatura, chave paga ou consumo financeiro é autorizado por este ADR.
