# STATUS

Última atualização: 2026-10-05 — paleta de cores APROVADA; agente `mapa-web` criado; planejando F2 (mapa web).

## Feito
- Estrutura de pastas, `CLAUDE.md`, docs (`DADOS.md`, `DECISOES.md`, `ROADMAP.md`), `.gitignore`, `environment.yml`, `pyproject.toml`.
- Configuração do Claude Code: `.claude/settings.json`, agentes `coletor-tse` e `analista-eleitoral`, skills `fechar-sessao` e `tse-dados`.
- Repositório conectado ao GitHub: https://github.com/larrybers87/analise_eleicoes_2026. Ambiente conda `eleicao2026` criado.
- `src/eleicao/tse_client.py` + `scripts/validar_fontes.py`: cliente async com rate limit/cache/retry/abort; 3 arquivos de teste validados (etapa 1).
- **Coleta completa (etapa 2)**: `scripts/coletar_presidente.py` baixou os 5786 arquivos (1 BR + 28 UF + 5757 municípios, inclui exterior `zz`) em 10min33s, 0 404/0 erro, `data/raw/ele2026/6257/` (~52,7MB, 5787 arquivos) — log em `data/raw/coleta_6257.log` (não versionado).
- `src/eleicao/parse_ea20.py`: parser puro do EA20 (BR/UF/município) → `(df_candidatos, df_totais)`.
- `scripts/processar_presidente.py`: gera os 6 Parquet em `data/processed/` (`presidente_t1_{municipio,uf,br}[_totais].parquet`), versionados (~1,3MB total; `.gitignore` ajustado para liberar só esses 6 arquivos).
- `scripts/diagnostico_join_ibge.py`: join TSE↔IBGE (`geobr.read_municipality(year=2024)`) por `cd_mun_ibge` — 100% de correspondência (5571=5571), 0 órfão de cada lado; os 186 municípios do exterior não entram no join (esperado, sem `cdi`).
- **Conferência com a spec oficial (etapa 3)**: PDFs EA10/EA12/EA20 em `docs/specs/`; confrontamos parser e testes contra a spec — 5 correções em `src/eleicao/parse_ea20.py`/`tests/test_invariantes.py` (fórmula completa de `tv`, `eleito`→`classificado`, campos-raiz `md`/`tf`/`dv`, invariante `c+a==esi`). Detalhes em `docs/DADOS.md` → "Confronto com a especificação oficial".
- **Investigação BA/MG (etapa 4)**: `scripts/diagnostico_ba_mg.py` comparou `dg`/`hg`/`idg` de município vs UF — confirmou que os 11 municípios divergentes serviam uma geração de 04/10 ~21:00 (`idg`~1,8M) enquanto as UFs já estavam em 05/10 ~02:59 (`idg`~2,79M). `coletar_presidente.py` ganhou a opção `--apenas` (lista explícita `uf:<sigla>`/`mun:<uf>:<cd>`/`br`, usar com `--force`) para rebaixar só os 13 arquivos afetados sem "varrer tudo de novo". Resultado: **MG convergiu** (nova geração, `and=f`, `snt=0` em todos os 8); **BA não convergiu** (os 3 municípios voltaram com os mesmos bytes antigos mesmo com `--force` — pendência do backend do TSE, fora do nosso controle).
- `data/known_issues.csv`: catálogo da divergência residual de BA (12 linhas: 5 campos de totais + 7 candidatos, todas < 0,02% do total da UF). `tests/test_invariantes.py` agora exige igualdade exata entre divergências observadas e catalogadas (21 testes, **21 passam**).
- `data/processed/snapshot_6257.json`: geração exata (`idg`/`dg`/`hg`) do arquivo BR + horários da coleta completa e da atualização dirigida BA/MG — registra "a que versão do TSE" os Parquet correspondem.
- **Agentes**: `model: sonnet` fixado no frontmatter de `coletor-tse` e `analista-eleitoral` (D-012); futuro agente de mapa (F2) nasce com `model: opus`.
- `scripts/verificar_atualizacoes.py`: rotina de manutenção — rebaixa com `--force` só o BR e os itens de `data/known_issues.csv` (UF/município extraídos dinamicamente da coluna `cd_mun_tse`, agora populada e pipe-separada), compara geração com `snapshot_6257.json`, e só reprocessa Parquet/roda testes/atualiza known_issues se algo mudou. Uso documentado no `README.md`. Testado 2x nesta sessão: divergência de BA **ainda não convergiu** do lado do TSE.
- **Paleta de cores — v1 proposta** (D-013): `config/candidatos.yaml`, `src/eleicao/cores.py` (`mistura_oklab`, `vencedor_margem` v1, `simular_daltonismo`, `distancia_oklab`), preview em `notebooks/01_paleta.ipynb`/`docs/img/paleta_preview.png` (mapa por UF).
- **Paleta de cores — v2, revisão pedida pelo usuário** (D-014): faixa de matiz `FAIXA_RESERVADA_PT_PL` (260°–30° em OKLCH, medida varrendo o gradiente PT↔PL) reservada só para a mistura PT×PL — nenhum outro candidato pode cair nela; Renan Santos (4º) movido para ciano (H=200°), Ronaldo Caiado (5º) promovido a croma médio em âmbar (H=75°, antes croma baixo), os 7 candidatos <1% dos válidos viraram CINZA (C=0, `L` espaçado 0,35–0,77) em vez de hues de croma baixo (colidiam sob deuteranopia, ΔE~0,5–2,6). `vencedor_margem` reescrito: `MARGEM_SATURACAO=0.40` (40pp já satura), interpolação linear em OKLab entre `NEUTRO_EMPATE_HEX` (acromático, L=0,92 — empate exato não carrega hue de nenhum candidato) e a cor plena do vencedor. Nova `agrupar_outros`/`COR_OUTROS` para legendas (não usada no mapa). `tests/test_cores.py`: 39 testes (whole suite).
- **Paleta de cores — APROVADA** (complemento D-013): Ronaldo Caiado vence **0 municípios** em todo o Brasil (`presidente_t1_municipio.parquet`) — ΔE(Caiado×PT)=0,063 sob deuteranopia nunca aparece no mapa de vitória (só em swatch de legenda). Risco aceito pelo usuário; `config/candidatos.yaml`/`src/eleicao/cores.py` congelados como v1 do mapa (ver F2).

