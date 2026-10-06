# Análises exploratórias: 1º turno de Presidente 2026

Snapshot de **05/10/2026 02:59** (dia seguinte ao 1º turno). O Brasil ainda está `and="p"`, 41 seções não instaladas e 3 municípios da BA com geração antiga do TSE (`data/known_issues.csv`, divergência de < 0,02%). Os números podem mudar com a totalização final. Todos os números abaixo saem de funções testadas em `src/eleicao/analise/` (suíte `pytest`: 173 testes passando), e os notebooks `notebooks/10_panorama.ipynb` a `17_filho_da_terra.ipynb` só chamam essas funções e plotam.

**Escopo e o que ficou de fora.** Os agregados "Brasil" são ponderados (soma de votos ÷ soma de válidos) e excluem o exterior, que aparece como recorte à parte (186 postos). Os percentuais têm denominador explícito: válidos, comparecimento ou eleitorado. Ficaram de fora: 52 pares sem comparação entre 2022 e 2026 (8 municípios ou postos sem par e 44 postos do exterior com zero votos válidos em um dos anos), listados em `sem_par` e nunca tratados como zero; os 2 empates exatos (SP 62448, TO 73555), sem vencedor; e os 3 municípios da BA em divergência conhecida. **Corte de eleitorado** para o ranking de abstenção: 10 mil eleitores (D-021), por sensibilidade medida. **Correção para múltiplos testes** na LISA: Benjamini-Hochberg, α = 0,05, permutações bicaudais (D-024). **Área**: Albers equal-area, não EPSG:5880, que é Polyconic (D-022). **Teto** de Bolsonaro = % de válidos no 2º turno 2022, no município (D-023). **Bolsão** = componente queen de municípios acima de 3× a média nacional (D-025). **Identidade**: o nº 22 é Bolsonaro em 2022 e Flávio Bolsonaro em 2026, então o swing mede a sigla, não a mesma pessoa. **Ressalva geral**: todos os achados de município são correlações ecológicas e não dizem nada sobre o comportamento de um eleitor. Os dados de PIB são de 2023 e a população é do Censo 2022, ambos defasados em relação ao eleitorado de 2026.

---

## 1. Renan Santos não tem nenhum município acima de 3× a sua média; Caiado tem 237 dos 246 de Goiás acima disso

- **Número**: média nacional de Renan Santos (nº 14) = 2,24% dos válidos BR; limiar 3× = 6,73%. **Nenhum** município ultrapassa o limiar. Caiado (nº 55): média 2,19%, limiar 6,56%; em GO ele tem 12,33% dos válidos da UF (razão 5,6×), e **237 de 246** municípios goianos passam do limiar (denominador: municípios de GO). Zema (nº 30) tem 0,82% em MG contra 0,27% nacional (razão 3,0×), com 176 de 853 municípios acima de 3× e 26 bolsões, o maior com 106 municípios no Triângulo/Alto Paranaíba (pico: Araxá, 4,67%). Cury (nº 70) tem um único município acima do limiar (Colina/SP, 17,31%).
- **Gráfico**: `img/analises/bolsoes_caiado_zema_mapa.png`
- **Ressalvas**: o "bolsão" de Caiado é, na prática, o estado de GO, então é um achado sobre estado, não sobre território. Para candidatos com pouca votação, 3× é um limiar baixo e os bolsões pequenos são em boa parte ruído. A média é ponderada sobre válidos, não a média dos municípios.
- **Vale virar seção no site?** Sim, como parte de uma seção de "redutos" com os números de UF (razão e % da UF). Os bolsões de município são difíceis de explicar ao leitor e ficam melhor como mapa de apoio.

## 2. A média simples dos municípios distorce o swing; o agregado ponderado é outro número

