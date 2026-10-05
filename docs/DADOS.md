# Fontes de dados

Atualizado em 2026-10-05. Toda descoberta nova sobre os dados entra aqui.

## Resposta curta: existe base pronta?

Existe, em duas camadas, e **não precisamos criar dados do zero** — precisamos montar a nossa base *a partir* das fontes oficiais:

1. **API JSON de divulgação do TSE** (disponível agora, é o que alimenta o site de resultados). Resultado por Brasil, UF e **município**, inclusive exterior. Não traz zona/seção agregadas.
2. **Portal de Dados Abertos do TSE** (CSV). Para 2026, em 05/10, só existem "Correspondências esperadas e efetivadas" e logs. Os conjuntos "Resultados - 2026" (votação por seção, votação nominal por município e zona, detalhe da apuração) **ainda não foram publicados**. Em 2022/2024 eles saíram depois da eleição; a data exata para 2026 não sei — monitorar.
3. **Arquivos de urna por seção** (BU) via mesma CDN da API JSON — permitem zona/seção já agora, mas são ~470 mil seções. Plano B.

Estratégia: fase 1 com a API JSON (município); fase 2 com os CSVs do Dados Abertos quando saírem (zona/seção). Ver `DECISOES.md` (D-002).

## 1. API JSON de divulgação (resultados.tse.jus.br)

- Base: `https://resultados.tse.jus.br/oficial`
- Configuração geral: `/comum/config/ele-c.json`
  - Pleito **3220** (04/10/2026), ciclo **`ele2026`**
  - **6257** Eleição Ordinária Federal 1º turno (Presidente, cargo `1`) → 2º turno **6258**
  - **6259** Estadual 1º turno (Governador `3`, Senador `5`, Dep. Federal `6`, Dep. Estadual `7`, Dep. Distrital `8`) → 2º turno **6260**
  - 6261 Conselheiro Distrital (cargo `25`)
- Padrões de diretório (do próprio `ele-c.json`):
  - `u` (resultado unificado, EA20) e `ab` (acompanhamento): `<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>`
  - `cm` (config de municípios, EA12): `<base>/<ambiente>/<ciclo>/<cd_eleicao>/config`
  - `ft` (fotos): `.../<cd_eleicao>/fotos/<uf>`
  - `cs` (config de seções, EA16): `<base>/<ambiente>/<ciclo>/arquivo-urna/<cd_pleito>/config/<uf>`
  - `aux` (arquivos da seção, EA18/BU): `.../arquivo-urna/<cd_pleito>/dados/<uf>/<municipio>/<zona>/<secao>`
- Nomes de arquivo (padrão confirmado no simulado; eleição com 6 dígitos):
  - Config municípios: `config/mun-e006257-cm.json`
  - Presidente Brasil: `dados/br/br-c0001-e006257-u.json`
  - Presidente por UF: `dados/{uf}/{uf}-c0001-e006257-u.json`
  - Presidente por município: `dados/{uf}/{uf}{cdmun5}-c0001-e006257-u.json` (ex.: `pr75353-c0001-e006257-u.json`)
  - Acompanhamento: `dados/br/br-e006257-ab.json`, `dados/{uf}/{uf}-e006257-ab.json`
- Join com IBGE: no config, cada município tem `cd` (TSE, 5 dígitos) e `cdi` (IBGE, 7 dígitos).
- Exterior: UF `zz`; "municípios" são cidades no exterior (sem código IBGE → mapa por ponto/país).
- Especificações oficiais (PDF): EA10 eleitos, EA11 config eleições, EA12 config municípios, EA14/EA15 acompanhamento, EA16 config seções, EA18 auxiliar de seção, EA20 resultado unificado. Página: https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados — **baixar os PDFs para `docs/specs/`** antes de escrever o parser.

### Armadilhas

- **Rate limit 100 req/s por IP**, bloqueio 10 min renovável. Usar ≤10 req/s.
- **404 em excesso bloqueia o IP.** Gerar URLs só a partir do config. Município com 5 dígitos.
- Não há arquivo de índice; não dá para listar diretórios.
- CDN suporta ETag/Last-Modified, mas 304 também conta no rate limit.
- Campo `and` = `f` indica totalização final da abrangência (Presidente: município/UF quando `snt=0`; BR na totalização final).
- Os JSONs são assinados (JWS) — verificação opcional, manual oficial na mesma página.
- `robots.txt` bloqueia crawlers genéricos (WebFetch do Claude falha); acesso programático por script próprio é o uso previsto pelo TSE para "entidades divulgadoras" (sem cadastro, Res. TSE 23.751/2026, arts. 264–269).

## 2. Portal de Dados Abertos (dadosabertos.tse.jus.br)

- Grupo resultados: https://dadosabertos.tse.jus.br/group/resultados
- Esperado para 2026 (por analogia a 2022): `votacao_secao_2026_<UF>.zip`, `votacao_candidato_munzona_2026`, `detalhe_votacao_munzona_2026` (abstenção, brancos, nulos por zona), boletins de urna. **Ainda não publicado em 05/10/2026.**
- Já disponível: **Eleitorado 2026** — perfil do eleitorado por seção e **eleitorado por local de votação** (inclui coordenadas dos locais — usar para o mapa por zona/local). https://dadosabertos.tse.jus.br/dataset/eleitorado-2026
- Encoding dos CSVs do TSE costuma ser `latin-1`, separador `;`. Verificar ao baixar.

## 3. Geometria

- Municípios/UFs: IBGE via pacote `geobr` (`read_municipality(year=2024)`, `read_state`). Simplificar (mapshaper/`topojson`) para o web.
- Zonas eleitorais: **não há polígono oficial**. Opções: (a) pontos dos locais de votação (Eleitorado por local de votação); (b) polígonos derivados (Voronoi/hull dos locais por zona) — aproximação, marcar como tal no mapa.
- Exterior: pontos por cidade ou agregação por país (geometria Natural Earth).

## Schemas normalizados (alvo, `data/processed/`)

`presidente_t1_municipio.parquet` (uma linha por município × candidato):
`uf, cd_mun_tse, cd_mun_ibge, nm_mun, nr_candidato, nm_candidato, partido, votos, pct_validos`

`presidente_t1_municipio_totais.parquet` (uma linha por município):
`uf, cd_mun_tse, cd_mun_ibge, eleitorado, comparecimento, abstencao, brancos, nulos, validos, secoes_totalizadas, secoes_total, totalizacao_final`

(A confirmar contra a spec EA20 — nomes dos campos do JSON a mapear em `src/eleicao/parse_ea20.py`.)
