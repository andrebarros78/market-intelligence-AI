# AUDITORIA GIT V2 — RECUPERAÇÃO DEFINITIVA DO API ML

**Projeto:** Market Intelligence IA / antigo API ML  
**Data:** 12/08/2026  
**Artefato analisado:** `20260812-154824-SAFE-TO-SHARE.zip`  
**Estado:** AUDITORIA GIT V2 CONCLUÍDA; CAMADA AVANÇADA PERDIDA NÃO RECUPERADA PELO GIT LOCAL

## 1. Parecer executivo

A coleta Git V2 confirmou a ruptura das referências Git e permitiu separar, com precisão, o que ainda existe do que foi perdido.

Conclusão central:

> O banco Git local atual não contém mais o histórico de commits que sustentava as fases avançadas do OAuth. Os 72 registros de objetos encontrados pelo coletor são duplicados por duas cópias idênticas do mesmo índice histórico e correspondem, na prática, a 36 caminhos históricos recuperáveis. Nenhum dos 46 arquivos avançados realmente ausentes possui seu blob antigo recuperável no Git atual.

Portanto:

- o Git local não consegue restaurar automaticamente a camada avançada perdida;
- a árvore física atual continua sendo a principal fonte de verdade operacional;
- a documentação, relatórios de testes e especificações históricas devem ser usados para reconstruir seletivamente as funções perdidas;
- não deve ser feito reset, checkout, clean, gc ou prune no repositório atual antes de preservar os objetos restantes.

## 2. Correção dos números da coleta V2

O console informou:

- `RAIZES=3`;
- `REPOS_GIT_VALIDOS=3`;
- `HEAD_VALIDOS=0`;
- `OBJETOS_HISTORICOS_ENCONTRADOS=72`;
- `OBJETOS_HISTORICOS_AUSENTES=122`;
- `OBJETOS_BLOQUEADOS_SEGREDO=4`.

A auditoria do conteúdo mostra que dois desses números precisam ser reinterpretados.

### 2.1 Somente um repositório é Git operacional

`C:\D-MIRROR\Projetos\API-ML` responde a comandos Git e possui índice.

Os diretórios:

- `API-ML-RECUPERACAO-BASE-20260729-1715`;
- `API-ML-RECUPERACAO-ESTADO-20260729-1712`;

possuem marcador `.git`, porém o próprio `git.exe` responde:

`fatal: not a git repository (or any of the parent directories): .git`

Logo, `REPOS_GIT_VALIDOS=3` significa apenas que três caminhos tinham marcador `.git`; não significa três repositórios funcionais.

**Resultado efetivo: 1 repositório Git operacional e 2 marcadores Git inválidos/incompletos.**

### 2.2 Os 72/122 objetos foram contados duas vezes

O repositório principal contém duas cópias do mesmo relatório histórico `git-index.txt`:

- uma em `.recovery\pre-loop-...\reports\recovery-full-...`;
- outra em `reports\recovery-full-...`.

Cada índice contém os mesmos 97 caminhos.

Por isso:

- 72 encontrados = 36 caminhos encontrados x 2;
- 122 ausentes = 61 caminhos ausentes x 2.

Contagem deduplicada:

- **97 caminhos históricos únicos**;
- **36 caminhos com objeto histórico ainda presente**;
- **61 versões históricas cujo blob antigo não existe mais**;
- **31 blobs históricos únicos presentes** entre esses 36 caminhos, porque alguns caminhos compartilham o mesmo blob vazio/conteúdo.

## 3. Estado real do repositório principal

O repositório `C:\D-MIRROR\Projetos\API-ML` apresenta:

- branch nominal: `main`;
- `HEAD`: inválido;
- `git status`: `No commits yet on main`;
- refs: nenhuma;
- branches referenciadas: nenhuma;
- reflog: vazio;
- log: vazio;
- remote: nenhum registrado no pacote;
- commits históricos conhecidos `9927420...` e `bf56b526...`: ausentes do banco Git atual.

Isso significa que o repositório foi reinicializado ou teve sua base de objetos/referências substituída de forma equivalente. Não existe caminho normal de `git checkout <commit>` ou `git reset <commit>` para os commits históricos porque esses commits não estão mais presentes.

## 4. O que o índice atual ainda preserva

Apesar de não existir commit, o índice Git atual ainda possui 69 entradas staged.

O status registra:

