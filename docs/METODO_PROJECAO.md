# Método da projeção do 2º turno (F5a)

Atualizado em 2026-10-08. Decisões: `docs/DECISOES.md` D-033, D-034 e D-035. Configuração aprovada: `config/projecao_t2.yaml`. Código: `src/eleicao/inferencia_ecologica.py` (métodos) e `src/eleicao/projecao_t2.py` (cenários e saídas). Execução: `python scripts/projetar_t2_2026.py`. Notebook: `notebooks/f5a_projecao_t2.ipynb`.

**Resumo honesto.** Esta é uma projeção por inferência ecológica, calibrada em eleições anteriores. A faixa de incerteza é uma heurística de um único backtest (n=1), não um intervalo de confiança. Regra de leitura: se o % PL projetado ficar a menos de 2 p.p. de 50 (Brasil) ou 2,5 p.p. (UF e exterior), **o método não distingue vencedor**. Os resultados da projeção 2026 estão na seção 7, mantida fora do commit público.

## 1. Formulação

Tudo é medido sobre **eleitores aptos** (denominador = eleitorado do município).

- T1 2026: Flávio (22), Lula (13), Cury (70), Renan (14), Caiado (55), outros (7 candidatos abaixo de 1% dos válidos), brancos+nulos (BN = comparecimento − válidos) e abstenção (ABST = eleitorado − comparecimento).
- T2: PL (Flávio), PT (Lula), BN e ABST. As colunas são por lado partidário, não por pessoa.
- Matriz de transferência B (linhas = categorias do T1, colunas = PL, PT, BN, ABST; B ≥ 0, cada linha soma 1).
- Projeção: o T2 projetado de cada município é `x_i · B`, com `x_i` as contagens do T1 2026 daquele município (votos absolutos, não percentuais). O município soma à UF e a UF soma ao Brasil **somando votos**; nunca se tira média de percentuais.

**Goodman restrito.** Em um conjunto de municípios, ajusta-se `Y ≈ X B` (parcelas sobre aptos) por mínimos quadrados ponderados por aptos, com B ≥ 0 e linhas somando 1 (programa quadrático em cvxpy, solver CLARABEL, em forma de estatísticas suficientes `X'WX` e `X'WY`). Isso gera as linhas de Flávio, Lula, BN e ABST (B nacional de 2022, T1 2022 → T2 2022).

**Regressão ecológica de composição (terceiros).** Para Cury, Renan, Caiado e outros_2026 não há análogo em 2022. Estima-se por Goodman restrito, nos municípios pareados, como o eleitorado de 2022-T2 (Lula22, Bolsonaro22, BN22, ABST22) se distribui entre as categorias do T1 2026; por Bayes, obtém-se a **composição** de cada categoria (fração dos seus eleitores que vem de cada grupo de 2022-T2). A linha de transferência no T2 2026 é essa composição com **identidade**: Lula22→PT, Bolsonaro22→PL, BN22→BN, ABST22→ABST.

**Pareamento.** Chave `(uf, cd_mun_tse)`. Municípios sem par (Boa Esperança do Norte/MT, o posto Vaticano só em 2022 e 6 postos novos do exterior) ficam fora da regressão, mas **continuam projetados** (`x_i · B`). A lista está em `data/processed/projecao_t2_2026_sem_par.csv`.

**Modelo de referência (D-034, D-035).** Matriz nacional, sem B por UF. Terceiros (incluindo outros_2026) por composição. Linhas de BN e ABST da B nacional 2022 ("mobilização tipo 2022"). O exterior (ZZ) usa a matriz nacional; a matriz própria estimada com os postos de 2022 é o cenário `zz_propria`.

## 2. Cenários

Eixo A (terceiros: regressão × análogos) × eixo B (linhas de BN e ABST: tipo 2022 × tipo 2018) dá 4 combinações:

| Cenário | Terceiros | BN e ABST |
|---|---|---|
| `base` | composição | tipo 2022 |
| `desmob_2018` | composição | tipo 2018 |
| `analogos` | Caiado→Tebet 2022; Renan e Cury→Ciro 2022; outros→outros_2022 | tipo 2022 |
| `analogos_desmob_2018` | análogos | tipo 2018 |

Cenário adicional `identidade_sem_retorno_abst` (D-035, seção 4): como o base, mas as linhas compostas não devolvem à abstenção o componente ABST22. Sensibilidade: `outros_goodman`, `manual_original` (linhas manuais do primeiro rascunho, placeholders), `outros_divididos`, `limite_pro_pl`, `limite_pro_pt` e `zz_propria` (exterior com a matriz estimada nos postos de 2022). Todos os cenários cruzados usam a matriz nacional também no exterior.

A base do eixo B é 2022 porque é a eleição mais recente, com o mesmo par PL×PT; BN 2026 T1 = 3,78% dos aptos (Brasil sem exterior), BN 2022 T1 = 3,50% e BN 2018 T1 = 7,02%; e a abstenção subiu 0,97 p.p. entre os turnos de 2018 e caiu 0,36 p.p. em 2022, principal fonte do erro do backtest do modelo por blocos.

