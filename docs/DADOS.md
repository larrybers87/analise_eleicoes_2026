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
- Especificações oficiais (PDF): EA10 eleitos, EA11 config eleições, EA12 config municípios, EA14/EA15 acompanhamento, EA16 config seções, EA18 auxiliar de seção, EA20 resultado unificado. Página: https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados — **baixar os PDFs para `docs/specs/`** antes de escrever o parser. **Não conseguimos baixar em 05/10/2026** (ver Armadilhas); campos abaixo documentados por inspeção direta dos 3 JSONs reais (`mun-e006257-cm.json`, `br-c0001-e006257-u.json`, `pr75353-c0001-e006257-u.json`).

### Estrutura real confirmada (validação 05/10/2026, ver `scripts/validar_fontes.py`)

**Config de municípios (EA12, `mun-e006257-cm.json`)** — chaves de topo `dg`/`hg`/`idg` (data/hora/id de geração), `f`, e `abr`: lista com **28 abrangências** (27 UFs + `zz`=EXTERIOR), cada uma `{cd: sigla uf minúscula, ds: nome da UF, mu: [...]}`. Cada município em `mu[]`: `cd` (código TSE, 5 dígitos), `cdi` (código IBGE, 7 dígitos; **vazio `""` no exterior**, sem correspondente IBGE), `nm` (nome em caixa alta, UTF-8 válido — se aparecer corrompido no terminal é problema de codepage do console, não do arquivo), `c` (`"s"` para a capital da UF — exatamente 1 por UF, todas `"n"` em `zz`; é assim que achamos o código de Curitiba sem hardcode), `z` (lista de zonas eleitorais, string de 4 dígitos). Total **5.757 entradas** em `abr[].mu`: **5.571** municípios do Brasil (inclui DF) + **186** "municípios" do exterior (cidades, sem código IBGE).

**Resultado unificado (EA20, `*-c0001-e006257-u.json`)** — mesmo schema em BR/UF/município, abrangência identificada por `tpabr` (`br`|`uf`|`mu`) + `cdabr`. Cabeçalho: `ele` (eleição), `t` (turno), `dg`/`hg` (geração), `dt`/`ht` (totalização), `and` (**status da totalização**: `"p"` parcial, `"f"` final — confirma a nota de Armadilhas sobre `and=f`), `md`.
  - Bloco `s` (seções): `ts`/`st` (total), `snt` (não totalizadas), `si`/`sni` (informadas / não informadas), `sa`/`sna` (aptas / não aptas) — cada um com par `p<campo>` (% formatado, 2 casas, ex. `"99,99"`) e `p<campo>n` (% com mais casas decimais, ex. `"99,991787649"`). **Correção 05/10/2026 (coleta completa): `p<campo>n` também usa vírgula como separador decimal, não ponto** — a entrada anterior desta tabela estava errada (baseada em leitura apressada de um valor que por coincidência não tinha parte decimal, ex. `"100"`/`"0"`). Ver Armadilhas.
  - Bloco `e` (eleitorado): `te`/`est` (total), `esnt`/`esi`/`esni` (idem seções), `esa`/`esna`, **`c` (comparecimento)**, **`a` (abstenção)**.
  - Bloco `v` (votos): `tv` (total = `c`), `vv` (válidos), `vvc` (válidos computados, igual a `vv` nas amostras), `vnom` (nominais, = `vv` para Presidente — sem voto de legenda), `van` (anulados), `vansj` (**anulados sub judice** — `0` nas amostras), `vb` (brancos), **`tvn` (total de nulos) = `vn` (nulos comuns) + `vnt` (nulos "técnicos")**, `vsan`/`vscv` (0 nas amostras).
  - `carg[]` (cargo Presidente): `fed[]` (federações partidárias), `agr[]` (agremiações: coligação `tp="c"` ou partido isolado `tp="i"`) → `agr.par[]` (partido: `n`, `sg`, `nm`, `nfed`) → `par.cand[]` (candidato: `n` número, `sqcand`, `nm` nome completo, `nmu` nome de urna, `seq` **posição de classificação** (1º, 2º...), `e` (eleito `"s"`/`"n"`), `st` (situação, vazio até decidido), `vap` **votos apurados**, `pvap`/`pvapn` **% sobre `vv`**, `vs[]` vice (`tp="v"`)).

**Totalização ainda em curso em 05/10/2026**: no nível BR, `and="p"` com `s.sni=41` (41 seções sem dado ainda); no município de Curitiba, `and="f"` com `s.sni=0` (totalizado). Isso afeta os invariantes — ver Armadilhas.

### Armadilhas

