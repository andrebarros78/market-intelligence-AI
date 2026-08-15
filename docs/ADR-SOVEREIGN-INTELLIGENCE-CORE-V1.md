# ADR — Núcleo Soberano de Inteligência e Contrainteligência de Mercado V1

## Estado
Aceito para implementação.

## Decisão
O Núcleo Soberano é a unidade cognitiva central do Market Intelligence AI. O Radar Universal Soberano permanece ativo e passa a ser formalmente um subsistema sensorial/vigilante do Núcleo.

O Núcleo é universal e não depende de um marketplace ou de uma LLM específica.

## Órgãos
1. **Sondador** — procura superfícies, lacunas e novas perguntas.
2. **Radar Universal Soberano** — observa continuamente.
3. **Correlator** — liga sinais por entidade, tempo e dimensões observáveis.
4. **Instigador** — transforma sinais e correlações em hipóteses falsificáveis.
5. **Investigador** — usa o mecanismo de investigação progressiva existente.
6. **Experimentador** — desenha experimentos; mudanças externas nunca executam dentro do Núcleo.
7. **Inteligência** — converte evidência em significado, ameaça, oportunidade e necessidade de desenvolvimento.
8. **Contrainteligência** — contesta conclusões e mantém o mapa do que a operação revela à plataforma.
9. **Validador Soberano** — controla progressão epistemológica.
10. **MCL-P+** — aprendizagem contínua soberana já existente; somente evidência guardada pode ser promovida.
11. **Preditor** — produz previsões falsificáveis e novos indicadores a sondar.
12. **Auditor Cognitivo** — detecta sobreconfiança, contradição e autoridade indevida.
13. **Motor de Decisão** — emite `ActionIntent`; não possui transporte de escrita de marketplace.

## Progressão de conhecimento
`HYPOTHESIS -> OBSERVED -> CORRELATED -> TESTED -> VALIDATED`

Saídas também podem ser `REJECTED` ou `QUARANTINED`.

Uma alegação causal sem controle e replicação independente não pode ser promovida a verdade causal.

## Fronteira de autoridade
O Núcleo:
- pode observar, correlacionar, investigar, aprender, prever e recomendar;
- pode automatizar apenas processamento interno determinístico de baixo risco;
- não pode escrever diretamente em marketplace;
- não importa transporte HTTP de marketplace nem adaptadores de escrita;
- emite apenas intenção de ação para uma camada separada de Action Gateway;
- preserva `MI_READ_ONLY=true`, `MI_ALLOW_MARKETPLACE_WRITES=false` no runtime cognitivo.

Preço, estoque, publicação, pausa, encerramento, mensagens externas, campanhas, orçamento, reembolso e qualquer ação sensível exigem Action Gateway e política apropriada.

## Verdade compartilhada
Os órgãos não mantêm verdades independentes. Todos trabalham sobre:
- ledger temporal de eventos/snapshots já existente;
- evidências;
- investigações;
- ledger MCL-P+;
- `sovereign_intelligence`;
- `exposure_map`;
- `cognitive_audits`;
- checkpoints soberanos.

## Contrainteligência
Contrainteligência é defensiva e analítica. Ela registra:
`dado/evento -> o que a plataforma observa -> inferências possíveis -> risco -> mitigação -> evidência`.

Ela não autoriza invasão, evasão de autenticação, acesso a dados de terceiros ou exploração de vulnerabilidades como fonte operacional.

## Persistência
A migração `0009_sovereign_intelligence_core` adiciona:
- `sovereign_intelligence`;
- `exposure_map`;
- `cognitive_audits`;
- `sovereign_core_checkpoints`.

`marketplace_writes` nos checkpoints possui restrição física de banco igual a zero.

## Runtime
`scripts/run_sovereign_intelligence_core.py` executa o ciclo cognitivo continuamente e é supervisionado junto ao Radar, sensores, PostgreSQL e webhook.

O status do Núcleo deve continuar separado do painel. O painel somente consome sua inteligência.

## Gates
A missão só pode ser considerada provada quando:
- compilação PASS;
- testes unitários PASS;
- teste de arquitetura PASS;
- stress 12.000 cenários PASS;
- gate MCL-P+ legado continua PASS;
- Alembic upgrade/check/rollback/reupgrade PASS;
- ciclo real em PostgreSQL PASS;
- persistência do Núcleo PASS;
- supervisor recupera o processo após reinício;
- Radar continua saudável;
- `MARKETPLACE_WRITES=0`;
- nenhuma falha crítica.
