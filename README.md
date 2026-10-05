# Análise Eleição 2026

Mapa interativo e análise dos resultados da eleição presidencial de 2026 (Brasil + exterior; UF, município, zona), a partir dos dados oficiais do TSE.

- Fontes de dados: [`docs/DADOS.md`](docs/DADOS.md)
- Onde estamos: [`docs/STATUS.md`](docs/STATUS.md)
- Fases: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Decisões: [`docs/DECISOES.md`](docs/DECISOES.md)

## Setup (Windows + Anaconda)

No Anaconda Prompt, dentro da pasta do projeto:

```bash
conda env create -f environment.yml
conda activate eleicao2026
python -c "import eleicao, geobr, duckdb; print('ok')"
```

No VS Code: `Ctrl+Shift+P` → *Python: Select Interpreter* → `eleicao2026`.

## Coleta e processamento (Presidente 1º turno)

```bash
python scripts/coletar_presidente.py --eleicao 6257      # coleta completa (BR + 27 UF + zz + 5757 municípios)
python scripts/processar_presidente.py --eleicao 6257    # gera os Parquet em data/processed/
pytest -q                                                 # testes de invariantes (soma município=UF=BR)
```

Rebaixar só alguns arquivos específicos (ex. depois de um diagnóstico apontar divergência),
sem "varrer tudo de novo":

```bash
python scripts/coletar_presidente.py --force --apenas uf:ba,mun:ba:33693
```

### Rotina de manutenção: `verificar_atualizacoes.py`

O TSE pode atualizar resultados depois da coleta inicial (seções ainda pendentes,
recursos, decisões judiciais). `data/known_issues.csv` cataloga divergências
conhecidas entre a soma dos municípios e o arquivo oficial de UF que não
fecharam na última verificação; `data/processed/snapshot_6257.json` registra a
geração (`idg`/`dg`/`hg`) do arquivo BR e dos itens catalogados.

```bash
python scripts/verificar_atualizacoes.py --eleicao 6257
```

O script rebaixa com `--force` **só** o arquivo BR e os municípios/UFs listados
em `data/known_issues.csv` (extraídos dinamicamente do CSV, nunca hardcoded),
compara a geração contra o snapshot e:
- se nada mudou de geração: só informa e termina (nenhuma requisição extra ao
  TSE além das poucas do `--force` dirigido);
- se algo mudou: reprocessa os Parquet, roda `pytest -q`, atualiza o snapshot
  e remove de `data/known_issues.csv` as divergências que convergiram (e só
  essas — qualquer divergência nova faria o teste de invariantes falhar, não
  é silenciada).

Rode esta rotina periodicamente (ex. a cada atualização de apuração) em vez de
repetir a coleta completa — mais rápido e evita bater no rate limit do TSE à
toa. Detalhes do porquê de cada divergência em [`docs/DADOS.md`](docs/DADOS.md).

## GitHub

Com o [GitHub CLI](https://cli.github.com/) instalado e logado (`gh auth login`):

```bash
git init -b main
git add .
git commit -m "setup inicial do projeto"
gh repo create analise_eleicao_2026 --public --source=. --remote=origin --push
```

(Use `--private` se preferir. Para publicar o mapa depois: Settings → Pages → branch `main`, pasta `/web`.)

## Licença dos dados

Dados do TSE sob Creative Commons Atribuição. Cite "Tribunal Superior Eleitoral" como fonte no mapa.