## 3. Premissas não testáveis

Nenhuma destas pode ser verificada com os dados que existem antes do 2º turno. A comparação pós-25/10 (`scripts/comparar_projecao_t2.py`) vai testar algumas.

1. **Identidade e retenção.** Cada componente de 2022-T2 (Lula22, Bolsonaro22, BN22, ABST22) volta ao mesmo destino em 2026 (Lula22→PT etc.), sem matriz de retenção. Em aberto se se deve aplicar alguma. No backtest, a linha composta de Ciro ficou longe da linha estimada diretamente (PL 0,54 contra 0,26), o que mostra que a identidade é imperfeita.
2. **Mobilização de 2026 entre turnos.** Abstenção e BN do T2 2026 dependem de contexto próprio; as linhas de BN e ABST medem a mobilização de 2022 (ou de 2018, no cenário alternativo).
3. **Mudança de papel do PT.** Em 2022 o PT era desafiante; em 2026 é incumbente. A fidelidade e a rejeição de Lula podem diferir do que a matriz de 2022 capta.
4. **Flávio ≠ Jair.** O mapeamento 22→22 assume fidelidade ao campo (sigla/número), não à pessoa (D-023, item 2).
5. **Renovação do eleitorado 2022→2026 na regressão de composição.** A regressão usa parcelas sobre aptos de anos diferentes (aptos de 2022 no X, de 2026 no Y) e ignora entradas e saídas de eleitores; o eleitorado cresceu cerca de 2,3 milhões entre os anos.

## 4. Limitações

- **Falácia ecológica.** Todas as matrizes descrevem associação entre municípios, não o comportamento de eleitores individuais.
- **Viés sistemático de abstenção da identidade (D-035).** Na composição, eleitores que votaram no T1 recebem um componente "abstenção 2022" (a regressão atribui parte do eleitorado de um candidato ao grupo Abst22) e a identidade os devolve à abstenção no T2. Isso tende a inflar a abstenção projetada em relação ao T1; é um viés do método, não ruído. No backtest 2018→2022 o `regter_nac` errou a abstenção do Brasil em **+1,36 p.p.** (previsto − observado). Na projeção 2026, o efeito aparece comparando o cenário base com os cenários `analogos` e `identidade_sem_retorno_abst` (valores na seção 7, fora do commit público). **A base não muda.** Cenário `identidade_sem_retorno_abst`: nas linhas compostas, zera-se o componente ABST22, renormalizam-se PL/PT/BN e aplica-se a taxa r de abstenção T1→T2 de quem votou no T1: linha = (1−r)·linha renormalizada + r em ABST. **r** = média, ponderada pelos votos do T1 do ano de calibração (Brasil sem exterior), da coluna ABST da B nacional in-sample nas linhas de votantes com candidato (lula, bolsonaro, tebet, ciro, outros; em 2018: pl, pt, ciro, centro, outros). BN fica fora de r: a linha de BN descreve quem compareceu e anulou/branqueou, e a coluna ABST dela é 0 nas duas calibrações, então incluí-lo só diluiria r em cerca de 4% do seu valor. **r 2022 = 0,0056** (origem quase única: linha de Lula, ABST 0,011; as demais linhas de votantes têm ABST 0 na fronteira); **r 2018 = 0,0124** (linhas do PT, 0,027, e do centro, 0,057). No backtest, r vem da B 2018 in-sample, para manter a separação fora da amostra. Resultado do backtest, na seção 5: a correção **não melhora** o erro de abstenção (+1,44 p.p., contra +1,36 do `regter_nac`), porque nos blocos de 2018→2022 as linhas compostas já têm componente ABST22 quase nulo; o +1,36 do backtest vem sobretudo das linhas de BN, ABST e PT de 2018 (ablação, seção 5), não da identidade das linhas compostas. A correção só pode fazer diferença onde as composições de 2026 têm componente ABST22 relevante.
- **Mudança de comparecimento entre turnos.** O modelo trata a abstenção como categoria; mudanças de mobilização por região não são modeladas.
- **Candidatos sem análogo.** Cury, Renan, Caiado e outros dependem da composição (ou de análogos discutíveis). As linhas compostas têm IC largo (seção 7).
- **IC do bootstrap das linhas compostas é indicativo.** O bootstrap percentil é inconsistente quando o parâmetro está na fronteira do espaço paramétrico (Andrews, D. W. K., 2000, "Inconsistency of the Bootstrap when a Parameter Is on the Boundary of the Parameter Space", *Econometrica* 68(2): 399–405). Aqui as linhas são restritas a B ≥ 0 e a soma 1, e vários componentes estimados ficam em 0 ou em 1. Isso explica por que, em Cury e Renan, o IC percentil não contém a estimativa pontual. Trate larguras e limites como ordem de grandeza.
- **Hipótese não adotada (achado post-hoc).** Na ablação do backtest 2018→2022, trocar só a linha de abstenção (ABST T1→T2) pela do T2 observado reduz o erro de abstenção do Brasil de +1,54 para +0,77 p.p. no modelo por blocos (B 2018 pura; a ablação não foi feita sobre o `regter_nac`, cujo erro de abstenção é +1,36) O achado foi feito olhando o resultado (usa o T2 2022 como oráculo), então não entra no modelo: fica como hipótese a testar fora da amostra na próxima aplicação (comparação com o T2 2026, `scripts/comparar_projecao_t2.py`). (D-035, item 6.)
- **n=1 de backtest.** Só uma comparação fora da amostra (2018→2022). A faixa heurística vem dela.
- **Compensação de erros no `regter`.** O erro quase nulo do modelo de referência no backtest (−0,06 p.p.) é em parte compensação de erros: a linha composta de Ciro está errada e empurra o PL para cima, o que compensa as linhas de BN e ABST de 2018 (ablação em `data/interim/projecao_t2/backtest_ablacao_linhas.csv`). Não é precisão comprovada.
- **Exterior.** Cerca de 136 pares para a regressão própria do exterior, com IC de PL−PT muito largo nos terceiros (valores na seção 7); por isso a matriz nacional é a base (D-035). O exterior pesa cerca de 0,6% do eleitorado.
- **Bootstrap.** O bootstrap estratificado por UF mede só a variância de estimação; no backtest, o erro real foi 20 a 30 vezes o desvio do bootstrap nos modelos por blocos.

