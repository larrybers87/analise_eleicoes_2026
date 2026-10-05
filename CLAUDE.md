# CLAUDE.md — Análise Eleição 2026

Guia de bordo para o Claude Code. Leia este arquivo e `docs/STATUS.md` no início de **toda** sessão. Não precisa ler o resto do `docs/` a menos que a tarefa toque o assunto.

## Objetivo

Mapa interativo + análise exploratória do resultado da eleição de **Presidente 2026** (1º turno em 04/10/2026; 2º turno em 25/10/2026, se houver), com drill-down Brasil → UF → município → zona (→ seção, se viável), incluindo **exterior** (UF `ZZ`). Cada candidato tem uma cor fixa; a cor da região é a mistura ponderada pelos votos. Depois, se tudo estiver sólido: Governador, Senador, Deputados.

Análises além do mapa: % por região/UF/município, abstenção, brancos, nulos, comparecimento, concentração de votos, comparativos entre recortes.

## Stack (decidido — ver `docs/DECISOES.md`)

- **Python 3.12**, ambiente conda `eleicao2026` (`environment.yml`). Usuário em Windows + Anaconda.
- Coleta: `httpx` (async, com rate limit). Processamento: `pandas` + `duckdb`. Armazenamento analítico: **Parquet**.
- Geometria: malhas do IBGE via `geobr` (código IBGE de 7 dígitos). Join TSE↔IBGE pelo campo `cdi` do JSON do TSE.
- Front-end do mapa: site estático em `web/` (MapLibre GL JS + GeoJSON/TopoJSON simplificado). Sem backend.
- Análises exploratórias: `notebooks/` (Jupyter), sempre com a lógica final movida para `src/eleicao/`.

## Estrutura

```
src/eleicao/      pacote Python (coleta, parsing, transformação, cores)
scripts/          entrypoints CLI (ex.: python scripts/coletar_presidente.py)
data/raw/         JSON/CSV exatamente como baixados (NÃO versionado)
data/interim/     dados normalizados intermediários (NÃO versionado)
data/processed/   Parquet/GeoJSON finais consumidos pelo web/ (versionar só os pequenos)
notebooks/        exploração
web/              mapa estático
docs/             documentação viva (ver abaixo)
.claude/agents/   subagentes do projeto
.claude/skills/   skills do projeto
```

## Documentação viva — regra principal

O usuário quer que **nem ele nem o Claude se percam**. Portanto:

1. `docs/STATUS.md` é a fonte da verdade do que foi feito / em andamento / próximo. Atualize **ao final de toda tarefa**, sem exceção (use a skill `fechar-sessao`).
2. `docs/DECISOES.md` — log de decisões no formato ADR curto (data, decisão, motivo, alternativas). Nova decisão não-trivial = nova entrada.
3. `docs/DADOS.md` — fontes, URLs, schemas, armadilhas do TSE. Qualquer descoberta sobre os dados vai para lá.
4. Docs são curtos e escaneáveis. Atualize no lugar; não duplique informação entre arquivos.

## Regras de dados do TSE (críticas)

- Base oficial: `https://resultados.tse.jus.br/oficial/ele2026/...` — ciclo `ele2026`, pleito `3220`, eleição federal **6257** (2º turno **6258**), estadual 6259 (2º turno 6260). Detalhes em `docs/DADOS.md`.
- **Limite: 100 req/s por IP**, bloqueio de 10 min (renovável). Use no máximo ~10 req/s e cache em disco.
- **Muitos 404 causam bloqueio de IP.** Nunca "adivinhe" URLs: monte a lista de municípios a partir do arquivo de configuração (`mun-e006257-cm.json`). Código de município TSE sempre com **5 dígitos** (zeros à esquerda).
- Nunca rebaixe algo que já está em `data/raw/` sem motivo (cache primeiro, `--force` para refazer).
- `data/raw/` é imutável: transformações sempre geram arquivos novos em `interim/` ou `processed/`.

## Convenções de código

- Português nos nomes de domínio (`municipio`, `zona`, `votos_validos`); inglês ok para termos técnicos.
- Type hints, funções puras para transformação, I/O isolado. `ruff` para lint/format.
- Testes mínimos em `tests/` para parsers e totais (soma dos municípios = total da UF = total BR é um invariante obrigatório).
- Commits pequenos, mensagem em português no imperativo (`adiciona coletor de municípios`).

## Comandos

```bash
conda env create -f environment.yml     # primeira vez
conda activate eleicao2026
ruff check . && ruff format .
pytest -q
```

## Como trabalhar comigo (usuário)

Respostas diretas, sem firula. Precisão acima de tudo; especulação marcada como tal. Se algo é ambíguo, pergunte antes de construir. Prefira prosa a listas excessivas.
