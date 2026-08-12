# AUDITORIA DEFINITIVA DA RECUPERAÇÃO LOCAL — ZIP 2026-08-12

**Projeto:** Market Intelligence IA / antigo API ML  
**Data:** 12/08/2026  
**Artefato auditado:** `20260812-132001-SAFE-TO-SHARE.zip`  
**Estado:** AUDITORIA FÍSICA CONCLUÍDA; RECUPERAÇÃO DE OBJETOS GIT PENDENTE  
**Substitui como evidência do ZIP:** o relatório preliminar `AUDITORIA-RECUPERACAO-PONTA-A-PONTA-2026-08-12.md`

## 1. Parecer executivo

A recuperação física foi bem-sucedida e permite determinar a principal fonte local de código.

A conclusão central é:

> **Não existem 13 cópias equivalentes do API ML. A fonte física dominante é `C:\D-MIRROR\Projetos\API-ML`. O backup `API-ML-RECUPERACAO-BASE-20260729-1715` é uma referência histórica incompleta, e os demais candidatos são principalmente metadados de orquestrador, sessões ou falsos positivos do painel NocoBase.**

Também existe evidência documental e de índice Git de que uma parte avançada do OAuth existiu e desapareceu da árvore de trabalho. Foram identificados **47 caminhos marcados `AD` no índice histórico**, dos quais apenas **1** voltou a existir fisicamente. Portanto, **46 arquivos permanecem ausentes da árvore atual** e devem ser procurados nos objetos/reflogs do Git local antes de qualquer consolidação definitiva.

## 2. Resultado bruto da recuperação

A segunda coleta registrou:

- 13 candidatos;
- 5.035 arquivos inventariados;
- 2.535 arquivos texto copiados para o pacote seguro;
- 67 arquivos omitidos pelo filtro de possível segredo;
- 2.681 hashes únicos;
- 752 grupos de hashes duplicados;
- 21 caminhos com conteúdo divergente;
- 0 candidatos relevantes na Lixeira;
- nenhuma alteração nos repositórios;
- nenhum upload automático.

## 3. Reclassificação dos 13 candidatos

### 3.1 Fonte física principal

`01-API-ML`  
`C:\D-MIRROR\Projetos\API-ML`

- 4.795 dos 5.035 arquivos inventariados;
- 2.637 dos 2.681 hashes únicos;
- 2.387 arquivos incluídos na cópia segura;
- 65 arquivos omitidos como potencialmente sensíveis;
- contém código, testes, relatórios de recuperação, documentação e evidência histórica.

**Classificação:** FONTE FÍSICA PRINCIPAL.

### 3.2 Backup histórico real

`03-API-ML-RECUPERACAO-BASE-20260729-1715`  
`C:\D-MIRROR\Projetos\API-ML-RECUPERACAO-BASE-20260729-1715`

- 47 arquivos;
- 39 copiados com segurança;
- 4 hashes únicos;
- 2 arquivos omitidos pelo filtro sensível.

Esse backup não é autossuficiente: seu `main.py` referencia módulos OAuth que não existem dentro da própria cópia.

**Classificação:** REFERÊNCIA HISTÓRICA; NÃO É BASELINE EXECUTÁVEL.

### 3.3 Estado de recuperação

`04-API-ML-RECUPERACAO-ESTADO-20260729-1712`

Não apresentou conteúdo útil inventariado para competir como fonte de código.

**Classificação:** METADADO/ESTADO DE RECUPERAÇÃO.

### 3.4 Orquestradores

`02-api-ml` e `05-api-ml` pertencem às áreas `.orquestrador`. Os 22 hashes exclusivos encontrados em `05` são arquivos temporários `.tmp` de workers/orquestração, não código-fonte do API ML.

**Classificação:** EVIDÊNCIA OPERACIONAL; EXCLUIR DO RUNTIME CONSOLIDADO.

### 3.5 Sessões

Candidatos `07` a `12` são sessões do GCO/GPT-CODEX-ORQUESTRADOR e contêm principalmente `session.json`/eventos de sessão.

**Classificação:** HISTÓRICO DE ORQUESTRAÇÃO; NÃO SÃO CÓPIAS DO PROJETO.

### 3.6 Falsos positivos do painel

`06-plugin-block-timeline` e `13-timeline` pertencem ao NocoBase/painel e foram capturados por coincidência de termos do detector.

**Classificação:** FORA DO ESCOPO DO API ML.

## 4. Árvore lógica atual

Depois de retirar ambientes virtuais, caches, relatórios de recuperação, bancos de estado, arquivos gerados e outras evidências que não compõem o runtime, a árvore principal contém aproximadamente **77 arquivos lógicos de projeto**.

A base física atual inclui:

