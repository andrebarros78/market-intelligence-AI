# Market Intelligence AI

Baseline técnico do projeto **Market Intelligence IA**.

Este repositório preserva a arquitetura própria do produto e mantém componentes de terceiros em baselines limpas, rastreáveis e reproduzíveis.

## Regra de componentes

Código de terceiros não é misturado ao código autoral do Market Intelligence IA.

Cada componente aprovado possui:

- repositório oficial de origem;
- função no projeto;
- estágio de adoção;
- tag/commit resolvido na captura;
- SHA-256 do pacote preservado;
- licença e avisos mantidos dentro do snapshot original.

As cópias limpas são empacotadas a partir do código-fonte oficial e armazenadas como **assets de uma Release deste próprio repositório**. O Git normal mantém apenas os manifestos e hashes, evitando inflar permanentemente o histórico com centenas de megabytes de dependências externas.

## Separação arquitetural

- `Market Intelligence AI`: núcleo de integração, dados e inteligência.
- `andrebarros78/painel`: interface/control plane NocoBase, desacoplada do núcleo.
- Higress: gateway entre o painel/IA e as APIs autorizadas.

NocoBase não é duplicado neste repositório.

## Estado

Baseline inicial de componentes em preparação.