- **Rate limit 100 req/s por IP**, bloqueio 10 min renovável. Usar ≤10 req/s.
- **404 em excesso bloqueia o IP.** Gerar URLs só a partir do config. Município com 5 dígitos.
- Não há arquivo de índice; não dá para listar diretórios.
- CDN suporta ETag/Last-Modified, mas 304 também conta no rate limit.
- Campo `and` = `f` indica totalização final da abrangência (Presidente: município/UF quando `snt=0`; BR na totalização final).
- Os JSONs são assinados (JWS) — verificação opcional, manual oficial na mesma página.
- `robots.txt` bloqueia crawlers genéricos (WebFetch do Claude falha); acesso programático por script próprio é o uso previsto pelo TSE para "entidades divulgadoras" (sem cadastro, Res. TSE 23.751/2026, arts. 264–269).
- **`www.tse.jus.br` e `divulgacandcontas.tse.jus.br` retornam 403 para o IP deste ambiente de execução** (inclusive a própria home e o `robots.txt` — bloqueio de rede/WAF, não é o rate limit de resultados). `resultados.tse.jus.br` (API de resultados) e `dadosabertos.tse.jus.br` funcionam normalmente. Consequência: não conseguimos baixar os PDFs EA12/EA20 nesta sessão; documentamos os campos por inspeção direta dos JSONs reais. Se precisar dos PDFs, baixar fora deste ambiente (rede doméstica) e colocar em `docs/specs/`.
- `comparecimento + abstencao == eleitorado` (bloco `e`: `c + a == te`) só vale exatamente quando a abrangência está **totalizada** (`and == "f"` e `s.sni == 0`). Enquanto há seções não informadas (`s.sni > 0`, `and == "p"`), `e.c + e.a == e.esi` (eleitorado das seções já apuradas), que é menor que `e.te`. Confirmado comparando BR (parcial, `sni=41` em 05/10/2026 02:58) com Curitiba (final, `sni=0`).
- `validos + brancos + nulos == comparecimento` vale usando **`v.tvn`** (total de nulos) como "nulos" — não `v.vn` isolado. `v.tvn = v.vn + v.vnt` (nulos comuns + nulos "técnicos"). Ou seja: `v.vv + v.vb + v.tvn == v.tv == e.c`.
- `v.vansj` (votos anulados sub judice) existe como campo mas veio `"0"` nas 3 amostras — tratamento à parte só será necessário se algum caso tiver valor > 0.
- **Todos os campos percentuais usam vírgula como separador decimal, inclusive os `p<campo>n`** (ex. `pvapn: "57,499675335"`, `pcn: "80,280790419"`). A entrada original desta tabela (etapa 1) dizia que `p<campo>n` usava ponto — erro, baseado em amostra que coincidentemente não tinha parte decimal. Corrigido na etapa 2 (`src/eleicao/parse_ea20.py`, função `_float`: faz `valor.replace(",", ".")` antes de `float()`). Atenção ao escrever qualquer novo parser/notebook que leia esses campos.
- Config de municípios tem alguns nomes com acentuação corrompida quando lidos por `cat`/terminal Windows com codepage errado (ex. `ACREL�NDIA`) — **não é problema do arquivo** (é UTF-8 válido; confirmado abrindo com `encoding="utf-8"` em Python), é só exibição no console.

### Divergências reais encontradas na coleta completa (05/10/2026, 1º turno)

Coleta completa executada 05/10/2026 11:40:49–11:51:22 (10min33s), 5786 itens
(1 BR + 28 UF + 5757 municípios), 5784 novos + 2 cache-hit (BR e Curitiba,
herdados da etapa 1), **0 404 / 0 erro**. Ao rodar `tests/test_invariantes.py`
sobre o resultado, **3 dos 9 testes falharam** — não foram "corrigidos" para
passar; são divergências reais nos dados do TSE, documentadas aqui:

