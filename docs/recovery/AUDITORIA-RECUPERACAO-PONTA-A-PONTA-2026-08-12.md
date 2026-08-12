# AUDITORIA DE RECUPERAÇÃO PONTA A PONTA — MARKET INTELLIGENCE IA

**Data:** 12/08/2026  
**Escopo:** recuperação do patrimônio técnico do antigo API ML após ruptura de arquivos  
**Estado:** ANÁLISE AVANÇADA, CONSOLIDAÇÃO FINAL AINDA BLOQUEADA PELO PACOTE LOCAL NÃO ANEXADO

## 1. Evidência da recuperação local

Segunda coleta forense informada como concluída:

- projetos/conjuntos candidatos: **13**;
- arquivos inventariados: **5035**;
- arquivos seguros copiados: **2535**;
- candidatos sensíveis omitidos do pacote compartilhável: **67**;
- repositórios Git detectados: **3**;
- arquivos com hash único: **2681**;
- caminhos com conteúdo divergente: **21**;
- candidatos encontrados na Lixeira: **0**;
- nenhum upload automático;
- nenhum repositório local modificado.

Pacote local produzido:

`C:\Users\andre\Documents\Market-Intelligence-Recovery\20260812-132001-SAFE-TO-SHARE.zip`

## 2. Leitura técnica dos números

A população de 5035 arquivos foi reproduzida nas duas coletas. Isso aumenta a confiança de que a descoberta das árvores principais estabilizou.

Os 2681 hashes únicos mostram que mais da metade das instâncias inventariadas aparece apenas uma vez no universo comparado. Portanto, as 13 árvores não são simples clones equivalentes: existe patrimônio exclusivo que pode ser perdido se uma única pasta for escolhida por data ou nome.

Os 21 conflitos de caminho são críticos. Eles representam o mesmo caminho lógico com conteúdos SHA-256 diferentes em conjuntos distintos. Nenhum desses caminhos deve ser escolhido automaticamente por data de modificação.

Os 67 arquivos omitidos são um gate de segurança, não descarte. Precisam permanecer fora de qualquer repositório público até classificação individual e sanitização.

## 3. Baseline histórico aprovado

O último baseline Git aprovado conhecido do antigo projeto é:

`bf56b52633550ec1968dfe7b06dadfe5969ac4a2`

Mensagem:

`feat: add local OAuth runtime acceptance harness`

Este baseline corresponde à EXE-07K. O histórico aprovado anterior contém, entre outras etapas:

- SQLite fix;
- PostgreSQL storage;
- PKCE foundation;
- local OAuth transaction flow;
- encrypted PostgreSQL OAuth transactions;
- secure callback token exchange;
- encrypted token vault;
- atomic refresh rotation;
- credential health;
- controlled refresh batch executor;
- safe OAuth refresh operation control;
- runtime composition and simulation;
- local OAuth runtime acceptance harness.

## 4. Camada posterior não aprovada integralmente — EXE-07L

Após o baseline existia trabalho não consolidado de ativação/preflight OAuth, incluindo:

- migration `0008_oauth_activation_decisions_postgresql.sql`;
- `activation_cli.py`;
- `activation_models.py`;
- `activation_providers.py` em revisões posteriores;
- `activation_sanitizer.py`;
- `activation_service.py`;
- `activation_store.py`;
- `activation_store_postgresql.py`;
- `authorization_plan.py`;
- `preflight_fingerprint.py`;
- correções em `migration_manifest.py`;
- correções em `readiness.py`;
- testes de ativação e integração PostgreSQL;
- script PowerShell de preflight.

Essa camada evoluiu por várias revisões. Houve execuções com 229 testes aprovados + 10 skips e revisão posterior com 238 testes aprovados + 10 skips em duas passagens, além de whitespace e `git diff --check` limpos.

Mesmo assim, a validação permaneceu bloqueada em pontos funcionais, especialmente estrutura/integração PostgreSQL em determinadas revisões. Logo, EXE-07L é patrimônio candidato e não baseline automático.

## 5. Defeitos funcionais históricos que devem virar testes de regressão

Os relatórios de continuidade documentaram defeitos reais que não podem reaparecer na consolidação:

### ActivationService

- não pode ignorar `settings`, `database_probe`, `migration_provider` e `credential_health`;
- não pode ler configuração crítica diretamente de `os.getenv` fora do contrato;
- deve verificar banco, migrations, saúde de credencial, transação pendente, reautorização e decisão soberana;
- provider ausente/falho deve bloquear quando for requisito;
- validação de chaves deve ser estrita;
- fingerprint não pode usar valores fabricados.

### Fingerprint

Deve derivar de estado real sanitizado e reproduzível: ambiente, App ID mascarado, URI sanitizada, migrations reais, hashes reais, flags e baseline.

### Sanitização

Não pode persistir/exibir DATABASE_URL, senha, Client Secret, tokens, authorization code, verifier, state, chaves, nonce ou ciphertext.

### Authorization plan

Não pode conter IDs, URLs, riscos ou etapas artificiais usados apenas para satisfazer teste.

### PowerShell

`preflight`, `plan` e `status` precisam executar modos distintos de verdade.

### PostgreSQL activation store