- 33 arquivos `A` — staged e iguais à árvore de trabalho;
- 35 arquivos `AM` — staged, mas modificados posteriormente na árvore de trabalho;
- 1 arquivo `AD` — staged, mas removido da árvore (`requirements.txt`);
- 12 arquivos `??` — não rastreados pelo índice atual.

Os 12 não rastreados incluem patrimônio posterior relevante, como:

- `src/api_ml/oauth/refresh.py`;
- `src/api_ml/radar/service.py`;
- `tests/test_oauth_refresh.py`;
- `tests/test_postgres_oauth_refresh_integration.py`;
- `tests/test_radar_loop.py`;
- `tests/test_runtime_policy.py`;
- scripts de PostgreSQL de teste e política de dependências.

Portanto, o **worktree físico é mais avançado que o índice staged** e deve prevalecer sobre o índice quando o conteúdo posterior for validado por testes e coerência funcional.

## 5. Reconciliação dos 97 caminhos históricos

A comparação entre o índice histórico, o índice atual e a árvore física produz quatro grupos.

### 5.1 36 caminhos cujo objeto histórico ainda existe

Esses 36 são principalmente a fundação inicial:

- documentos de arquitetura;
- `.gitignore`;
- `pyproject.toml`;
- migration `0001`;
- parte do webhook;
- `oauth/security.py`;
- arquivos `__init__.py`;
- testes básicos.

Desses 36:

- 23 permanecem staged e fisicamente iguais à versão histórica;
- 11 mantêm o blob histórico no índice, mas a árvore de trabalho possui versão posterior modificada;
- `src/api_ml/mercadolivre/__init__.py` possui uma versão staged diferente da versão histórica;
- `requirements.txt` tem versão histórica recuperável, mas está removido da árvore de trabalho e o índice aponta para outra versão.

Esses objetos são úteis como evidência, porém não representam a camada avançada perdida.

### 5.2 15 versões históricas perderam o blob, mas o caminho ainda existe hoje

Os seguintes caminhos continuam existindo em versão posterior/diferente:

- `README.md`;
- `powershell/Instalar-API-ML.ps1`;
- `powershell/Testar-API-ML.ps1`;
- `src/api_ml/main.py`;
- `src/api_ml/oauth/credentials.py`;
- `src/api_ml/oauth/credentials_postgresql.py`;
- `src/api_ml/oauth/crypto.py`;
- `src/api_ml/oauth/fake_client.py`;
- `src/api_ml/oauth/network_guard.py`;
- `src/api_ml/oauth/router.py`;
- `src/api_ml/oauth/token_exchange.py`;
- `src/api_ml/oauth/transactions.py`;
- `src/api_ml/oauth/transactions_postgresql.py`;
- `tests/test_postgres_oauth_store_integration.py`;
- `tests/test_oauth_refresh.py`.

A perda aqui é da versão histórica exata, não necessariamente da função atual.

### 5.3 46 arquivos estão realmente ausentes

Foram confirmados **46 caminhos que estavam staged no índice histórico com status `AD`, não existem hoje na árvore física, não aparecem no índice atual e cujo blob histórico também não existe mais no Git atual**.

Distribuição:

- 6 migrations PostgreSQL;
- 3 scripts PowerShell;
- 18 módulos Python OAuth;
- 19 arquivos de teste.

#### Migrations ausentes

1. `db/migrations/0002_oauth_transactions_postgresql.sql`
2. `db/migrations/0003_meli_oauth_credentials_postgresql.sql`
3. `db/migrations/0004_meli_oauth_refresh_state_postgresql.sql`
4. `db/migrations/0005_meli_oauth_operational_indexes_postgresql.sql`
5. `db/migrations/0006_oauth_refresh_execution_audit_postgresql.sql`
6. `db/migrations/0007_oauth_operation_requests_postgresql.sql`

#### Scripts ausentes

1. `scripts/Get-OAuthCredentialHealth.ps1`
2. `scripts/Invoke-OAuthRefreshBatch.ps1`
3. `scripts/Test-OAuthRuntimeAcceptance.ps1`

#### Módulos OAuth ausentes

