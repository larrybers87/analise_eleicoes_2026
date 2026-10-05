# Fontes de dados

Atualizado em 2026-10-05. Toda descoberta nova sobre os dados entra aqui.

## Resposta curta: existe base pronta?

Existe, em duas camadas, e **não precisamos criar dados do zero** — precisamos montar a nossa base *a partir* das fontes oficiais:

1. **API JSON de divulgação do TSE** (disponível agora, é o que alimenta o site de resultados). Resultado por Brasil, UF e **município**, inclusive exterior. Não traz zona/seção agregadas.
2. **Portal de Dados Abertos do TSE** (CSV). Para 2026, em 05/10, só existem "Correspondências esperadas e efetivadas" e logs; os conjuntos "Resultados - 2026" (votação por seção, votação nominal por município e zona, detalhe da apuração) **ainda não foram publicados**. Em 2022/2024 eles saíram depois da eleição; a data exata para 2026 não sei — monitorar. **Já usados (F3, enriquecimento)**: Resultados **2022** completos (Presidente, município×zona, 2 turnos) e **Eleitorado 2026** (perfil por município×zona×demografia) — ver seção 2 abaixo.
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
- Especificações oficiais (PDF): EA10 eleitos, EA11 config eleições, EA12 config municípios, EA14/EA15 acompanhamento, EA16 config seções, EA18 auxiliar de seção, EA20 resultado unificado. Página: https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados. **Não conseguimos baixar em 05/10/2026** por bloqueio de rede neste ambiente (ver Armadilhas); campos documentados inicialmente por inspeção direta dos 3 JSONs reais (`mun-e006257-cm.json`, `br-c0001-e006257-u.json`, `pr75353-c0001-e006257-u.json`). **Atualização (mesmo dia, coleta completa)**: o usuário baixou os PDFs EA10/EA12/EA20 fora deste ambiente e colocou em `docs/specs/`; conferimos a inspeção contra a spec oficial — resultado em "Confronto com a especificação oficial" logo abaixo.

### Estrutura real confirmada (validação 05/10/2026, ver `scripts/validar_fontes.py`)

**Config de municípios (EA12, `mun-e006257-cm.json`)** — chaves de topo `dg`/`hg`/`idg` (data/hora/id de geração), `f`, e `abr`: lista com **28 abrangências** (27 UFs + `zz`=EXTERIOR), cada uma `{cd: sigla uf minúscula, ds: nome da UF, mu: [...]}`. Cada município em `mu[]`: `cd` (código TSE, 5 dígitos), `cdi` (código IBGE, 7 dígitos; **vazio `""` no exterior**, sem correspondente IBGE), `nm` (nome em caixa alta, UTF-8 válido — se aparecer corrompido no terminal é problema de codepage do console, não do arquivo), `c` (`"s"` para a capital da UF — exatamente 1 por UF, todas `"n"` em `zz`; é assim que achamos o código de Curitiba sem hardcode), `z` (lista de zonas eleitorais, string de 4 dígitos). Total **5.757 entradas** em `abr[].mu`: **5.571** municípios do Brasil (inclui DF) + **186** "municípios" do exterior (cidades, sem código IBGE).

**Resultado unificado (EA20, `*-c0001-e006257-u.json`)** — mesmo schema em BR/UF/município, abrangência identificada por `tpabr` (`br`|`uf`|`mu`) + `cdabr`. Cabeçalho: `ele` (eleição), `t` (turno), `dg`/`hg` (geração), `dt`/`ht` (totalização), `and` (**status da totalização**: `"p"` parcial, `"f"` final — confirma a nota de Armadilhas sobre `and=f`), `md`.
  - Bloco `s` (seções): `ts`/`st` (total), `snt` (não totalizadas), `si`/`sni` (informadas / não informadas), `sa`/`sna` (aptas / não aptas) — cada um com par `p<campo>` (% formatado, 2 casas, ex. `"99,99"`) e `p<campo>n` (% com mais casas decimais, ex. `"99,991787649"`). **Correção 05/10/2026 (coleta completa): `p<campo>n` também usa vírgula como separador decimal, não ponto** — a entrada anterior desta tabela estava errada (baseada em leitura apressada de um valor que por coincidência não tinha parte decimal, ex. `"100"`/`"0"`). Ver Armadilhas.
  - Bloco `e` (eleitorado): `te`/`est` (total), `esnt`/`esi`/`esni` (idem seções), `esa`/`esna`, **`c` (comparecimento)**, **`a` (abstenção)**.
  - Bloco `v` (votos): `tv` (total = `c`), `vv` (válidos), `vvc` (válidos computados, igual a `vv` nas amostras), `vnom` (nominais, = `vv` para Presidente — sem voto de legenda), `van` (anulados), `vansj` (**anulados sub judice** — `0` nas amostras), `vb` (brancos), **`tvn` (total de nulos) = `vn` (nulos comuns) + `vnt` (nulos "técnicos")**, `vsan`/`vscv` (0 nas amostras).
  - `carg[]` (cargo Presidente): `fed[]` (federações partidárias), `agr[]` (agremiações: coligação `tp="c"` ou partido isolado `tp="i"`) → `agr.par[]` (partido: `n`, `sg`, `nm`, `nfed`) → `par.cand[]` (candidato: `n` número, `sqcand`, `nm` nome completo, `nmu` nome de urna, `seq` **posição de classificação** (1º, 2º...), `e` (`"s"`/`"n"` — **"s" = eleito OU vai a 2º turno**, não só "eleito"; ver "Confronto com a especificação oficial"), `st` (situação, vazio até decidido), `vap` **votos apurados**, `pvap`/`pvapn` **% sobre `vv`**, `vs[]` vice (`tp="v"`)).

**Totalização ainda em curso em 05/10/2026**: no nível BR, `and="p"` com `s.sni=41` (41 seções **não instaladas**, não "não totalizadas" — `s.snt=0` na BR; ver nota de correção em Armadilhas sobre `snt` vs `sni`); no município de Curitiba, `and="f"` com `s.sni=0` e `s.snt=0` (totalizado). Isso afeta os invariantes — ver Armadilhas.

### Confronto com a especificação oficial (PDFs em `docs/specs/`, conferido 05/10/2026)

O usuário baixou `tse-ea12-arquivo-de-configuracao-de-municipios.pdf` e
`tse-ea20-arquivo-de-resultado-unificado.pdf` fora deste ambiente (bloqueado
por rede). Conferimos o parser (`src/eleicao/parse_ea20.py`) e os testes
(`tests/test_invariantes.py`) contra a spec oficial. Resultado:

**EA12 (config de municípios): nenhuma divergência.** Toda a estrutura que
documentamos por inspeção (`dg`/`hg`/`idg`/`f`/`abr[].cd,ds,mu[].cd,cdi,nm,c,z`)
bate exatamente com a spec, inclusive os significados (`c="s"`→capital,
`cdi`→código IBGE, `z[]`→zonas eleitorais 4 dígitos).

**EA20 (resultado unificado): 4 divergências entre o que inferimos empiricamente
e o que a spec realmente define — todas corrigidas no parser/testes nesta
sessão (commit "confronta parser EA20 com especificação oficial"):**

