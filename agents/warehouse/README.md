# Almoxarifado de Agentes — Market Intelligence IA

Este diretório é o estoque técnico de agentes e Agent Skills recrutados no mercado.

## Regra principal

**Estar no almoxarifado não significa estar ativo.** Nenhum código, script, binário, MCP, CLI ou instrução de terceiro é executado automaticamente.

O inventário soberano está em `recruits.json`. Cada recrutado possui origem, repositório, caminho, commit fixado, licença, função e estado.

## Estados

- `WAREHOUSE_APPROVED_INACTIVE`: fonte e licença verificadas, referência fixada, ainda não promovida para execução.
- `WAREHOUSE_APPROVED_REQUIRES_LOCAL_TOOL_REVIEW`: fonte/licença verificadas, porém depende de ferramenta externa ou execução local adicional antes da promoção.

## Promoção para trabalho ativo

Uma competência externa só pode sair do almoxarifado após:

1. inspeção do conteúdo completo;
2. confirmação da licença e da referência fixada;
3. geração de manifesto SHA-256 da cópia local;
4. análise de instruções, scripts e dependências;
5. execução em sandbox sem credenciais reais;
6. testes do comportamento esperado;
7. revisão independente do QA Verifier e, quando aplicável, Security Guardian;
8. registro do checkpoint no GitHub.

Skills promovidas para o Codex devem ser instaladas sob `.agents/skills/`. Agentes nativos do projeto ficam em `.codex/agents/`.

## Motor principal

O motor de engenharia do projeto é **Codex local** quando houver acesso à máquina. GitHub é a fonte persistente de código, decisões, hashes, testes, falhas, checkpoints e proveniência.

Qwen Code pode ser usado como runtime alternativo/benchmark quando houver ganho comprovado, sem criar dependência obrigatória.

## Segurança

O script `tools/Sync-Agent-Warehouse.ps1` apenas baixa/copia referências fixadas e calcula hashes. Ele não instala pacotes, não executa scripts de terceiros e não promove automaticamente nenhum recrutado.