## 5. Backtest 2018 → 2022 (fora da amostra)

B estimada em 2018 (T1→T2), λ escolhido só com dados de 2018 (λ = 0,01), aplicada ao T1 2022; T2 2022 real: 49,10% PL entre válidos (Brasil, sem exterior). Erro = previsto − observado, em p.p.

| Modelo | Erro BR | UF: média abs | UF: p90 abs | UF: máx abs | MAE municipal pond. | Vencedor UF certo | Erro abstenção BR |
|---|---|---|---|---|---|---|---|
| base_nac (blocos, matriz nacional) | −1,84 | 1,75 | 2,54 | 3,36 | 1,76 | 26/27 | +1,54 |
| base_uf | −1,57 | 1,66 | 2,91 | 3,13 | 1,52 | 26/27 | +1,46 |
| amoedo_nac | −1,86 | 1,80 | 2,62 | 3,39 | 1,78 | 26/27 | +1,55 |
| amoedo_uf | −1,53 | 1,58 | 2,71 | 3,01 | 1,53 | 26/27 | +1,48 |
| **regter_nac (referência)** | **−0,06** | **0,66** | 1,17 | 1,89 | 0,88 | **27/27** | **+1,36** |
| regter_nac_semretorno (D-035, r 2018 = 0,0124) | −0,09 | 0,66 | **1,14** | 1,90 | **0,87** | 27/27 | +1,44 |
| regter_uf | +0,90 | 1,06 | 2,16 | 4,91 | 1,40 | 25/27 | +1,18 |
| baseline (a): T1 renormalizado | −1,95 | 1,81 | 2,45 | 2,73 | 1,69 | 26/27 | +6,70 |
| baseline (b): terceiros e BN proporcionais | −1,79 | 1,73 | 2,22 | 2,78 | 1,69 | 26/27 | +0,36 |

Lado a lado, `regter_nac` contra `regter_nac_semretorno`: erro do % PL no Brasil −0,06 contra −0,09 p.p.; erro de abstenção +1,36 contra +1,44 p.p.; MAE municipal 0,88 contra 0,87 p.p.; vencedor por UF 27/27 nos dois. Na prática, a correção é neutra no backtest.

Ablação (diagnóstico, usa o T2 2022 como oráculo): a B de 2018 pura erra −1,84; com a composição só no bloco Ciro passa a −0,52; nos três blocos, −0,06; com o oráculo 2022 completo (in-sample), −0,05. O erro do modelo por blocos vem sobretudo das linhas de BN e ABST de 2018. O bootstrap do backtest cobriu o resultado real do Brasil só no `regter_nac` (e em 7 de 27 UFs). Ver `data/interim/projecao_t2/backtest_*.csv`.

**Faixa heurística (n=1), D-034:** ±2 p.p. no % PL dos válidos (Brasil), ±2,5 p.p. por UF, ±1,5 p.p. dos aptos na abstenção. Simétrica, sem correção de viés. Para município e exterior, que não foram calibrados, usa-se ±2,5 p.p. Não é intervalo de confiança.

## 6. Como atualizar após o 2º turno

`scripts/comparar_projecao_t2.py` (pronto, não executado) compara a projeção com o resultado real da eleição 6258 e estima a matriz real do 2026 T1→T2. Consome `data/processed/presidente_t2_municipio.parquet` e `presidente_t2_municipio_totais.parquet`, que o coletor-tse deve gerar (mesmo schema do T1 2026). Não baixa nada.
