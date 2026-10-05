""" "Força" de um candidato por município: % dos votos válidos + escala da cor.

Alimenta o modo "Força" do mapa (D-018): todos os municípios pintados pelo
percentual de votos válidos de UM candidato, numa escala sequencial de claro
até a cor dele (`eleicao.cores.escala_forca`).

Duas funções puras, isoladas aqui (e não em `scripts/exportar_web.py`) para
poderem ser testadas direto:

- `pct_por_municipio`: matriz `% dos válidos` por município × candidato, com
  o índice em ORDEM NUMÉRICA CRESCENTE de `cd_mun_ibge` — é essa ordem que os
  arrays posicionais de `web/data/resultados/forca/cand_<nr>.json` seguem.
- `escala_maxima`: o teto da escala de cor (percentil 98).

Armadilha que as duas evitam explicitamente: o **exterior** (`uf == "zz"`,
186 "municípios" sem código IBGE) NÃO entra em nenhuma das duas. Se entrasse,
os 41 postos sem seção instalada (0 votos válidos) e os postos minúsculos
distorceriam o percentil silenciosamente — e o exterior não tem geometria no
mapa (F2.1), então não há o que pintar com essa escala.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PERCENTIL_FORCA = 98
"""Percentil (sobre os 5.571 municípios do Brasil) que satura a escala de cor
do modo "Força".

Motivo de usar p98 e não o máximo: a distribuição de % por município tem
cauda longa para quase todos os candidatos (ex. Augusto Cury: mediana 2,3%,
p98 4,6%, máximo 17,3% num único município). Com o máximo como teto, 98% do
mapa ficaria comprimido no terço claro da rampa e não se distinguiria nada.
Com p98, os ~111 municípios acima dele saturam na cor plena — perda de
informação deliberada, no extremo da cauda, em troca de contraste onde está a
massa dos dados."""


def pct_por_municipio(df_candidatos: pd.DataFrame, df_totais: pd.DataFrame) -> pd.DataFrame:
    """`%` dos votos válidos por município × candidato (exterior EXCLUÍDO).

    Entradas: `presidente_t1_municipio.parquet` (uma linha por município ×
    candidato) e `presidente_t1_municipio_totais.parquet` (uma linha por
    município, com `validos` e `eh_exterior`).

    Saída: `DataFrame` indexado por `cd_mun_ibge` (string de 7 dígitos),
    **ordenado numericamente**, com uma coluna por `nr_candidato` (ordenadas
    pelo número) e valores em pontos percentuais dos votos válidos do próprio
    município. Municípios sem voto válido (não deve haver nenhum no Brasil,
    mas a função não assume isso) saem com 0 em todas as colunas; candidatos
    sem voto no município também saem com 0 — o zero é um dado, não um
    buraco, e precisa estar lá para o percentil não ser calculado só sobre os
    municípios onde o candidato pontuou.
    """
    totais = df_totais[~df_totais["eh_exterior"]]
    if totais["cd_mun_ibge"].isna().any() or (totais["cd_mun_ibge"].astype(str) == "").any():
        raise ValueError("município do Brasil sem cd_mun_ibge — join com o IBGE quebrado")

    chaves = totais[["uf", "cd_mun_tse", "cd_mun_ibge", "validos"]]
    cand = df_candidatos.merge(chaves, on=["uf", "cd_mun_tse"], how="inner")

    pivo = cand.pivot_table(
        index="cd_mun_ibge",
        columns="nr_candidato",
        values="votos",
        aggfunc="sum",
        fill_value=0,
    )
    ordem = sorted(totais["cd_mun_ibge"].astype(str), key=int)
    pivo = pivo.reindex(index=ordem, fill_value=0).fillna(0)
    pivo.columns = [int(c) for c in pivo.columns]
    pivo = pivo[sorted(pivo.columns)]

    validos = totais.set_index(totais["cd_mun_ibge"].astype(str))["validos"].reindex(ordem)
    pct = pivo.div(validos.replace(0, np.nan), axis=0).fillna(0.0) * 100
    pct.index.name = "cd_mun_ibge"
    return pct


def escala_maxima(pct_do_candidato: pd.Series | np.ndarray) -> float:
    """Teto da escala de cor do candidato: percentil 98 sobre os municípios.

    Recebe a COLUNA de um candidato em `pct_por_municipio` (ou seja, já sem
    exterior e já com os zeros incluídos). Se o percentil der 0 (candidato
    sem votos em quase lugar nenhum), cai para o maior valor observado, para
    a escala não degenerar numa divisão por zero no front-end.
    """
    valores = np.asarray(pct_do_candidato, dtype=float)
    if valores.size == 0:
        raise ValueError("série de percentuais vazia")
    teto = float(np.percentile(valores, PERCENTIL_FORCA))
    if teto <= 0:
        teto = float(valores.max())
    return teto
