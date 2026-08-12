# RADAR DE PERDAS, EXCEÇÕES E ANOMALIAS — FUNÇÕES SOBERANAS V1

**Projeto:** Market Intelligence IA  
**Data:** 12/08/2026  
**Estado:** ESPECIFICAÇÃO FUNCIONAL APROVADA PARA IMPLEMENTAÇÃO  
**Módulo:** 01  
**Nome funcional:** Radar de Perdas, Exceções e Anomalias — Detector de Desconhecidos

## 1. Missão do Radar

O Radar é a camada central de detecção e investigação do Market Intelligence IA.

Sua missão não é apenas conferir regras previamente escritas. Ele deve detectar alterações relevantes, perdas, exceções, mudanças de regime e comportamentos anormais mesmo quando ninguém tiver descrito previamente o problema em texto ou criado uma regra específica.

O Radar deve responder continuamente:

1. O que mudou?
2. O que está causando ou pode causar perda?
3. O comportamento observado é normal ou anormal?
4. Existe uma causa conhecida suficiente para explicar o desvio?
5. Há perda de exposição, distribuição, conversão, competição, margem ou disponibilidade não explicada?
6. Qual é o impacto estimado?
7. Qual é a confiança da conclusão?
8. Qual ação humana deve ser tomada agora?
9. O que precisa continuar sendo observado para confirmar ou rejeitar a hipótese?

## 2. Princípio central — detectar o não previsto

O Radar deve operar em dois planos simultâneos:

### 2.1 Problemas conhecidos

Detectar condições explicitamente conhecidas, como:

- anúncio pausado, encerrado, moderado ou desaparecido;
- estoque zerado ou em risco de ruptura;
- preço abaixo do piso definido;
- perda de catálogo/competição;
- queda de vendas;
- atraso logístico;
- cancelamento;
- reclamação;
- devolução;
- perda de qualidade;
- erro de integração;
- falha de OAuth;
- indisponibilidade de endpoint;
- mudança de schema conhecida.

### 2.2 Problemas desconhecidos

Detectar desvios que não possuem uma regra prévia suficiente.

Exemplo conceitual:

- preço normal;
- estoque normal;
- reputação normal;
- logística normal;
- qualidade normal;
- anúncio ativo;
- nenhuma advertência explícita;
- mas o tráfego, conversão ou venda passa a divergir fortemente do padrão esperado.

Nesse caso o Radar deve abrir investigação mesmo que nenhuma regra textual tenha sido acionada.

## 3. Camadas de detecção

O Radar deve combinar as seguintes camadas.

### 3.1 Regras conhecidas

Regras determinísticas e versionadas para situações já conhecidas e comprovadas.

Cada regra deve registrar:

- origem;
- condição;
- entradas;
- versão;
- severidade;
- impacto esperado;
- ação recomendada;
- data de criação;
- data da última revisão.

### 3.2 Anomalia estatística

Detectar valores ou distribuições fora do comportamento histórico esperado.

Exemplos:

- visitas;
- vendas;
- conversão;
- ticket;
- estoque;
- preço;
- cancelamento;
- atraso;
- reclamação;
- devolução;
- CTR;
- CPC;
- custo de Ads;
- competição de catálogo.

### 3.3 Anomalia temporal

Detectar alteração de comportamento considerando tempo, sazonalidade e sequência.

O Radar deve diferenciar:

- pico isolado;
- tendência;
- quebra brusca;
- queda progressiva;
- alteração de sazonalidade;
- mudança persistente de patamar;
- recuperação parcial;
- comportamento cíclico.

### 3.4 Anomalia multivariada

Detectar situações em que cada variável isoladamente parece aceitável, mas a combinação delas deixa de ser normal.

Exemplo:

`preço + estoque + reputação + logística + visitas + conversão + competição`

podem formar um estado anormal mesmo que nenhum campo individual ultrapasse um limite.

### 3.5 Mudança de regime

