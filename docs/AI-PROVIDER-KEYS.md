# Inventário de credenciais de integração

Somente nomes; valores nunca devem ser versionados.

## Inteligência artificial

- `MI_AI_SYSTEM_API_KEY`: Gemini exclusivo da IA do sistema.
- `MI_AI_AGENTS_API_KEY`: Gemini exclusivo dos agentes/workers.

## Mercado Livre

- `MI_ML_CLIENT_SECRET`: Client Secret OAuth do aplicativo Mercado Livre.

Configurações não secretas, quando usadas, devem permanecer separadas dos Secrets: provider, model, base URL, Client ID e redirect URI.
