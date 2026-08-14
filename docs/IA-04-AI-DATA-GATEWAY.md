# IA-04 — Gateway de Dados para IA

Data: 2026-08-14

## Objetivo

Impedir que dados brutos do Mercado Livre, credenciais ou dados pessoais sejam encaminhados diretamente a qualquer provedor de IA.

## Princípio

O gateway opera por **allowlist por finalidade**. Ele não tenta tornar um objeto bruto seguro removendo alguns campos; em vez disso, descarta tudo que não faça parte do contrato analítico aprovado.

Finalidades iniciais:

- `radar_alert_explanation`;
- `radar_investigation_summary`;
- `synthetic_test`.

Qualquer finalidade desconhecida falha fechada.

## Controles

- somente campos analíticos explicitamente permitidos;
- denylist independente para nomes de credenciais e PII;
- e-mail, Bearer e prefixos comuns de segredo bloqueados mesmo dentro de campo permitido;
- objetos aninhados e estruturas complexas bloqueados;
- listas somente de escalares e com limite de tamanho;
- strings limitadas;
- payload serializado limitado a 8 KiB;
- números não finitos bloqueados;
- SHA-256 canônico da entrada e saída para evidência sem registrar a entrada bruta;
- nenhum valor de credencial é retornado pelo resultado;
- o resultado declara explicitamente `credential_exposed=false`, `pii_exposed=false` e `business_data_minimized=true`.

## Separação de responsabilidades

O gateway não executa inferência e não conhece API keys. Ele transforma um contrato analítico interno em um envelope minimizado. A fila Temporal e os adapters de provedor permanecem responsáveis pela execução.

## Regra de integração

Nenhum fluxo futuro de IA poderá aceitar um objeto bruto de marketplace. A entrada deverá passar por `AIDataGateway.minimize(...)` e o payload de inferência será construído somente a partir do resultado minimizado.

A IA-03 continua bloqueando qualquer modo não-sandbox até a integração desse envelope ser implementada e testada.

## Gate IA-04

A fase é aprovada quando o CI comprovar:

1. unknown fields são descartados;
2. credenciais/PII por nome são descartadas;
3. conteúdo sensível em campo permitido é bloqueado;
4. objetos aninhados não atravessam;
5. limites de string/lista/payload são aplicados;
6. hashes são determinísticos;
7. números inválidos são bloqueados;
8. nenhum teste exige chamada externa.
