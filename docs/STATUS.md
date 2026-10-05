# STATUS

Última atualização: 2026-10-05 — parser EA20 conferido contra a spec oficial; 19/21 invariantes passam.

## Feito
- Estrutura de pastas, `CLAUDE.md`, docs (`DADOS.md`, `DECISOES.md`, `ROADMAP.md`), `.gitignore`, `environment.yml`, `pyproject.toml`.
- Configuração do Claude Code: `.claude/settings.json`, agentes `coletor-tse` e `analista-eleitoral`, skills `fechar-sessao` e `tse-dados`.
- Repositório conectado ao GitHub: https://github.com/larrybers87/analise_eleicoes_2026. Ambiente conda `eleicao2026` criado.
- `src/eleicao/tse_client.py` + `scripts/validar_fontes.py`: cliente async com rate limit/cache/retry/abort; 3 arquivos de teste validados (etapa 1).
- **Coleta completa (etapa 2)**: `scripts/coletar_presidente.py` baixou os 5786 arquivos (1 BR + 28 UF + 5757 municípios, inclui exterior `zz`) em 10min33s, 0 404/0 erro, `data/raw/ele2026/6257/` (~52,7MB, 5787 arquivos) — log em `data/raw/coleta_6257.log` (não versionado).
- `src/eleicao/parse_ea20.py`: parser puro do EA20 (BR/UF/município) → `(df_candidatos, df_totais)`.
- `scripts/processar_presidente.py`: gera os 6 Parquet em `data/processed/` (`presidente_t1_{municipio,uf,br}[_totais].parquet`), versionados (~1,3MB total; `.gitignore` ajustado para liberar só esses 6 arquivos).
- `scripts/diagnostico_join_ibge.py`: join TSE↔IBGE (`geobr.read_municipality(year=2024)`) por `cd_mun_ibge` — 100% de correspondência (5571=5571), 0 órfão de cada lado; os 186 municípios do exterior não entram no join (esperado, sem `cdi`).
- **Conferência com a spec oficial (etapa 3)**: usuário baixou os PDFs EA10/EA12/EA20 em `docs/specs/`; confrontamos parser e testes contra a spec. EA12: sem divergência. EA20: 5 correções feitas (todas documentadas em `docs/DADOS.md` → "Confronto com a especificação oficial"): fórmula completa de `tv` (faltava somar `van`+`vansj`), coluna `eleito`→`classificado` (campo `e` significa "eleito OU vai a 2º turno", não só "eleito"), campos-raiz `md`/`tf`/`dv` que faltavam (a BR já tem `md="s"` = 2º turno matematicamente definido em 05/10/2026!), invariante de comparecimento corrigido (`c+a==esi` sempre, não `c+a==eleitorado` condicionado a `and`). Achado colateral: nossa primeira leitura confundiu `s.sni` com `s.snt` da BR — corrigido.
- `tests/test_invariantes.py` (21 testes, era 9): **19 passam, 2 falham** — só a divergência real de agregação UF↔município em BA/MG (ver Bloqueios). O caso dos 40 municípios `zz` deixou de ser "divergência" (era nosso invariante incompleto, não bug do TSE).

## Em andamento
- (nada)

## Próximo (em ordem)
1. Investigar se os 11 municípios (BA: 3, MG: 8) com `s.snt` não refletido no agregado de UF já convergiram (rodar `coletar_presidente.py --force` só nesses itens e comparar) — opcional, não bloqueia F2.
2. Paleta de cores dos candidatos (lista final: 12 candidatos, ver `presidente_t1_br.parquet`) — definir com o usuário.
3. F2: mapa v1 em `web/` (MapLibre), Brasil → UF → município, usando `presidente_t1_municipio*.parquet`.
4. Fixar `model:` no frontmatter dos agentes (`.claude/agents/`).
5. Acompanhar `matematicamente_definido` (`md`) da BR — já `"s"` (2º turno) em 05/10/2026; quando `tf_judicial` virar `"s"`, `situacao`/`classificado` dos candidatos passam a ser confiáveis para saber quem avança.

## Bloqueios / dúvidas abertas
- **2 invariantes ainda falham por divergência real do TSE** (não é bug do parser/coleta): UF marca `and="f"` (`s.snt==0` agregado) mas a soma do `snt` dos seus próprios municípios é >0 (BA: 6 seções em 3 municípios; MG: 36 seções em 8 municípios) — soma município≠UF oficial nesses 2 estados. Confirmado que não é timing da nossa coleta (BR cacheada da etapa 1 às 02:58 bate exatamente com a soma das 28 UFs frescas de 11:40 — a apuração não avançou nesse intervalo). A spec não prevê nem explica essa lacuna de agregação; é comportamento do backend do TSE, não documentado. Números completos em `docs/DADOS.md` → "Divergências reais encontradas".
- Data de publicação dos CSVs de seção/zona 2026 no Dados Abertos: desconhecida. Checar semanalmente.