- **Número**: swing do PT (nº 13) 1T22→1T26 agregado, sobre válidos e ponderado: Brasil −3,3 p.p. (48,4% → 45,2%). A **mediana** municipal é −5,5 p.p. e a média simples no Centro-Oeste é −8,7 p.p., contra −5,2 p.p. no agregado ponderado. Para o PL (nº 22), o agregado é +3,8 p.p. (43,2% → 47,0%) e a mediana municipal é +5,6 p.p. (denominador do agregado: válidos de cada ano, mesma base de 5.570 municípios). **Δmargem** (variação da margem do PL sobre o PT, definida como (PL 2026 − PT 2026) − (PL 2022 − PT 2022), em p.p. de válidos de cada ano, agregado ponderado na mesma base): **+7,1 p.p.** (D-030).
- **Gráfico**: `img/analises/swing_agregado_regiao.png`, `img/analises/swing_histograma.png`
- **Ressalvas**: a diferença vem de porte. Municípios pequenos, com swing maior, pesam o mesmo que os grandes na média simples. Isso não é erro, mas é uma definição diferente, e quem lê um "swing médio" precisa saber qual das duas está sendo dita. A identidade do nº 22 muda (Jair → Flávio).
- **Vale virar seção no site?** Sim, mas só com o agregado ponderado e com a média simples explicitamente rotulada, porque a diferença entre elas é grande o bastante para virar manchete errada.

## 3. Em área, o mapa empata. Em eleitorado, não

- **Número** (municípios vencidos por cada candidato, sem exterior): PL venceu 2.906 municípios (52,2% dos 5.571), com **51,7% da área** e **56,9% do eleitorado** BR. PT venceu 2.663 (47,8%), com 48,3% da área e 43,1% do eleitorado. Dos votos nacionais do PL, **69,1%** vieram dos municípios que ele venceu; no PT, 57,4%. Os dois empates ficam fora.
- **Gráficos**: `img/analises/mapa_mente_vencedores.png`, `img/analises/mapa_mente_area_eleitorado_votos.png`
- **Ressalvas**: área é proxy geográfico. Município grande e pouco povoado pesa na área e quase nada no eleitorado. Área em Albers equal-area; EPSG:5880 não serve para isso (D-022).
- **Vale virar seção no site?** Sim. O mapa de vencedores é o que o leitor vê primeiro, e este número mostra que a leitura visual engana sobre o peso dos votos.

## 4. Lula espalha mais votos entre municípios que Flávio; Renan concentra votos em cidades grandes, mas seu apoio em % é uniforme; Caiado concentra o apoio em Goiás

- **Número** (5 candidatos acima de 1% nacional; denominador: 5.571 municípios brasileiros). Concentração de **votos absolutos** (Gini de votos e nº de municípios para 50% dos votos): para chegar a 50%, Lula precisa de **270** municípios (do maior para o menor), Flávio de **190**, Cury de 138, Caiado de 106 e Renan de **99**. O Gini de votos absolutos vai de 0,70 (Lula) a 0,81 (Renan). Esse Gini mede também o tamanho dos municípios: Renan é concentrado porque tem muitos votos nas cidades grandes. Concentração de **% sobre válidos** (Gini de % por município, cada um com peso 1): Renan 0,24, Lula 0,22, Flávio 0,22, Cury 0,21 (apoio uniforme entre municípios) e **Caiado 0,44**, o dobro, porque o apoio dele é regional (GO; ver achado 1).
- **Gráfico**: `img/analises/concentracao_lorenz.png`
- **Ressalvas**: os dois Ginis respondem perguntas diferentes e não devem ser lidos como uma só medida. Concentração entre municípios não diz quem votou em quem dentro de cada município.
- **Vale virar seção no site?** Não como seção própria. Serve como nota na seção de redutos (achado 1), porque o contraste entre Caiado (concentrado em % ) e Renan (uniforme em %) é mais claro ali.


## 5. A renda é o correlato mais forte do voto no PT entre municípios