## Em andamento
- (nada)

## Próximo (em ordem)
1. Usuário aprova (ou pede novo ajuste) da paleta de cores v2 — ver `docs/img/paleta_preview.png` e as 3 decisões de design marcadas em `config/candidatos.yaml` (cinza nos candidatos <1%; Caiado âmbar com ΔE baixo contra PT sob deuteranopia).
2. F2: mapa v1 em `web/` (MapLibre), Brasil → UF → município, usando `presidente_t1_municipio*.parquet` + `src/eleicao/cores.py`.
3. Acompanhar `matematicamente_definido` (`md`) da BR — já `"s"` (2º turno) em 05/10/2026; quando `tf_judicial` virar `"s"`, `situacao`/`classificado` dos candidatos passam a ser confiáveis para saber quem avança. Rodar `scripts/verificar_atualizacoes.py` periodicamente até lá.

## Bloqueios / dúvidas abertas
- **Divergência residual de BA (3 municípios) sem solução do nosso lado**: confirmada de novo via `scripts/verificar_atualizacoes.py` nesta sessão — o backend do TSE segue servindo uma geração de 04/10 ~21:00 para `ba33693`/`ba34673`/`ba36013`, mesmo sob `--force`. Catalogada em `data/known_issues.csv`; todas as diferenças são < 0,02% dos totais da UF. Rodar `scripts/verificar_atualizacoes.py` periodicamente.
- Data de publicação dos CSVs de seção/zona 2026 no Dados Abertos: desconhecida. Checar semanalmente.
- **Ambiente Windows tem 2 outras instalações de conda/miniconda no `PATH` do sistema** (`C:\ProgramData\miniconda3` e `C:\Users\Usuário\miniconda3`, distintas de `C:\Users\Usuário\Miniconda3\envs\eleicao2026` usada pelo projeto) — causou `DeadKernelError` em matplotlib/Jupyter por conflito de DLL (`freetype`/`libpng`); contornado prefixando `PATH` com `...\envs\eleicao2026\Library\bin` antes de rodar o kernel. Não é um problema do projeto, mas vale limpar o `PATH` do sistema ou documentar o workaround se notebooks voltarem a travar.
