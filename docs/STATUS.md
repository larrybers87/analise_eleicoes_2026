# STATUS

Última atualização: 2026-10-05 — base de municípios fechada: BA/MG investigados, 21/21 invariantes passam.

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

## Em andamento
- (nada)

## Próximo (em ordem)
1. Paleta de cores dos candidatos (lista final: 12 candidatos, ver `presidente_t1_br.parquet`) — definir com o usuário.
2. F2: mapa v1 em `web/` (MapLibre), Brasil → UF → município, usando `presidente_t1_municipio*.parquet`.
3. Fixar `model:` no frontmatter dos agentes (`.claude/agents/`).
4. Acompanhar `matematicamente_definido` (`md`) da BR — já `"s"` (2º turno) em 05/10/2026; quando `tf_judicial` virar `"s"`, `situacao`/`classificado` dos candidatos passam a ser confiáveis para saber quem avança. Nessa hora, revisar se a divergência de BA (`data/known_issues.csv`) finalmente convergiu.

## Bloqueios / dúvidas abertas
- **Divergência residual de BA (3 municípios) sem solução do nosso lado**: o backend do TSE segue servindo uma geração de 04/10 ~21:00 para `ba33693`/`ba34673`/`ba36013`, mesmo sob `--force`. Catalogada em `data/known_issues.csv`; todas as diferenças são < 0,02% dos totais da UF. Reavaliar periodicamente com `scripts/diagnostico_ba_mg.py` + `coletar_presidente.py --force --apenas ...`.
- Data de publicação dos CSVs de seção/zona 2026 no Dados Abertos: desconhecida. Checar semanalmente.