- **Número** (Spearman, n = 5.570 municípios; denominador do voto: válidos do município): ρ = **−0,75** entre o log do PIB per capita de 2023 e o % do PT. Na regressão WLS ponderada pelo eleitorado, com as demais variáveis controladas, cada 10 vezes a renda está associada a **−17,7 p.p.** no PT (IC 95%: −19,0 a −16,3) e a +16,9 p.p. no PL. R² do modelo completo: 0,56 (PT) e 0,51 (PL).
- **Gráficos**: `img/analises/perfil_coeficientes_pt_pl.png`
- **Ressalvas**: falácia ecológica: município mais rico não significa eleitor mais rico votando diferente. O PIB é de 2023 e a população é do Censo 2022, ambos defasados em relação ao eleitorado de 2026. A renda pode carregar efeitos de urbanização e de estrutura regional, que não foram separados aqui.
- **Vale virar seção no site?** Sim, mas como correlação municipal, com o aviso de falácia ecológica na própria seção, e sem o modelo de regressão, que o leitor não consegue interpretar.

## 6. Escolaridade superior e renda andam juntas; controlar a renda atenua o coeficiente da escolaridade, sem inverter o sinal

- **Número**: correlação ecológica (Spearman, 5.570 municípios) entre % de superior completo e log do PIB pc: ρ = **0,65**. Bivariadas com o voto: ρ = **−0,65** com o % do PT e ρ = **+0,63** com o % do PL. Na regressão WLS, o coeficiente do superior completo (p.p. de válidos por p.p. de eleitorado) passa de **−0,58** no modelo básico, sem renda nem porte (IC 95%: −0,65 a −0,52), para **−0,35** no completo (IC: −0,42 a −0,28): atenuação de cerca de 40%, mesmo sinal. Para o PL, passa de **+0,44** (IC: 0,37 a 0,51) para **+0,24** (IC: 0,17 a 0,31): atenuação de cerca de 45%, mesmo sinal. O VIF do superior completo é **2,14** e o do log PIB pc é **1,87** (modelo completo); os dois são baixos, porque o VIF mede a parte de cada variável que as outras explicam, e a correlação par a par de 0,65 não entra com força nessa conta.
- **Gráficos**: `img/analises/perfil_coeficientes_pt_pl.png`
- **Ressalvas**: a atenuação é o que se espera quando duas variáveis dividem variância: parte do efeito que o superior tinha sozinho é atribuída à renda. Não é possível separar as duas contribuições com esses dados. Não interprete o coeficiente de escolaridade como efeito próprio. Os coeficientes são ecológicos (nível município).
- **Vale virar seção no site?** Não. O achado é um aviso metodológico, e o público vai ler o coeficiente como efeito causal de escolaridade.


## 7. O voto é espacialmente agrupado de forma extrema

- **Número** (Moran I global, sobre 5.568 municípios sem ilhas nem sem par, 999 permutações, p < 0,001 no mínimo possível): PT **I = 0,90**; PL **I = 0,89**; swing do PL **I = 0,59**. Clusters LISA após Benjamini-Hochberg (α = 0,05, de um total de 5.568 testes por variável): PT tem 1.337 municípios alto-alto (quase todo o Nordeste) e 1.167 baixo-baixo (áreas do Centro-Oeste, Norte, Minas e Sul); PL tem 1.097 alto-alto e 1.330 baixo-baixo. Sem correção, 3.061 municípios do PT passam de p < 0,05; após BH, 2.510.
- **Gráficos**: `img/analises/lisa_pt.png`, `img/analises/lisa_pl.png`, `img/analises/lisa_swing.png`
- **Ressalvas**: autocorrelação mostra estrutura regional comum, não um efeito local. Clusters grandes do Nordeste refletem uma região inteira, não cidades vizinhas com a mesma história. Não sirva de evidência sobre o eleitor.
- **Vale virar seção no site?** Sim, como mapa de clusters, desde que o texto diga que é padrão regional e não efeito de vizinhança.

## 8. A mudança de 2022 para 2026 não é uniforme entre as regiões

