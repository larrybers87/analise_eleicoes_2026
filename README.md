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
