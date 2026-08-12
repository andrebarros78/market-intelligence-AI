# Market Intelligence IA — coleta local e importação

## Objetivo

Reunir tudo o que já existe no PC relacionado ao antigo API ML / Market Intelligence IA, preservar o que funciona, eliminar duplicações e montar uma única fonte de verdade no GitHub.

## Regra principal

A coleta é dividida em duas etapas:

1. **Inventário somente leitura** — localizar projetos, arquivos, Git, dependências, bancos, relatórios, testes e possíveis segredos sem enviar conteúdo do PC.
2. **Importação sanitizada** — selecionar a melhor cópia de cada artefato, excluir segredos/dados privados/gerados, consolidar estrutura e só então enviar ao repositório.

Nunca fazer push bruto de uma pasta inteira do PC.

## Raízes verificadas pelo coletor

- `C:\Projetos`
- `C:\New Projet`
- `D:\Projetos`

O coletor procura nomes relacionados a:

- API-ML / API ML / API_ML;
- Market Intelligence / Market Intelligence AI;
- MELI;
- Mercado Livre.

Também testa diretamente os caminhos históricos conhecidos do projeto.

## Saídas do inventário

O script `tools/Collect-Local-MarketIntelligence.ps1` produz:

- `projects.json` — raízes de projeto encontradas;
- `inventory.json` — inventário completo de arquivos;
- `inventory.csv` — versão tabular;
- `git-state.json` — branch, HEAD, status, remotes, tags, últimos commits e `git fsck`;
- `secret-risks.csv` — caminhos potencialmente sensíveis, sem registrar valores;
- `SUMMARY.md` — resumo executivo;
- pacote ZIP contendo apenas esses relatórios.

O inventário calcula SHA-256 dos arquivos para identificar duplicatas e descobrir qual cópia é realmente igual ou divergente.

## O que não é enviado automaticamente

- `.env`;
- tokens e credenciais;
- chaves privadas;
- bancos de dados;
- logs;
- dumps;
- backups;
- dados pessoais;
- caches;
- ambientes virtuais;
- `node_modules`;
- arquivos de build.

## Consolidação posterior

Depois do inventário, cada artefato será classificado como:

- **PRESERVAR** — código ou documento atual e necessário;
- **MESCLAR** — duas ou mais cópias contêm trabalho válido diferente;
- **SUBSTITUIR** — versão antiga será substituída por uma mais nova;
- **ARQUIVAR** — útil como evidência histórica, mas não entra no runtime;
- **DESCARTAR** — cache, duplicata ou artefato gerado;
- **BLOQUEAR** — contém segredo ou dado que não pode ir ao GitHub.

## Fonte de verdade final

A montagem final deve separar:

```text
market-intelligence-AI/
├── src/                 # código autoral do produto
├── tests/               # testes
├── migrations/          # schema e migrações
├── tools/               # operação e diagnóstico
├── docs/                # documentação soberana atualizada
├── components/          # proveniência dos componentes de terceiros
├── infrastructure/      # compose/configuração de execução
├── contracts/           # contratos internos versionados
├── examples/            # somente dados sintéticos/sanitizados
└── archive/             # histórico selecionado, se necessário
```

O `painel` permanece em repositório próprio e se conecta ao Market Intelligence IA por API/Higress. Componentes de terceiros permanecem rastreados por baseline e checksums, sem misturar sua origem com código autoral.

## Gate antes do push do conteúdo local

Antes de qualquer importação de código do PC:

1. conferir o relatório de riscos de segredo;
2. definir a cópia vencedora por hash/Git/data/evidência;
3. validar testes disponíveis;
4. remover credenciais e dados privados;
5. criar staging sanitizado;
6. revisar `git diff`;
7. só então realizar commit/push.

A montagem não considera um arquivo “mais novo” apenas pela data de modificação. Git, conteúdo, hashes e testes têm prioridade sobre timestamp.
