# IA-02 — Estado da inferência controlada em sandbox

Data: 2026-08-14

## Objetivo

Comprovar, usando somente texto sintético, o caminho real de inferência das duas capacidades de IA atualmente selecionadas no Market Intelligence AI:

- sistema: OpenAI / `gpt-5-mini`;
- agentes: Z.AI / `glm-4.7-flash`.

Nenhum dado do Mercado Livre ou outro dado de negócio foi autorizado para esta fase.

## Segurança implementada

A inferência de sandbox:

- usa prompt sintético fixo no código;
- limita tokens de saída;
- usa `store=false` no OpenAI;
- usa thinking desabilitado no Z.AI durante o teste;
- não registra a resposta textual bruta;
- registra somente correspondência esperada, hash, tamanho, tokens e latência;
- marca `synthetic_data_only=true` e `business_data_sent=false`;
- mantém as chaves mascaradas nos logs;
- não habilita inferência de produção.

## Prova OpenAI / GPT

Workflow `AI Sandbox Inference`, run `31816402501`, job `94819034764`:

- `authenticated=true`;
- `provider=openai`;
- `model=gpt-5-mini`;
- `inference_executed=true`;
- `synthetic_data_only=true`;
- `business_data_sent=false`;
- `store_enabled=false`;
- `expected_output_match=true`;
- input tokens: 24;
- output tokens: 118;
- total tokens: 142;
- latência: 2905 ms;
- saída armazenada apenas como SHA-256 `4f30e818c4ce70ac7c31c3674f2c3f0b916ac2e2011327f70c15f1ffab136a97` e comprimento 10.

Resultado: **GPT sandbox comprovado**.

## Histórico corretivo Z.AI

### Primeira tentativa

No primeiro ciclo de IA-02, o sandbox Z.AI com o modelo então configurado (`glm-5.1`) retornou HTTP 429. O probe autenticado de conectividade no mesmo ciclo estava funcional.

A hipótese de concorrência entre probe e sandbox foi eliminada na correção seguinte.

### Decisão de produto

O modelo de agentes foi alterado para `glm-4.7-flash`.

A configuração, perfil 2, testes, documentação e workflows foram migrados para esse modelo. O CI do PR de correção passou integralmente antes do merge.

### Tentativa isolada GLM-4.7-Flash

Workflow `AI Sandbox Inference`, run `31817460101`, job `94822462899`:

- GPT foi explicitamente `skipped`;
- não houve probe Z.AI concorrente;
- `MI_AI_PROFILE_2_MODEL=glm-4.7-flash`;
- chave presente e mascarada;
- retries = 0;
- store = false;
- resultado: HTTP 429, exposto apenas como erro estável `ai_provider_rate_limited`.

Resultado: a hipótese de colisão entre nossos workflows foi rejeitada.

## Diagnóstico Z.AI sem inferência

Para não repetir inferência às cegas, foi executado apenas o probe de listagem de modelos.

Workflow `AI Provider Connectivity`, run `31817892426`, job `94823855144`:

- `authenticated=true`;
- `provider=zai`;
- `model=glm-4.7-flash`;
- `model_available=false`;
- `inference_executed=false`;
- `business_data_sent=false`;
- endpoint `api.z.ai`;
- chave presente e mascarada.

Isso demonstra que a credencial é aceita pela Z.AI, porém **essa credencial/conta não expõe `glm-4.7-flash` na listagem de modelos neste momento**.

## Integridade do projeto

- CI pré-merge da correção GLM-4.7-Flash: run `31817165195` — sucesso integral.
- CI pós-merge da correção: run `31817460293` — sucesso integral.
- CI do diagnóstico: run `31817709163` — sucesso integral.
- CI pós-merge do diagnóstico: run `31817892379` — sucesso integral.

Compilação, PostgreSQL, migrations, drift, rollback e suíte de testes permaneceram verdes.

## Estado da missão

`MISSION_BLOCKED_EXTERNAL_ZAI_MODEL_ACCESS`

A IA-02 não pode ser declarada `MISSION_PROVEN` enquanto uma inferência real mínima com `glm-4.7-flash` não concluir com sucesso.

O bloqueio restante não é um erro conhecido no código do Market Intelligence AI: a chave autentica, o sistema está íntegro e o endpoint/modelo estão configurados conforme o contrato, mas a conta/chave Z.AI usada pelo Environment não disponibiliza o modelo no probe e as tentativas de inferência recebem HTTP 429.

## Ação externa necessária

No painel Z.AI associado à chave `MI_AI_AGENTS_API_KEY`, verificar disponibilidade/rate limits do `glm-4.7-flash` e garantir que a chave usada pelo Market Intelligence AI tenha acesso ao modelo. Se for necessário substituir a chave, o novo valor deve ser colocado diretamente no GitHub Environment Secret; nunca em código, documentação ou chat.

Depois que o acesso externo estiver liberado, o reteste deve executar somente uma inferência sintética GLM-4.7-Flash e exigir:

- `authenticated=true`;
- `model=glm-4.7-flash`;
- `inference_executed=true`;
- `synthetic_data_only=true`;
- `business_data_sent=false`;
- `expected_output_match=true`;
- nenhuma credencial exposta.
