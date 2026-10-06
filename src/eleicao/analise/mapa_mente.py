"""Mapa "mente": o que cada candidato ganha em número de municípios, área, eleitorado e votos.

Denominadores (todos explícitos nos nomes das colunas):
- `pct_municipios_vencidos` = municípios vencidos ÷ 5.571 municípios brasileiros (sem exterior)
- `pct_area_sobre_area_br`  = área dos municípios vencidos ÷ área total da malha BR
- `pct_eleitorado_sobre_eleitorado_br` = eleitorado dos vencidos ÷ eleitorado BR (sem exterior)
- `pct_validos_nacionais_nos_vencidos` = válidos dos municípios vencidos ÷ válidos BR
- `pct_votos_do_candidato_nos_vencidos` = votos do candidato nos municípios que venceu
  ÷ votos NACIONAIS desse candidato (pergunta: quanto dos votos dele "vem" do mapa que ele ganha)

Ressalva: município é a unidade; "área" é um proxy geográfico, não população. Um
município gigante e pouco povoado pesa muito na área e quase nada no eleitorado.
"""

from __future__ import annotations

import pandas as pd

from .base import pct


def resumo_vencedores(
    vencedores: pd.DataFrame,
    municipios: pd.DataFrame,
    candidatos: pd.DataFrame,
    area_km2: pd.DataFrame,
) -> pd.DataFrame:
    """Uma linha por candidato vencedor de pelo menos um município.

    - `vencedores`: uf, cd_mun_tse, nr_vencedor, votos_1o, validos (de `base.vencedor_municipal`).
    - `municipios`: uf, cd_mun_tse, eleitorado (SEM exterior).
    - `candidatos`: uf, cd_mun_tse, nr_candidato, votos (SEM exterior).
    - `area_km2`: uf, cd_mun_tse, area_km2 (SEM exterior).
    Municípios sem vencedor (empate exato) não entram em nenhum candidato.
    """
    chave = ["uf", "cd_mun_tse"]
    v = vencedores.dropna(subset=["nr_vencedor"]).copy()
    v = v.merge(municipios[[*chave, "eleitorado"]], on=chave, validate="1:1")
    v = v.merge(area_km2[[*chave, "area_km2"]], on=chave, validate="1:1")

    n_mun = len(municipios)
    eleit_br = float(municipios["eleitorado"].sum())
    area_br = float(area_km2["area_km2"].sum())
    validos_br = float(vencedores["validos"].sum())
    votos_nac = candidatos.groupby("nr_candidato")["votos"].sum()

    # votos do candidato nos municípios que venceu = votos do vencedor no próprio município
    linhas = []
    for nr, g in v.groupby("nr_vencedor"):
        votos_do_cand_nos_vencidos = float(g["votos_1o"].sum())
        linhas.append(
            {
                "nr_candidato": int(nr),
                "n_municipios_vencidos": int(len(g)),
                "pct_municipios_vencidos": pct(len(g), n_mun),
                "area_km2_vencidos": float(g["area_km2"].sum()),
                "pct_area_sobre_area_br": pct(float(g["area_km2"].sum()), area_br),
                "eleitorado_vencidos": int(g["eleitorado"].sum()),
                "pct_eleitorado_sobre_eleitorado_br": pct(float(g["eleitorado"].sum()), eleit_br),
                "validos_vencidos": int(g["validos"].sum()),
                "pct_validos_nacionais_nos_vencidos": pct(float(g["validos"].sum()), validos_br),
                "votos_do_candidato_nos_vencidos": int(votos_do_cand_nos_vencidos),
                "pct_votos_do_candidato_nos_vencidos": pct(
                    votos_do_cand_nos_vencidos, float(votos_nac.loc[nr])
                ),
            }
        )
    return pd.DataFrame(linhas).sort_values("n_municipios_vencidos", ascending=False)