- FastAPI e `main.py`;
- receptor de notificações;
- SQLite e PostgreSQL para notificações;
- OAuth state/PKCE;
- AES-GCM;
- transações OAuth SQLite/PostgreSQL;
- credenciais/refresh em módulos cujo conteúdo foi parcialmente omitido do ZIP seguro;
- cliente Mercado Livre somente leitura;
- fila SQLite local;
- Radar operacional sintético;
- rotas internas somente leitura;
- PowerShell de instalação/teste/diagnóstico;
- testes unitários e de integração;
- migrations físicas atuais 0001 e migrations de recuperação/teste.

O `requirements.lock` existe fisicamente, com SHA-256 registrado no inventário, mas não foi copiado para o ZIP porque a extensão `.lock` não fazia parte da lista de texto do coletor.

## 5. Validação possível a partir do ZIP

A cópia segura da árvore principal foi submetida a compilação Python:

```text
python -m compileall -q src tests
```

Resultado do código Python copiado: **exit code 0**.

Isso comprova integridade sintática da parcela compartilhada, mas **não comprova runtime completo**, porque arquivos potencialmente sensíveis foram intencionalmente omitidos do ZIP seguro.

Consequentemente, não é válido declarar a suíte completa como reproduzida a partir deste pacote.

## 6. Estado real do Radar encontrado na árvore antiga

O Radar físico existente é um **scaffold operacional somente leitura**, não o novo Detector de Desconhecidos.

Ele contém:

- `ProbeSpec`;
- `RadarSnapshot`;
- persistência SQLite de snapshots/métricas;
- scheduler por janela temporal;
- worker que executa sondas autorizadas;
- retries de leitura;
- heartbeat e stop file;
- testes de idempotência, retry, persistência e bloqueio de métricas sensíveis.

A rota interna de capacidades registra `anomalias` como indisponível.

**Decisão:** preservar esse Radar antigo como patrimônio de ingestão/scheduling/testes, mas não tratá-lo como implementação do novo `Radar de Perdas, Exceções e Anomalias — Detector de Desconhecidos`.

O novo Radar continua exigindo:

- anomalia estatística;
- anomalia temporal;
- anomalia multivariada;
- mudança de regime;
- grupos de controle/contrafactual;
- modelo esperado x observado;
- resíduo não explicado;
- investigação progressiva;
- Sensor do Canal ML;
- separação FATO / INFERÊNCIA / HIPÓTESE.

## 7. Fila e notificações

A fila SQLite física possui boa cobertura local para:

- idempotência;
- persistência após reabertura;
- reserva concorrente;
- expiração de lease;
- retry;
- dead-letter;
- bloqueio de conclusão por worker incorreto;
- rejeição de payloads sensíveis.

Porém, ela não possui prova de fencing monotônico suficiente para promoção como motor durável de produção.

Além disso, a arquitetura histórica de webhook/InBox e job não comprova atomicidade única entre persistência do evento e criação do trabalho.

**Decisão:** preservar fila/testes como referência local, mas usar **Temporal** para workflows duráveis na arquitetura nova. PostgreSQL permanece como fonte operacional/histórica.

## 8. OAuth — patrimônio aproveitável

A árvore física atual contém melhorias importantes que devem ser preservadas/refatoradas:

- armazenamento do SHA-256 de `state`, em vez do valor bruto;
- uso único do state;
- TTL e validação temporal;
- PKCE;
- AES-GCM com nonce e AAD;
- store PostgreSQL de transação OAuth;
- proteção de banco de teste;
- fake client e guardas de rede/escrita.

Há relatórios históricos que comprovam testes PostgreSQL reais com dados sintéticos e concorrência, incluindo uma execução documentada com **44 testes aprovados, 0 falhas e 0 skips** na persistência OAuth cifrada.

Também existem relatórios de Loop Engineering com **67 testes aprovados e 9 skips**, sendo os skips associados ao PostgreSQL não configurado naquela execução.

Esses números são evidência histórica; não foram reproduzidos integralmente neste ZIP seguro.

## 9. Ruptura confirmada — 46 arquivos ainda ausentes

O relatório histórico `recovery-full-20260729-182427/git-status.txt` mostra 47 caminhos em estado `AD`: arquivos adicionados ao índice Git que estavam ausentes da árvore de trabalho.

Na árvore física atual apenas `tests/test_oauth_refresh.py` voltou a existir.

Os **46 caminhos ainda ausentes** são:

### Migrations

1. `db/migrations/0002_oauth_transactions_postgresql.sql`
2. `db/migrations/0003_meli_oauth_credentials_postgresql.sql`
3. `db/migrations/0004_meli_oauth_refresh_state_postgresql.sql`
4. `db/migrations/0005_meli_oauth_operational_indexes_postgresql.sql`
5. `db/migrations/0006_oauth_refresh_execution_audit_postgresql.sql`
6. `db/migrations/0007_oauth_operation_requests_postgresql.sql`

