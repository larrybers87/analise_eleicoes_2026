# Análise Eleição 2026

[![Deploy do mapa (GitHub Pages)](https://github.com/larrybers87/analise_eleicoes_2026/actions/workflows/pages.yml/badge.svg)](https://github.com/larrybers87/analise_eleicoes_2026/actions/workflows/pages.yml)

Mapa interativo e análise dos resultados da eleição presidencial de 2026 (Brasil + exterior; UF, município, zona), a partir dos dados oficiais do TSE.

**Mapa publicado:** https://larrybers87.github.io/analise_eleicoes_2026/

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

Depois (uma vez por clone — não é global, fica no `.git/config` local): instale o filtro
que limpa outputs de notebook antes de cada commit, para não versionar imagens
embutidas em `.ipynb` (`.gitattributes` já diz quais arquivos passam pelo filtro,
mas o hook em si precisa ser registrado a cada clone novo):

```bash
nbstripout --install --attributes .gitattributes
```

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

## Mapa web (`web/`)

Site 100% estático (MapLibre GL JS + topojson-client via CDN, sem backend e sem
build step). Os dados que ele consome ficam em `web/data/`, gerados a partir de
`data/processed/`:

```bash
python scripts/exportar_web.py                  # tudo (~10 min: a geometria é o custo)
python scripts/exportar_web.py --sem-geometria   # só os JSON de resultado (~1 min)
python scripts/exportar_web.py --apenas-nacional # só brasil_municipios.topojson (~4 min)

python scripts/verificar_export_web.py           # confere web/data/ contra os Parquet
```

Depois de uma atualização de resultados (`verificar_atualizacoes.py`), basta
rodar `--sem-geometria`: a geometria só muda se a malha do IBGE mudar.

Para ver localmente:

```bash
cd web && python -m http.server 8765
# abra http://127.0.0.1:8765/
```

Não abra `web/index.html` direto pelo `file://` — o `fetch` dos dados é bloqueado
por CORS. Em produção, qualquer HTTP estático serve (GitHub Pages inclusive).

Todos os caminhos em `web/` (fetch de `data/...`, `css/estilo.css`, `js/app.js`)
são **relativos**, sem barra inicial — o site roda num subcaminho
(`/analise_eleicoes_2026/`), não na raiz do domínio. Testado servindo
`web/` de dentro de um diretório pai (`python -m http.server` na raiz do
projeto, abrindo `/web/`) para simular o subcaminho antes de publicar.

### Deploy (GitHub Pages via Actions)

`.github/workflows/pages.yml` publica `web/` a cada push na `main` que toque
`web/**` (ou manualmente via `workflow_dispatch`). **Ativação única** (depois
do primeiro push com o workflow): Settings → Pages → Source → **GitHub
Actions** (não "Deploy from a branch" — não existe mais pasta `/web` sendo
servida diretamente, o workflow empacota e publica o conteúdo de `web/`).

URL publicada: https://larrybers87.github.io/analise_eleicoes_2026/

## GitHub

Com o [GitHub CLI](https://cli.github.com/) instalado e logado (`gh auth login`):

```bash
git init -b main
git add .
git commit -m "setup inicial do projeto"
gh repo create analise_eleicao_2026 --public --source=. --remote=origin --push
```

(Use `--private` se preferir — GitHub Pages funciona em repositório privado
também, desde que o plano permita.)

## Licença dos dados

Dados do TSE sob Creative Commons Atribuição. Cite "Tribunal Superior Eleitoral" como fonte no mapa.
