"""Dados dos modos "2º turno" e "Virada" do mapa principal (`web/data/resultados/t2.json`).

Mesma convenção de `resultados/swing.json`: arrays por município na ordem de `cd_mun_ibge`
crescente (numérico), alinhados com `forca/cand_<nr>.json` e `meta.forca_offsets`. As escalas
saem prontas daqui (o JS só interpola os stops, como no modo Swing).

Margem = (PT − PL) em % dos votos dos DOIS FINALISTAS, nos dois turnos (D-039); swing = margem
do 2º turno − margem do 1º. Brasil sem exterior (D-027).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from eleicao.analise import virada
from eleicao.cores import carregar_paleta, escala_divergente_assimetrica

NR_PL, NR_PT = 22, 13
LIMITE_RESULTADO_PP = 40.0
"""Saturação da escala do resultado do 2º turno (margem entre finalistas), em p.p."""
LIMITE_VIRADA_PP = 10.0
"""Saturação da escala do swing por município, em p.p.: município pequeno oscila muito por
acaso, então a escala é truncada e o tooltip mostra os eleitores aptos."""
CONTORNO_VIROU_PT = "#111111"
CONTORNO_VIROU_PL = "#ffd400"
CASAS = 2

CAMPOS_REGIAO = [
    "margem_t1",
    "margem_t2",
    "swing",
    "pt_t2",
    "pl_t2",
    "aptos_t2",
    "virou_pt",
    "virou_pl",
    "municipios",
]


def _r(x: float, casas: int = CASAS) -> float:
    return round(float(x), casas)


def _regiao(g: pd.DataFrame) -> list[float]:
    r = virada.resumo_grupo(g.assign(_g=1), "_g").iloc[0]
    return [
        _r(r["margem_t1"]),
        _r(r["margem_t2"]),
        _r(r["swing"]),
        int(g["pt_t2"].sum()),
        int(g["pl_t2"].sum()),
        int(g["eleitorado_t2"].sum()),
        int(r["virou_pt"]),
        int(r["virou_pl"]),
        int(r["municipios"]),
    ]


def _oficial(o: dict[str, float] | None) -> dict[str, Any] | None:
    """Total oficial do 2º turno (COM exterior), para o painel nacional: pt, pl, aptos."""
    if o is None:
        return None
    margem = 100 * (o["pt"] - o["pl"]) / (o["pt"] + o["pl"])
    return {"pt": int(o["pt"]), "pl": int(o["pl"]), "aptos": int(o["aptos"]), "m2": _r(margem)}


def _escala(limite: float, cor_pl: str, cor_pt: str) -> dict[str, Any]:
    e = escala_divergente_assimetrica(-limite, limite, cor_pl, cor_pt)
    return {
        "limite_pp": limite,
        "valores": [round(v, 4) for v, _ in e],
        "cores": [c for _, c in e],
        "cor_pl": cor_pl,
        "cor_pt": cor_pt,
    }


def montar(
    d: pd.DataFrame,
    offsets_meta: dict[str, int],
    n_meta: int,
    cor_sem_dado: str,
    oficial: dict[str, float] | None = None,
) -> dict[str, Any]:
    """`d` = `virada.virada_municipal` (já sem exterior). Confere ordem e offsets com o meta."""
    paleta = carregar_paleta()
    cor_pl, cor_pt = paleta[NR_PL], paleta[NR_PT]
    d = d.assign(_ibge=d["cd_mun_ibge_t1"].astype(int)).sort_values("_ibge").reset_index(drop=True)
    if len(d) != n_meta:
        raise ValueError(f"{len(d)} municípios != meta.n_municipios_br {n_meta}")
    inicio = d.groupby("uf").head(1).set_index("uf").index
    offsets = {u: int(d.index[d["uf"] == u][0]) for u in inicio}
    if offsets != offsets_meta:
        raise ValueError("offsets por UF diferentes de meta.forca_offsets (ordem desalinhada)")
    contiguo = all(
        (d.index[d["uf"] == u] == range(offsets[u], offsets[u] + (d["uf"] == u).sum())).all()
        for u in offsets
    )
    if not contiguo:
        raise ValueError("UF não contígua na ordem por cd_mun_ibge")

    vr = d["virou_pt"].astype(int) - d["virou_pl"].astype(int)
    ufs = {u: _regiao(g) for u, g in d.groupby("uf")}
    n_alem = int((d["swing"].abs() > LIMITE_VIRADA_PP).sum())
    pl_vira = d[d["virou_pl"]]
    return {
        "n": len(d),
        "ordem": "cd_mun_ibge crescente (numérico)",
        "m1": [_r(x) for x in d["margem_t1"]],
        "m2": [_r(x) for x in d["margem_t2"]],
        "sw": [_r(x) for x in d["swing"]],
        "pt": d["pt_t2"].astype(int).tolist(),
        "pl": d["pl_t2"].astype(int).tolist(),
        "aptos": d["eleitorado_t2"].astype(int).tolist(),
        "vr": vr.tolist(),
        "formato_regiao": CAMPOS_REGIAO,
        "br": _regiao(d),
        "oficial": _oficial(oficial),
        "ufs": ufs,
        "escala_t2": {**_escala(LIMITE_RESULTADO_PP, cor_pl, cor_pt), "cor_sem_dado": cor_sem_dado},
        "escala_virada": {
            **_escala(LIMITE_VIRADA_PP, cor_pl, cor_pt),
            "contorno_pt": CONTORNO_VIROU_PT,
            "contorno_pl": CONTORNO_VIROU_PL,
            "n_alem_escala": n_alem,
            "n_total": len(d),
            "virou_pl": [
                {"ibge": str(int(r["_ibge"])), "uf": r["uf"], "nome": r["nm_mun_t1"]}
                for _, r in pl_vira.iterrows()
            ],
        },
    }