### Scripts

7. `scripts/Get-OAuthCredentialHealth.ps1`
8. `scripts/Invoke-OAuthRefreshBatch.ps1`
9. `scripts/Test-OAuthRuntimeAcceptance.ps1`

### Código OAuth

10. `src/api_ml/oauth/acceptance_cli.py`
11. `src/api_ml/oauth/acceptance_fixture.py`
12. `src/api_ml/oauth/audit_store.py`
13. `src/api_ml/oauth/factory.py`
14. `src/api_ml/oauth/health_service.py`
15. `src/api_ml/oauth/migration_manifest.py`
16. `src/api_ml/oauth/models_operation.py`
17. `src/api_ml/oauth/models_refresh.py`
18. `src/api_ml/oauth/operation_cli.py`
19. `src/api_ml/oauth/operation_service.py`
20. `src/api_ml/oauth/operation_store.py`
21. `src/api_ml/oauth/operation_store_postgresql.py`
22. `src/api_ml/oauth/readiness.py`
23. `src/api_ml/oauth/refresh_batch_executor.py`
24. `src/api_ml/oauth/refresh_service.py`
25. `src/api_ml/oauth/runtime_factory.py`
26. `src/api_ml/oauth/runtime_settings.py`
27. `src/api_ml/oauth/service.py`

### Testes

28. `tests/test_crypto_leak.py`
29. `tests/test_oauth_acceptance.py`
30. `tests/test_oauth_acceptance_postgresql_integration.py`
31. `tests/test_oauth_callback.py`
32. `tests/test_oauth_callback_postgresql_integration.py`
33. `tests/test_oauth_credentials.py`
34. `tests/test_oauth_credentials_postgresql_integration.py`
35. `tests/test_oauth_health.py`
36. `tests/test_oauth_health_postgresql_integration.py`
37. `tests/test_oauth_operation.py`
38. `tests/test_oauth_operation_postgresql_integration.py`
39. `tests/test_oauth_refresh_batch.py`
40. `tests/test_oauth_refresh_batch_postgresql_integration.py`
41. `tests/test_oauth_refresh_postgresql_integration.py`
42. `tests/test_oauth_runtime.py`
43. `tests/test_oauth_runtime_postgresql_integration.py`
44. `tests/test_oauth_security.py`
45. `tests/test_oauth_start.py`
46. `tests/test_postgres_oauth_store.py`

O índice histórico também preserva os SHA-1 Git dos blobs correspondentes. Isso permite testar diretamente se os objetos ainda existem no object database do repositório local.

## 10. Evolução posterior EXE-07L

O relatório `EXE-07L-R1-DIAGNOSTICO-FALHAS.txt` preserva evidência de uma evolução ainda posterior, baseada no histórico em que aparece:

`bf56b52633550ec1968dfe7b06dadfe5969ac4a2`

Também aparecem migration `0008` e módulos de ativação/preflight.

Essa evolução não está presente na árvore física atual.

O mesmo relatório documenta falhas reais, incluindo migration/tabela de activation não aplicada e placeholders ainda existentes. Portanto:

**EXE-07L deve ser recuperada como evidência/candidata, mas nunca promovida automaticamente por ser posterior.**

## 11. Resolução dos 21 conflitos físicos

Os conflitos relevantes são majoritariamente entre `01-API-ML` e `03-RECUPERACAO-BASE`.

### Manter versão atual da árvore principal

- `.gitignore`: versão atual é mais completa;
- `pyproject.toml`: versão atual possui gates e restrições mais maduras;
- `README.md`: versão atual representa melhor o estado de recuperação;
- `tests/test_notifications.py`: diferenças semânticas não justificam regressão;
- `tests/test_storage.py`: diferenças essencialmente de forma;
- `src/api_ml/main.py`: a base antiga referencia módulos ausentes e não é autossuficiente;
- `src/api_ml/oauth/security.py`: manter versão atual;
- `src/api_ml/oauth/transactions.py`: versão atual é materialmente superior por armazenar hash do state e endurecer TTL/tempo;
- `src/api_ml/mercadolivre/__init__.py`: versão atual exporta cliente/erros;
- `powershell/Iniciar-API-ML.ps1`: versão atual evita caminho absoluto rígido;
- `powershell/Instalar-API-ML.ps1`: versão atual usa ambiente/dependências mais controlados;
- `powershell/Testar-API-ML.ps1`: versão atual possui gates e evidências melhores;
- demais webhooks/storage com diferenças de formatação/comentários: manter atual.

### Preservar até revisão segura

