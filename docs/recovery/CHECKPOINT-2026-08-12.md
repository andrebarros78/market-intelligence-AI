# CHECKPOINT DE CONTINUIDADE — MARKET INTELLIGENCE IA

**Data:** 12/08/2026  
**Origem:** antigo projeto API ML  
**Estado:** recuperação e consolidação antes da montagem definitiva

## 1. Objetivo atual

Recuperar integralmente o patrimônio técnico existente no PC, identificar a fonte de verdade entre cópias históricas e montar o Market Intelligence IA no repositório `andrebarros78/market-intelligence-AI` sem perder código útil e sem publicar segredos.

## 2. Evidências de coleta executadas

### 2.1 Primeira coleta — inventário

Concluída em `20260812-121745`:

- projetos/cópias candidatos: **13**;
- arquivos inventariados: **5035**;
- sinais de possível segredo: **153**;
- nenhum arquivo foi enviado automaticamente ao GitHub.

Pacote local informado:

`C:\Users\andre\Documents\Market-Intelligence-Collection\20260812-121745.zip`

### 2.2 Segunda coleta — recuperação forense e cópia segura

Concluída em `20260812-132001`:

- projetos/cópias candidatos: **13**;
- arquivos inventariados: **5035**;
- arquivos de código/texto copiados para pacote seguro: **2535**;
- arquivos omitidos do pacote seguro por risco de sensibilidade: **67**;
- repositórios Git encontrados: **3**;
- hashes únicos: **2681**;
- caminhos com conteúdos divergentes: **21**;
- candidatos relacionados ao projeto encontrados na Lixeira: **0**;
- nenhum upload foi realizado;
- nenhum repositório local foi modificado.

Relatório local:

`C:\Users\andre\Documents\Market-Intelligence-Recovery\20260812-132001`

Pacote seguro para análise:

`C:\Users\andre\Documents\Market-Intelligence-Recovery\20260812-132001-SAFE-TO-SHARE.zip`

### 2.3 Interpretação técnica

A segunda coleta confirmou a mesma população de 13 candidatos e 5035 arquivos da primeira coleta, aumentando a confiança de que a descoberta de caminhos está estável.

Os **2681 hashes únicos** demonstram que há patrimônio não redundante entre as cópias. Os **21 conflitos de caminho** demonstram que existem arquivos com o mesmo caminho relativo, porém conteúdos diferentes. Portanto, nenhuma cópia pode ser promovida automaticamente como fonte de verdade apenas por data, nome de pasta ou localização.

A definição da fonte de verdade deverá usar, em conjunto:

- conteúdo real;
- SHA-256;
- histórico Git;
- HEAD/branch/tags/reflog/stash;
- testes e evidências existentes;
- coerência com a arquitetura aprovada;
- completude funcional;
- segurança e ausência de segredos.

Os **67 omitidos sensíveis** são apenas arquivos que o segundo coletor decidiu não copiar para o pacote compartilhável. Esse número não deve ser comparado diretamente com os 153 sinais da primeira coleta como se fossem a mesma métrica, pois os detectores têm finalidades diferentes.

## 3. Caminhos históricos prioritários

- `D:\Projetos\API-ML`
- `C:\Projetos\API-ML`
- `C:\New Projet\API-ML`
- `C:\D-MIRROR\Projetos\API-ML`
- equivalentes `market-intelligence-AI` nos mesmos locais, quando existirem.

A existência de cópias Mirror/backup deve ser tratada como evidência até a comparação por SHA-256 e Git terminar. Nenhuma cópia deve ser apagada antes da consolidação.

## 4. Ruptura de arquivos

Houve relato de ruptura de arquivos. A recuperação deve preservar o estado antes de qualquer correção destrutiva.

Proibido durante a coleta e consolidação:

- `git reset --hard`;
- `git clean`;
- checkout/restore destrutivo;
- apagar cópias antigas;
- sobrescrever arquivos divergentes sem comparação;
- publicar conteúdo não sanitizado.

Devem ser preservados e comparados:

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

Especificação soberana registrada em:

`docs/radar/RADAR-FUNCOES-V1.md`

Commit de criação da especificação: `d0493bb2a8a2080b8baf30dd4aa69a8c3e4e347a`.

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

Analisar o pacote seguro `20260812-132001-SAFE-TO-SHARE.zip` e produzir uma comparação determinística entre os 13 candidatos:

1. identificar os 13 caminhos reais;
2. analisar os 3 repositórios Git e seus históricos recuperáveis;
3. classificar os 2681 hashes únicos;
4. resolver tecnicamente os 21 conflitos de caminho;
5. identificar código exclusivo, obsoleto e duplicado;
6. revisar os 67 itens omitidos apenas por metadados, sem expor valores secretos;
7. definir baseline recuperável;
8. definir arquivos que exigem merge;
9. definir patrimônio que será migrado para a arquitetura nova;
10. somente depois iniciar a montagem definitiva da aplicação.
