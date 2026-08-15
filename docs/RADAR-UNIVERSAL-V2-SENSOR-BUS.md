# RADAR UNIVERSAL V2 - SENSOR BUS E MEMORIA CONTINUA

Estado: implementacao operacional validada localmente em modo somente leitura.

## Identidade
O Radar permanece uma Unidade Soberana Universal. Processos de coleta sao executores internos substituiveis.

## Sensor Bus
Contrato universal para eventos de negocio, telemetria de canal, mudanca de schema, ausencia/silencio, sinais derivados e correlacoes entre marketplaces.

Regras: raw nao e fato permanente; hipotese/inferencia nao vira fato validado; payload com chave de segredo e rejeitado; correlacao cross-market so e elegivel a fato com identidade EXACT ou STRONG.

## Mercado Livre
Primeiro sensor profundo. Coleta continua somente leitura para identidade, anuncios ativos, detalhes, visitas, competicao de catalogo quando disponivel, pedidos recentes, perguntas e reclamacoes abertas. Dados pessoais e texto livre sao minimizados antes da persistencia.

O unico POST permitido fora da superficie de marketplace e refresh OAuth no endpoint de token quando necessario. Nao altera recurso de marketplace.

## Persistencia historica
Usa raw_events, channel_events, entities, snapshots e evidence existentes. Nenhuma migration adicional foi necessaria.

## Multimarketplace
Mercado Livre: CONNECTED_READ_ONLY.
Shopee: BLOCKED_EXTERNAL_AUTH ate existir credencial/autorizacao oficial e validacao atual do contrato de assinatura.
Amazon, TikTok Shop e SHEIN: arquitetura pronta para adapters read-only; conexao real exige credenciais proprias.

## Politica permanente
MI_READ_ONLY=true
MI_ALLOW_MARKETPLACE_WRITES=false