Detectar quando o sistema passa a operar de maneira estruturalmente diferente do histórico.

Exemplos:

- perda persistente de tráfego sem causa aparente;
- mudança simultânea em diversos anúncios;
- alteração de comportamento da API no mesmo intervalo;
- mudança de competição em catálogo sem alteração observável suficiente;
- deterioração gradual de conversão sem ruptura explícita.

### 3.6 Anomalia relacional

Comparar entidades relacionadas para encontrar inconsistências.

Relações prioritárias:

- anúncio ↔ SKU;
- anúncio ↔ catálogo;
- anúncio ↔ preço;
- anúncio ↔ estoque;
- anúncio ↔ visitas;
- anúncio ↔ pedidos;
- pedido ↔ envio;
- pedido ↔ pagamento;
- item ↔ reclamação;
- item ↔ devolução;
- produto ↔ concorrência;
- conta ↔ conjunto de anúncios;
- anúncio investigado ↔ grupo de controle comparável.

## 4. Detector de distribuição e efeito algorítmico

O Radar deve investigar perda de exposição ou distribuição quando o comportamento comercial deixa de ser explicado pelos fatores observáveis.

### 4.1 O que pode detectar

O Radar pode afirmar, quando houver evidência suficiente:

- houve perda anormal de tráfego;
- houve perda anormal de conversão;
- houve perda de competição em catálogo;
- houve mudança de regime;
- os fatores observáveis conhecidos não explicam suficientemente a alteração;
- anúncios de controle comparáveis não sofreram alteração equivalente;
- existe correlação temporal com mudança observável da plataforma ou do canal;
- uma hipótese de mudança de distribuição, elegibilidade ou ranqueamento merece investigação prioritária.

### 4.2 O que não pode afirmar sem prova

O Radar não deve afirmar intenção interna do Mercado Livre.

É proibido concluir automaticamente:

- “o Mercado Livre prejudicou deliberadamente a conta”;
- “houve punição secreta”;
- “o algoritmo aplicou penalidade X”;
- “shadow ban confirmado”.

Sem evidência direta, isso permanece hipótese.

## 5. Modelo esperado versus observado

O Radar deve construir uma expectativa operacional para cada entidade relevante.

Exemplo conceitual:

```text
tráfego esperado: 2.400–2.900 visitas/dia
tráfego observado: 680 visitas/dia
```

O sistema deve calcular:

- esperado;
- observado;
- desvio absoluto;
- desvio percentual;
- intervalo de confiança quando aplicável;
- fatores conhecidos que explicam parte do desvio;
- resíduo não explicado.

## 6. Resíduo não explicado

Depois de considerar fatores observáveis, o Radar deve medir quanto da alteração permanece sem explicação suficiente.

Exemplo conceitual:

```text
queda total observada: -74%
explicação por sazonalidade: -2%
explicação por preço: -1%
explicação por concorrência observável: -2%
resíduo não explicado: aproximadamente -69%
```

O resíduo não explicado não é prova de causa algorítmica. Ele é um sinal de investigação.

## 7. Comparação contrafactual e grupo de controle

Sempre que houver dados suficientes, o Radar deve comparar a entidade investigada com controles semelhantes.

Critérios possíveis:

- mesma categoria;
- faixa de preço semelhante;
- mesma logística;
- reputação semelhante;
- qualidade semelhante;
- histórico de vendas parecido;
- sazonalidade semelhante;
- catálogo/produto comparável.

Objetivo:

estimar o que provavelmente teria acontecido caso o comportamento anormal não tivesse ocorrido.

## 8. Sensor do Canal Mercado Livre

O Radar deve observar não apenas dados de negócio, mas também o comportamento técnico do canal de integração.

### 8.1 Dados a registrar de forma sanitizada

Para cada interação relevante:

