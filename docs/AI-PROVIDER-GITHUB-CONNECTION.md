# Conexão da API de IA ao API ML via GitHub

## Objetivo

Preparar o API ML para consumir um provedor de IA por contrato estável, mantendo a credencial fora do código e usando o GitHub apenas como repositório/CI, não como barramento de runtime.

## Configuração atual

- provider: `openai`;
- model: `gpt-5-mini`;
- base URL: `https://api.openai.com/v1`;
- driver: `OpenAIResponsesDriver`;
- armazenamento de resposta pretendido: desabilitado (`store=false`) quando a etapa de inferência for implementada;
- retries pretendidos: `0` por padrão;
- seleção de provider/model/base URL feita por configuração, não por acoplamento do restante do sistema.

## Implementação

- `market_intelligence.ai.ProviderManager`: contrato estável para selecionar drivers;
- `market_intelligence.ai.OpenAIResponsesDriver`: driver atual;
- `AIProviderConfig`: configuração por variáveis de ambiente;
- `scripts/probe_ai_provider.py`: prova de conectividade sem inferência.

## Probe seguro

A prova inicial usa somente `GET /v1/models`.

Ela comprova:

1. que a credencial foi aceita pelo provedor;
2. que o endpoint oficial respondeu;
3. que o modelo configurado aparece entre os modelos disponíveis para aquela credencial.

Ela não:

- executa inferência;
- envia anúncios, pedidos, métricas ou outros dados de negócio;
- grava a credencial em saída;
- segue redirects;
- aceita host arbitrário para o driver OpenAI.

O driver recusa base URL diferente de HTTPS + `api.openai.com` + `/v1`, evitando que uma configuração maliciosa redirecione a credencial para outro host.

## Credencial

Nome de ambiente esperado pelo código: `MI_AI_API_KEY`.

A credencial deve existir somente como Secret/variável de ambiente protegida. Nunca deve ser salva em commit, arquivo `.env` versionado, issue, PR, log ou mensagem de chat.

## GitHub Actions

O workflow autenticado não foi criado automaticamente nesta etapa porque a ação de escrita do conector recusou um arquivo que referenciava GitHub Secrets. Esse bloqueio não deve ser contornado por commits de baixo nível.

Ponto seguro atual:

- código do Provider Manager: preparado;
- probe sem inferência: preparado;
- testes sintéticos: preparados;
- credencial real: não recebida pelo ChatGPT e não versionada;
- chamada externa real: não executada;
- GitHub Secret: inserção ainda necessária por interface segura do GitHub;
- workflow autenticado: pendente de uma ação de escrita de alto nível que aceite referência a Secret, ou configuração manual no GitHub.

## Critério para declarar conexão comprovada

A conexão só pode ser declarada concluída quando:

1. o Secret estiver configurado no GitHub;
2. o probe executar no GitHub Actions sem revelar a credencial;
3. `authenticated=true`;
4. `model_available=true` para o modelo configurado;
5. nenhum dado de negócio tiver sido enviado durante o teste.
