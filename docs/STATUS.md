# STATUS

Última atualização: 2026-10-05 — setup inicial.

## Feito
- Estrutura de pastas, `CLAUDE.md`, docs (`DADOS.md`, `DECISOES.md`, `ROADMAP.md`), `.gitignore`, `environment.yml`, `pyproject.toml`.
- Configuração do Claude Code: `.claude/settings.json`, agentes `coletor-tse` e `analista-eleitoral`, skills `fechar-sessao` e `tse-dados`.
- Levantamento das fontes: API JSON do TSE confirmada (ciclo `ele2026`, eleição 6257, pleito 3220). CSVs "Resultados 2026" do Dados Abertos ainda não publicados.

## Em andamento
- (nada)

## Próximo (em ordem)
1. Criar ambiente conda e repositório GitHub (passos no README).
2. Baixar PDFs das specs EA12 e EA20 para `docs/specs/` e mapear campos em `DADOS.md`.
3. Implementar `src/eleicao/tse_client.py` (httpx async, rate limit ≤10 req/s, cache em `data/raw/`, sem 404 especulativo).
4. Coletar config de municípios + Presidente BR, 27 UFs + ZZ, todos os municípios → `data/raw/ele2026/6257/`.
5. Parser EA20 → `data/processed/presidente_t1_municipio*.parquet` + teste de invariantes (soma municípios = UF = BR).

## Bloqueios / dúvidas abertas
- Data de publicação dos CSVs de seção/zona 2026 no Dados Abertos: desconhecida. Checar semanalmente.
- Paleta de cores dos candidatos: definir com o usuário quando tivermos a lista final do 1º turno.
