# Market Intelligence AI

Núcleo do **Market Intelligence IA** — plataforma de inteligência de mercado orientada a evidências, inicialmente para Mercado Livre e preparada para múltiplos marketplaces.

## Estado atual

A base atual preserva capacidades e evidências válidas, com arquitetura orientada a múltiplos marketplaces, workflows duráveis, rastreabilidade e separação entre fatos, inferências e hipóteses.

Esta versão é **read-only, sem OAuth real, sem chamadas reais ao Mercado Livre e sem escrita externa**.

## Módulo 01

**Radar de Perdas, Exceções e Anomalias — Detector de Desconhecidos**.

O Radar deve evoluir de regras conhecidas para anomalias estatísticas, temporais, multivariadas, mudanças de regime, relações anormais, contrafactuais e resíduos não explicados, sempre separando fato, inferência e hipótese.

## Arquitetura

- FastAPI: API interna.
- PostgreSQL: estado operacional e histórico.
- Temporal: workflows duráveis.
- DuckDB + Polars: analytics.
- PyOD: camada de detecção de anomalias em evolução.
- Higress: gateway para painel/IA.
- NocoBase: painel desacoplado no repositório `andrebarros78/painel`.

Consulte `docs/architecture/BASE-V1.md` e `docs/radar/RADAR-FUNCOES-V1.md`.

## Segurança

- escrita em marketplace desabilitada por padrão;
- segredos não devem entrar em logs, telemetria ou evidências;
- código recuperado sensível não é importado automaticamente;
- conexão real só será liberada depois de sandbox/digital twin aprovados.