- timestamp;
- direção `ML -> nós` ou `nós -> ML`;
- endpoint/recurso;
- tópico da notificação;
- status HTTP;
- latência;
- tamanho da resposta;
- número de tentativa;
- horários `sent` e `received` quando existirem;
- request/correlation ID operacional quando permitido;
- headers operacionais permitidos;
- `Retry-After`;
- respostas parciais e indicação de campos ausentes;
- mudança de schema;
- campos novos;
- campos desaparecidos;
- frequência e cadência de notificações;
- mudança de padrão de erro;
- sequência temporal dos eventos.

### 8.2 Segredos proibidos

Nunca persistir em texto aberto:

- `Authorization`;
- Bearer token;
- Client Secret;
- access token;
- refresh token;
- chave privada;
- credencial de banco.

### 8.3 Mudança conjunta de comportamento

O Radar deve correlacionar sinais técnicos com sinais de negócio.

Exemplo:

- tráfego cai;
- vendas caem;
- atributos do anúncio permanecem estáveis;
- comportamento de determinados endpoints muda;
- frequência de notificações muda;
- latência/status/retries mudam no mesmo período.

Resultado permitido:

`mudança de regime detectada no ecossistema; causa interna específica não confirmada`.

## 9. Sensores funcionais do Radar

O Radar deverá evoluir para os seguintes sensores:

1. Sensor de Dados de Negócio;
2. Sensor Temporal;
3. Sensor Estatístico;
4. Sensor Multivariado;
5. Sensor de Mudança de Regime;
6. Sensor de Concorrência;
7. Sensor de Catálogo;
8. Sensor de Distribuição/Exposição;
9. Sensor de Estoque;
10. Sensor de Preço/Margem;
11. Sensor de Conversão;
12. Sensor Logístico;
13. Sensor de Pós-venda;
14. Sensor de Qualidade;
15. Sensor de Ads/Promoções quando disponíveis;
16. Sensor do Canal Mercado Livre;
17. Sensor de Integridade dos Dados;
18. Sensor de Mudança de Contrato/API.

## 10. Linguagem de evidência obrigatória

Toda conclusão do Radar deve ser classificada em uma destas categorias.

### 10.1 FATO

Informação diretamente observada e comprovada.

Exemplo:

`As visitas caíram 68% entre os períodos comparados.`

### 10.2 INFERÊNCIA

Conclusão derivada de dados suficientes, mas não observada diretamente.

Exemplo:

`A queda não é explicada pelas variáveis observáveis analisadas.`

### 10.3 HIPÓTESE

Explicação candidata ainda não confirmada.

Exemplo:

`Uma mudança no mecanismo de distribuição/rankeamento é atualmente a hipótese prioritária.`

O sistema nunca deve apresentar hipótese como fato.

## 11. Contrato mínimo de alerta

Todo alerta relevante deve conter:

```text
entidade
mudança_observada
evidência
classificação_evidência
severidade
impacto_estimado
confiança
causas_observáveis
resíduo_não_explicado
hipóteses
comparação_controle
recomendação
responsável
prazo
estado
resultado_posterior
primeira_observação
última_observação
versão_detector
```

## 12. Priorização

O Radar deve priorizar pelo efeito provável no negócio, não apenas pela intensidade estatística.

Critérios:

- perda financeira estimada;
- risco de ruptura;
- perda de exposição;
- velocidade de deterioração;
- quantidade de entidades afetadas;
- risco à reputação;
- risco logístico;
- urgência;
- confiança;
- reversibilidade;
- janela de ação.

## 13. Indicador de Anomalia de Distribuição — IAD

O projeto deve prever um indicador de anomalia de distribuição calibrável.

Componentes conceituais:

- desvio de tráfego;
- desvio de conversão;
- mudança de competição;
- divergência contra controles;
- mudança de regime;
- causas observáveis conhecidas;
- resíduo não explicado;
- sinais correlatos do canal.

A escala e os pesos não devem ser fixados arbitrariamente. Devem ser calibrados e versionados usando dados históricos reais.

