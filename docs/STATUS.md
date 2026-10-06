# STATUS

Última atualização: 2026-10-06 — F3 fase A entregue (análises exploratórias 10–17, `docs/ANALISES.md`); crash do numpy/scipy diagnosticado e corrigido (BLAS).

## Feito
- **F0 (setup)**: estrutura de pastas, `CLAUDE.md`, docs, `.gitignore`, `environment.yml`, `pyproject.toml`; `.claude/` com agentes `coletor-tse`/`analista-eleitoral` e skills `fechar-sessao`/`tse-dados`; repo no GitHub; ambiente `eleicao2026`.
- **F1 (base Presidente 1º turno 2026)**: cliente async com rate limit/cache (`src/eleicao/tse_client.py`); coleta completa de 5.786 arquivos (BR + 28 UF + 5.757 municípios, inclui exterior `zz`), 0 erro; parser EA20 (`src/eleicao/parse_ea20.py`) conferido com a spec oficial (`docs/specs/`); 6 Parquet versionados em `data/processed/`; join TSE↔IBGE 5.571=5.571. Divergência residual da BA em `data/known_issues.csv` (MG convergiu; BA depende do backend do TSE). Testes de invariantes em `tests/test_invariantes.py`.
- **Paleta (D-013, D-014)**: `config/candidatos.yaml`, `src/eleicao/cores.py` (mistura OKLab, `vencedor_margem`, `agrupar_outros`/`COR_OUTROS`), aprovada pelo usuário.
- **F2 (mapa web v1) e F2.2 (seleção de candidato)**: `scripts/exportar_web.py` gera `web/data/` (geometria TopoJSON sobre a malha completa do geobr, D-016); `web/` MapLibre estático com drill-down Brasil↔UF↔município, modos de cor, seleção de candidato ("Onde venceu" e "Força"), exterior em tabela, estado na URL. `scripts/verificar_export_web.py` (391 verificações, 0 falhas). Publicado no GitHub Pages (`.github/workflows/pages.yml`).
- **F3 base de enriquecimento (D-019)**: Presidente 2022 (1º e 2º turno, município), perfil do eleitorado 2026 (sexo, faixa etária com derivadas 16–17/70+, escolaridade), IBGE (população Censo 2022; PIB per capita 2023). Schemas em `docs/DADOS.md`.
- **F3 fase A — análises exploratórias ENTREGUE (06/10/2026)**:
  - Pacote `src/eleicao/analise/`: `regioes`, `carga` (única camada de I/O), `base`, `composicao` (encadeia as funções para os notebooks), `participacao`, `concentracao`, `mapa_mente`, `geometria` (Albers), `swing`, `perfil` (WLS/VIF), `espacial` (Moran/LISA/BH), `bolsoes`, `graficos` (plots; não calcula).
  - Notebooks `notebooks/10_panorama` … `17_filho_da_terra` (executados sem erro); 16 figuras em `docs/img/analises/`; `docs/ANALISES.md` com 13 achados ranqueados e ressalvas.
  - `data/processed/capitais.csv` (27) gerado por `scripts/persistir_capitais.py`.
  - Testes novos: 64 (`tests/test_analise_base.py`, `_swing.py`, `_estat.py`, `_geometria.py` — o último usa a malha do geobr, marcador `geo`). Suíte: **173 passam**.
  - Decisões D-020 a D-029 em `docs/DECISOES.md` (dependências/BLAS, corte 10k, Albers, swing/sem-par/teto, BH bicaudal, redutos/bolsões, concentração, regiões/capitais, WLS, uniformidade).
- **Diagnóstico e correção do crash numérico (06/10/2026)**: no env `eleicao2026`, numpy/scipy com MKL 2026.1.0 derrubavam o processo (`Windows fatal exception 0xc06d007f`, exit 127, sem traceback) em `np.cov`, `matmul`, `scipy.stats.spearmanr` e `scipy.stats.f_oneway`. Reproduzido isolado. Conserto: BLAS trocado para OpenBLAS (`conda install -c conda-forge "libblas=*=*openblas" "libcblas=*=*openblas" "liblapack=*=*openblas" numpy scipy`), verificado. Fixado em `environment.yml`. Substitutos em Python puro foram usados por um tempo e removidos depois do conserto. Registrado em `DECISOES.md` D-020 e `DADOS.md` (Armadilhas do ambiente).
- **Armadilhas corrigidas durante a F3 fase A**: 44 postos do exterior com zero votos válidos (0/0) viraram `sem_par` (não NaN); `bolsoes()` sem resultados perdia o esquema de colunas; agrupamento "Outros" perdia o código do candidato (legenda com números); `scipy` `pearsonr`/`spearmanr` e `f_oneway` ok após o conserto.
- **Ambiente**: `ruff check .` e `ruff format --check .` verdes. Notebooks de análise com ignores só de formato (`pyproject.toml`, `per-file-ignores`); erros reais continuam valendo.

