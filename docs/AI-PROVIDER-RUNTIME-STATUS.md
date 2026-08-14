# Status seguro das IAs do API ML

O módulo `market_intelligence.ai.status` expõe somente metadados não secretos de configuração para os papéis `system` e `agents`.

Campos permitidos: papel, provedor, modelo, host do endpoint, booleano de configuração, `credential_exposed=false`, `inference_enabled=false`, `store_enabled` e número de retries.

Nenhuma API key, header de autenticação ou valor de Secret pode aparecer no status, em logs ou em respostas HTTP futuras que reutilizem esse contrato.
