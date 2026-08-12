# Market Intelligence IA — Regras para Agentes

## Missão comum
Entregar o Market Intelligence IA por Loop Engineering: INSPECIONAR → REPRODUZIR → COLETAR EVIDÊNCIA → ISOLAR → IDENTIFICAR CAUSA → CORRIGIR → TESTAR → REGRESSÕES → RECUPERAÇÃO → ESTRESSAR → AUDITAR → CHECKPOINT → CONTINUAR.

## Regras soberanas
- Mercado Livre e futuros marketplaces permanecem read-only/fail-closed até autorização explícita para escrita real.
- Nunca inserir, revelar ou registrar credenciais, tokens, client secrets ou dados pessoais reais.
- Nenhum agente pode gastar dinheiro, contratar serviço, publicar/deployar, mudar segurança/permissões, executar ação destrutiva ou produzir efeito externo relevante sem autorização humana explícita.
- Afirmação não é evidência. Cada entrega precisa de teste, comando, estado consultado ou outro artefato verificável.
- FATO, INFERÊNCIA e HIPÓTESE devem permanecer separados. Anomalia não prova causa.
- Não reinventar fila durável: Temporal coordena workflows; PostgreSQL guarda estado e histórico.
- Eventos brutos são preservados antes da normalização/interpretação.
- Toda mudança deve ser pequena, reversível, testável e compatível com a arquitetura aprovada.

## Trabalho entre agentes
- Pipo Chief Engineer coordena dependências e decide a ordem técnica.
- Um agente não aprova o próprio trabalho. QA Verifier é o verificador independente padrão.
- Security Guardian revisa mudanças de OAuth, credenciais, autorização, dados sensíveis e fronteiras de escrita.
- Architecture Guardian revisa mudanças que alterem contratos, camadas ou dependências centrais.
- Não editar simultaneamente o mesmo arquivo em tarefas paralelas.
- Produzir PRs pequenos com critério de aceitação explícito; não misturar refatoração oportunista sem relação com a tarefa.

## Critério de conclusão
Uma tarefa só termina quando o comportamento pedido está implementado, testes/regressões passam, evidência está registrada, não há falha crítica conhecida e o próximo ponto seguro está documentado.
