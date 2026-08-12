# CHECKPOINT DE CONTINUIDADE — MARKET INTELLIGENCE IA

**Data:** 12/08/2026  
**Origem:** antigo projeto API ML  
**Estado:** recuperação e consolidação antes da montagem definitiva

## 1. Objetivo atual

Recuperar integralmente o patrimônio técnico existente no PC, identificar a fonte de verdade entre cópias históricas e montar o Market Intelligence IA no repositório `andrebarros78/market-intelligence-AI` sem perder código útil e sem publicar segredos.

## 2. Evidência de coleta já executada

Primeira coleta local concluída em `20260812-121745`:

- projetos/cópias candidatos: **13**;
- arquivos inventariados: **5035**;
- sinais de possível segredo: **153**;
- nenhum arquivo foi enviado automaticamente ao GitHub.

Pacote local informado:

`C:\Users\andre\Documents\Market-Intelligence-Collection\20260812-121745.zip`

## 3. Caminhos históricos prioritários

- `D:\Projetos\API-ML`
- `C:\Projetos\API-ML`
- `C:\New Projet\API-ML`
- `C:\D-MIRROR\Projetos\API-ML`
- equivalentes `market-intelligence-AI` nos mesmos locais, quando existirem.

A existência de cópias Mirror/backup deve ser tratada como evidência até a comparação por SHA-256 e Git terminar. Nenhuma cópia deve ser apagada antes da consolidação.

## 4. Ruptura de arquivos

Houve relato de ruptura de arquivos. A recuperação deve preservar o estado antes de qualquer correção destrutiva.

Proibido durante a coleta:

- `git reset --hard`;
- `git clean`;
- checkout/restore destrutivo;
- apagar cópias antigas;
- sobrescrever arquivos divergentes;
- publicar conteúdo não sanitizado.

Devem ser coletados:

- branch e HEAD;
- `git status`;
- branches, tags e worktrees;
- stashes;
- reflogs;
- commits e objetos inalcançáveis/dangling;
- arquivos deletados e untracked;
- hashes SHA-256;
- arquivos únicos por cópia;
- conflitos em caminhos iguais com conteúdos diferentes;
- candidatos na Lixeira;
- arquivos soltos/archives relacionados ao projeto.

## 5. Ferramentas de recuperação no repositório

- `tools/Collect-Local-MarketIntelligence.ps1`: inventário inicial somente leitura.
- `tools/Recover-Local-MarketIntelligence.ps1`: segunda coleta forense e cópia segura de código/texto, omitindo candidatos a segredo.

## 6. Arquitetura alvo atual

Núcleo imediato:

- Higress;
- Temporal Server + Temporal Python SDK;
- FastAPI;
- Pydantic;
- HTTPX;
- Authlib;
- SQLAlchemy;
- Alembic;
- cryptography;
- PostgreSQL;
- DuckDB;
- Polars.

Preparados/entrada posterior:

- PyOD;
- pgvector;
- StatsForecast;
- OpenTelemetry;
- Prometheus.

NocoBase permanece desacoplado no repositório/painel e não deve ser duplicado no núcleo.

## 7. Módulo 01 — definição atual

Nome funcional evoluído:

**Radar de Perdas, Exceções e Anomalias — Detector de Desconhecidos**

O Radar não deve depender somente de regras previamente escritas. Deve combinar:

- regras conhecidas;
- anomalia estatística;
- anomalia temporal;
- anomalia multivariada;
- mudança de regime;
- comparação entre entidades/controles;
- investigação de resíduo não explicado;
- telemetria do canal Mercado Livre.

A camada de canal deve registrar, de forma sanitizada, sinais como status HTTP, latência, retries, request IDs, headers operacionais permitidos, mudanças de schema, frequência das notificações, 429/Retry-After e respostas parciais. Nunca registrar Authorization Bearer, Client Secret, access token ou refresh token em texto aberto.

O Radar deve separar sempre:

1. **fato observado**;
2. **inferência suportada pelos dados**;
3. **hipótese ainda não confirmada**.

## 8. Regra de segurança

O repositório estava público durante esta fase. Código real coletado do PC não deve ser enviado ao repositório antes de sanitização e revisão dos sinais de segredo.

OAuth real, callback público, credenciais reais e escrita no Mercado Livre continuam fora desta etapa de recuperação.

## 9. Próximo gate

Executar a recuperação forense local, receber/analisar o pacote seguro, comparar as 13 cópias e definir:

- baseline recuperável;
- arquivos exclusivos a preservar;
- divergências que exigem merge;
- código obsoleto;
- segredos que devem permanecer fora do Git;
- patrimônio que será migrado para a nova arquitetura.

Somente depois iniciar a montagem definitiva da aplicação.