Dados precisam ser sanitizados antes da persistência e combinações de tipo/status precisam ser validadas. Não criar aprovação automática.

## 6. Arquitetura: o que preservar e o que substituir

### Preservar e migrar seletivamente

- FastAPI e modularização útil;
- contratos/configuração;
- PostgreSQL e migrations corretas;
- OAuth Authorization Code + PKCE S256;
- state de uso único;
- tokens cifrados;
- rotação atômica de refresh;
- saúde de credencial;
- bloqueios de rede/escrita;
- sanitização;
- idempotência;
- testes existentes que expressem comportamento válido;
- trilha de auditoria;
- raw/snapshots quando adequadamente redigidos.

### Substituir/rearquitetar

- fila PostgreSQL artesanal como orquestração principal, pois a arquitetura atual prevê Temporal para workflows duráveis;
- dependência arquitetural ativa de Railway;
- documentação antiga que conflita com a arquitetura atual;
- componentes fictícios ou testes que validem literais em vez de comportamento;
- modelos de dados focados apenas em infraestrutura sem entidades de negócio suficientes.

### Não duplicar

O painel NocoBase permanece desacoplado em seu repositório próprio.

## 7. Radar — requisito novo que altera a consolidação

O Módulo 01 atual é:

**Radar de Perdas, Exceções e Anomalias — Detector de Desconhecidos**.

A consolidação deve preparar desde o primeiro evento real:

- histórico de snapshots;
- dados observados versus esperados;
- anomalia estatística;
- anomalia temporal;
- anomalia multivariada;
- mudança de regime;
- grupos de controle/contrafactuais;
- resíduo não explicado;
- fatos, inferências e hipóteses separados;
- telemetria sanitizada do canal Mercado Livre;
- alertas com evidência, impacto, confiança, ação, prazo, estado e resultado posterior.

Isso significa que a persistência antiga deve ser avaliada também por sua capacidade de sustentar séries históricas e causalidade operacional, não apenas OAuth/webhooks.

## 8. Ordem de precedência para resolver os 21 conflitos

Para cada caminho divergente, usar esta ordem:

1. contrato funcional atual aprovado;
2. teste de comportamento reproduzível;
3. integração real/sandbox quando aplicável;
4. baseline Git aprovado;
5. correção posterior comprovadamente superior;
6. compatibilidade com dependentes;
7. segurança e sanitização;
8. data de modificação apenas como evidência auxiliar.

Nunca usar somente "arquivo mais novo".

Classificações permitidas:

- `MANTER_BASELINE`;
- `MANTER_VARIANTE_POSTERIOR`;
- `MESCLAR`;
- `LEGADO_PRESERVADO`;
- `DESCARTAR_GERADO`;
- `BLOQUEADO_SEGREDO`;
- `INCONCLUSIVO`.

## 9. Fonte de verdade provisória

Até leitura do pacote forense, a fonte de verdade deve ser composta, e não uma pasta única:

`baseline bf56b526 + correções posteriores comprovadas + documentação soberana atual + componentes limpos pinados`.

Não promover uma das 13 árvores inteiras como "a correta" sem comparar seus manifests.

## 10. Gates obrigatórios antes da montagem definitiva

1. abrir o pacote `SAFE-TO-SHARE`;
2. ler `projects.csv` e mapear os 13 conjuntos;
3. ler `git-summary.csv` e identificar os 3 repositórios, HEADs, branches, stashes, deleted/untracked e objetos recuperáveis;
4. ler `path-conflicts.csv` e decidir os 21 conflitos individualmente;
5. ler `unique-hashes.csv` e identificar arquivos únicos relevantes de código, migration, teste e documentação;
6. revisar `sensitive-skipped.csv` apenas por nome/razão, sem publicar valores;
7. reconstruir árvore candidata em sandbox;
8. executar compile/lint/type/security/tests;
9. subir PostgreSQL de teste e executar migrations/integrações;
10. testar fluxo sintético ponta a ponta;
11. testar interrupção, retomada e idempotência;
12. produzir matriz requisito → código → teste → evidência;
13. somente então criar baseline consolidado.

## 11. Limitação atual desta auditoria

O pacote local `20260812-132001-SAFE-TO-SHARE.zip` ainda não está anexado ao ambiente desta conversa/File Library. Por isso, esta auditoria consegue fechar arquitetura, precedência, baseline histórico, defeitos conhecidos e estratégia de merge, mas **não pode nomear os 13 caminhos nem decidir os 21 conflitos individualmente**.

Declarar esses itens sem o CSV real seria inventar evidência.

## 12. Parecer

**RECUPERAÇÃO: APROVADA.**  
**PATRIMÔNIO: PRESERVADO COM BOA CONFIANÇA.**  
**CONSOLIDAÇÃO FINAL: BLOQUEADA SOMENTE PELA AUSÊNCIA DO PACOTE FORENSE NO AMBIENTE DE ANÁLISE.**  
**RECOMEÇAR DO ZERO: REJEITADO.**  
**ESCOLHER UMA PASTA POR DATA: REJEITADO.**  
**PROMOVER EXE-07L INTEGRALMENTE: REJEITADO.**  
**CAMINHO APROVADO: baseline histórico + merge seletivo + revalidação completa + arquitetura Market Intelligence IA atual.**
