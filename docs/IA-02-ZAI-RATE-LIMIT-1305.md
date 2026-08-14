# IA-02 — Diagnóstico comprovado Z.AI / GLM-4.7-Flash

Data: 2026-08-14

## Correção de diagnóstico

O diagnóstico anterior `MISSION_BLOCKED_EXTERNAL_ZAI_MODEL_ACCESS` foi superado por evidência mais específica.

A ausência de `glm-4.7-flash` na resposta do endpoint de listagem de modelos não deve ser tratada isoladamente como prova de falta de acesso ao modelo. A documentação oficial da Z.AI inclui `glm-4.7-flash` no endpoint de Chat Completion e o classifica como modelo gratuito.

## Teste controlado definitivo do erro

Workflow: `ZAI 429 Diagnostic`

Run: `31819272899`

Job: `94828359494`

Commit: `d31209521e0a4d9f31d437fb32884e18104add19`

A chamada foi feita para:

- endpoint: `https://api.z.ai/api/paas/v4/chat/completions`;
- modelo: `glm-4.7-flash`;
- autenticação: `Authorization: Bearer <secret>`;
- prompt: sintético e fixo;
- `thinking`: disabled;
- `stream`: false;
- `max_tokens`: 32;
- nenhum dado de negócio;
- nenhuma credencial impressa;
- nenhuma mensagem bruta do provedor persistida.

Resultado sanitizado:

```json
{
  "business_data_sent": false,
  "http_status": 429,
  "model": "glm-4.7-flash",
  "status": "provider_error",
  "zai_code": "1305"
}
```

## Interpretação

O código Z.AI `1305` significa que a API acionou um rate limit.

Portanto, a causa comprovada atual é:

`MISSION_BLOCKED_EXTERNAL_ZAI_RATE_LIMIT_1305`

Não há evidência, neste teste, de:

- chave ausente;
- chave não enviada;
- autenticação 401/403;
- endpoint incorreto;
- envio de dados do Mercado Livre;
- falha estrutural no API ML.

## Estado da IA-02

- OpenAI / GPT sistema: sandbox real comprovado.
- Z.AI / GLM-4.7-Flash agentes: integração construída e requisição chega ao provedor, mas a inferência é bloqueada externamente pelo rate limit `1305`.
- CI estrutural permanece separado do gate externo.

A IA-02 somente poderá ser declarada `MISSION_PROVEN` quando uma inferência sintética GLM-4.7-Flash concluir com HTTP 2xx e saída válida, sem dados de negócio e sem exposição de credenciais.
