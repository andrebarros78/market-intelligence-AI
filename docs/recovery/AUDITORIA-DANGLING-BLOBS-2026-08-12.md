# AUDITORIA FINAL DOS DANGLING BLOBS — API ML

**Projeto:** Market Intelligence IA / antigo API ML  
**Data:** 12/08/2026  
**Artefato analisado:** `20260812-163415-SAFE-TO-SHARE.zip`  
**Estado:** RECUPERAÇÃO FÍSICA DO GIT ENCERRADA

## 1. Objetivo

Analisar os três blobs dangling ainda não identificados no Git local, verificar se algum deles correspondia aos 46 arquivos avançados desaparecidos e decidir se havia justificativa técnica para continuar a recuperação física.

## 2. Resultado

Os três objetos foram exportados com sucesso e nenhum apresentou segredo forte no filtro de segurança.

### 2.1 `37b1287a4851f749cf165a57b6cfc3dcdf88d2c6`

Conteúdo identificado: **versão histórica de `src/api_ml/oauth/router.py`**.

Características observadas:

- define `/meli/oauth/authorization/start`;
- cria transação OAuth com `state` e PKCE;
- mantém troca de token bloqueada por padrão;
- permite somente cliente com `network_mode=synthetic`;
- consome `state` uma única vez;
- efetua troca sintética de código;
- salva credencial OAuth;
- evita refletir `code` e `state` nas mensagens de erro.

O caminho `src/api_ml/oauth/router.py` **não faz parte dos 46 arquivos realmente ausentes**. A árvore física atual contém uma versão diferente desse arquivo. No inventário da recuperação atual, o arquivo físico possui tamanho/hash distintos do blob dangling.

Decisão: **PRESERVAR COMO DOADOR HISTÓRICO / NÃO SUBSTITUIR AUTOMATICAMENTE A VERSÃO ATUAL**.

### 2.2 `9d43dbcb603cc7c70311253643476cfa7797b38a`

Conteúdo identificado: **versão histórica de `src/api_ml/jobs/sqlite_queue.py`** (`SQLiteJobQueue`).

Foi comparada diretamente com a versão sobrevivente presente no pacote seguro anterior.

A versão física atual é superior em pontos objetivos:

- substitui `assert` por erros explícitos quando um job inserido/reservado não pode ser relido;
- melhora o tratamento de `Callable` para Python moderno;
- corrige codificação/documentação;
- melhora a verificação de campos sensíveis terminados em `_token` e `_secret`;
- mantém o mesmo modelo funcional de fila persistente, lease, retry e dead-letter.

Decisão: **DESCARTAR COMO CÓDIGO ATIVO; PRESERVAR SOMENTE COMO EVIDÊNCIA HISTÓRICA**.

Observação arquitetural: a nova arquitetura do Market Intelligence IA utilizará Temporal para workflows duráveis. Portanto, mesmo a versão física atual da fila SQLite será tratada como doadora/teste local e não como orquestrador principal de produção.

### 2.3 `a01a0e40dc76690a98268de6aa70ee5d56abf78e`

Conteúdo identificado: **snapshot de dependências Python (`requirements.txt`)**, incluindo FastAPI, HTTPX, psycopg, cryptography, pytest, uvicorn e demais dependências do ambiente.

Decisão: **PRESERVAR COMO REGISTRO DE AMBIENTE; NÃO USAR COMO FONTE DE VERDADE DE DEPENDÊNCIAS**.

A nova base deve usar dependências fixadas e aprovadas no manifesto de componentes atual do Market Intelligence IA.

## 3. Cruzamento com os 46 arquivos desaparecidos

Resultado: **0 dos 3 blobs corresponde a qualquer um dos 46 arquivos avançados realmente ausentes**.

Logo:

- 46 arquivos avançados permanecem sem blob histórico recuperável no Git local;
- nenhum dangling blob restante restaura migrations 0002–0007, serviços OAuth avançados, runtime/readiness perdido ou seus testes;
- a possibilidade razoável de restauração automática pelo Git local foi esgotada.

## 4. Encerramento da recuperação física

A partir desta auditoria, a estratégia oficial é:

1. encerrar tentativas de ressuscitar o Git antigo;
2. preservar a árvore sobrevivente `C:\D-MIRROR\Projetos\API-ML` como principal doadora física;
3. preservar os relatórios históricos, testes, contratos e auditorias como especificações de comportamento;
4. tratar os 46 arquivos perdidos como **capacidades a reconstruir**, e não como arquivos a reproduzir byte por byte;
5. reconstruir essas capacidades na arquitetura nova e corrigida do Market Intelligence IA;
6. usar Temporal para workflows duráveis, PostgreSQL para estado persistente, DuckDB/Polars para analytics, Higress para gateway e o Radar de Perdas, Exceções e Anomalias como requisito soberano do Módulo 01;
7. não publicar código recuperado no repositório enquanto ele estiver público sem revisão/sanitização e autorização de mudança de visibilidade.

## 5. Decisão técnica final

**RECUPERAÇÃO FÍSICA DO GIT: ENCERRADA.**

**RECONSTRUÇÃO SELETIVA NA ARQUITETURA NOVA: RECOMENDADA E LIBERADA COMO PRÓXIMA FASE TÉCNICA, respeitando o gate de segurança do repositório público antes de importar código proprietário.**