## 14. Doador operacional e estratégia de detectores

O Radar não deve depender de um único algoritmo.

### 14.1 PyOD

Doador operacional principal previsto para detecção de anomalias e ensembles.

Uso esperado:

- múltiplos detectores;
- comparação entre detectores;
- combinação/ensemble;
- detecção não supervisionada;
- seleção por desempenho observado.

### 14.2 Benchmark e seleção

O projeto deve validar os detectores em dados históricos próprios antes de promover qualquer algoritmo para produção.

Nenhum detector deve ser considerado universal.

### 14.3 Modelos experimentais

Arquiteturas de pesquisa para zero-shot, investigação autônoma ou foundation models podem ser avaliadas em laboratório, mas não entram no núcleo de produção sem benchmark, explicabilidade e teste de falso positivo.

## 15. Investigação progressiva

Quando uma anomalia relevante for aberta, o Radar deve poder executar um ciclo investigativo:

```text
DETECTAR
-> LOCALIZAR A ENTIDADE/PERÍODO
-> REUNIR EVIDÊNCIAS
-> COMPARAR COM HISTÓRICO
-> COMPARAR COM CONTROLES
-> BUSCAR CAUSAS OBSERVÁVEIS
-> MEDIR RESÍDUO NÃO EXPLICADO
-> GERAR HIPÓTESES
-> CALCULAR CONFIANÇA
-> RECOMENDAR AÇÃO
-> CONTINUAR OBSERVANDO
-> CONFIRMAR OU REJEITAR HIPÓTESE
```

## 16. Integridade e memória histórica

O Radar depende de histórico próprio.

Devem ser preservados:

- raw sanitizado;
- snapshots normalizados;
- eventos;
- métricas;
- mudanças de schema;
- alertas;
- hipóteses;
- decisões humanas;
- resultado posterior;
- versão do detector/regra;
- hashes/evidências.

Sem histórico suficiente, o sistema deve reduzir explicitamente sua confiança.

## 17. Falso positivo e resultado posterior

O Radar deve aprender com o resultado das decisões.

Cada alerta deve posteriormente ser classificado, quando possível, como:

- confirmado;
- parcialmente confirmado;
- falso positivo;
- inconclusivo;
- resolvido;
- persistente;
- causa externa;
- causa interna;
- causa não identificada.

Isso servirá para calibrar regras, modelos e prioridades.

## 18. Segurança operacional

Durante o Módulo 01:

- operação somente leitura;
- nenhuma alteração automática no Mercado Livre;
- nenhum scraping como substituto silencioso da API oficial;
- nenhum dado sensível enviado à IA sem minimização;
- nenhuma credencial nos dados analíticos;
- nenhuma hipótese apresentada como acusação ou fato.

## 19. Critério de conclusão do Radar V1

O Radar V1 somente poderá ser declarado validado quando demonstrar em sandbox/digital twin e depois em leitura real autorizada:

1. ingestão de eventos e snapshots;
2. detecção de regra conhecida;
3. detecção de anomalia não prevista;
4. detecção de mudança de regime;
5. comparação com controle;
6. cálculo do resíduo não explicado;
7. captura sanitizada da telemetria do canal;
8. separação de fato/inferência/hipótese;
9. geração de alerta completo;
10. priorização por impacto;
11. reinício sem perda do histórico;
12. baixa taxa de falso positivo dentro do limiar que será homologado;
13. evidência reproduzível de cada conclusão.

## 20. Decisão soberana

O Módulo 01 deixa de ser um simples `Radar de Perdas e Exceções` e passa a ser formalmente concebido como:

> **Radar de Perdas, Exceções e Anomalias — Detector de Desconhecidos**, responsável por detectar problemas conhecidos e desconhecidos, investigar mudanças de regime, medir perdas não explicadas, observar sinais do canal Mercado Livre e produzir evidências úteis para decisão sem confundir hipótese com fato.
