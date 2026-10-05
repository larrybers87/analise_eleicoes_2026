# Log de decisões

Formato: ID · data · decisão · motivo · alternativas descartadas. Nova decisão não-trivial = nova entrada no fim.

## D-001 · 2026-10-05 · Python + Parquet + DuckDB; front estático com MapLibre
Motivo: stack que o usuário domina; Parquet/DuckDB aguentam o volume por seção (~470 mil seções × candidatos) sem banco servidor; site estático é publicável de graça (GitHub Pages).
Alternativas: Streamlit/Dash (mais rápido de começar, mas drill-down de mapa fica pior e exige servidor); PostgreSQL+PostGIS (overkill para dado estático).

## D-002 · 2026-10-05 · Fase 1 pela API JSON do TSE (município); fase 2 pelos CSV do Dados Abertos (zona/seção)
Motivo: a API JSON já tem o resultado final por município incluindo exterior; os CSVs de seção/zona de 2026 ainda não foram publicados.
Alternativas: baixar todos os BUs por seção já agora (viável, mas ~470 mil requisições e parser de BU; fica como plano B se os CSVs demorarem).

## D-003 · 2026-10-05 · Ambiente conda `eleicao2026` via `environment.yml`
Motivo: usuário usa Anaconda no Windows; `geopandas`/`geobr` instalam sem dor pelo conda-forge.
Alternativas: `uv` + venv (mais rápido, mas GDAL/Shapely no Windows dão mais trabalho via pip).

## D-004 · 2026-10-05 · Cor por mistura ponderada em OKLab (a validar visualmente)
Motivo: mistura em RGB gera tons barrentos; OKLab é perceptualmente uniforme.
Ressalva: com 3+ candidatos fortes a mistura tende a cinza e perde legibilidade. Manter como modo alternativo "vencedor + intensidade pela margem" (escala sequencial na cor do vencedor) e deixar o usuário alternar no mapa.
