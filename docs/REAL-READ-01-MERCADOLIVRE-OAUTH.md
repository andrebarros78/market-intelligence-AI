# REAL-READ-01 — OAuth real Mercado Livre somente leitura

Estado: PREPARACAO TECNICA

Objetivo: habilitar a primeira conexão real do adapter Mercado Livre sem liberar qualquer escrita de negócio.

Portões invariantes:

- `MI_READ_ONLY=true`.
- `MI_ALLOW_MARKETPLACE_WRITES=false`.
- rede real Mercado Livre desligada por padrão.
- OAuth real usa Authorization Code + `state` de uso único + PKCE S256.
- `Client Secret`, authorization code, access token e refresh token nunca são persistidos em claro nem enviados a logs.
- a primeira consulta após a troca de token é exclusivamente `GET /users/me`.
- a identidade retornada por `/users/me` é a chave de vinculação da credencial; identificador informado pelo operador nunca substitui a identidade observada.
- chamadas de negócio continuam limitadas a `GET` pelo `Module01SecurityPolicy`.
- POST é permitido apenas no cliente OAuth e apenas para `https://api.mercadolibre.com/oauth/token`.
- redirect URI deve ser HTTPS, estática e corresponder à registrada no DevCenter.
- o runtime sintético permanece separado e continua sendo a base de CI sem rede real.

Configuração protegida prevista:

```text
MI_ML_REAL_READ_ENABLED=false
MI_ML_APP_ID=<identificador publico da aplicacao>
MI_ML_CLIENT_SECRET=<segredo fora do Git>
MI_ML_REDIRECT_URI=https://<callback registrado>/v1/oauth/mercadolivre/callback
MI_ML_OAUTH_KEY_B64=<chave AES-256 em base64 fora do Git>
```

Critério do Gate 1:

1. configuração segura presente;
2. aplicação no DevCenter configurada com escopo somente leitura e PKCE;
3. callback HTTPS válido;
4. autorização humana concluída no Mercado Livre;
5. troca de code por token concluída sem vazamento;
6. `GET /users/me` retorna 2xx;
7. identidade é persistida com tokens cifrados;
8. telemetria sanitizada da primeira leitura é registrada;
9. nenhuma escrita de marketplace é possível.

Somente após o Gate 1 será executado o Auditor de Capacidades em modo read-only e de forma sequencial.