1. **UF marca `and="f"` (final, `s.si==s.ts`) mas 11 municípios dentro dela
   ainda estão `and="p"`** (não é artefato de timing da nossa coleta — ver
   abaixo). Afeta 2 UFs:
   - **BA** (UF: `s.si=35476=s.ts`, `and="f"`): municípios `33693` BELO CAMPO
     (54/58 seções), `34673` CONCEIÇÃO DO COITÉ (186/187), `36013` ITAETÉ
     (39/40) — todos `and="p"`.
   - **MG** (UF: `s.si=52062=s.ts`, `and="f"`): municípios `41556` BOM JESUS
     DO GALHO (38/41), `41696` BOTUMIRIM (10/19), `42005` CURRAL DE DENTRO
     (12/19), `46078` IJACI (15/16), `47198` JOAÍMA (34/40), `40622` ROSÁRIO
     DA LIMEIRA (12/16), `51977` SANTO ANTÔNIO DO AMPARO (46/47), `53171`
     SENADOR MODESTINO GONÇALVES (12/17) — todos `and="p"`.
   - Efeito: soma dos municípios ≠ arquivo oficial da UF para
     `comparecimento`/`abstencao`/`validos`/`brancos`/`nulos_tvn` (não para
     `eleitorado`, que é fixo). BA: comparecimento -1.322, abstenção -334,
     válidos -1.244, brancos -29, nulos -49. MG: comparecimento -8.413,
     abstenção -3.366, válidos -7.908, brancos -138, nulos -367. Por
     candidato (soma município < UF oficial), maior efeito em `13` (Lula:
     BA -967, MG -4.898) e `22` (PL/Bolsonaro: BA -236, MG -2.600).
   - **Não é timing da nossa coleta**: o arquivo BR (cacheado da etapa 1,
     gerado 05/10 02:58:39, `and="p"`, `s.sni=41`) bate **exatamente, voto a
     voto**, com a soma das 28 UFs baixadas ~9h depois (05/10 11:40), nos 6
     campos testados. Ou seja, a apuração nacional não avançou nesse
     intervalo — os 41 `s.sni` (seções não informadas) da BR são as mesmas
     seções pendentes nesses 11 municípios desde pelo menos 02:58. A
     inconsistência é do próprio TSE entre o agregado de UF (que já marca
     essas seções como totalizadas) e o arquivo específico do município
     (que ainda não). Não investigamos mais a fundo (fora do escopo); se
     refizéssemos a coleta destes 11 municípios agora (`--force`), é
     provável que já estejam `and="f"` e a soma feche.
2. **`and="f"` não garante `comparecimento+abstencao==eleitorado`** mesmo
   restringindo ao `status_totalizacao=="f"` (contradiz a nota anterior
   desta tabela, que assumia `and="f" ⇔ s.sni==0`): **40 das 186
   "cidades" do exterior (`zz`)** têm `s.ts=1`, `s.si=0` (a única seção
   nunca foi informada) mas `and="f"` mesmo assim, com `comparecimento=0` e
   `abstencao=0` enquanto `eleitorado` > 0 (ex. `99198` ABUJA, eleitorado=3;
   `99104` TBILISI, eleitorado=29). A soma do eleitorado dessas 40 cidades é
   **exatamente 423** — igual ao `e.esni` (eleitorado em seções não
   informadas) do arquivo BR. Hipótese mais provável: posto consular com
   seção cadastrada mas sem urna instalada/boletim gerado (eleitorado
   residual pequeníssimo, 1 a 29 pessoas); o TSE marca `and="f"` porque não
   espera mais nenhum dado dessa seção, não porque ela foi efetivamente
   contabilizada. Para o schema isso significa: **ao calcular abstenção/
   comparecimento por município, não assumir que `and="f"` implica os 3
   blocos (`s`, `e`, `v`) estão internamente consistentes** — checar também
   `s.si == s.ts` linha a linha, não só o campo `and`.
   `tests/test_invariantes.py::test_comparecimento_mais_abstencao_igual_eleitorado_quando_final`
   fica **vermelho de propósito** por causa deste caso — não foi relaxado.

## 2. Portal de Dados Abertos (dadosabertos.tse.jus.br)

- Grupo resultados: https://dadosabertos.tse.jus.br/group/resultados
- Esperado para 2026 (por analogia a 2022): `votacao_secao_2026_<UF>.zip`, `votacao_candidato_munzona_2026`, `detalhe_votacao_munzona_2026` (abstenção, brancos, nulos por zona), boletins de urna. **Ainda não publicado em 05/10/2026.**
- Já disponível: **Eleitorado 2026** — perfil do eleitorado por seção e **eleitorado por local de votação** (inclui coordenadas dos locais — usar para o mapa por zona/local). https://dadosabertos.tse.jus.br/dataset/eleitorado-2026
- Encoding dos CSVs do TSE costuma ser `latin-1`, separador `;`. Verificar ao baixar.

## 3. Geometria

- Municípios/UFs: IBGE via pacote `geobr` (`read_municipality(year=2024)`, `read_state`). Simplificar (mapshaper/`topojson`) para o web.
- Zonas eleitorais: **não há polígono oficial**. Opções: (a) pontos dos locais de votação (Eleitorado por local de votação); (b) polígonos derivados (Voronoi/hull dos locais por zona) — aproximação, marcar como tal no mapa.
- Exterior: pontos por cidade ou agregação por país (geometria Natural Earth).

## Schemas normalizados (`data/processed/`, implementado na etapa 2)

