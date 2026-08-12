# Pesquisa de Mercado — Agentes e Skills — 2026-08-12

## Decisão executiva

O Market Intelligence IA adotará **Codex local como runtime principal de engenharia**, `AGENTS.md` como governança comum, `.codex/agents/` para especialistas nativos e o padrão aberto **Agent Skills** para competências portáteis.

GitHub permanece como fonte persistente de código, checkpoints, evidências, proveniência e CI. Não existe necessidade técnica de contratar GitHub Copilot Cloud Agent para formar a equipe.

## Mercado pesquisado

### OpenAI Codex

A documentação oficial atual do Codex suporta subagentes, agentes customizados por projeto em `.codex/agents/`, governança por `AGENTS.md` e skills por repositório em `.agents/skills/`. Isso permite manter equipe especializada no próprio projeto e executar localmente quando a máquina estiver disponível.

### Agent Skills / GitHub

O ecossistema GitHub adotou o padrão aberto Agent Skills e disponibilizou tooling para descobrir/instalar skills em diferentes hosts, incluindo Codex, Qwen Code, Claude Code, Gemini e Copilot. A própria documentação alerta que skills de terceiros devem ser inspecionadas antes de uso; por isso nosso almoxarifado é inativo por padrão.

Fonte selecionada: `github/awesome-copilot`, fixada no commit `0a6e37e4e242c944380228fa29dbd14e64ac1b63`, licença MIT.

Recrutados principais dessa fonte: Principal Software Engineer, System Architecture Reviewer, Security Reviewer, SAST/SCA Analyzer, GitOps/CI Specialist, PostgreSQL DBA, QA Subagent, Project Documenter, além de skills de governança, supply chain, OWASP, segurança, MCP, pytest, avaliação agentic e fechamento auditável de bugs.

### China — Alibaba

Foram selecionadas duas competências de forte valor técnico:

1. `alibaba/open-code-review` — projeto de revisão de código originado em uso interno da Alibaba e posteriormente aberto; fonte fixada no commit `140871d70f608ad90749d33635db6d3a96706d3a`, licença Apache-2.0. Selecionada a skill `open-code-review-delegate`, que mantém o julgamento no LLM do host e usa a ferramenta para análise/regras determinísticas.
2. `alibaba/skill-up` — ferramenta para avaliar e evoluir Agent Skills com casos estruturados e relatórios; fonte fixada no commit `bce25ec5eba6880fd1837ea909ba68579c19bbfc`, release 0.9.0, licença Apache-2.0. Selecionada a skill `skill-upper`.

Qwen Code foi avaliado como runtime alternativo compatível com subagentes e Agent Skills. Ele pode servir para benchmark, arena ou segunda opinião, mas não será dependência obrigatória da arquitetura.

## Fontes rejeitadas/quarentenadas nesta rodada

- Repositório antigo `openai/skills`: não adotado porque foi descontinuado/deprecated em favor da infraestrutura atual de plugins/skills da OpenAI.
- Skills externas com scripts ou permissões pouco explícitas: não promovidas automaticamente. Exemplo identificado no ecossistema Anthropic foi mantido fora da primeira turma até revisão específica.
- Qualquer agente que exija assinatura, conta, API key ou serviço pago adicional: não ativado sem autorização de custo.

## Equipe resultante

- 11 agentes internos especializados, agora também definidos no formato nativo do Codex.
- 19 agentes/skills externos recrutados e armazenados como referências imutáveis no almoxarifado.
- Total: 30 recursos especializados disponíveis.

Os 19 externos ficam **inativos**. Nenhum script de terceiro foi executado nesta fase.

## Política de operação local

Quando houver acesso à máquina do projeto:

1. usar Codex local como executor principal;
2. sincronizar o almoxarifado por commit fixado;
3. gerar SHA-256 de cada recurso copiado;
4. inspecionar scripts/instruções/dependências antes de ativar;
5. promover somente as competências necessárias para a fase;
6. separar executor de verificador;
7. registrar no GitHub toda decisão, teste, falha, correção e próximo passo.

Não depender de memória de conversa para continuidade operacional.
