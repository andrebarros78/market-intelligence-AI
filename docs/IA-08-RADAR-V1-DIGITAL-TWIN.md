# IA-08 — Digital Twin de Aceitação do Radar V1

Data: 2026-08-14

## Objetivo

Transformar os critérios soberanos de conclusão do Radar V1 em provas executáveis e permanentes no CI.

## Execução

`python scripts/run_radar_digital_twin.py`

O processo usa somente dados sintéticos e PostgreSQL de teste. Não executa OAuth real, não chama o Mercado Livre, não realiza inferência externa e não escreve em marketplace.

## Provas obrigatórias

O relatório exige aprovação de:

1. ingestão de evento bruto e snapshot;
2. detecção por regra conhecida;
3. detecção de anomalia sem regra conhecida;
4. mudança de regime sem inferir causa interna;
5. comparação com controles por contrafactual operacional não causal;
6. resíduo não explicado após fatores observáveis;
7. correlação com telemetria sanitizada do canal;
8. persistência sanitizada da telemetria, com credenciais redigidas;
9. separação explícita entre FATO, INFERENCIA e HIPOTESE;
10. contrato completo do alerta;
11. persistência do alerta e suas evidências;
12. priorização por impacto de negócio;
13. reinício com histórico preservado e deduplicação ativa;
14. taxa de falso positivo sintética dentro do limite;
15. evidência reproduzível.

## Falso positivo

O Digital Twin homologa **somente o sandbox sintético** com limite inicial máximo de 5%.

Isso não substitui a homologação com histórico real. O relatório mantém:

- `real_historical_false_positive_homologation_required=true`;
- `authorized_real_read_required=true`;
- `production_ready=false`.

Portanto, um CI verde prova a maturidade sintética do Radar, mas não autoriza afirmar que o Radar V1 está homologado em produção.

## Priorização de impacto

A nova função `prioritize_alerts` ordena primeiro por `estimated_impact`, depois por severidade e confiança. Uma anomalia estatisticamente extrema com impacto baixo não ultrapassa automaticamente uma perda estimada maior.

## Reinício

A prova fecha o primeiro engine SQLAlchemy, cria um novo engine/sessões e verifica:

- entidade ainda recuperável;
- evento duplicado recusado;
- snapshot duplicado recusado;
- histórico PostgreSQL preservado.

## Segurança de canal

O cenário tenta persistir valores sintéticos nos campos `authorization` e `access_token`. O repositório deve manter apenas `[REDACTED]`; o valor secreto sintético original não pode aparecer no registro armazenado.

## Gate permanente

O workflow `Validate Market Intelligence Base` executa o Digital Twin depois de migrations, rollback e pytest. Qualquer critério obrigatório falso encerra o job com código diferente de zero.