1. `src/api_ml/oauth/acceptance_cli.py`
2. `src/api_ml/oauth/acceptance_fixture.py`
3. `src/api_ml/oauth/audit_store.py`
4. `src/api_ml/oauth/factory.py`
5. `src/api_ml/oauth/health_service.py`
6. `src/api_ml/oauth/migration_manifest.py`
7. `src/api_ml/oauth/models_operation.py`
8. `src/api_ml/oauth/models_refresh.py`
9. `src/api_ml/oauth/operation_cli.py`
10. `src/api_ml/oauth/operation_service.py`
11. `src/api_ml/oauth/operation_store.py`
12. `src/api_ml/oauth/operation_store_postgresql.py`
13. `src/api_ml/oauth/readiness.py`
14. `src/api_ml/oauth/refresh_batch_executor.py`
15. `src/api_ml/oauth/refresh_service.py`
16. `src/api_ml/oauth/runtime_factory.py`
17. `src/api_ml/oauth/runtime_settings.py`
18. `src/api_ml/oauth/service.py`

#### Testes ausentes

1. `tests/test_crypto_leak.py`
2. `tests/test_oauth_acceptance.py`
3. `tests/test_oauth_acceptance_postgresql_integration.py`
4. `tests/test_oauth_callback.py`
5. `tests/test_oauth_callback_postgresql_integration.py`
6. `tests/test_oauth_credentials.py`
7. `tests/test_oauth_credentials_postgresql_integration.py`
8. `tests/test_oauth_health.py`
9. `tests/test_oauth_health_postgresql_integration.py`
10. `tests/test_oauth_operation.py`
11. `tests/test_oauth_operation_postgresql_integration.py`
12. `tests/test_oauth_refresh_batch.py`
13. `tests/test_oauth_refresh_batch_postgresql_integration.py`
14. `tests/test_oauth_refresh_postgresql_integration.py`
15. `tests/test_oauth_runtime.py`
16. `tests/test_oauth_runtime_postgresql_integration.py`
17. `tests/test_oauth_security.py`
18. `tests/test_oauth_start.py`
19. `tests/test_postgres_oauth_store.py`

`tests/test_oauth_refresh.py` também estava `AD` no índice histórico, mas foi posteriormente reconstruído e hoje existe como arquivo não rastreado; por isso não integra os 46 realmente ausentes.

## 6. Os 72 registros encontrados não recuperam os 46 ausentes

Este é o achado mais importante da V2.

Nenhum dos 46 caminhos realmente ausentes possui `object_exists=True` no banco Git atual.

Os objetos recuperados pertencem à fundação antiga e a arquivos que, em grande parte, já existem fisicamente hoje.

Logo:

> **A recuperação automática da camada avançada pelo banco Git local está encerrada sem sucesso para esses 46 arquivos.**

Isso não significa que a funcionalidade esteja irrecuperável: os relatórios históricos preservam nomes, contratos, sequência de migrations, testes executados, falhas encontradas e comportamento esperado. A reconstrução deverá usar essas evidências, mas será uma reconstrução técnica, não um simples `git restore`.

## 7. Objetos dangling restantes

`git fsck` encontrou quatro blobs dangling:

- `37b1287a4851f749cf165a57b6cfc3dcdf88d2c6`
- `3b16fd641eec1e0cf26ad3dc85d19b774de1939a`
- `9d43dbcb603cc7c70311253643476cfa7797b38a`
- `a01a0e40dc76690a98268de6aa70ee5d56abf78e`

Um deles foi identificado:

- `3b16fd...` = versão histórica de `requirements.txt`.

Os outros três blobs não foram exportados no pacote V2 e continuam sem caminho lógico identificado. Eles devem ser preservados e inspecionados antes de qualquer `git gc` ou `git prune`, porque podem representar versões intermediárias úteis.

## 8. Filtro de segurança

O coletor relatou 4 objetos bloqueados, porém são duas referências duplicadas a apenas dois caminhos históricos:

- `tests/test_postgres_store.py`;
- `tests/test_storage.py`.

O filtro foi deliberadamente conservador e não exportou o conteúdo. Nenhum valor secreto deve ser copiado para documentação ou para o repositório público.

## 9. Verificação independente do pacote sanitizado

A parcela Python efetivamente presente no pacote seguro foi materializada em ambiente isolado.

Resultados:

- `python -m compileall -q src tests` → **aprovado / exit code 0**;
- `pytest tests/test_job_queue.py tests/test_runtime_policy.py` → **9 passed**.