Gerados por `src/eleicao/parse_ea20.py` (`parse_ea20`, função pura) +
`scripts/processar_presidente.py` (orquestração/empilhamento). Mesmo schema
para os 3 níveis (`presidente_t1_municipio*`, `presidente_t1_uf*`,
`presidente_t1_br*`); o nível é identificado pela coluna `abrangencia`
(`"br"|"uf"|"mun"`) e, no caso de município, `presidente_t1_municipio*.parquet`
também tem a coluna booleana `eh_exterior`.

`presidente_t1_<nivel>.parquet` (candidatos; 1 linha por candidato):
`uf, cd_mun_tse, nr_candidato, nm_urna, partido, votos, pct_validos, eleito, situacao` +
`extra_cand_nm_completo, extra_cand_sqcand, extra_cand_posicao_classificacao, extra_cand_dvt,
extra_partido_nm, extra_partido_nfed, extra_agremiacao_tipo, extra_agremiacao_nome,
extra_vice_nm_urna, extra_vice_sqcand`.
- `nr_candidato` ← `cand.n`; `nm_urna` ← `cand.nmu`; `partido` ← `par.sg`; `votos` ← `cand.vap`;
  `pct_validos` ← `cand.pvapn` **convertido de vírgula para ponto decimal** (ver Armadilhas —
  `pvapn` NÃO é ponto-decimal nativamente, ao contrário do que a etapa 1 tinha documentado);
  `eleito` ← `cand.e` (`"s"→True`, `"n"→False`); `situacao` ← `cand.st` (vazio → `None`;
  sempre vazio nas amostras — eleição ainda não decidida).
- `extra_*`: campos existentes no JSON que não foram descartados mas também não entraram no
  nome "oficial" da coluna — nome completo do candidato (`cand.nm`, diferente de `nmu`),
  `sqcand`, posição de classificação (`cand.seq`), validade da candidatura (`cand.dvt`), nome
  completo do partido, código da federação (`par.nfed`), tipo/nome da coligação (`agr.tp`/`nm`),
  nome de urna e `sqcand` do vice (`cand.vs[0]`).

`presidente_t1_<nivel>_totais.parquet` (1 linha por município/UF/BR):
`uf, cd_mun_tse, cd_mun_ibge, nm_mun, abrangencia, eleitorado, comparecimento, abstencao,
validos, brancos, nulos_vn, nulos_tvn, secoes_totalizadas, secoes_total, status_totalizacao,
data_hora_totalizacao, anulados, anulados_sub_judice` + `extra_v_vvc, extra_v_vnom, extra_v_vnt,
extra_v_vsan, extra_v_vscv, extra_s_snt, extra_s_sni, extra_s_sa, extra_s_sna, extra_e_esi,
extra_e_esni, extra_e_esa, extra_e_esna` (em `presidente_t1_municipio_totais.parquet` também
`eh_exterior`, preenchida pela orquestração, não pelo parser).
- `cd_mun_tse`/`cd_mun_ibge`/`nm_mun` são `None` para BR e UF (o EA20 não traz nome/código IBGE
  de município — vêm do config, passados como argumento ao parser, não do próprio EA20).
- `eleitorado` ← `e.te`; `comparecimento` ← `e.c`; `abstencao` ← `e.a`; `validos` ← `v.vv`;
  `brancos` ← `v.vb`; `nulos_vn` ← `v.vn`; `nulos_tvn` ← `v.tvn` (**usar `nulos_tvn` para o
  invariante `validos+brancos+nulos==comparecimento`**, não `nulos_vn` — ver Armadilhas);
  `secoes_totalizadas` ← `s.si`; `secoes_total` ← `s.ts`; `status_totalizacao` ← `and`
  (`"f"` final, `"p"` parcial — **não é booleano**, decisão da etapa 2: manter o código
  original em vez de um `totalizacao_final: bool` para preservar informação, já que não há
  outro valor documentado além de `"f"`/`"p"` até agora); `anulados` ← `v.van`;
  `anulados_sub_judice` ← `v.vansj`.
- `extra_*` de `v`: `vvc` (válidos computados), `vnom` (nominais, == `vv` para Presidente),
  `vnt` (componente "técnico" de `tvn`), `vsan`/`vscv` (sempre `"0"` nas amostras, sem
  documentação oficial do significado exato). `extra_*` de `s`/`e`: contagens brutas (não os
  percentuais formatados, que são deliberadamente omitidos como derivados — ver Armadilhas)
  de seções/eleitorado não totalizadas/informadas, relevantes para interpretar abrangências
  com `status_totalizacao == "p"`.
- Percentuais formatados (`p<campo>`, `p<campo>n`) de ambos os blocos **não** viram coluna:
  são 100% derivados dos contadores absolutos já capturados (`campo / total * 100`); refazer
  esse cálculo em pandas/duckdb é mais simples e mais confiável do que parsear string com
  vírgula decimal. Isso é uma omissão deliberada, documentada aqui — não um descarte silencioso.
