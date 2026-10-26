"""A virada do 2º turno 2026: swing municipal T1→T2 (margem PT−PL) e recortes.

Funções puras sobre os Parquet de `data/processed/` já carregados. Margem = (PT − PL) em
% dos votos dos DOIS FINALISTAS (PT + PL) do próprio turno, nos dois turnos: com os válidos
no denominador do T1, os terceiros inflariam mecanicamente a margem do T2 nos redutos de cada
lado. Swing = margem do T2 − margem do T1 (positivo = andou para o PT). Brasil sem exterior
(o exterior é tratado à parte, D-027).
"""

from __future__ import annotations

import pandas as pd

NR_PL, NR_PT = 22, 13
CHAVE = ["uf", "cd_mun_tse"]


def base_turno(candidatos: pd.DataFrame, totais: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por município: votos PT/PL, válidos, eleitorado, abstenção e margem."""
    v = (
        candidatos.assign(nr=candidatos["nr_candidato"].astype(int))
        .pivot_table(index=CHAVE, columns="nr", values="votos", aggfunc="sum", fill_value=0)
        .rename(columns={NR_PT: "pt", NR_PL: "pl"})[["pt", "pl"]]
    )
    t = totais.set_index(CHAVE)
    d = v.join(t[["nm_mun", "cd_mun_ibge", "eleitorado", "validos", "abstencao"]], how="inner")
    d["margem"] = 100 * (d["pt"] - d["pl"]) / (d["pt"] + d["pl"])
    d["abst_pct"] = 100 * d["abstencao"] / d["eleitorado"]
    return d.reset_index()


def virada_municipal(t1: pd.DataFrame, t2: pd.DataFrame) -> pd.DataFrame:
    """Une T1 e T2 por município (Brasil sem exterior) e calcula swing, Δabstenção e troca."""
    a = t1[t1["uf"] != "zz"]
    b = t2[t2["uf"] != "zz"]
    d = a.merge(b, on=CHAVE, suffixes=("_t1", "_t2"), validate="one_to_one")
    d["swing"] = d["margem_t2"] - d["margem_t1"]
    d["dabst"] = d["abst_pct_t2"] - d["abst_pct_t1"]
    d["dmargem_votos"] = (d["pt_t2"] - d["pl_t2"]) - (d["pt_t1"] - d["pl_t1"])
    d["virou_pt"] = (d["margem_t1"] < 0) & (d["margem_t2"] > 0)
    d["virou_pl"] = (d["margem_t1"] > 0) & (d["margem_t2"] < 0)
    return d


def resumo_grupo(d: pd.DataFrame, por: str) -> pd.DataFrame:
    """Margens entre finalistas, swing ponderado (votos) e mediana municipal por grupo."""

    def f(g: pd.DataFrame) -> pd.Series:
        m1 = 100 * (g["pt_t1"].sum() - g["pl_t1"].sum()) / (g["pt_t1"].sum() + g["pl_t1"].sum())
        m2 = 100 * (g["pt_t2"].sum() - g["pl_t2"].sum()) / (g["pt_t2"].sum() + g["pl_t2"].sum())
        return pd.Series(
            {
                "municipios": len(g),
                "eleitorado": g["eleitorado_t1"].sum(),
                "margem_t1": m1,
                "margem_t2": m2,
                "swing": m2 - m1,
                "swing_mediana_mun": g["swing"].median(),
                "swing_p10_mun": g["swing"].quantile(0.1),
                "swing_p90_mun": g["swing"].quantile(0.9),
                "dabst_pp": 100 * g["abstencao_t2"].sum() / g["eleitorado_t2"].sum()
                - 100 * g["abstencao_t1"].sum() / g["eleitorado_t1"].sum(),
                "virou_pt": int(g["virou_pt"].sum()),
                "virou_pl": int(g["virou_pl"].sum()),
                "ganho_margem_votos": g["dmargem_votos"].sum(),
            }
        )

    return d.groupby(por).apply(f, include_groups=False).reset_index()


FAIXAS_PORTE = (
    ("até 5 mil", 0, 5e3),
    ("5–10 mil", 5e3, 10e3),
    ("10–20 mil", 10e3, 20e3),
    ("20–50 mil", 20e3, 50e3),
    ("50–100 mil", 50e3, 100e3),
    ("100–500 mil", 100e3, 500e3),
    ("mais de 500 mil", 500e3, float("inf")),
)


def faixa_porte(eleitorado: pd.Series) -> pd.Series:
    """Faixa de eleitorado (rótulos de `FAIXAS_PORTE`), limite superior inclusivo."""
    rotulos = {(lo, hi): r for r, lo, hi in FAIXAS_PORTE}

    def f(x: float) -> str:
        return next(r for (lo, hi), r in rotulos.items() if lo < x <= hi or (x == 0 and lo == 0))

    return eleitorado.map(f)
