# REAL-READ-01 — OAuth real Mercado Livre somente leitura

Estado: PREPARACAO_TECNICA_VALIDADA_EM_CI

Objetivo: habilitar a primeira conexão real do adapter Mercado Livre sem liberar qualquer escrita de negócio.

## Portões invariantes

- `MI_READ_ONLY=true`.
- `MI_ALLOW_MARKETPLACE_WRITES=false`.
- `MI_ML_REAL_READ_ENABLED=false` por padrão.
- OAuth real usa Authorization Code + `state` de uso único + PKCE S256.
- `Client Secret`, authorization code, access token e refresh token nunca são persistidos em claro nem enviados a logs.
- token que contenha escopo `write` é rejeitado antes de qualquer leitura de negócio.
- token sem escopo `read` comprovável é rejeitado em modo fail-closed.
- a primeira consulta após a troca de token é exclusivamente `GET /users/me`.
- a identidade retornada por `/users/me` é a chave de vinculação da credencial; identificador informado pelo operador nunca substitui a identidade observada.
- chamadas de negócio continuam limitadas a `GET` pelo `Module01SecurityPolicy`.
- POST é permitido apenas no cliente OAuth e apenas para `https://api.mercadolibre.com/oauth/token`.
- redirect URI deve ser HTTPS, estática e corresponder exatamente à registrada no DevCenter.
- credencial cifrada, telemetria de `/users/me` e auditoria de sucesso são gravadas atomicamente.
- o runtime sintético permanece separado e continua sendo a base de CI sem rede real.
- o servidor OAuth local escuta somente em `127.0.0.1` e roda com access log desligado para não registrar `code` ou `state` da query de callback.

## Configuração protegida prevista

```text
MI_READ_ONLY=true
MI_ALLOW_MARKETPLACE_WRITES=false
MI_ML_REAL_READ_ENABLED=false
MI_ML_APP_ID=<identificador publico da aplicacao>
MI_ML_CLIENT_SECRET=<segredo fora do Git>
MI_ML_REDIRECT_URI=https://<callback registrado>/v1/oauth/mercadolivre/callback
MI_ML_OAUTH_KEY_B64=<chave AES-256 em base64 fora do Git>
MI_DATABASE_URL=<PostgreSQL protegido>
MI_ML_OAUTH_LOCAL_PORT=8771
```

## Runner local

```text
python scripts/run_real_read_oauth.py
```

O runner fica deliberadamente em loopback. Qualquer exposição HTTPS deve acontecer por túnel/reverse proxy separado, autorizado e limitado ao callback registrado.

## Critério do Gate 1 real

1. configuração segura presente;
2. aplicação no DevCenter configurada com escopo somente leitura e PKCE;
3. callback HTTPS exato válido;
4. autorização humana concluída no Mercado Livre;
5. troca de code por token concluída sem vazamento;
6. retorno de escopos contém `read` e não contém `write`;
7. `GET /users/me` retorna 2xx;
8. identidade observada é validada;
9. tokens são persistidos cifrados;
10. telemetria sanitizada da primeira leitura é registrada;
11. nenhuma escrita de marketplace é possível.

Somente após o Gate 1 real será executado o Auditor de Capacidades em modo read-only e de forma sequencial.