1. **`v.vn` vs `v.tvn` — confirmado pela spec, não só empiricamente.** A spec
   (pg.19, hierarquia do elemento `v`) define literalmente:
   `tvn (Total de Votos Nulos) = vn (Votos Nulos) + vnt (Votos Nulos Técnicos)`.
   `vn`: "Votos Nulos - Quantidade de votos nulos computados" (voto inválido
   escolhido pelo eleitor na urna). `vnt`: "Votos Nulos Técnicos" — a spec não
   detalha a causa técnica exata, só a fórmula de composição. Nossa inferência
   da etapa 2 (baseada em `tvn = vn + vnt` bater nos dados) estava **correta**;
   agora tem respaldo textual, não só numérico.
2. **Fórmula completa de `tv` (comparecimento) — tínhamos uma versão incompleta.**
   A spec (pg.20) define `tv = vb + vn + vnt + van + vansj + vv` — nosso teste
   de invariante original checava só `vv + vb + tvn == tv`, omitindo `van`
   (anulados) e `vansj` (anulados sub judice). Como os dois são `0` em toda a
   amostra de 05/10/2026, o teste "fechava" por coincidência, não porque a
   fórmula estivesse completa. Corrigido: o teste agora soma `anulados +
   anulados_sub_judice` também (continua passando, mas pela fórmula certa —
   deixaria de "fechar por acaso" se algum candidato tiver votos anulados no
   futuro, ex. cassação após o 1º turno).
