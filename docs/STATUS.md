# STATUS

Última atualização: 2026-10-05 — coleta completa de Presidente 1T (todos os municípios) e parquet processados.

## Feito
- Estrutura de pastas, `CLAUDE.md`, docs (`DADOS.md`, `DECISOES.md`, `ROADMAP.md`), `.gitignore`, `environment.yml`, `pyproject.toml`.
- Configuração do Claude Code: `.claude/settings.json`, agentes `coletor-tse` e `analista-eleitoral`, skills `fechar-sessao` e `tse-dados`.
- Repositório conectado ao GitHub: https://github.com/larrybers87/analise_eleicoes_2026. Ambiente conda `eleicao2026` criado.
- `src/eleicao/tse_client.py` + `scripts/validar_fontes.py`: cliente async com rate limit/cache/retry/abort; 3 arquivos de teste validados (etapa 1).
- **Coleta completa (etapa 2)**: `scripts/coletar_presidente.py` baixou os 5786 arquivos (1 BR + 28 UF + 5757 municípios, inclui exterior `zz`) em 10min33s, 0 404/0 erro, `data/raw/ele2026/6257/` (~52,7MB, 5787 arquivos) — log em `data/raw/coleta_6257.log` (não versionado).
- `src/eleicao/parse_ea20.py`: parser puro do EA20 (BR/UF/município) → `(df_candidatos, df_totais)`; corrigiu engano da etapa 1 sobre separador decimal dos campos `p<campo>n` (ver `docs/DADOS.md`).
- `scripts/processar_presidente.py`: gera os 6 Parquet em `data/processed/` (`presidente_t1_{municipio,uf,br}[_totais].parquet`), agora versionados (~1,3MB total; `.gitignore` ajustado para liberar só esses 6 arquivos).
- `tests/test_invariantes.py` (9 testes): 6 passam; **3 falham por divergência real nos dados do TSE** (documentada em `docs/DADOS.md`, não escondida/ajustada) — ver "Bloqueios" abaixo.
- `scripts/diagnostico_join_ibge.py`: join TSE↔IBGE (`geobr.read_municipality(year=2024)`) por `cd_mun_ibge` — 100% de correspondência (5571=5571), 0 órfão de cada lado; os 186 municípios do exterior não entram no join (esperado, sem `cdi`).

## Em andamento
- (nada)

## Próximo (em ordem)
1. Investigar se os 11 municípios (BA: 3, MG: 8) e os 40 "municípios" `zz` com `and="f"` porém dados incompletos já convergiram (rodar `coletar_presidente.py --force` só nesses itens e comparar) — opcional, não bloqueia F2.
2. Paleta de cores dos candidatos (lista final: 12 candidatos, ver `presidente_t1_br.parquet`) — definir com o usuário.
3. F2: mapa v1 em `web/` (MapLibre), Brasil → UF → município, usando `presidente_t1_municipio*.parquet`.
4. Fixar `model:` no frontmatter dos agentes (`.claude/agents/`).
5. PDFs EA10/EA12/EA20 apareceram em `docs/specs/` nesta sessão (não baixados por mim — provavelmente o usuário seguindo a sugestão da etapa 1); conferir o schema documentado em `docs/DADOS.md` contra eles quando houver tempo.

## Bloqueios / dúvidas abertas
- **3 invariantes falhando por divergência real do TSE** (não é bug do parser/coleta): (1) UF marca `and="f"` mas 11 municípios (BA: 3, MG: 8) seguem `and="p"` — soma município≠UF oficial; (2) 40 "cidades" do exterior têm `and="f"` com a única seção nunca informada (`comparecimento=abstencao=0`, eleitorado>0); confirmado que BR (cache da etapa 1, 02:58) bate exatamente com a soma das 28 UFs frescas (11:40) — apuração parada nesse intervalo, não é timing da nossa coleta. Números completos em `docs/DADOS.md` → Armadilhas.
- PDFs EA12/EA20: ver item 5 em "Próximo" — apareceram em `docs/specs/` por via externa a este agente; não commitados por mim (não verifiquei a origem/integridade).
- Data de publicação dos CSVs de seção/zona 2026 no Dados Abertos: desconhecida. Checar semanalmente.
