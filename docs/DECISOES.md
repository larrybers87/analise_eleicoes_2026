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

## D-005 · 2026-10-05 · Documentar schema do EA12/EA20 por inspeção direta do JSON, sem os PDFs oficiais
Motivo: `www.tse.jus.br` e `divulgacandcontas.tse.jus.br` (onde ficam os PDFs EA12/EA20) retornam 403 para o IP do ambiente de execução — bloqueio de rede, não relacionado ao rate limit de resultados (`resultados.tse.jus.br` funciona normalmente). Baixamos as 3 fontes de teste e documentamos os campos reais em `docs/DADOS.md` a partir do JSON.
Alternativas: esperar acesso aos PDFs fora deste ambiente antes de prosseguir (descartada — atrasaria a coleta sem necessidade; a inspeção direta já deu campos suficientes e consistentes para o parser).

## D-006 · 2026-10-05 · Coleta completa com worker pool (fila + N tasks) em vez de `asyncio.gather` simples
Motivo: com ~5786 itens, `gather` com `return_exceptions=True` deixaria tasks já em voo continuarem batendo no TSE mesmo depois de um 403/429/abort-por-404 (justamente o cenário que a skill `tse-dados` proíbe). Fila + 10 workers (igual ao `MAX_CONCORRENCIA` do `TseClient`) + `asyncio.Event` de abort garante que, ao detectar bloqueio, nenhum worker pega item novo da fila.
Alternativas: `gather` simples (mais simples de escrever, mas não corta requisições em voo ao abortar); sequencial sem concorrência (correto mas ~3-5x mais lento que o rate limit permite).

## D-007 · 2026-10-05 · Versionar os 6 Parquet de `presidente_t1_*` (nível BR/UF/município)
Motivo: total ~1,3MB (bem abaixo de qualquer limite prático do GitHub); CLAUDE.md já previa versionar "só os pequenos" em `data/processed/`. Ajustamos `.gitignore` para liberar só esses 6 arquivos nominalmente (continua bloqueando `*.parquet` de seção/zona, que serão grandes).
Alternativas: deixar fora do git e depender só de regeneração via `coletar_presidente.py`+`processar_presidente.py` (descartada por ora — o usuário/CI ainda não tem forma de regenerar sem rodar a coleta completa de novo, ~10min; reconsiderar quando o pipeline estiver mais maduro ou se o repo crescer demais).

## D-008 · 2026-10-05 · Correção: campos `p<campo>n` do EA20 usam vírgula decimal, não ponto
Motivo: a etapa 1 documentou (incorretamente) que `p<campo>n` usava ponto decimal, com base numa amostra que coincidentemente não tinha parte fracionária (`"100"`/`"0"`). A coleta completa expôs o erro ao parsear `pvapn` (ex. `"57,499675335"`) como float. Corrigido em `parse_ea20._float` (`.replace(",", ".")`) e em `docs/DADOS.md`.
Alternativas: nenhuma — é uma correção factual, não uma escolha de design.
