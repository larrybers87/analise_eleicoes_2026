"""Composições usadas pelos notebooks 10–17: encadeiam as funções testadas, sem lógica nova.

Os notebooks chamam estas funções e plotam. Qualquer número que aparece em
docs/ANALISES.md sai daqui (ou das funções que estas chamam) e é coberto por teste.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from . import base, carga
from . import espacial as esp
from . import geometria as geo
from . import swing as sw
from .regioes import REGIOES_BR


def base_2026() -> pd.DataFrame:
    """Base municipal 2026 completa (com exterior, perfil e IBGE). Ver docs/DADOS.md."""
    b = base.base_municipal(carga.totais_2026(), carga.capitais())
    return base.enriquecer(b, carga.perfil_eleitorado_2026(), carga.ibge())


def candidatos_2026_br() -> pd.DataFrame:
    """Votos município×candidato 2026, sem exterior (agregados 'Brasil')."""
    c = carga.candidatos_2026()
    return c[c["uf"] != "zz"].copy()


def ordem_regioes() -> list[str]:
    return list(REGIOES_BR)


def pct_municipal_bloco(cand: pd.DataFrame, bb: pd.DataFrame, nrs: list[int]) -> pd.DataFrame:
    """% sobre válidos do município de cada candidato listado (grade cheia)."""
    partes = [sw.pct_municipal(cand, bb, nr).assign(nr=nr) for nr in nrs]
    return pd.concat(partes, ignore_index=True)


def swing_pt_pl() -> dict[str, pd.DataFrame]:
    """Swing 1T22→1T26 para PT (13→13) e PL (22→22: Bolsonaro 2022 → Flávio 2026).

    Devolve dicionário com: 'pt', 'pl' (municipais, pareados, com regiao), 'sem_par'.
    Identidade: nr 22 muda de PESSOA (Jair → Flávio); o swing mede sigla/numeração.
    """
    t22 = carga.totais_2022(1)
    t26 = carga.totais_2026()
    c22 = carga.candidatos_2022(1)
    c26 = carga.candidatos_2026()
    par, sem = sw.parear(t22, t26)
    regiao = base.base_municipal(t26, carga.capitais())[["uf", "cd_mun_tse", "regiao"]]
    out = {"sem_par": sem}
    for nome, nr in (("pt", 13), ("pl", 22)):
        s = sw.swing_municipal(par, c22, t22, c26, t26, nr, nr)
        out[nome] = s.merge(regiao, on=["uf", "cd_mun_tse"], validate="1:1")
    return out


def lente_pl_teto() -> pd.DataFrame:
    """PL 2026 (1º turno) vs teto de Bolsonaro no 2º turno 2022, por município (sem exterior)."""
    pl = swing_pt_pl()["pl"]
    pl_br = pl[pl["uf"] != "zz"]
    c22_t2 = carga.candidatos_2022(2)
    t22_t2 = carga.totais_2022(2)
    return sw.lente_pl_vs_teto(pl_br, c22_t2, t22_t2, sw.NR_BOLSONARO_2022)


def malha_com_codigos(base_b: pd.DataFrame) -> gpd.GeoDataFrame:
    """Malha municipal completa (IBGE) no CRS de área, com uf/cd_mun_tse do TSE (só Brasil)."""
    malha = carga.geometria_municipios_2024().reset_index(drop=True)
    malha = geo.areas_km2(malha)
    chaves = base_b[base_b["uf"] != "zz"][["cd_mun_ibge", "uf", "cd_mun_tse"]]
    return malha.merge(chaves, on="cd_mun_ibge", how="left", validate="1:1")


def vizinhanca_queen(malha: gpd.GeoDataFrame):
    """Pesos queen sobre a malha (todas as linhas, inclusive ilhas)."""
    return geo.pesos_queen(malha.reset_index(drop=True))


def lisa_pt_pl_swing(permutacoes: int = 999) -> dict[str, pd.DataFrame]:
    """LISA + BH para % PT, % PL 2026 e swing PL, com a MESMA vizinhança (sem ilhas nem sem-par)
    sem par). Devolve dict com 'pt', 'pl', 'swing' (tabelas por município) e 'moran' (I global).
    """
    b = base_2026()
    malha = malha_com_codigos(b)
    c26 = candidatos_2026_br()
    t26 = b[b["uf"] != "zz"]
    pl = swing_pt_pl()["pl"]
    pl_br = pl[pl["uf"] != "zz"][["uf", "cd_mun_tse", "swing_pp"]]

    pct = {}
    for nome, nr in (("pt", 13), ("pl", 22)):
        p = sw.pct_municipal(c26, t26, nr)[["uf", "cd_mun_tse", "pct_validos"]]
        pct[nome] = p.rename(columns={"pct_validos": f"pct_{nome}"})
    m = malha.merge(pct["pt"], on=["uf", "cd_mun_tse"], how="left", validate="m:1")
    m = m.merge(pct["pl"], on=["uf", "cd_mun_tse"], how="left", validate="m:1")
    m = m.merge(pl_br, on=["uf", "cd_mun_tse"], how="left", validate="m:1")

    # vizinhança e amostra: municípios com TODAS as variáveis definidas (sem ilhas, sem sem-par)
    mascara = m[["pct_pt", "pct_pl", "swing_pp"]].notna().all(axis=1).to_numpy()
    sub = m[mascara].reset_index(drop=True)
    w = geo.pesos_queen(sub)
    sem_ilha = np.ones(len(sub), dtype=bool)
    sem_ilha[[int(i) for i in w.islands]] = False  # Noronha e Ilhabela: sem vizinho
    sub = sub[sem_ilha].reset_index(drop=True)
    w_final = geo.pesos_queen(sub)  # vizinhança sem ilhas e sem o município sem par
    if len(w_final.islands) != 0:
        raise ValueError("ainda há ilhas após a remoção")
    ids = sub["cd_mun_ibge"].to_numpy()

    resultados = {"malha": sub, "w_n": w_final.n}
    for nome, col in (("pt", "pct_pt"), ("pl", "pct_pl"), ("swing", "swing_pp")):
        y = sub[col].to_numpy(dtype=float)
        resultados[f"moran_{nome}"] = esp.moran_global(y, w_final, permutacoes, seed=12345)
        resultados[nome] = esp.lisa_com_fdr(y, w_final, ids, 0.05, permutacoes, seed=12345)
    return resultados


def bolsoes_por_candidato(nrs_menores: list[int], limiar_x: float = 3.0) -> dict[str, object]:
    """Bolsões (componentes queen de municípios > limiar_x × média nacional) para candidatos
    com < 5% nacional. Média nacional = % sobre válidos BR (sem exterior)."""
    from . import bolsoes as bo

    b = base_2026()
    malha = carga.geometria_municipios_2024().reset_index(drop=True)
    w = geo.pesos_queen(malha)
    vizinhos = {i: list(w.neighbors[i]) for i in range(w.n)}
    chave = b[b["uf"] != "zz"][
        ["cd_mun_ibge", "uf", "cd_mun_tse", "nm_mun", "eleitorado", "validos"]
    ]
    ordem = malha[["cd_mun_ibge"]].merge(chave, on="cd_mun_ibge", how="left", validate="1:1")
    c26 = candidatos_2026_br()
    validos_br = float(chave["validos"].sum())
    out: dict[str, object] = {}
    for nr in nrs_menores:
        votos_br = float(c26.loc[c26["nr_candidato"] == nr, "votos"].sum())
        media = bo.media_nacional_pct(votos_br, validos_br)
        cv = c26.loc[c26["nr_candidato"] == nr, ["uf", "cd_mun_tse", "votos"]]
        x = ordem.merge(cv, on=["uf", "cd_mun_tse"], how="left", validate="1:1")
        x["votos"] = x["votos"].fillna(0)
        x["pct"] = 100 * x["votos"] / x["validos"]
        x = x.rename(columns={"nm_mun": "nome"}).reset_index(drop=True)
        out[str(nr)] = {
            "media_nacional_pct": media,
            "limiar_pct": limiar_x * media,
            "bolsoes": bo.bolsoes(x, "pct", media, vizinhos, limiar_x),
            "municipios": x,
        }
    return out


def tabela_reduto(uf: str, nr: int) -> dict[str, float]:
    """Desempenho num reduto (UF) do candidato `nr` vs média nacional."""
    from . import bolsoes as bo

    b = base_2026()
    chave = b[b["uf"] != "zz"]
    c26 = candidatos_2026_br()
    validos_br = float(chave["validos"].sum())
    media = bo.media_nacional_pct(
        float(c26.loc[c26["nr_candidato"] == nr, "votos"].sum()), validos_br
    )
    cv = c26.loc[c26["nr_candidato"] == nr, ["uf", "cd_mun_tse", "votos"]]
    x = chave.merge(cv, on=["uf", "cd_mun_tse"], how="left", validate="1:1")
    x["votos"] = x["votos"].fillna(0)
    x["pct"] = 100 * x["votos"] / x["validos"]
    return bo.resumo_reduto(x, "pct", uf, media)


def ponderar_regioes(tabela: pd.DataFrame, grupo: str = "regiao") -> pd.DataFrame:
    """Só reordena as regiões para plotagem (ordem fixa N, NE, CO, SE, S)."""
    ordem = {r: i for i, r in enumerate(REGIOES_BR)}
    return tabela.assign(_ord=tabela[grupo].map(ordem)).sort_values("_ord").drop(columns="_ord")


def percentuais_nacionais(cand: pd.DataFrame, bb: pd.DataFrame) -> dict[int, float]:
    """% nacional sobre válidos (sem exterior) de cada candidato: {nr: pct}."""
    g = base.votos_por_grupo(cand, bb.assign(_br="BR"), ["_br"])
    return dict(zip(g["nr_candidato"].astype(int), g["pct_sobre_validos_grupo"], strict=True))


def resumo_mapa_mente(b: pd.DataFrame) -> pd.DataFrame:
    """12_mapa_mente: municípios/área/eleitorado/votos vencidos por candidato (sem exterior)."""
    from . import mapa_mente as mm

    bb = base.apenas_brasil(b)
    cand = candidatos_2026_br()
    malha = malha_com_codigos(b)
    area = malha[["uf", "cd_mun_tse", "area_km2"]].dropna()
    vw = base.vencedor_municipal(cand)
    return mm.resumo_vencedores(vw, bb[["uf", "cd_mun_tse", "eleitorado", "validos"]], cand, area)


def tabela_concentracao(b: pd.DataFrame, nrs: list[int]) -> pd.DataFrame:
    """13_concentracao: Gini (votos absolutos e % sobre válidos) e nº de municípios para 50%."""
    from . import concentracao as cc

    bb = base.apenas_brasil(b)
    cand = candidatos_2026_br()
    linhas = []
    for nr in nrs:
        x = cand.loc[cand["nr_candidato"] == nr, ["uf", "cd_mun_tse", "votos"]].merge(
            bb[["uf", "cd_mun_tse", "validos"]], on=["uf", "cd_mun_tse"], validate="1:1"
        )
        pct_mun = 100 * x["votos"] / x["validos"]
        linhas.append(
            {
                "nr_candidato": nr,
                "n_municipios": len(x),
                "votos_nacionais": int(x["votos"].sum()),
                "gini_votos_absolutos": cc.gini(x["votos"].to_numpy()),
                "gini_pct_validos": cc.gini(pct_mun.to_numpy()),
                "n_municipios_50pct_votos": cc.n_municipios_para_fracao(x["votos"].to_numpy(), 0.5),
            }
        )
    return pd.DataFrame(linhas)


def lorenz_por_candidato(
    b: pd.DataFrame, nrs: list[int]
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    from . import concentracao as cc

    cand = candidatos_2026_br()
    curvas = {}
    for nr in nrs:
        x = cand.loc[cand["nr_candidato"] == nr, ["uf", "cd_mun_tse", "votos"]]
        curvas[nr] = cc.lorenz(x["votos"].to_numpy())
    return curvas


def resumo_bolsoes(bolsoes_dict: dict[str, object]) -> pd.DataFrame:
    """Uma linha por candidato: média nacional, limiar, nº de bolsões e maior bolsão."""
    linhas = []
    for nr, v in bolsoes_dict.items():
        bl = v["bolsoes"]
        maior = bl.sort_values("n_municipios", ascending=False).head(1)
        linhas.append(
            {
                "nr_candidato": int(nr),
                "media_nacional_pct": v["media_nacional_pct"],
                "limiar_3x_pct": v["limiar_pct"],
                "n_municipios_acima_limiar": int((v["municipios"]["pct"] > v["limiar_pct"]).sum()),
                "n_bolsoes": len(bl),
                "maior_bolsao_municipios": int(maior["n_municipios"].item()) if len(maior) else 0,
                "maior_bolsao_eleitorado": int(maior["eleitorado"].item()) if len(maior) else 0,
                "municipio_pico": maior["municipio_maior_pct"].item() if len(maior) else "",
            }
        )
    return pd.DataFrame(linhas)


def malha_vencedores(b: pd.DataFrame) -> gpd.GeoDataFrame:
    """Malha (sem exterior) com `vencedor` (nr do 1º colocado, ou None no empate)."""
    cand = candidatos_2026_br()
    vw = base.vencedor_municipal(cand)[["uf", "cd_mun_tse", "nr_vencedor"]]
    m = malha_com_codigos(b)
    return m.merge(vw, on=["uf", "cd_mun_tse"], how="left", validate="1:1")


def malha_swing(b: pd.DataFrame) -> gpd.GeoDataFrame:
    """Malha (sem exterior) com `swing_pp` do PL; sem par = sem valor (listados fora)."""
    pl = swing_pt_pl()["pl"]
    m = malha_com_codigos(b)
    return m.merge(pl[["uf", "cd_mun_tse", "swing_pp"]], on=["uf", "cd_mun_tse"], how="left",
                   validate="1:1")  # fmt: skip


def malha_bolsoes(bolsoes_dict: dict[str, object], nr: str, b: pd.DataFrame) -> gpd.GeoDataFrame:
    """Malha com flag `em_bolsao` (1 = município em qualquer bolsão do candidato `nr`)."""
    membros = set()
    for _, row in bolsoes_dict[nr]["bolsoes"].iterrows():
        membros.update(row["membros"])
    m = malha_com_codigos(b)
    m["em_bolsao"] = [(u, c) in membros for u, c in zip(m["uf"], m["cd_mun_tse"], strict=True)]
    return m
