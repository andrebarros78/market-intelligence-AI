# Radar Soberano — Runtime Permanente

## Estado

Decisão arquitetural obrigatória do Market Intelligence AI.

## Regra central

O Radar e o Registry de Skills formam o núcleo permanente de observação e inteligência do sistema.

Eles operam continuamente, 24x7, com horizonte arquitetural mínimo de 5.000 anos, sem expiração operacional normal.

O Radar não possui fluxo de desligamento rotineiro. Seu comportamento padrão é permanecer ativo, reiniciar após falha e retomar automaticamente a coleta e investigação. Somente uma parada de emergência de segurança pode interromper o processo, e a retomada deve ocorrer assim que a condição segura for restabelecida.

## Escopo de observação

O Radar deve coletar e investigar continuamente todos os sinais autorizados e tecnicamente observáveis disponíveis ao sistema, incluindo:

- eventos de negócio;
- webhook e metadados de canal;
- respostas oficiais em leitura;
- mudanças de schema;
- status HTTP;
- latência;
- retries;
- rate limit;
- sinais de cache e conteúdo parcial quando expostos;
- alterações temporais;
- histórico de entidades;
- comportamento de mercado e concorrência quando a fonte for autorizada;
- padrões, anomalias e mudanças de regime.

A regra não autoriza invasão, bypass de segurança, coleta de segredo ou acesso a informação não disponibilizada por fonte autorizada.

## Funções permanentes

- observar eventos e estado do marketplace;
- preservar histórico;
- validar evidências;
- detectar anomalias e mudanças de regime;
- investigar causas observáveis;
- correlacionar sinais de negócio e telemetria do canal;
- estudar padrões históricos continuamente;
- analisar mercado, concorrência e tendência;
- acionar Skills aprovadas;
- produzir alertas e explicações;
- informar o restante do sistema.

## Regra de conhecimento

Raw não é fato.

Hipótese não é fato.

Conhecimento permanente exige evidência validada conforme o contrato do domínio.

## Segurança permanente

```text
MI_READ_ONLY=true
MI_ALLOW_MARKETPLACE_WRITES=false
```

O Radar não possui autorização para modificar preço, estoque, título, pedidos, mensagens ou qualquer outro recurso de marketplace.

## Relação com IAs

LLMs são aceleradores opcionais de análise e explicação, não a fonte primária nem o mecanismo de persistência do Radar.

Se GPT, Claude ou qualquer outro modelo estiver indisponível, o Radar continua observando, persistindo, comparando, detectando e registrando.

## Meta de eficácia

A exigência de superar uma análise baseada apenas em LLMs será verificada objetivamente por métricas, incluindo:

- cobertura de sinais observáveis;
- completude histórica;
- latência de detecção;
- taxa de falso positivo;
- qualidade e completude da evidência;
- detecção de mudança de regime;
- recuperação após falha;
- continuidade sem LLM;
- capacidade de reproduzir uma conclusão a partir das evidências armazenadas.

O sistema não declarará superioridade com base em opinião. A vantagem deverá ser comprovada por benchmark e histórico operacional.