## Em andamento
- (nada)

## Próximo (em ordem)
1. **Usuário revisar** `docs/ANALISES.md` e decidir quais achados viram seção no site (F3 fase B, pendente no `docs/ROADMAP.md`; `web/` não foi tocado).
2. **Usuário revisar as decisões** D-020 a D-029 (principalmente D-021 corte de 10 mil, D-024 BH bicaudal, D-025 bolsão = estado para Caiado, D-023 teto/lente) e confirmar o conserto do BLAS nos outros clones (`environment.yml` já tem a fixação).
3. Acompanhar a totalização: snapshot de 05/10/2026 (`and="p"`, `tf="n"`). Rodar `scripts/verificar_atualizacoes.py` e, se os números mudarem, rodar de novo `notebooks/10`–`17` e atualizar `docs/ANALISES.md`.
4. F2.1: geocodificação do exterior (186 postos → país/coordenadas).
5. Monitorar `matematicamente_definido` (`md`) e `tf_judicial` da BR; `situacao` só confiável após `tf="s"`.

## Publicação
- **Site**: https://larrybers87.github.io/analise_eleicoes_2026/ — deploy automático via `.github/workflows/pages.yml` (push em `main` tocando `web/**`, ou `workflow_dispatch`).
- Caminhos em `web/` relativos (sem barra inicial), testados em subcaminho.

## Auditoria do repositório (D-017)
- `AGENTS.md` removido. `git ls-files` sem cache, editor ou dado bruto.
- `notebooks/01_paleta.ipynb` limpo com `nbstripout` (histórico não reescrito, pedido do usuário).
- `nbstripout` é filtro git local: **rodar `nbstripout --install` em todo clone novo**. Os notebooks da F3 são commitados sem outputs; confirmar com `git diff --cached` antes de cada commit.
- `.gitignore` bloqueia `data/processed/*secao*` e `*zona*` (F4).

## Bloqueios / dúvidas abertas
- **Malha municipal fora de `data/processed/`**: as análises de área (12) e de vizinhança (16) leem a malha do `geobr` (`carga.geometria_municipios_2024`), não um arquivo processado. É a única entrada externa às análises (documentado em `DADOS.md`). Se o usuário preferir regra estrita (só `data/processed/`), é preciso gerar um Parquet da malha, que fica grande demais para versionar.
- **Divergência residual de BA (3 municípios)**: o backend do TSE segue servindo a geração antiga (`data/known_issues.csv`). Os totais das análises usam o valor do TSE, sem correção.
- **Bolsão de Caiado = estado de GO** (237 de 246 municípios): é uma propriedade do limiar de 3×, não um território. Decisão registrada em D-025; o usuário pode preferir outra regra.
- Data de publicação dos CSVs de seção/zona 2026: desconhecida.
- `www.ibge.gov.br` e `www.tse.jus.br` retornam 403 neste ambiente; as fontes usadas (SIDRA, FTP do IBGE, `resultados.tse.jus.br`, `dadosabertos.tse.jus.br`) funcionam.
- **Ambiente Windows tem 2 outras instalações de conda no `PATH`** (`C:\ProgramData\miniconda3`, `C:\Users\Usuário\miniconda3`): causou `DeadKernelError` em Jupyter por conflito de DLL; contornado prefixando `envs\eleicao2026\Library\bin`. Limpar o `PATH` ou documentar se voltar.
- `data/raw/dadosabertos/` com ~1GB (não versionado).
- Manaus/AM (2022): diferença residual de 84 votos entre `comparecimento+abstenção` e `eleitorado` (0,006%), não investigada a fundo.
