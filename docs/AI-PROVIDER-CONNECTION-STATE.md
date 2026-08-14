# Estado da conexão das IAs

## Estado final

**MISSION_PROVEN** para a conexão das APIs de IA do API ML.

- Provider Manager: implementado e desacoplado;
- papel `system`: OpenAI/GPT;
- modelo do sistema validado: `gpt-5-mini`;
- papel `agents`: Z.AI/GLM;
- modelo dos agentes validado: `glm-5.1`;
- credenciais: separadas;
- Environment GitHub: `INTELIGENCI DE MERCADO API`;
- `MI_AI_SYSTEM_API_KEY`: presente e autenticada, valor não exposto;
- `MI_AI_AGENTS_API_KEY`: presente e autenticada, valor não exposto;
- workflow autenticado final: `AI Provider Connectivity` run #3 / `31812722075` = success;
- `system-gpt`: authenticated=true, model_available=true;
- `agents-zai`: authenticated=true, model_available=true;
- inferência durante os probes: nenhuma;
- dados de negócio enviados aos providers durante os probes: nenhum;
- CI integral pós-merge: `Validate Market Intelligence Base` #184 / `31812722077` = success;
- SHA técnico comprovado: `9528c3f896a7ebb889342d3d876966a5490a1df6`.

## Limites

Esta prova confirma conectividade, autenticação, disponibilidade dos modelos e isolamento de credenciais. Ela deliberadamente não executou geração de conteúdo, não mediu qualidade/custo de inferência, não ativou escrita no Mercado Livre e não conclui o projeto API ML como um todo.
