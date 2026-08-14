# IA-02 — Controle de tráfego Z.AI / GLM-4.7-Flash

Data: 2026-08-14

## Evidência de origem

O diagnóstico controlado do API ML comprovou HTTP 429 com código Z.AI `1305` ao chamar `glm-4.7-flash`. A integração, autenticação e endpoint já haviam sido isolados dos dados de negócio.

## Controle implementado

O caminho operacional Z.AI agora usa um adapter guardado instalado pelo `ProviderManager` público do pacote `market_intelligence.ai`.

O adapter:

- limita a concorrência local Z.AI a 1 requisição por processo;
- mantém requisições adicionais aguardando o gate local;
- respeita `Retry-After` quando fornecido pelo provedor;
- aceita `Retry-After` em segundos ou HTTP-date;
- limita `Retry-After` a 60 segundos;
- aplica backoff exponencial determinístico quando o cabeçalho não existe;
- limita o backoff a 30 segundos;
- preserva cooldown local após HTTP 429, inclusive quando o retry automático está desabilitado;
- permite no máximo a quantidade de retries já definida no perfil de IA;
- não lê nem registra o corpo do erro para decidir retry;
- não registra chave, Authorization ou resposta textual do provedor.

Para o sandbox continua valendo o limite anterior: no máximo um retry configurado, `store=false`, prompt sintético fixo e sem dados de negócio.

## Limite arquitetural explícito

`InProcessProviderTrafficGate` coordena somente requisições dentro de um processo do API ML. Ele reduz burst local e protege o adapter, mas não substitui a fila persistente de jobs/orquestração quando houver múltiplos processos, réplicas ou workers.

A coordenação multi-worker deverá ser feita pela camada persistente já responsável por jobs e execução, evitando introduzir estado distribuído dentro do adapter de provedor.

## Critério de validação

A alteração só pode ser promovida se o CI comprovar:

- cálculo e limite de `Retry-After`;
- fallback exponencial;
- limite de concorrência e cooldown;
- retry único de uma resposta 429 sintética seguido de sucesso;
- `ProviderManager` público entregando o adapter Z.AI guardado;
- nenhuma regressão na suíte integral.

Nenhuma chamada externa Z.AI é necessária para validar esta alteração estrutural.
