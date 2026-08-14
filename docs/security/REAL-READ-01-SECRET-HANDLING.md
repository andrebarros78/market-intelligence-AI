# REAL-READ-01 — Manuseio de segredos

Este gate não aceita segredo em Git, issue, PR, log, relatório ou resposta HTTP.

Segredos esperados somente no ambiente de execução protegido:

- `MI_ML_CLIENT_SECRET`
- `MI_ML_OAUTH_KEY_B64`

Valores não secretos de configuração:

- `MI_ML_APP_ID`
- `MI_ML_REDIRECT_URI`
- `MI_ML_REAL_READ_ENABLED`

Regras:

1. `MI_ML_REAL_READ_ENABLED` nasce `false` e só é `true` durante uma execução autorizada.
2. O Client Secret é usado exclusivamente no POST do endpoint OAuth `/oauth/token`.
3. Authorization code e PKCE verifier nunca são incluídos em auditoria.
4. Access token e refresh token são cifrados com AES-256-GCM antes da persistência.
5. `/users/me` é a primeira e única leitura de negócio do Gate 1.
6. O request-id, status HTTP, latência e headers operacionais permitidos de `/users/me` podem ser persistidos; Authorization nunca pode.
7. O callback OAuth deve ser executado com access log que não grave query strings, pois `code` e `state` chegam na URL de retorno.
8. A configuração do DevCenter deve permanecer em escopo somente leitura durante este gate.
