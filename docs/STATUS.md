# STATUS

Última atualização: 2026-10-08 - `web/` atualizado para o snapshot final do T1; F5a (projeção do 2º turno) entregue; divergência da BA resolvida.

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
- **F3 fase B — página de análises e modo Swing ENTREGUE (06/10/2026, D-030)**:
  - `web/analises.html` + `web/js/analises.js` (Observable Plot 0.6.17 + d3 via CDN): 6 seções com link "ver no mapa"; status "provisório" enquanto `tf="n"`. Números só de `web/data/analises.json` (`scripts/exportar_analises.py` → `src/eleicao/analise/site.py`); `tests/test_exportar_analises.py` confere cada número contra o achado do `ANALISES.md` e proíbe dígitos no HTML.
  - Mapa: modo **"Swing 2022→2026"** (botão no grupo base, `?modo=swing`): Δmargem PL−PT, `cores.escala_divergente_assimetrica` (limites por lado, D-031: −8,64 p.p. = p95 dos 58 municípios que andaram para o PT; +27,34 p.p. = p99 dos 5.512 que andaram para o PL), `resultados/swing.json`, swing por UF em `br.json`; Boa Esperança do Norte/MT sem par, com hachura e motivo no tooltip. Link "Análises" no topo.
  - Empates exatos sem vencedor no export do mapa (usa `analise.base.vencedor_municipal`): painel com **Flávio 2.906, Lula 2.663, 2 empates** (antes 2.908 para Flávio). Bissau (exterior) também virou empate.
  - Novas funções testadas: `swing.delta_margem_municipal`/`_agregado`/`limites_escala_delta`. `docs/ANALISES.md`: definição da Δmargem (+7,1 p.p.) no achado 2 e correção do PT no Sudeste (−2,9, estava −3,0).
  - Dados novos: +209,5KB brutos / +74,0KB gzip. `verificar_export_web.py`: **540 verificações, 0 falhas**. `pytest -q`: **285 passam**.
  - Prints: `docs/img/analises_preview_*.png`, `docs/img/mapa_preview_f3b_*.png`.
- **Acabamento para divulgação (06/10/2026, D-031, D-032)**: escala do swing com um percentil por lado (−8,64 / +27,34 p.p.); Open Graph/Twitter Card com `web/img/og.png` (1200×627, `scripts/gerar_og.py`); rodapé "projeto pessoal e não oficial" nas duas páginas; README como vitrine; `LICENSE` MIT; favicon; correções de acessibilidade apontadas pelo Lighthouse (ver notas no relatório da sessão). Links das duas páginas checados (200) e console sem erros em desktop e 375px.
- **T1 2026 final (08/10/2026)**: recoleta completa; BR `idg` 2837531 (05/10/2026 12:51:47), `and="f"`, `tf="s"`. Divergência da BA resolvida (`data/known_issues.csv` vazio; município = UF = BR com 0 divergência). Snapshot em `data/processed/snapshot_t1_2026.json` (`scripts/gerar_snapshot_t1.py`). Presidente 2018 (T1 e T2, município) também em `data/processed/` (`scripts/processar_presidente_2018.py`).
- **`web/` no snapshot final do T1 (08/10/2026)**: `exportar_web.py --sem-geometria` e `exportar_analises.py` regerados sobre o `idg` 2837531; só 3 municípios da BA mudaram (os da antiga divergência), nenhum vencedor mudou (Flávio 2.906, Lula 2.663, 2 empates), textos da página de análises iguais. Selo inicial de `analises.html` neutro (o JS decide entre provisório e final) e rodapés sem "provisórios até a totalização final". `verificar_export_web.py`: 540 verificações, 0 falhas. 23 prints de `docs/img/` regerados com o carimbo final por `scripts/capturar_prints.py` (Playwright; sobe e derruba o `http.server`; lista declarativa de arquivo/viewport/estado). `analises_preview_celular_renda.png` não mudou (sem carimbo).
- **F5a - projeção do 2º turno por inferência ecológica ENTREGUE (08/10/2026, D-033, D-034)**:
  - Módulos `src/eleicao/inferencia_ecologica.py` (Goodman restrito com cvxpy, shrinkage por UF, regressão de composição, bootstrap estratificado, baselines, métricas) e `src/eleicao/projecao_t2.py` (cenários, projeção, saídas); `config/projecao_t2.yaml` APROVADO; scripts `ajuste_2022_insample.py`, `backtest_2018_2022.py`, `projetar_t2_2026.py`, `comparar_projecao_t2.py` (pronto, NÃO executado: espera a eleição 6258).
  - Backtest 2018→2022 (fora da amostra): modelo de referência = terceiros por composição com matriz nacional (erro BR de -0,06 p.p., em boa parte compensação de erros); modelo por blocos puro erra -1,8 p.p. Faixa heurística (n=1) de ±2 p.p. (BR), ±2,5 p.p. (UF), ±1,5 p.p. de abstenção.
  - Saídas: `data/processed/projecao_t2_2026_{municipio,uf,br}.parquet` (+ `sem_par.csv`, `linhas_compostas.csv`), formato longo por `cenario`; metadados do snapshot (`t1_idg`, `t1_and`, `t1_tf`) nas colunas. Resultados: ver a seção 7 do `docs/METODO_PROJECAO.md` (mantida fora do commit público).
  - D-035 (emenda à D-034): viés de abstenção da identidade (cenário `identidade_sem_retorno_abst`), IC bootstrap indicativo (Andrews 2000), exterior com matriz nacional na base (`zz_propria` vira cenário).
  - Documento: `docs/METODO_PROJECAO.md`. Notebook: `notebooks/f5a_projecao_t2.ipynb`. Testes: `tests/test_inferencia_ecologica.py`, `tests/test_projecao_t2.py`.
