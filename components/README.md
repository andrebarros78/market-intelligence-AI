# Baseline limpo de componentes

Baseline: `2026-08-12-initial`

Os arquivos-fonte limpos são armazenados como assets da Release correspondente deste repositório. Cada pacote possui origem, tag, commit e SHA-256 registrados em `resolved.json`.

| Componente | Estágio | Ref fixada | Commit |
|---|---|---|---|
| higress | core_now | `v2.2.3` | `39ec41aab6eb` |
| temporal-server | core_now | `v1.31.2` | `19a774302c61` |
| temporal-python-sdk | core_now | `1.31.0` | `84b519e0ff40` |
| fastapi | core_now | `0.141.1` | `95f8322ee1dc` |
| pydantic | core_now | `v2.13.4` | `cf67d4b3193c` |
| httpx | core_now | `0.28.1` | `26d48e0634e6` |
| authlib | core_now | `v1.7.2` | `a0b76fac3fa1` |
| sqlalchemy | core_now | `rel_2_0_52` | `190990768104` |
| alembic | core_now | `rel_1_19_1` | `efe73dec1397` |
| cryptography | core_now | `50.0.0` | `dcb7050b807b` |
| postgresql | core_now | `REL_18_3` | `62d6c7d3df62` |
| duckdb | core_now | `v1.5.5` | `d8cdaa33fda8` |
| polars | core_now | `rs-0.55.2` | `d7488c71ecfb` |
| pyod | analytics_later | `v3.6.4` | `3d0169a32ab8` |
| pgvector | prepared_later | `v0.8.6` | `8ee86c96f0fd` |
| statsforecast | analytics_later | `v2.1.1` | `264166ec0ddb` |
| opentelemetry-python | observability_later | `v1.44.0` | `53a5a40c9604` |
| prometheus | observability_later | `v3.13.2` | `bb5dff00cf8f` |

## Verificação

Baixe os assets da Release e execute `sha256sum -c components/CHECKSUMS.sha256` no mesmo diretório dos pacotes.

Nenhum pacote deste baseline utiliza uma referência móvel `latest` depois da captura.