- **Número** (swing agregado ponderado, p.p. de válidos): PT cai **−5,5** no Sul, **−5,2** no Centro-Oeste, **−3,0** no Nordeste, **−2,9** no Sudeste e **−2,4** no Norte. PL sobe **+5,5** no Sul, **+3,9** no Nordeste, **+3,8** no Sudeste, **+3,7** no Norte e **+2,7** no Centro-Oeste. Teste de uniformidade (5.570 municípios): Kruskal-Wallis H = 1.303 para o PT e 687 para o PL; a região explica **23%** da variância municipal do swing do PT (eta² = 0,23) e **15%** do swing do PL (eta² = 0,15). Os p-valores são todos menores que 0,001, mas com n tão grande o que importa é o eta².
- **Gráficos**: `img/analises/swing_agregado_regiao.png`, `img/analises/swing_mapa_pl.png`
- **Ressalvas**: o teste é sobre municípios, não eleitores. Como eta² ainda é moderado, a região não explica tudo: dentro de cada região o swing varia muito.
- **Vale virar seção no site?** Sim. É a resposta mais direta à pergunta "onde mudou", com o aviso de que o efeito regional é real mas parcial.

## 9. Nas capitais, PT e PL empatam; PL lidera nas cidades de 50 mil a 1 milhão de eleitores e PT no porte pequeno e no grupo acima de 1 milhão

- **Número** (% sobre válidos do recorte, ponderado): nas **27 capitais**, PT 44,9% e PL 45,5% (empate técnico, 0,6 p.p.). No **interior** (5.544 municípios), PT 45,2% e PL 47,5%. Por porte do município (eleitorado de 2026), PT × PL: <10 mil, 49,0% × 44,9% (PT); 10–50 mil, 50,8% × 43,3% (PT); **50–200 mil, 40,8% × 51,2% (PL)**; **200 mil–1 milhão, 40,3% × 50,5% (PL)**; >1 milhão, 45,4% × 44,8% (PT, por 0,6 p.p.; são só **12** municípios).
- **Gráficos**: `img/analises/panorama_capitais_interior.png`, `img/analises/panorama_faixa_eleitorado.png`
- **Ressalvas**: capital × interior e porte são recortes ecológicos. O recorte de porte não controla a composição regional de cada faixa, então não isola um efeito de porte. O grupo >1 milhão tem 12 municípios, e a diferença de 0,6 p.p. nele não é robusta.
- **Vale virar seção no site?** Sim, como tabela de referência, sem gráfico de correlação.


## 10. Lente secundária: PL 2026 (1º turno) acima do teto de Bolsonaro no 2º turno 2022 em 67% dos municípios

- **Número**: o teto é o % de válidos de Bolsonaro (nº 22) no 2º turno 2022, por município. O PL 2026 (1T) está **acima** do teto em **3.731 de 5.570 municípios** (67,0%). No agregado regional (ponderado, mesma base), só o **Nordeste** fica acima: PL 30,85% contra teto 30,66% (+0,2 p.p.); Norte −1,9, Centro-Oeste −3,7, Sudeste −2,9 e Sul −1,8 p.p. Por região, a fração de municípios acima do teto vai de 52% (CO) a 83% (NE).
- **Gráficos**: `img/analises/lente_teto_regiao.png`
- **Ressalvas principais**: **1º e 2º turno não são comparáveis diretamente.** O 2º turno é binário, com outro comparecimento e dinâmica de rejeição. A lente é só a posição de um número em relação a outro. Não é projeção, e não indica que o PL "ganharia" o 2º turno. O nº 22 em 2022 era Jair Bolsonaro; em 2026, Flávio.
- **Vale virar seção no site?** Não. Pelo risco de leitura como projeção, fica como nota interna.

## 11. Abstenção nacional está estável (20,8%); a variação regional é grande

