# STATUS

Última atualização: 2026-10-05 — etapa 1 da coleta validada (3 arquivos de teste, cliente TSE pronto).

## Feito
- Estrutura de pastas, `CLAUDE.md`, docs (`DADOS.md`, `DECISOES.md`, `ROADMAP.md`), `.gitignore`, `environment.yml`, `pyproject.toml`.
- Configuração do Claude Code: `.claude/settings.json`, agentes `coletor-tse` e `analista-eleitoral`, skills `fechar-sessao` e `tse-dados`.
- Levantamento das fontes: API JSON do TSE confirmada (ciclo `ele2026`, eleição 6257, pleito 3220). CSVs "Resultados 2026" do Dados Abertos ainda não publicados.
- Repositório conectado ao GitHub: https://github.com/larrybers87/analise_eleicoes_2026 (remote `origin`, push direto, sem conflitos).
- Ambiente conda `eleicao2026` criado (Windows, interpretador em `Miniconda3/envs/eleicao2026/python.exe`).
- `src/eleicao/tse_client.py`: cliente async (httpx), rate limit global ≤10 req/s (`_LimitadorTaxaGlobal`), cache em `data/raw/` via `config.caminho_local`, retry (tenacity, 4 tentativas) só para 5xx/timeout, abort imediato em 403/429, abort após >5 404s.
- `scripts/validar_fontes.py`: baixa e valida as 3 fontes mínimas (config municípios, Presidente BR, Presidente Curitiba — código obtido do próprio config, nunca hardcoded). Executado com sucesso; cache confirmado (reexecução não gera requisição).
- `docs/DADOS.md`: estrutura real de `mun-e006257-cm.json` e do EA20 (`*-c0001-e006257-u.json`) documentada por inspeção direta (ver Armadilhas e "Estrutura real confirmada"); schemas normalizados atualizados com os nomes de campo reais.
- Testes `tests/test_tse_client.py`: rate limiter, cache (não repete requisição) e abort após 404s — todos passando (`pytest -q`: 8 passed).

## Em andamento
- (nada)

## Próximo (em ordem)
1. Coletar config de municípios + Presidente BR, 27 UFs + ZZ, todos os municípios → `data/raw/ele2026/6257/` (≈5.786 requisições, ~10 min a 10 req/s — ver estimativa no relatório da sessão).
2. Parser EA20 → `data/processed/presidente_t1_municipio*.parquet` + teste de invariantes (soma municípios = UF = BR), usando `v.tvn` como nulos e checando `totalizacao_final` antes de exigir `comparecimento+abstencao==eleitorado` (ver `docs/DADOS.md`).
3. Rodar a coleta completa só depois de confirmar que o 1º turno está com `and="f"` (totalização final) na BR — hoje (05/10) ainda tinha seções pendentes.
4. Fixar `model:` no frontmatter dos agentes (`.claude/agents/`) — pedir prompt ao Claude do projeto.
5. Paleta de cores dos candidatos: definir com o usuário quando tivermos a lista final do 1º turno.

## Bloqueios / dúvidas abertas
- **PDFs EA12/EA20 não baixados**: `www.tse.jus.br` e `divulgacandcontas.tse.jus.br` retornam 403 para o IP deste ambiente (bloqueio de rede, confirmado até no `robots.txt` e na home — não é o rate limit de resultados). `resultados.tse.jus.br` e `dadosabertos.tse.jus.br` funcionam normalmente. Campos documentados por inspeção direta dos JSONs reais; se precisar dos PDFs, baixar fora deste ambiente.
- Data de publicação dos CSVs de seção/zona 2026 no Dados Abertos: desconhecida. Checar semanalmente.
- Paleta de cores dos candidatos: definir com o usuário quando tivermos a lista final do 1º turno.
