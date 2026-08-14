# ADR — Multimarketplace Intelligence Core V1

**Data:** 14/08/2026  
**Estado:** IMPLEMENTADO EM BRANCH / AGUARDANDO GATE DE CI  
**Escopo:** núcleo de domínio, adapters, evidência, skills, agentes e planos de IA

## Decisão

O Market Intelligence IA é uma plataforma de inteligência de marketplaces. Mercado Livre é o primeiro adapter de prova, não o domínio central do produto.

O núcleo não pode conhecer identificadores, contratos ou semântica exclusivos de Mercado Livre, Amazon, Shopee, TikTok Shop, SHEIN ou qualquer outro marketplace.

```text
Mercado Livre ─┐
Amazon ─────────┤
Shopee ─────────┤
TikTok Shop ────┤
SHEIN ──────────┤ -> Marketplace Adapter -> Canonical Model -> Intelligence Core
Temu ───────────┤
1688 ───────────┤
Outros ─────────┘
```

## Modelo canônico

O contrato central passa a reconhecer conceitos universais:

- account, seller, store;
- product, SKU, variant, offer/listing e catalog item;
- category, price, fee e promotion;
- inventory, order, shipment, return, refund e claim;
- review;
- ad campaign e ad metric;
- search keyword e ranking;
- competitor offer;
- metric, event, evidence, alert e recommendation.

`Product` e `Offer` são entidades diferentes. Um mesmo produto pode possuir várias ofertas no mesmo marketplace e em marketplaces diferentes.

## Dois planos de evidência

### Plano operacional

Dados da própria operação conectada: pedidos, vendas, estoque, Ads, reclamações, logística, recebimentos e estado da conta.

### Plano de mercado

Dados externos: concorrentes, preços, ranking, demanda, tendências, keywords, reviews, share, novos produtos e movimentos de categoria.

Os dois planos alimentam o mesmo núcleo, mas preservam origem, frescor, confiança e classe epistemológica.

## Proveniência e epistemologia

Toda observação que cruza um adapter deve preservar:

- marketplace;
- tipo e ID canônico da entidade;
- plano `operational` ou `market`;
- `fact`, `inference` ou `hypothesis`;
- fonte;
- timestamp de observação;
- hash do payload/evidência;
- confiança.

Nenhuma estimativa externa deve ser promovida silenciosamente a fato operacional.

## Capability Registry

Cada marketplace declara suas capacidades. Ausência de declaração significa `UNKNOWN` e falha fechada.

Exemplos:

- product_search;
- product_read;
- offer_read;
- price_read;
- inventory_read;
- order_read;
- fulfillment_read;
- review_read;
- ads_metrics_read;
- competitor_price_read;
- notifications;
- oauth.

Capacidades de escrita podem ser descritas, mas o projeto continua globalmente read-only. `write_price`, `write_inventory` e `write_ads` permanecem bloqueadas independentemente da declaração do adapter.

## Entity Resolution

Comparação cross-marketplace não pode depender de semelhança textual tratada como verdade.

Ordem V1:

1. mesmo marketplace + mesmo ID externo -> identidade exata;
2. GTIN/EAN/UPC igual -> evidência forte;
3. marca + MPN igual -> evidência forte;
4. GTIN/MPN conflitante -> conflito explícito;
5. somente similaridade de marca/modelo/texto -> `UNRESOLVED`.

Matching probabilístico futuro pode produzir inferência, nunca fato sem evidência forte.

## Skill Registry

Skill é competência, não autoridade.

Cada skill declara:

- função;
- marketplaces suportados;
- capabilities exigidas;
- origem/licença;
- estado de execução;
- plano de IA.

Skills proprietárias ou em quarentena não são executáveis. O lote Nexscope permanece referência de estudo até resolução/licenciamento e adaptação própria aprovada.

## Agentes operacionais

O runtime do produto possui uma equipe especializada separada dos agentes de engenharia do Codex.

Todos os agentes operacionais:

- são read-only;
- pedem capacidades lógicas, nunca nomes de modelos;
- usam exclusivamente `AI_ROLE=agents`;
- não podem escalar para `AI_ROLE=system`;
- não recebem autoridade direta sobre banco, cofre, GitHub ou marketplace;
- trabalham sobre dados previamente minimizados pelo AI Data Gateway.

## Duas IAs / dois planos de execução

```text
IA DO SISTEMA
  role = system
  fila = market-intelligence-ai-system-v1
  finalidade = orquestração/síntese/decisão soberana do sistema

IA DOS AGENTES
  role = agents
  fila = market-intelligence-ai-agents-v1
  finalidade = execução dos especialistas operacionais
```

As filas, limites e configurações de provedor são independentes. Nenhum agente escolhe OpenAI, GLM, Qwen, DeepSeek, Kimi ou outro fornecedor diretamente. O Provider Manager/Router resolve o provedor conforme política, benchmark, disponibilidade e custo.

A existência de adapter pago não autoriza gasto.

## Dependências permitidas

```text
adapter marketplace -> contratos centrais
agente -> skill registry / AI Data Gateway / fila agents
intelligence core -> canonical model / evidência
```

Dependência proibida:

```text
core/intelligence/skills/agents -> mercadolivre/amazon/shopee/tiktok/shein
```

O núcleo nunca importa um adapter concreto.

## Critério de aprovação

Este ADR só pode ser integrado quando:

1. modelo canônico possuir testes;
2. capability registry provar fail-closed;
3. escrita continuar bloqueada;
4. entity resolution provar match forte, conflito e unresolved;
5. skill proprietária/quarentena permanecer não executável;
6. todos os agentes operacionais usarem `AI_ROLE=agents`;
7. filas `system` e `agents` permanecerem distintas;
8. regressões existentes passarem;
9. CI principal ficar verde.

## Próximo passo depois do gate

O segundo marketplace só deve ser implementado como novo adapter depois desta fronteira estar integrada. Nenhuma duplicação do Intelligence Core por marketplace é permitida.