- `src/api_ml/oauth/router.py`: duas variantes, ambas omitidas do ZIP seguro pelo filtro;
- `tests/test_postgres_oauth_store_integration.py`: variante atual e histórica devem ser comparadas diretamente em ambiente seguro.

### Fora do projeto

Conflitos de `session.json`, `events.jsonl` e README/timeline do painel são evidência de orquestrador/NocoBase, não disputa de fonte de verdade do API ML.

**Conclusão dos 21 conflitos:** nenhum conflito inspecionado justifica substituir a árvore principal pelo backup antigo como um todo.

## 12. Arquivos soltos ainda fora do pacote seguro

O inventário de arquivos soltos encontrou itens como:

- `C:\Users\andre\Desktop\API-ML-inspecao.txt`;
- `C:\Users\andre\Downloads\api-ml-margin.zip`;
- documentos e scripts auxiliares.

Eles não são necessários para definir a árvore física principal, mas o ZIP antigo `api-ml-margin.zip` e a inspeção do Desktop podem conter evidência histórica adicional. Devem ser preservados até o encerramento da recuperação.

## 13. Falha encontrada no próprio coletor Git

A segunda coleta informa três repositórios Git, mas os arquivos `head.txt`, `status.txt`, `fsck...` e o `git-summary.csv` não contêm resultados Git válidos.

Causa:

```powershell
function Invoke-GitLines {
    param([string]$Repo,[string[]]$Args)
    ...
    & git @Args
}
```

`$Args` é uma variável automática do PowerShell. O uso como parâmetro/splat fez o comando Git ser executado sem os argumentos esperados e a ajuda do Git foi gravada como saída.

Consequências:

- os valores de HEAD/branch da segunda coleta são inválidos;
- `stash_count=40`, `deleted_count=40`, `untracked_count=40` são falsos artefatos da tela de ajuda;
- o `fsck` dessa coleta não comprova existência/ausência de objetos.

**Correção:** foi criado `tools/Collect-Git-Recovery-Evidence.ps1`, usando o parâmetro explícito `$GitArguments` e focado somente na recuperação Git.

## 14. Próximo gate técnico

O coletor Git corrigido deve:

1. obter HEAD e branch reais;
2. capturar status, refs, tags, worktrees e stashes;
3. capturar reflogs;
4. executar `git fsck --full --unreachable --no-reflogs`;
5. capturar o índice atual;
6. testar os commits históricos `9927420...` e `bf56b526...`;
7. ler os `git-index.txt` históricos;
8. testar cada blob antigo com `git cat-file -e`;
9. exportar conteúdo textual recuperável somente após filtro de segredo forte;
10. nunca alterar o repositório.

## 15. Fonte de verdade provisória

Até a coleta Git corrigida:

```text
FONTE FÍSICA PRINCIPAL
C:\D-MIRROR\Projetos\API-ML

+

PATRIMÔNIO HISTÓRICO A RECUPERAR
objetos Git / reflogs / blobs antigos

+

ARQUITETURA NOVA
FastAPI + Temporal + PostgreSQL + DuckDB + Polars + Higress

+

RADAR SOBERANO NOVO
Detector de Desconhecidos
```

Não deve haver merge automático do backup de recuperação.

## 16. Segurança

O repositório `andrebarros78/market-intelligence-AI` permanece público durante esta auditoria.

Portanto:

- documentação sanitizada pode ser versionada;
- ferramentas de coleta sanitizadas podem ser versionadas;
- código proprietário recuperado do PC não deve ser enviado ainda;
- nenhum dos arquivos marcados como potencialmente sensíveis deve ser publicado;
- tornar o repositório privado é gate obrigatório antes da importação de fonte real.

## 17. Estado final

```text
COLETA FÍSICA                         APROVADA
13 CANDIDATOS                         RECLASSIFICADOS
FONTE FÍSICA PRINCIPAL               IDENTIFICADA
21 CONFLITOS                          TRIADOS
RADAR ANTIGO                          SCAFFOLD APROVEITÁVEL
NOVO DETECTOR DE DESCONHECIDOS       AINDA NÃO IMPLEMENTADO
RUPTURA DE OAUTH                      CONFIRMADA
46 ARQUIVOS HISTÓRICOS AUSENTES       CONFIRMADOS
CAPTURA GIT DA SEGUNDA COLETA         INVÁLIDA
COLETOR GIT CORRIGIDO                 CRIADO
FONTE DE VERDADE DEFINITIVA           AGUARDANDO RECUPERAÇÃO GIT
IMPORTAÇÃO DE CÓDIGO NO GITHUB        BLOQUEADA ENQUANTO REPO FOR PÚBLICO
```

**Parecer:** continuar a recuperação Git; não reconstruir do zero e não substituir a árvore atual pelo backup antigo.