- **Número** (denominador: eleitorado): abstenção BR de **20,8%** em 2026 e **20,8%** em 2022 (sem exterior). Por região em 2026: Nordeste 18,4%, Norte 19,4%, Sul 20,5%, Centro-Oeste 21,7%, Sudeste 22,7%. Nulos (denominador: comparecimento): Nordeste 3,4%, Sudeste 3,2%, Norte 2,4%, Centro-Oeste 2,1%, Sul 1,9%. Brancos: Sudeste 2,2%, Nordeste 1,7%, Sul 1,9%, Centro-Oeste 1,2%, Norte 1,0%.
- **Gráficos**: `img/analises/participacao_correlacao_facultativa.png`
- **Ressalvas**: os nulos aqui são `nulos_tvn` (comuns + técnicos); os técnicos somam 5.246 votos, 0,004% do comparecimento, e não mudam a conclusão regional. O ranking municipal de abstenção depende muito do corte de eleitorado: o top-20 muda quase por completo entre cortes vizinhos (Jaccard 0,18 sem corte, 0,25 com corte de 5 mil; D-021). Por isso o ranking municipal não é apresentado como achado. Hipótese não testada: parte da abstenção alta concentrada em Minas Gerais pode refletir cadastro desatualizado (eleitores que já não moram no município); os dados usados não permitem testar isso.
- **Vale virar seção no site?** Sim, só a tabela regional. O ranking municipal não vai para o site, por instabilidade.


## 12. Brancos caem onde há mais jovens de 16–17 anos (correlação ecológica forte, mas confundida)

- **Número** (Spearman, 5.571 municípios): ρ = **−0,59** entre % do eleitorado de 16–17 anos e % de brancos sobre o comparecimento. Com a abstenção, a correlação com 16–17 é fraca (ρ = −0,15) e com 70+ é fraca (ρ = +0,11).
- **Gráficos**: `img/analises/participacao_correlacao_facultativa.png`
- **Ressalvas**: falácia ecológica: é uma propriedade de municípios, não de jovens. O peso do 16–17 pode carregar urbanização, renda ou região (hipótese; não foi testada aqui). Não há controle por esses fatores aqui, então não é possível dizer qual deles explica a correlação.
- **Vale virar seção no site?** Não. A correlação forte é tentadora, mas o leitor vai interpretar como comportamento de jovens, o que não é o que os dados mostram.

## 13. Exterior (recorte à parte): PT 47,6% e PL 43,5% dos válidos; abstenção de 62,7%

- **Número** (denominador: válidos do exterior, 330.882; eleitorado do exterior, 916.534): PT 47,6%, PL 43,5%. Abstenção sobre o eleitorado de **62,66%** (574.345 ÷ 916.534). Os 186 postos incluem **41 com zero votos válidos em 2026** (eleitorado somado de 495; comparecimento zero). Esses postos entram no denominador. Sem eles, a abstenção fica em **62,69%** (574.273 ÷ 916.039): a diferença é de 0,03 p.p., porque são só 0,05% do eleitorado. Os 41 postos não são idênticos aos 40 em que a seção nunca foi instalada (`esi = 0`, eleitorado 423): são conjuntos parecidos, mas não iguais.
- **Gráficos**: `img/analises/panorama_regioes_pt_pl.png` (o exterior não aparece no gráfico, só nos números)
- **Ressalvas**: exterior não é Brasil. Postos consulares têm eleitorado muito pequeno e variam de ano para ano (6 postos novos e 1 extinto em 2026). Não some com o Brasil em nenhum agregado.
- **Vale virar seção no site?** Não. A tabela de postos que já existe no mapa (F2) é suficiente.

---

## Recomendações resumidas para o site

Vale virar seção: achados 1 (com a parte de UF), 2 (com o agregado ponderado rotulado), 3, 7 (com aviso de padrão regional), 8, 9 (tabela) e 11 (tabela). Os demais ficam como nota ou fora do site, pelo risco de leitura como efeito individual ou como projeção. A decisão de virar seção é do usuário; a fase B (página no site) está pendente no `docs/ROADMAP.md`, e `web/` não foi tocado.

Limitações que valem para todo o texto: snapshot provisório de 05/10/2026 (`tf="n"`, totalização não final); PIB de 2023 e população do Censo 2022 contra eleitorado de 2026; correlação ecológica em todos os achados de município; e o exterior tratado à parte.