- **Ambiente**: `ruff check .` e `ruff format --check .` verdes. Notebooks de análise com ignores só de formato (`pyproject.toml`, `per-file-ignores`); erros reais continuam valendo.

## Em andamento
- (nada). Aguardando a eleição 6258 (25/10/2026) para rodar `scripts/comparar_projecao_t2.py`.

## Próximo (em ordem)
0. **Pós-25/10**: coletar o T2 2026 (eleição 6258) com o coletor-tse, gerar os parquet `presidente_t2_*` e rodar `scripts/comparar_projecao_t2.py` (projeção contra o resultado e matriz real T1→T2).
1. **Usuário revisar a página de análises e o modo Swing** (D-030, D-031).
2. **Usuário revisar as decisões** D-020 a D-029 (principalmente D-021 corte de 10 mil, D-024 BH bicaudal, D-025 bolsão = estado para Caiado, D-023 teto/lente) e confirmar o conserto do BLAS nos outros clones (`environment.yml` já tem a fixação).
3. Acompanhar eventuais retotalizações do T1 (snapshot atual: final, `idg` 2837531, `and="f"`, `tf="s"`). Rodar `scripts/verificar_atualizacoes.py` e, se os números mudarem, rodar `exportar_web.py --sem-geometria`, `exportar_analises.py` e `pytest tests/test_exportar_analises.py` (aponta o que mudou), e atualizar `docs/ANALISES.md`.
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
- **Pendência (resultados da F5a)**: merge de `f5a-resultados` em `main` + push após totalização do T2 (≥26/10). O branch local `f5a-resultados` (sem upstream) tem `projecao_t2_2026_br.parquet`, `projecao_t2_2026_uf.parquet` (exceção no `.gitignore`), `projecao_t2_2026_linhas_compostas.csv` e a seção 7 do `METODO_PROJECAO.md`. `main` não recebe nada disso antes.
- **Projeção F5a**: modelo único de n=1 backtest; retenção por identidade e demais premissas não testáveis em `docs/METODO_PROJECAO.md`. As linhas compostas de `outros_2026` e do exterior têm IC muito largo (ver o documento).
- `.gitignore`: `projecao_t2_2026_municipio.parquet` (4,7 MB) e os parquet de 2018 continuam fora do git; só `projecao_t2_2026_br` e `_uf` ganham exceção (commit local).
- **Lighthouse em produção (06/10/2026)**, desempenho / acessibilidade / boas práticas / SEO: mapa no desktop 98/100/100/100, mapa no celular **51**/100/100/100, análises no desktop 93/100/100/100, análises no celular 86/100/100/100. Pendências: no celular, o MapLibre bloqueia a thread principal (~700 ms de TBT, custo de terceiro); o painel do mapa (CLS 0,25) e o texto da seção 1 das análises (CLS 0,17) mudam de altura quando o JSON chega. Nenhuma das duas correções é barata.
- **Swing do município-mãe de Boa Esperança do Norte/MT**: o município novo saiu do território de outro(s) entre 2022 e 2026, então o swing do município de origem compara áreas diferentes. Não tratado (D-023 só exclui o município novo).
- **Malha municipal fora de `data/processed/`**: as análises de área (12) e de vizinhança (16) leem a malha do `geobr` (`carga.geometria_municipios_2024`), não um arquivo processado. É a única entrada externa às análises (documentado em `DADOS.md`). Se o usuário preferir regra estrita (só `data/processed/`), é preciso gerar um Parquet da malha, que fica grande demais para versionar.
- **Bolsão de Caiado = estado de GO** (237 de 246 municípios): é uma propriedade do limiar de 3×, não um território. Decisão registrada em D-025; o usuário pode preferir outra regra.
- Data de publicação dos CSVs de seção/zona 2026: desconhecida.
- `www.ibge.gov.br` e `www.tse.jus.br` retornam 403 neste ambiente; as fontes usadas (SIDRA, FTP do IBGE, `resultados.tse.jus.br`, `dadosabertos.tse.jus.br`) funcionam.
- **Ambiente Windows tem 2 outras instalações de conda no `PATH`** (`C:\ProgramData\miniconda3`, `C:\Users\Usuário\miniconda3`): causou `DeadKernelError` em Jupyter por conflito de DLL; contornado prefixando `envs\eleicao2026\Library\bin`. Limpar o `PATH` ou documentar se voltar.
- `data/raw/dadosabertos/` com ~1GB (não versionado).
- Manaus/AM (2022): diferença residual de 84 votos entre `comparecimento+abstenção` e `eleitorado` (0,006%), não investigada a fundo.