3. **`van`/`vansj` (anulados / anulados sub judice): confirmado o significado
   pela spec, distinto de "nulo".** `van`: "Votos Anulados – Quantidade de
   votos anulados computados". `vansj`: "Votos Anulados Sub Judice". Esses
   campos compõem `vvc` (`vvc = vv + van + vansj`, "Votos a Votáveis
   Concorrentes") — são votos dados a um candidato cuja destinação foi
   **anulada** (ex. por decisão judicial sobre a candidatura), e por isso
   descontados dos válidos; **não são a mesma coisa que voto nulo** (escolha
   inválida do eleitor na urna, blocos `vn`/`vnt`). Campo `cand.dvt` /
   `par.dvt` ("Destinação do voto") usa exatamente os 4 valores — Válido,
   Válido (legenda), Anulado, Anulado sub judice — confirmando que
   "anulado" é uma categoria de **destinação do voto do candidato**, não de
   tipo de voto da urna.
4. **Campo `e` (candidato): renomeamos a coluna `eleito`→`classificado` —
   divergência de nomenclatura, não de dado.** A spec (pg.13) diz
   textualmente: "`e`: Indica se o candidato está eleito ou não... Caso o
   candidato tenha ido para o segundo turno, esse campo **também** será
   preenchido com `s`." Ou seja, `e="s"` significa "eleito OU vai a 2º
   turno" — nomear a coluna `eleito` (como fizemos na etapa 2) seria
   enganoso assim que o 1º turno definir quem avança (hoje, 05/10, `e="n"`
   para todos os candidatos, inclusive os 2 primeiros colocados — mas o
   campo `md` da BR já é `"s"` = "segundo turno matematicamente definido",
   então o `e` dos 2 primeiros deve virar `"s"` em breve). Renomeado para
   `classificado`; `situacao` (`st`) continua sendo o campo que desambigua
   (`"Eleito"` vs `"2º turno"` vs `"Não eleito"` etc.), mas só é preenchido
   após a **totalização final** (ver item 5).
5. **Campos raiz que faltavam: `md`, `tf`, `dv` — agora capturados.**
   Descobrimos ao ler a spec que `tf` (Totalização Final, **judicial** — "o
   processo de finalização da eleição, quando um juiz eleitoral finaliza a
   eleição elegendo ou não os candidatos") é **diferente** de `and`
   (totalização **operacional** do recebimento de boletins). A nota anterior
   desta tabela e o teste antigo ("só vale quando `and=='f'`") confundiam os
   dois conceitos. Novo mapeamento: `matematicamente_definido` ← `md` (`"s"`
   segundo turno, `"e"` eleito, ausente = não definido — **hoje, 05/10/2026,
   a BR já tem `md="s"`: o 2º turno já está matematicamente certo**, mesmo
   com a totalização ainda parcial); `tf_judicial` ← `tf` (`"s"`/`"n"`,
   sempre `"n"` nesta amostra); `divulga_votacao` ← `dv`.

**Nenhuma outra divergência spec-vs-JSON foi encontrada** nos elementos
`carg`/`fed`/`agr`/`par`/`cand`/`vs`/`s`/`e` além dos 5 pontos acima — os
demais campos que já mapeávamos (`nr_candidato`, `nm_urna`, `partido`,
`votos`, `pct_validos`, `eleitorado`, `comparecimento`, `abstencao`,
`validos`, `brancos`, `secoes_*`) batem exatamente com os nomes e definições
da spec.

### Armadilhas

- **Rate limit 100 req/s por IP**, bloqueio 10 min renovável. Usar ≤10 req/s.
- **404 em excesso bloqueia o IP.** Gerar URLs só a partir do config. Município com 5 dígitos.
- Não há arquivo de índice; não dá para listar diretórios.
- CDN suporta ETag/Last-Modified, mas 304 também conta no rate limit.
- Campo `and` (andamento, **operacional** — distinto de `tf`, totalização final **judicial**, ver "Confronto com a especificação oficial"): `"f"` indica totalização finalizada. Regra exata para Eleição Federal (spec EA20 pg.10): abrangência **municipal** → `and="f"` quando `s.snt==0` (seções não totalizadas); abrangência **estadual** → idem (`s.snt==0`, agregado na própria UF); abrangência **federal (BR)** → `and="f"` só quando houver totalização final. **Importante**: `s.snt==0` não é o mesmo que `s.sni==0` nem que `eleitorado==extra_e_esi` — ver os dois itens abaixo e os testes `test_comparecimento_mais_abstencao_igual_eleitorado_em_secoes_instaladas`/`test_eleitorado_igual_esi_somente_sem_pendencia_de_instalacao_ou_totalizacao`.
- Os JSONs são assinados (JWS) — verificação opcional, manual oficial na mesma página.
- `robots.txt` bloqueia crawlers genéricos (WebFetch do Claude falha); acesso programático por script próprio é o uso previsto pelo TSE para "entidades divulgadoras" (sem cadastro, Res. TSE 23.751/2026, arts. 264–269).
- **`www.tse.jus.br` e `divulgacandcontas.tse.jus.br` retornam 403 para o IP deste ambiente de execução** (inclusive a própria home e o `robots.txt` — bloqueio de rede/WAF, não é o rate limit de resultados). `resultados.tse.jus.br` (API de resultados) e `dadosabertos.tse.jus.br` funcionam normalmente. Consequência: não conseguimos baixar os PDFs EA12/EA20 nesta sessão; documentamos os campos por inspeção direta dos JSONs reais. Se precisar dos PDFs, baixar fora deste ambiente (rede doméstica) e colocar em `docs/specs/`.
- **`comparecimento + abstencao == eleitorado` NÃO é o invariante certo — correção pós-spec.** O invariante universal e exato (confirmado pela spec, pg.18-19, e por 100% das 5786 linhas coletadas, sem exceção) é `e.c + e.a == e.esi` (eleitorado das seções **instaladas**), sempre, independente de `and`. `e.esi == e.te` (eleitorado total) só quando **duas** condições valem ao mesmo tempo: `e.esni==0` (nenhuma seção "não instalada") **e** `e.esnt==0` (nenhuma seção "não totalizada") — não basta `and=="f"` (ver próximo item e os 2 testes correspondentes em `tests/test_invariantes.py`).
- `validos + brancos + nulos + anulados + anulados_sub_judice == comparecimento` (fórmula completa da spec, pg.20: `tv = vb + vn + vnt + van + vansj + vv`). Usamos **`v.tvn`** (não `v.vn` isolado) como "nulos", pois `v.tvn = v.vn + v.vnt` (nulos comuns + nulos "técnicos", spec pg.21). `van`/`vansj` são sempre `0` nesta amostra, mas agora estão na fórmula do teste (antes não estavam, e o teste só "fechava" porque `van`/`vansj` coincidiam com 0 — ver "Confronto com a especificação oficial").
- `v.van`/`v.vansj` (anulados / anulados sub judice): **não são "nulos"** — são votos de candidatos cuja destinação foi anulada (ex. decisão judicial sobre a candidatura), categoria de "destinação do voto" (`cand.dvt`/`par.dvt`: Válido | Válido (legenda) | Anulado | Anulado sub judice). Vieram `"0"` nas amostras de 05/10/2026; se algum caso tiver valor > 0 no futuro (ex. candidatura cassada), o invariante acima já soma esses campos corretamente — não precisa de tratamento à parte.
- **`and=="f"` NÃO garante que os blocos internos (`s`/`e`/`v`) estão "fechados"** (não há seção pendente). Isso é esperado pela própria spec, não é bug: para Eleição Federal, `and` de abrangência municipal/estadual vira `"f"` quando `s.snt==0` (seções "não totalizadas" zeradas) — mas uma seção pode estar `"não instalada"` (`s.sni>0`) e ainda assim contar como "totalizada" nesse sentido (ex.: posto consular cuja seção nunca teve urna instalada — ver os 40 casos `zz` documentados em "Divergências reais"). Para saber se `eleitorado==comparecimento+abstencao` (sem sobra), cheque `esni==0 and esnt==0`, não `and=="f"`.
- `tf` (Totalização Final, **judicial** — juiz declara eleitos/não eleitos) é diferente de `and` (andamento **operacional** do recebimento de boletins) — campos distintos no root do EA20, confundidos na primeira versão desta documentação. `tf="n"` em toda a amostra de 05/10/2026 (nenhuma abrangência teve finalização judicial ainda, nem mesmo as que já são `and="f"`).
- **Todos os campos percentuais usam vírgula como separador decimal, inclusive os `p<campo>n`** (ex. `pvapn: "57,499675335"`, `pcn: "80,280790419"`). A entrada original desta tabela (etapa 1) dizia que `p<campo>n` usava ponto — erro, baseado em amostra que coincidentemente não tinha parte decimal. Corrigido na etapa 2 (`src/eleicao/parse_ea20.py`, função `_float`: faz `valor.replace(",", ".")` antes de `float()`). Atenção ao escrever qualquer novo parser/notebook que leia esses campos.
- Config de municípios tem alguns nomes com acentuação corrompida quando lidos por `cat`/terminal Windows com codepage errado (ex. `ACREL�NDIA`) — **não é problema do arquivo** (é UTF-8 válido; confirmado abrindo com `encoding="utf-8"` em Python), é só exibição no console.
- **Arquivos de UF e de município podem estar em gerações diferentes do backend do TSE** (campos `dg`/`hg`/`idg` do cabeçalho do EA20 divergem entre o arquivo de um município e o arquivo da UF que o contém, mesmo pedindo os dois quase ao mesmo tempo). Confirmado investigando BA/MG (ver "Divergências reais" item 1): 11 municípios estavam servindo uma geração de **04/10/2026 ~21:00** (`idg`~1,8 milhão) enquanto suas UFs já estavam em **05/10/2026 ~02:59** (`idg`~2,79 milhão). Rebaixar com `--force` resolveu para MG (nova geração, convergiu) mas **não** para BA (o servidor respondeu com os mesmos bytes antigos de novo) — ou seja, `--force` não é garantia de pegar a geração mais nova; o CDN/backend pode genuinamente não ter propagado a atualização para aquele recurso específico ainda. **Lição para rotina de atualização futura**: comparar `idg` de município vs UF a cada atualização; se divergente, `--force` só nesse item (nunca "varrer tudo de novo" — risco de bloqueio); se persistir divergente após `--force`, tratar como pendência conhecida do TSE e catalogar em `data/known_issues.csv`, não insistir em loop.
- **O TSE pode atualizar resultados depois de qualquer snapshot que coletarmos** — por decisões judiciais, recursos, ou simplesmente a totalização operacional (`and`) continuar avançando. `data/processed/snapshot_6257.json` registra a geração exata do arquivo BR (`idg`/`dg`/`hg`) e quando a coleta completa (etapa 2) e a atualização dirigida de BA/MG foram feitas — é a "versão" do TSE que os Parquet de `data/processed/` representam. Reforça a distinção já documentada entre `and` (andamento **operacional**, pode variar a cada totalização) e `tf` (totalização **final judicial**, só muda quando um juiz eleitoral decide) — um snapshot com `tf="n"` (como o nosso) é, por definição, **provisório**: mesmo abrangências com `and="f"` podem ter seus números revistos depois se `tf` ainda não é `"s"`.

### Divergências reais encontradas na coleta completa (05/10/2026, 1º turno)

Coleta completa executada 05/10/2026 11:40:49–11:51:22 (10min33s), 5786 itens
(1 BR + 28 UF + 5757 municípios), 5784 novos + 2 cache-hit (BR e Curitiba,
herdados da etapa 1), **0 404 / 0 erro**. Ao rodar `tests/test_invariantes.py`
sobre o resultado, **3 dos 9 testes falharam** — não foram "corrigidos" para
passar; eram divergências reais, documentadas aqui. **Atualização pós-conferência
com a spec oficial**: 1 dessas 3 (item 2 abaixo) não era uma divergência real
do TSE — era a nossa compreensão do invariante que estava incompleta; a spec
explica o comportamento exatamente. Reescrevemos os testes correspondentes
(ver "Confronto com a especificação oficial"); agora **21 testes, 19 passam,
2 falham** — só o item 1 abaixo (genuinamente um dado inconsistente do TSE).

1. **[DIVERGÊNCIA REAL DO TSE — investigada a fundo em 05/10/2026 12:24,
   resultado MISTO: MG convergiu, BA continua divergente]** UF marcava
   `and="f"` (`s.snt==0` na UF) mas 11 municípios dentro dela ainda tinham
   `s.snt>0` (`and="p"`). Afetava 2 UFs (BA: 3 municípios; MG: 8 — ver lista
   completa na versão anterior desta entrada, no histórico do git).
   **Diagnóstico de geração** (`scripts/diagnostico_ba_mg.py`, compara
   `dg`/`hg`/`idg` do município com os da UF): os 11 municípios divergentes
   tinham `dg`/`hg`/`idg` de **04/10/2026 ~20:54–21:01** (noite da eleição,
   `idg` ~1,83–1,89 milhão), enquanto as UFs BA/MG já estavam em
   `dg`/`hg`/`idg` de **05/10/2026 ~02:59** (`idg` ~2,79 milhão) — ou seja,
   os arquivos de município estavam servindo uma **geração muito mais
   antiga** do backend do TSE do que o arquivo agregado da própria UF
   (confirma a hipótese de cache desatualizado/não propagado por
   município, não um erro de agregação por si só).
   - **Ação**: `python scripts/coletar_presidente.py --force --apenas
     uf:ba,uf:mg,mun:ba:33693,mun:ba:34673,mun:ba:36013,mun:mg:41556,mun:mg:41696,mun:mg:42005,mun:mg:46078,mun:mg:47198,mun:mg:40622,mun:mg:51977,mun:mg:53171`
     (13 arquivos, 0 404/0 erro, ~1,3s a ~10 req/s — ver
     `data/raw/coleta_6257.log`).
   - **MG convergiu totalmente**: os 8 municípios voltaram com nova geração
     (`dg`=05/10/2026 11:46, `idg`~2,82 milhão — mais recente até que a UF
     tinha antes), `and="f"`, `snt=0`, `si==ts` em todos. A própria UF de MG
     também avançou de geração (`idg` 2789926→2824258) ao ser rebaixada. Os
     testes de soma município↔UF para MG fecham perfeitamente agora.
   - **BA NÃO convergiu**: os 3 municípios voltaram com **exatamente os
     mesmos bytes** de antes (`dg`=04/10/2026 21:01, `idg`~1,88 milhão,
     `and="p"`) — o CDN/backend do TSE ainda está servindo a versão da
     noite da eleição para esses 3 recursos específicos, mesmo sob pedido
     forçado (não é cache do nosso lado: `--force` ignora nosso cache local
     e faz requisição HTTP nova; o servidor que respondeu com o conteúdo
     antigo). A UF de BA também não mudou (`idg` igual, 2789126) — ou seja,
     não houve nenhuma atualização de geração para BA desde 02:59:42, nem
     no agregado nem nos municípios. Divergência residual catalogada em
     `data/known_issues.csv` (ver item 3 abaixo).
   - Tamanho da divergência residual (BA, % do total oficial da UF):
     comparecimento -1.322 (-0,0146%), abstenção -334 (-0,0148%), válidos
     -1.244 (-0,0145%), brancos -29 (-0,0187%), nulos -49 (-0,0145%). Por
     candidato, maior efeito em `13`/Lula (-967, -0,0171% do total do
     candidato na UF) e `22`/Bolsonaro (-236, -0,0097%) — todas as
     divergências são **< 0,02%** de qualquer total relevante.
   - **Lição para uma rotina de atualização futura**: arquivos de UF e de
     município são cacheados/gerados **independentemente** no backend do
     TSE — não há garantia de que tenham a mesma geração (`dg`/`hg`/`idg`)
     no mesmo instante, mesmo que o agregado de UF já reflita dados mais
     novos. Uma rotina de atualização periódica deveria: (a) checar
     `idg` do município vs `idg` da UF a cada atualização; (b) se
     divergentes, rebaixar o município com `--force`; (c) se persistir
     divergente após `--force` (como BA aqui), tratar como "pendência
     conhecida do backend do TSE" e catalogar, não insistir em loop
     (reduz risco de bloqueio por excesso de requisições).
2. **[NÃO é mais tratado como divergência do TSE — nossa fórmula do
   invariante estava incompleta, a spec explica.]** Os 40 "municípios" do
   exterior (`zz`) com `s.ts=1`, `s.si=0` (a única seção nunca foi
   instalada) e `and="f"` mesmo assim, com `comparecimento=0` e
   `abstencao=0` enquanto `eleitorado>0` (ex. `99198` ABUJA, eleitorado=3) —
   isso é **exatamente o esperado pela spec**: `c`/`a` (comparecimento/
   abstenção) são definidos como "do eleitorado das seções **instaladas**"
   (spec pg.18-19), e `and="f"` para Eleição Federal depende só de
   `s.snt==0` (seções não totalizadas), não de `s.sni==0` (seções não
   instaladas) — uma seção pode nunca ter sido instalada (sem urna, ex.
   posto consular sem votantes presentes) e ainda assim contar como
   "totalizada" nesse sentido. Confirmamos com a spec: `comparecimento +
   abstencao == extra_e_esi` vale nos 40 casos (e nos outros 5746), só
   `eleitorado == extra_e_esi` que não vale (porque `extra_e_esni>0`). Os
   testes antigos (`test_comparecimento_mais_abstencao_igual_eleitorado_quando_final`)
   foram **substituídos** por
   `test_comparecimento_mais_abstencao_igual_eleitorado_em_secoes_instaladas`
   (universal, sempre passa) e
   `test_eleitorado_igual_esi_somente_sem_pendencia_de_instalacao_ou_totalizacao`
   (documenta exatamente quando `eleitorado==esi`, também sempre passa) —
   não foi "relaxado" para esconder o caso, foi corrigido porque a premissa
   anterior (comparar com `eleitorado`, condicionado a `and`) estava errada.
3. **Catálogo `data/known_issues.csv`**: como a divergência de BA (item 1)
   não converge mesmo com `--force` — é uma pendência do backend do TSE,
   fora do nosso controle —, catalogamos os valores exatos nesse CSV
   (colunas `uf, cd_mun_tse, campo, valor_soma, valor_oficial, diferenca,
   observado_em`; `cd_mun_tse` fica vazio porque a divergência é do
   **agregado** soma-dos-3-municípios vs UF, não atribuível a um único
   município isoladamente — não sabemos qual fração cada um dos 3
   contribui para o total final real, só o resultado agregado). Os testes
   `test_soma_municipios_por_uf_fecha_com_arquivo_oficial_da_uf` e
   `test_soma_municipios_por_uf_fecha_votos_por_candidato` agora exigem
   **igualdade exata** entre as divergências observadas e as catalogadas —
   uma divergência nova (não catalogada) falha o teste; uma divergência
   catalogada que deixar de se repetir (TSE corrigiu) **também** falha o
   teste, forçando revisão manual do CSV em vez de ficar "esquecido".

## 2. Portal de Dados Abertos (dadosabertos.tse.jus.br)

- Grupo resultados: https://dadosabertos.tse.jus.br/group/resultados
- Esperado para 2026 (por analogia a 2022): `votacao_secao_2026_<UF>.zip`, `votacao_candidato_munzona_2026`, `detalhe_votacao_munzona_2026` (abstenção, brancos, nulos por zona), boletins de urna. **Ainda não publicado em 05/10/2026.**
- Encoding dos CSVs do TSE: `latin-1`, separador `;`, campos entre aspas (inclusive numéricos). `#NULO`/`#NE` (texto) e `-1`/`-3` (numérico) são os marcadores de ausência do TSE — ver `leiame.pdf` de cada pacote (extraído e lido com o Read tool nesta sessão, não achado por busca na web).
- **Confirmado em 05/10/2026 (F3, enriquecimento): abrangência Federal (Presidente) mora inteira no CSV `..._BR.csv` de cada pacote** — não precisa dos outros 27 CSVs por UF (que só têm os cargos de abrangência estadual/municipal). Isso reduz drasticamente o que precisa ser lido: dos 642MB do zip `votacao_candidato_munzona_2022.zip`, só os 38MB do `..._BR.csv` interessam para Presidente.

### 2.1 Resultados 2022 — Presidente (município×zona)

- **Candidatos**: https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip (642MB; só o membro `votacao_candidato_munzona_2022_BR.csv`, 38MB/81.679 linhas, interessa — abrangência Federal). `data/raw/dadosabertos/cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip`.
- **Totais** (eleitorado/comparecimento/abstenção/brancos/nulos): https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2022.zip (4,4MB; membro `detalhe_votacao_munzona_2022_BR.csv`, 12.566 linhas). `data/raw/dadosabertos/cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2022.zip`.
- Os dois arquivos já trazem **1º e 2º turno juntos** (`NR_TURNO`) — baixar o 2º turno não custou nada a mais (ao contrário do que a tarefa temia).
- Nível real do arquivo: **município×zona×candidato** (candidatos) / **município×zona** (totais) — agregamos zona→município somando (`groupby(["uf","cd_mun_tse"])`, zonas de um mesmo município sempre têm o mesmo `NM_URNA_CANDIDATO`/`SG_PARTIDO`, usamos o primeiro valor do grupo para esses campos textuais).
- `ST_VOTO_EM_TRANSITO` e `NM_TIPO_DESTINACAO_VOTOS` são sempre `"N"`/`"Válido"` em toda a amostra de Presidente 2022 — nenhum voto em trânsito nem anulado/sub judice no cargo (diferente do que o `leiame.pdf` geral do portal insinua ser possível).
- **Mapeamento para `presidente_2022_t<turno>_municipio.parquet`** (candidatos): `SG_UF`→`uf` (minúsculo), `CD_MUNICIPIO`→`cd_mun_tse` (`.zfill(5)` — vem **sem** zero à esquerda neste arquivo, ex. `"5231"`, diferente do `detalhe_votacao_munzona` que já vem com 5 dígitos), `NR_CANDIDATO`→`nr_candidato`, `NM_URNA_CANDIDATO`→`nm_urna`, `SG_PARTIDO`→`partido`, `QT_VOTOS_NOMINAIS`→`votos` (somado por zona). `pct_validos` é **calculado** (`votos / validos_do_município * 100`), não vem pronto no CSV.
- **Mapeamento para `presidente_2022_t<turno>_municipio_totais.parquet`**: `QT_APTOS`→`eleitorado`, `QT_COMPARECIMENTO`→`comparecimento`, `QT_ABSTENCOES`→`abstencao`, `QT_TOTAL_VOTOS_VALIDOS`→`validos`, `QT_VOTOS_BRANCOS`→`brancos`, `QT_TOTAL_VOTOS_NULOS`→`nulos_tvn`, `QT_VOTOS_NULOS`→`nulos_vn` (sempre igual a `nulos_tvn` nesta amostra — `QT_VOTOS_NULOS_TECNICOS` é sempre 0, diferente de 2026 onde às vezes é >0), `QT_TOTAL_VOTOS_ANULADOS`→`anulados`, `QT_TOTAL_VOTOS_ANUL_SUBJUD`→`anulados_sub_judice` (ambos sempre 0 na amostra, igual a 2026). `cd_mun_ibge` é adicionado via join com o config de 2026 (`mun-e006257-cm.json`, `cd`→`cdi`) — **não vem do CSV de 2022**, que só tem o código TSE.
- **Invariantes confirmados contra o próprio arquivo (não só contra os números de referência do usuário)**: soma de `votos` de todos os candidatos no município == `validos` do município (100% das linhas, em todos os 5.751 municípios); `validos+brancos+nulos_tvn+anulados+anulados_sub_judice == comparecimento` (100%); soma nacional por candidato — **Lula 57.259.504 / Bolsonaro 51.072.345 no 1º turno** batem exatamente com os números de referência do usuário; 2º turno, Lula 60.345.999 / Bolsonaro 58.206.354 (checado contra o resultado oficial público, não fornecido pelo usuário).
- `comparecimento + abstencao == eleitorado` **não** é exato: 42 municípios divergem (soma residual nacional de -657). 41 são postos no exterior com `comparecimento=abstencao=0` mas `eleitorado>0` (mesmo padrão dos 40 casos de 2026 — seção nunca instalada; o arquivo de 2022 não tem os campos `esni`/`esnt` que explicariam exatamente, então não dá para provar a condição completa como em 2026, só documentar o padrão). O caso restante é **Manaus/AM** (`02550`): `eleitorado=1.418.757`, `comparecimento+abstencao=1.418.673`, diferença de -84 (0,006% do eleitorado do município) — pequeno demais para investigar a fundo, registrado aqui como quirk conhecido do dado de 2022.
- **Join 2022↔2026 pelo código TSE** (`cd_mun_tse`, 5.751 municípios em 2022 vs 5.757 em 2026): só **1** órfão de cada lado é inesperado, e ambos são explicáveis — **município criado/extinto é raro, mas não inexistente**, como a tarefa pediu para confirmar em vez de assumir:
  - Só em 2022: `zz99252` VATICANO — posto consular fechado entre as duas eleições.
  - Só em 2026: `mt73709` BOA ESPERANÇA DO NORTE (MT, `cdi=5101837`) — **município brasileiro novo**, emancipado depois de 2022, sem resultado 2022 para comparar (esperado — não existia); mais 6 postos consulares novos no exterior (`zz29629` DACCA, `zz99279` SANTA ELENA DE UAIRÉN, `zz99295` PYONGYANG, `zz99490` ORLANDO, `zz99503` EDIMBURGO, `zz99511` MARSELHA).

### 2.2 Perfil do eleitorado 2026

- https://dadosabertos.tse.jus.br/dataset/eleitorado-2026 → **Eleitorado - 2026**: https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_eleitorado/perfil_eleitorado_2026.zip (408MB; só o membro `perfil_eleitorado_2026_BRASIL.csv` interessa, 2,17GB descomprimido/~11M linhas — os 27+1 CSVs por UF dentro do mesmo zip são redundantes com ele, mesmo padrão do item 2.1). `data/raw/dadosabertos/cdn.tse.jus.br/estatistica/sead/odsele/perfil_eleitorado/perfil_eleitorado_2026.zip`.
- **Já vem agregado** por `SG_UF`×`CD_MUNICIPIO`×`NR_ZONA`×(gênero, estado civil, faixa etária, grau de escolaridade, raça/cor, identidade de gênero, quilombola, intérprete de libras) — **não é 1 linha por eleitor**, é a contagem `QT_ELEITORES` de cada combinação. Processado em `chunksize=1_000_000` (`scripts/processar_eleitorado.py`, ~1min/11M linhas) para não estourar memória; cada pedaço é reduzido a 4 somas parciais (total/sexo/faixa/grau) antes de acumular — só o agregado final fica em memória inteiro.
- **Nomes de colunas reais do CSV divergem do `leiame.pdf`** em 2 campos: o PDF documenta `QT_ELEITORES_PERFIL` e `QT_ELEITORES_INC_NM_SOCIAL`, o CSV real tem `QT_ELEITORES` e `QT_ELEITORES_NOME_SOCIAL`. Usamos os nomes reais do CSV (conferidos por inspeção direta do cabeçalho).
- **Categorias confirmadas por inspeção dos dados** (não assumidas do PDF, que só documenta os códigos de sexo/escolaridade, não a faixa etária):
  - `DS_GENERO`: `MASCULINO`, `FEMININO`, `NÃO INFORMADO`.
  - `DS_FAIXA_ETARIA`: `16 anos`, `17 anos`, `18 anos`, `19 anos`, `20 anos`, depois de 5 em 5 anos — `21 a 24 anos`, `25 a 29 anos`, ..., `95 a 99 anos` —, `100 anos ou mais`, e `Inválida` (idade não aferível, residual). **Não existe um bin único "16 a 17 anos"** — são dois bins de 1 ano cada (facultativo é 16 **e** 17, não "16 a 17" como categoria do TSE).
  - `DS_GRAU_ESCOLARIDADE`: `ANALFABETO`, `LÊ E ESCREVE`, `ENSINO FUNDAMENTAL INCOMPLETO`, `ENSINO FUNDAMENTAL COMPLETO`, `ENSINO MÉDIO INCOMPLETO`, `ENSINO MÉDIO COMPLETO`, `SUPERIOR INCOMPLETO`, `SUPERIOR COMPLETO`, `NÃO INFORMADO` (9 categorias, batem com o PDF).
- **Schema de saída** (`eleitorado_perfil_2026_municipio.parquet`, 1 linha por município, 5.757 linhas = Brasil + exterior): `uf, cd_mun_tse, nm_mun_tse, total` + `pct_sexo_<slug>` (3 colunas, partição, soma 100%) + `pct_faixa_<slug>` (23 colunas — 22 bins + `invalida`, partição, soma 100%) + `pct_grau_<slug>` (9 colunas, partição, soma 100%) + **2 colunas extras dedicadas**, fora da partição de faixa etária: `pct_faixa_facultativa_16_17` (= `pct_faixa_16 + pct_faixa_17`) e `pct_faixa_facultativa_70_mais` (soma de `70_74` até `100_mais`) — como a tarefa pediu destaque explícito para essas duas faixas (voto facultativo) e elas não existem como bin único do TSE, a soma é feita em Python (`src/eleicao/parse_eleitorado.py:pivotar_wide`), documentada para quem for somar `pct_faixa_*` "às cegas" não contar a mesma pessoa duas vezes.
- `_slug`: remove acento, minúsculo, `" a "`→`"_"`, `" ou mais"`→`"_mais"`, `" anos"`→`""` (ex. `"80 a 84 anos"`→`"80_84"`, `"Ensino médio completo"`→`"ensino_medio_completo"`).
- **Cruzamento com o EA20 (F1/F2) como conferência cruzada, não um invariante obrigatório** (são 2 produtos distintos do TSE, gerados em datas diferentes): `total` somado nacionalmente = **158.745.463** eleitores; `presidente_t1_br_totais.parquet.eleitorado` (EA20, 05/10/2026) = **158.745.502** — diferença de **39** (0,0000246%). O perfil é gerado a partir do cadastro eleitoral (`DT_GERACAO` nas linhas = 14/07/2026, bem antes da eleição — é o fechamento do alistamento, não um corte do dia da votação), o EA20 é o eleitorado apurado no 1º turno; a proximidade altíssima é uma boa confirmação de consistência entre as duas fontes, mas não motivo para forçar igualdade exata.
- **Join com o config de 2026**: as 5.757 chaves (`uf`+`cd_mun_tse`) do perfil batem **exatamente** com as 5.757 do `mun-e006257-cm.json` — 0 órfão de cada lado (diferente do cruzamento 2022↔2026, que tem postos abertos/fechados entre as duas eleições; aqui as duas fontes são do mesmo ciclo 2026).

## 4. IBGE

Duas fontes, hosts diferentes dentro do próprio IBGE — `www.ibge.gov.br` retorna
**403** neste ambiente (mesma classe de bloqueio documentada para
`www.tse.jus.br`, ver Armadilhas da seção 1), mas `servicodados.ibge.gov.br`
(API SIDRA) e `ftp.ibge.gov.br` funcionam normalmente.

### 4.1 População — Censo 2022

- API SIDRA, agregado **4709** ("População residente, Variação absoluta de
  população residente e Taxa de crescimento geométrico"), variável **93**
  ("População residente"), único período disponível: **2022** (1ª apuração
  do Censo). `GET https://servicodados.ibge.gov.br/api/v3/agregados/4709/periodos/2022/variaveis/93?localidades=N6[all]` — 1 requisição só, resposta de 689KB com os 5.570 municípios (nível `N6`). Salvo em `data/raw/ibge/servicodados.ibge.gov.br/api/v3/agregados/4709/periodos/2022/variaveis/93.json` (espelha host+path da API).
- `localidade.id` = `cd_mun_ibge` (7 dígitos); `serie."2022"` = população (string, convertida para `int`).
- **5.570 municípios** — não 5.571 como o config do TSE (`mun-e006257-cm.json`): o IBGE não reconhece Fernando de Noronha como município (é distrito estadual de PE), mas o TSE trata como uma "abrangência municipal" própria para fins eleitorais. Isso já era sabido do join TSE↔`geobr` de F1 (`scripts/diagnostico_join_ibge.py`); mencionado aqui de novo porque a diferença de contagem (5.570 vs 5.571/5.757) aparece outra vez nos joins de F3.
- Soma nacional: **203.080.756** — população residente total do Censo 2022 (1ª apuração), bate com o número oficialmente divulgado pelo IBGE.

### 4.2 PIB per capita municipal

- **Não existe um agregado SIDRA com PIB per capita em nível municipal** (checado: agregado **5938**, "PIB dos Municípios — Referência 2010", tem `N6` mas só 46 variáveis de PIB/VAB **absolutos** e "participação %", sem população nem per capita; o agregado **6784** tem PIB per capita mas só em nível **N1**, Brasil). O produto oficial "PIB per capita" municipal só existe no **arquivo de resultados completo do produto**, fora do SIDRA.
- Fonte usada: FTP público do IBGE, `https://ftp.ibge.gov.br/Pib_Municipios/2022_2023/base/base_de_dados_2010_2023_txt.zip` (7,75MB; pasta `2022_2023` é a mais recente do diretório `Pib_Municipios/`). Salvo em `data/raw/ibge/ftp.ibge.gov.br/Pib_Municipios/2022_2023/base/base_de_dados_2010_2023_txt.zip`.
- Formato: **texto de largura fixa** (não CSV), 1 linha por município×ano, 2010-2023, `latin-1`, CRLF, 1258 bytes/linha. Layout oficial em `layout_da_base_de_dados_2010_2023_em_formato_txt.pdf` (dentro do zip) — posições 1-indexadas; o parser (`src/eleicao/parse_ibge.py:_PIB_COLSPECS`) usa o intervalo **até a posição do próximo campo do layout** (não a "largura" declarada, que para campos monetários é só `dígitos.decimais`, ex. `"18.3"` — ambíguo quanto a espaço do separador decimal; a posição do próximo campo é inequívoca e foi conferida por slicing direto).
- **Ano mais recente disponível: 2023** (não 2021 — a tarefa avisou para não assumir). Nota 2 do layout: "Para os anos de 2022 e 2023 foram divulgados apenas o Produto Interno Bruto e o Produto Interno Bruto per capita" — as demais variáveis (VAB por setor etc.) ficam em branco nesses 2 anos; usamos só PIB total e per capita mesmo, então não afeta nosso schema. Nota 3: por falta da "Estimativa da População" (TCU) de 2022/2023, o PIB per capita desses 2 anos usa população do **Censo 2022** (2022) e da "Relação da População dos Municípios" enviada ao TCU em 2023 (2023) — **o PIB per capita já vem calculado pelo IBGE no arquivo**, não precisamos dividir PIB/população nós mesmos.
- Campos usados (posição → campo): 1→`ano`, 24→`sigla_uf`, 47→`cd_mun_ibge`, 55→`nm_mun_ibge` (formato `"Nome - UF"`, diferente do `nm`/`nm_mun` do TSE, que não tem sufixo de UF — não usar para exibição sem normalizar), 935→`pib_mil_reais` (R$ mil), 954→`pib_per_capita_reais` (R$ 1,00).
- **Join com população (Censo 2022) por `cd_mun_ibge`**: **5.570 = 5.570 municípios dos dois lados, 0 órfão** — as duas fontes do IBGE (Censo e PIB municipal) usam exatamente o mesmo universo de municípios.

## 5. Geometria

- Municípios/UFs: IBGE via pacote `geobr` (`read_municipality(year=2024)`, `read_state`). Simplificar (mapshaper/`topojson`) para o web.
- **Armadilha do `geobr`: `simplified=True` (o padrão) simplifica FEATURE A FEATURE.** Serve para um plot rápido no matplotlib, mas **não serve como entrada de uma topologia**: os vértices das fronteiras entre municípios vizinhos deixam de coincidir exatamente, e o `topojson.Topology` não consegue reconhecer os arcos compartilhados. Medido em 05/10/2026 (ver `docs/DECISOES.md` D-016): MG sai com **20.460 arcos** a partir da malha simplificada contra **2.533** a partir da completa; Brasil inteiro, **113.358** contra **18.140**. Como cada arco custa no mínimo 2 pontos no arquivo final, isso cria um piso de tamanho que nenhuma tolerância de simplificação consegue furar. Para qualquer uso topológico (TopoJSON, dissolve, vizinhança), use `read_municipality(year=2024, simplified=False)` — 5.571 municípios, 17.889.916 vértices, ~10s de leitura do cache do `geobr` — e simplifique depois, com `topojson`.
- A malha completa de 2024 vem com **1 geometria inválida** (corrigida com `make_valid()` em `scripts/exportar_web.py`); a simplificada vem com 0, mas pelo motivo errado.
- `dissolve` por UF da malha municipal completa leva ~70s e gera fronteiras de UF que coincidem exatamente com as dos municípios — preferível a `read_state` quando as duas camadas são desenhadas juntas.
- Zonas eleitorais: **não há polígono oficial**. Opções: (a) pontos dos locais de votação (Eleitorado por local de votação); (b) polígonos derivados (Voronoi/hull dos locais por zona) — aproximação, marcar como tal no mapa.
- Exterior: pontos por cidade ou agregação por país (geometria Natural Earth).

## Schemas normalizados (`data/processed/`, implementado na etapa 2, conferido contra a spec)

Gerados por `src/eleicao/parse_ea20.py` (`parse_ea20`, função pura) +
`scripts/processar_presidente.py` (orquestração/empilhamento). Mesmo schema
para os 3 níveis (`presidente_t1_municipio*`, `presidente_t1_uf*`,
`presidente_t1_br*`); o nível é identificado pela coluna `abrangencia`
(`"br"|"uf"|"mun"`) e, no caso de município, `presidente_t1_municipio*.parquet`
também tem a coluna booleana `eh_exterior`.

`presidente_t1_<nivel>.parquet` (candidatos; 1 linha por candidato):
`uf, cd_mun_tse, nr_candidato, nm_urna, partido, votos, pct_validos, classificado, situacao` +
`extra_cand_nm_completo, extra_cand_sqcand, extra_cand_posicao_classificacao, extra_cand_dvt,
extra_partido_nm, extra_partido_nfed, extra_partido_tvtn, extra_partido_tvan,
extra_agremiacao_tipo, extra_agremiacao_nome, extra_agremiacao_vag, extra_agremiacao_tvtn,
extra_agremiacao_tvan, extra_vice_nm_urna, extra_vice_sqcand`.
- `nr_candidato` ← `cand.n`; `nm_urna` ← `cand.nmu`; `partido` ← `par.sg`; `votos` ← `cand.vap`;
  `pct_validos` ← `cand.pvapn` **convertido de vírgula para ponto decimal** (ver Armadilhas —
  `pvapn` NÃO é ponto-decimal nativamente, ao contrário do que a etapa 1 tinha documentado).
- `classificado` ← `cand.e` (`"s"→True`, `"n"→False`). **Renomeado de `eleito` para
  `classificado` na conferência com a spec** (pg.13): `e="s"` significa "está eleito **ou**
  disputará o cargo no 2º turno" — chamar a coluna de `eleito` seria enganoso assim que o
  1º turno definir quem avança. Use `situacao` para o resultado desambiguado.
- `situacao` ← `cand.st` (vazio → `None`). Só preenchido após a totalização final
  (provavelmente ligada a `tf`, não a `and` — ver Armadilhas); valores possíveis pela spec:
  Eleito, Eleito por QP, Eleito por média, Não eleito, 2º turno, Suplente. Sempre `None` em
  05/10/2026 (nenhuma abrangência com `tf="s"` ainda).
- `extra_*`: campos existentes no JSON que não foram descartados mas também não entraram no
  nome "oficial" da coluna — nome completo do candidato (`cand.nm`, diferente de `nmu`),
  `sqcand`, posição de classificação (`cand.seq`), destinação do voto do candidato (`cand.dvt`:
  Válido/Válido (legenda)/Anulado/Anulado sub judice), nome completo do partido, código da
  federação (`par.nfed`), total de votos válidos/computados nominais do partido (`par.tvtn`/
  `tvan` — redundante com `votos` para Presidente, 1 candidato por partido, mas capturado por
  completude), tipo/nome/vagas/totais da agremiação (`agr.tp`/`nm`/`vag`/`tvtn`/`tvan`), nome de
  urna e `sqcand` do vice (`cand.vs[0]`).

`presidente_t1_<nivel>_totais.parquet` (1 linha por município/UF/BR):
`uf, cd_mun_tse, cd_mun_ibge, nm_mun, abrangencia, eleitorado, comparecimento, abstencao,
validos, brancos, nulos_vn, nulos_tvn, secoes_totalizadas, secoes_total, status_totalizacao,
data_hora_totalizacao, anulados, anulados_sub_judice, matematicamente_definido, tf_judicial,
divulga_votacao` + `extra_v_vvc, extra_v_vnom, extra_v_vnt, extra_v_vsan, extra_v_vscv,
extra_s_snt, extra_s_sni, extra_s_sa, extra_s_sna, extra_e_est, extra_e_esnt, extra_e_esi,
extra_e_esni, extra_e_esa, extra_e_esna, extra_sup, extra_esae, extra_mnae` (em
`presidente_t1_municipio_totais.parquet` também `eh_exterior`, preenchida pela orquestração,
não pelo parser).
- `cd_mun_tse`/`cd_mun_ibge`/`nm_mun` são `None` para BR e UF (o EA20 não traz nome/código IBGE
  de município — vêm do config, passados como argumento ao parser, não do próprio EA20).
- `eleitorado` ← `e.te`; `comparecimento` ← `e.c`; `abstencao` ← `e.a`; `validos` ← `v.vv`;
  `brancos` ← `v.vb`; `nulos_vn` ← `v.vn`; `nulos_tvn` ← `v.tvn` (**usar `nulos_tvn` para o
  invariante de comparecimento**, não `nulos_vn` isolado — ver Armadilhas, confirmado pela
  spec: `tvn = vn + vnt`); `secoes_totalizadas` ← `s.si`; `secoes_total` ← `s.ts`;
  `status_totalizacao` ← `and` (`"f"` final/`"p"` parcial/`"n"` não iniciada — **não é
  booleano**, decisão da etapa 2: manter o código original em vez de um `totalizacao_final:
  bool`, ainda mais importante depois de confirmar que `and` ≠ `tf` na spec); `anulados` ←
  `v.van`; `anulados_sub_judice` ← `v.vansj`.
- **Campos-raiz adicionados na conferência com a spec** (ausentes na primeira versão do
  parser): `matematicamente_definido` ← `md` (`"e"` eleito | `"s"` 2º turno matematicamente
  definido | ausente = não definido — **a BR já tem `md="s"` em 05/10/2026**, mesmo com
  `status_totalizacao="p"`: o 2º turno já é matematicamente certo antes mesmo da totalização
  terminar); `tf_judicial` ← `tf` (`"s"`/`"n"`, Totalização Final **judicial**, distinta de
  `and` — sempre `"n"` na amostra); `divulga_votacao` ← `dv` (`"s"`/`"n"`; quando `"n"`, a
  spec diz que os votos vêm zerados no arquivo — sempre `"s"` na amostra).
- `extra_*` de `v`: `vvc` (= `vv+van+vansj`, "votos a votáveis concorrentes"), `vnom`
  (nominais, == `vv` para Presidente, cargo majoritário sem voto de legenda), `vnt`
  (componente "técnico" de `tvn`), `vsan`/`vscv` (sempre `0` nas amostras; `vscv` tem
  definição na spec — "Votos Sem Candidato para Votar", só >0 quando não há candidato
  concorrendo ao cargo; `vsan`/"Votos de Seções Anuladas" não documentado com a mesma riqueza
  na spec lida). `extra_*` de `s`: contagens brutas de seções não totalizadas/instaladas/
  apuradas (não os percentuais formatados, deliberadamente omitidos — ver abaixo). `extra_*`
  de `e`: `est`/`esnt` (eleitorado em seções totalizadas/não totalizadas — **adicionados na
  conferência com a spec**, essenciais para explicar por que `eleitorado != esi` em
  abrangências com seções pendentes) e `esi`/`esni`/`esa`/`esna` (já capturados na etapa 2
  original). `extra_sup`/`extra_esae`/`extra_mnae`: eleição suplementar, "sem atribuição de
  eleito" e motivos — sempre ausentes/`None` nesta eleição (campos só populados em cenários
  que não ocorreram em 05/10/2026), capturados por completude.
- Percentuais formatados (`p<campo>`, `p<campo>n`) de ambos os blocos **não** viram coluna:
  são 100% derivados dos contadores absolutos já capturados (`campo / total * 100`); refazer
  esse cálculo em pandas/duckdb é mais simples e mais confiável do que parsear string com
  vírgula decimal. Isso é uma omissão deliberada, documentada aqui — não um descarte silencioso.

**Outros artefatos em `data/`** (fora do schema de candidatos/totais acima):
- `data/processed/snapshot_6257.json`: identifica a geração exata (`idg`/`dg`/`hg`) do arquivo
  BR e os horários da coleta completa (etapa 2) e da atualização dirigida de BA/MG — "a que
  versão do TSE" os Parquet correspondem (ver Armadilhas, "o TSE pode atualizar resultados
  depois").
- `data/known_issues.csv`: catálogo de divergências soma-município-vs-UF investigadas e sem
  conserto do lado do TSE (hoje, só BA — ver "Divergências reais" item 3). Lido por
  `tests/test_invariantes.py` (qualquer divergência fora desse catálogo falha o teste) e por
  `scripts/verificar_atualizacoes.py` (que extrai dinamicamente de `uf`/`cd_mun_tse` a lista de
  itens a reverificar — nunca hardcoded). Coluna `cd_mun_tse`: vazia quando a divergência é só de
  UF; quando há municípios associados, códigos TSE separados por `|` (ex. `33693|34673|36013`).

## Schemas normalizados (F3 — enriquecimento, `data/processed/`, 05/10/2026)

Gerados por `src/eleicao/parse_dadosabertos_2022.py` + `scripts/processar_presidente_2022.py`,
`src/eleicao/parse_eleitorado.py` + `scripts/processar_eleitorado.py`, e
`src/eleicao/parse_ibge.py` + `scripts/processar_ibge.py`. Mapeamento de campo a campo nas
seções 2.1/2.2/4 acima; aqui só o schema final.

`presidente_2022_t<turno>_municipio.parquet` (turno 1 ou 2; candidatos, 1 linha por
candidato×município, 63.261/11.502 linhas): `uf, cd_mun_tse, nr_candidato, nm_urna, partido,
votos, pct_validos` — schema deliberadamente mais enxuto que `presidente_t1_municipio.parquet`
(2026): sem os `extra_*` (nome completo do candidato, `sqcand`, coligação/federação etc.), porque
o CSV de 2022 não tem alguns desses campos no mesmo formato e a tarefa pediu só os comparáveis.

`presidente_2022_t<turno>_municipio_totais.parquet` (1 linha por município, 5.751 linhas = Brasil
+ exterior): `uf, cd_mun_tse, nm_mun_tse, eleitorado, comparecimento, abstencao, validos, brancos,
nulos_tvn, nulos_vn, anulados, anulados_sub_judice, cd_mun_ibge`. `cd_mun_ibge` vem de um join
com o config de 2026 (não existe no CSV de 2022) — `None` para os municípios/postos sem par (ver
seção 2.1, "Join 2022↔2026").

`eleitorado_perfil_2026_municipio.parquet` (1 linha por município, 5.757 linhas = Brasil +
exterior, 41 colunas): `uf, cd_mun_tse, nm_mun_tse, total` + `pct_sexo_<slug>` (3) +
`pct_faixa_<slug>` (23) + `pct_grau_<slug>` (9) + `pct_faixa_facultativa_16_17`,
`pct_faixa_facultativa_70_mais` — ver seção 2.2 para a lista de categorias e a observação sobre
as 2 colunas extras não fazerem parte da partição `pct_faixa_*`.

`ibge_municipio.parquet` (1 linha por município, 5.570 linhas — só Brasil, IBGE não tem código
para o exterior nem para Fernando de Noronha): `cd_mun_ibge, nm_mun_ibge, populacao_censo_2022,
pib_mil_reais, pib_per_capita_reais` — ver seção 4 para as fontes e o ano de cada métrica
(população: Censo 2022; PIB: 2023, o mais recente disponível).