A suíte completa não pôde ser reproduzida a partir do ZIP sanitizado porque o pacote omite deliberadamente arquivos marcados como sensíveis, incluindo `src/api_ml/mercadolivre/client.py`, `oauth/router.py`, stores/credentials e alguns testes. O ambiente isolado também não possui todas as dependências do projeto, como `psycopg`.

Portanto, falhas de coleta/importação nesse pacote não devem ser confundidas com defeito comprovado da árvore física original.

## 10. Estado do Radar recuperado

O Radar físico atual é aproveitável como fundação operacional e contém:

- `SQLiteRadarStore`;
- snapshots idempotentes;
- validação de métricas sensíveis;
- scheduler por janela;
- fila SQLite;
- worker com retry seguro;
- `RadarLoop` persistente;
- heartbeat e parada controlada;
- testes de loop e idempotência.

Contudo, essa implementação ainda é o Radar operacional inicial. Ela não implementa o contrato soberano atual do `Radar de Perdas, Exceções e Anomalias — Detector de Desconhecidos`, que exige anomalia estatística/temporal/multivariada, mudança de regime, comparação contrafactual, resíduo não explicado, Sensor do Canal ML e separação FATO/INFERÊNCIA/HIPÓTESE.

## 11. Decisão de fonte de verdade

A hierarquia de confiança para reconstrução passa a ser:

1. **árvore física atual `C:\D-MIRROR\Projetos\API-ML`**, preservada sem modificação;
2. worktree atual posterior ao índice staged, desde que validado por testes;
3. índice Git atual como fotografia intermediária de 69 arquivos;
4. 36 objetos históricos ainda existentes como referência de fundação;
5. relatórios de testes/auditorias que documentam as fases avançadas perdidas;
6. backup `API-ML-RECUPERACAO-BASE-20260729-1715` apenas como comparação histórica;
7. nunca promover automaticamente a versão mais antiga ou mais recente apenas por data.

O commit histórico `bf56b526...` continua sendo uma âncora documental importante porque os relatórios registram que ele existiu e foi usado como baseline, mas **o objeto commit não existe mais no Git local atual**. Portanto ele não pode ser usado diretamente para checkout/restauração.

## 12. Estratégia de reconstrução

### Preservar imediatamente

- árvore física atual;
- índice Git atual;
- quatro dangling blobs;
- dois ZIPs de recuperação;
- relatórios históricos;
- documentação atual do Radar.

### Reconstruir, não restaurar cegamente

As funções correspondentes aos 46 arquivos ausentes devem ser redesenhadas sobre a arquitetura atual, aproveitando contratos e testes históricos, sem recriar defeitos já conhecidos.

Particularmente:

- migrations devem ser consolidadas com Alembic/PostgreSQL atual;
- runtime/workflow OAuth deve ser reconstruído com contratos explícitos e testes;
- filas/jobs antigos não devem ser promovidos como arquitetura definitiva onde Temporal será o orquestrador durável;
- readiness, health e auditoria devem ser reconstruídos com semântica correta;
- testes antigos devem ser reescritos ou reaproveitados como regressão comportamental.

## 13. Próximo gate técnico

Antes de montar a aplicação definitiva:

1. inspecionar os três blobs dangling ainda desconhecidos;
2. preservar snapshot completo da árvore física atual;
3. criar uma matriz `função histórica perdida → evidência disponível → substituto atual → teste de aceitação`;
4. reconstruir primeiro a camada PostgreSQL/OAuth mínima e reproduzível;
5. somente depois integrar Temporal, Higress e o Radar novo;
6. não importar código sensível para o GitHub enquanto o repositório estiver público.

## 14. Estado final

- recuperação física: **APROVADA**;
- Git histórico completo: **PERDIDO / NÃO RECUPERÁVEL PELO BANCO ATUAL**;
- Git operacional atual: **1 repositório sem commits, com índice útil**;
- objetos históricos úteis: **36 caminhos deduplicados / 31 blobs únicos**;
- versões históricas sem blob: **61**;
- arquivos realmente ausentes: **46**;
- arquivos avançados restaurados automaticamente: **0 dos 46**;
- Radar operacional antigo: **RECUPERÁVEL E APROVEITÁVEL**;
- Radar Detector de Desconhecidos: **ESPECIFICADO, AINDA NÃO IMPLEMENTADO**;
- base definitiva: **AINDA NÃO HOMOLOGADA**;
- próxima ação: **preservar dangling blobs e iniciar reconstrução seletiva baseada em evidência**.
