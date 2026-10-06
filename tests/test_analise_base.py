"""Testes da base municipal, agregados ponderados, participação, concentração e mapa-mente.

Parte sintética (resposta conhecida) e parte com os Parquet reais de data/processed/.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from eleicao.analise import base, carga
from eleicao.analise import concentracao as cc
from eleicao.analise import mapa_mente as mm
from eleicao.analise import participacao as pa
from eleicao.analise.regioes import (
    FAIXAS_ELEITORADO,
    REGIOES_BR,
    UF_REGIAO,
    faixa_eleitorado,
    regiao_da_uf,
)

UFS_BR = [
    "ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt", "pa",
    "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to",
]  # fmt: skip


# ---------------------------------------------------------------- regiões e faixas


def test_mapeamento_regiao_cobre_27_ufs_sem_sobra():
    assert sorted(UF_REGIAO) == sorted(UFS_BR)
    assert set(UF_REGIAO.values()) == set(REGIOES_BR)


def test_regiao_exterior_e_recorte_a_parte():
    assert regiao_da_uf("zz") == "Exterior"
    assert regiao_da_uf("SP") == "SE"  # SE = Sudeste
    assert regiao_da_uf("se") == "NE"  # Sergipe é Nordeste


def test_regiao_uf_desconhecida_levanta():
    with pytest.raises(KeyError):
        regiao_da_uf("xx")


def test_faixas_de_eleitorado_limites_inclusivos_e_exclusivos():
    s = pd.Series([0, 9_999, 10_000, 49_999, 50_000, 199_999, 200_000, 999_999, 1_000_000, 9e6])
    r = faixa_eleitorado(s).astype(str).tolist()
    assert r == [
        "<10k", "<10k", "10k–50k", "10k–50k", "50k–200k", "50k–200k",
        "200k–1M", "200k–1M", ">1M", ">1M",
    ]  # fmt: skip
    assert [f[0] for f in FAIXAS_ELEITORADO] == ["<10k", "10k–50k", "50k–200k", "200k–1M", ">1M"]


def test_faixa_nula_fica_nula():
    r = faixa_eleitorado(pd.Series([np.nan, 5_000.0]))
    assert pd.isna(r.iloc[0]) and str(r.iloc[1]) == "<10k"


# ---------------------------------------------------------------- base e agregados sintéticos


def _totais_sinteticos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "uf": ["sp", "sp", "ba", "zz"],
            "cd_mun_tse": ["00001", "00002", "00003", "99001"],
            "eleitorado": [20_000, 5_000, 60_000, 500],
            "comparecimento": [16_000, 4_000, 45_000, 300],
            "abstencao": [4_000, 1_000, 15_000, 200],
            "brancos": [160, 40, 900, 3],
            "nulos_tvn": [800, 200, 2_250, 5],
            "nulos_vn": [800, 200, 2_200, 5],
            "validos": [15_040, 3_760, 41_850, 292],
        }
    )


def test_base_municipal_marca_exterior_e_capital():
    tot = _totais_sinteticos()
    caps = pd.DataFrame({"uf": ["sp"], "cd_mun_tse": ["00001"]})
    b = base.base_municipal(tot, caps)
    assert b.loc[b.cd_mun_tse == "00001", "eh_capital"].item() is True
    assert b.loc[b.cd_mun_tse == "00002", "eh_capital"].item() is False
    assert b.loc[b.uf == "zz", "regiao"].item() == "Exterior"
    assert pd.isna(b.loc[b.uf == "zz", "faixa"]).all()


def test_apenas_brasil_remove_exterior():
    tot = _totais_sinteticos()
    b = base.base_municipal(tot, pd.DataFrame({"uf": [], "cd_mun_tse": []}))
    assert "zz" not in base.apenas_brasil(b)["uf"].tolist()


def test_participacao_denominadores_explicitos():
    tot = _totais_sinteticos()
    g = base.participacao_agregada(tot[tot.uf == "sp"].assign(regiao="SE"), ["regiao"])
    lin = g.iloc[0]
    # sp: eleitorado 25.000, comparecimento 20.000, abstenção 5.000
    assert lin["pct_abstencao_sobre_eleitorado"] == pytest.approx(20.0)
    assert lin["pct_comparecimento_sobre_eleitorado"] == pytest.approx(80.0)
    # brancos (160+40=200) e nulos sobre comparecimento (20.000)
    assert lin["pct_brancos_sobre_comparecimento"] == pytest.approx(1.0)
    assert lin["pct_nulos_tvn_sobre_comparecimento"] == pytest.approx(5.0)


def test_votos_por_grupo_soma_bate_com_validos_e_pct_no_denominador_certo():
    # município 1 (SE): 13=60, 22=40 -> válidos 100; município 2 (SE): 13=0, 22=300 -> 300;
    # município 3 (NE): 13=500, 22=100 -> 600.
    cand = pd.DataFrame(
        {
            "uf": ["sp", "sp", "sp", "sp", "ba", "ba"],
            "cd_mun_tse": ["1", "1", "2", "2", "3", "3"],
            "nr_candidato": [13, 22, 13, 22, 13, 22],
            "votos": [60, 40, 0, 300, 500, 100],
        }
    )
    base_t = pd.DataFrame(
        {
            "uf": ["sp", "sp", "ba"],
            "cd_mun_tse": ["1", "2", "3"],
            "validos": [100, 300, 600],
            "regiao": ["SE", "SE", "NE"],
        }
    )
    g = base.votos_por_grupo(cand, base_t, ["regiao"]).set_index(["regiao", "nr_candidato"])
    assert g.loc[("SE", 22), "votos"] == 340
    assert g.loc[("SE", 13), "votos"] == 60
    assert g.loc[("SE", 22), "validos_grupo"] == 400
    assert g.loc[("SE", 22), "pct_sobre_validos_grupo"] == pytest.approx(85.0)
    assert g.groupby(level="regiao")["votos"].sum().to_dict() == {"NE": 600, "SE": 400}


def test_votos_por_grupo_grade_cheia_com_zero_explicito():
    cand = pd.DataFrame(
        {
            "uf": ["sp", "sp", "ba"],
            "cd_mun_tse": ["1", "1", "3"],
            "nr_candidato": [13, 22, 13],
            "votos": [10, 5, 40],
        }
    )
    base_t = pd.DataFrame(
        {"uf": ["sp", "ba"], "cd_mun_tse": ["1", "3"], "validos": [15, 40], "regiao": ["SE", "NE"]}
    )
    g = base.votos_por_grupo(cand, base_t, ["regiao"])
    zero = g[(g.regiao == "NE") & (g.nr_candidato == 22)]
    assert len(zero) == 1 and zero["votos"].item() == 0
    assert not g.isna().any().any()


def test_vencedor_municipal_empate_nao_tem_vencedor():
    cand = pd.DataFrame(
        {
            "uf": ["sp", "sp", "sp", "ba", "ba"],
            "cd_mun_tse": ["00001", "00001", "00001", "00003", "00003"],
            "nr_candidato": [13, 22, 15, 13, 22],
            "votos": [500, 300, 100, 400, 400],
        }
    )
    v = base.vencedor_municipal(cand).set_index("cd_mun_tse")
    assert v.loc["00001", "nr_vencedor"] == 13
    assert v.loc["00001", "margem_pp"] == pytest.approx(100 * 200 / 900)
    assert v.loc["00003", "nr_vencedor"] is None
    assert v.loc["00003", "margem_pp"] == 0


def test_pct_zero_denominador_levanta():
    with pytest.raises(ZeroDivisionError):
        base.pct(1, 0)


# ---------------------------------------------------------------- participação


def _municipios_participacao() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "uf": ["mg", "mg", "sp", "sp"],
            "cd_mun_tse": ["1", "2", "3", "4"],
            "nm_mun": ["A", "B", "C", "D"],
            "eleitorado": [2_000, 50_000, 3_000, 100_000],
            "pct_abstencao_sobre_eleitorado": [40.0, 20.0, 35.0, 10.0],
        }
    )


def test_ranking_respeita_corte_de_eleitorado():
    m = _municipios_participacao()
    r = pa.ranking_participacao(m, corte_eleitorado=10_000, n=5)
    assert r["maior_abstencao"]["cd_mun_tse"].tolist() == ["2", "4"]  # só >= 10k
    assert r["menor_abstencao"]["cd_mun_tse"].tolist() == ["4", "2"]


def test_ranking_sem_corte_inclui_pequenos():
    m = _municipios_participacao()
    r = pa.ranking_participacao(m, corte_eleitorado=0, n=2)
    assert r["maior_abstencao"]["cd_mun_tse"].tolist() == ["1", "3"]


def test_jaccard_limites():
    assert pa.jaccard(frozenset({1, 2}), frozenset({1, 2})) == 1.0
    assert pa.jaccard(frozenset({1}), frozenset({2})) == 0.0
    assert pa.jaccard(frozenset({1, 2, 3}), frozenset({2, 3, 4})) == pytest.approx(2 / 4)


def test_correlacao_monotona_e_spearman_um():
    d = pd.DataFrame({"x": np.arange(30.0), "y": np.arange(30.0) ** 3})
    r = pa.correlacao_ecologica(d, "x", "y", "spearman")
    assert r["r"] == pytest.approx(1.0) and r["n"] == 30
    assert pa.correlacao_ecologica(d, "x", "y", "pearson")["r"] < 1.0


def test_correlacao_metodo_invalido():
    with pytest.raises(ValueError):
        pa.correlacao_ecologica(pd.DataFrame({"x": [1, 2], "y": [1, 2]}), "x", "y", "kendall")


# ---------------------------------------------------------------- concentração


def test_gini_casos_conhecidos():
    assert cc.gini(np.array([1.0, 1, 1, 1])) == pytest.approx(0.0)
    assert cc.gini(np.array([0.0, 0, 0, 1])) == pytest.approx(0.75)


def test_gini_rejeita_negativos_e_vazios():
    with pytest.raises(ValueError):
        cc.gini(np.array([1.0, -1]))
    with pytest.raises(ValueError):
        cc.gini(np.array([]))


def test_lorenz_extremos():
    x, y = cc.lorenz(np.array([1.0, 2, 3]))
    assert (x[0], y[0]) == (0.0, 0.0) and (x[-1], y[-1]) == pytest.approx((1.0, 1.0))


def test_n_municipios_para_metade():
    assert cc.n_municipios_para_fracao(np.array([5.0, 3, 1, 1]), 0.5) == 1
    assert cc.n_municipios_para_fracao(np.array([5.0, 3, 1, 1]), 0.8) == 2
    assert cc.n_municipios_para_fracao(np.array([1.0, 1, 1, 1]), 0.5) == 2


# ---------------------------------------------------------------- mapa-mente sintético


def test_resumo_vencedores_sintetico_soma_consistente():
    municipios = pd.DataFrame(
        {"uf": ["sp", "sp", "ba"], "cd_mun_tse": ["1", "2", "3"], "eleitorado": [100, 300, 600]}
    )
    cand = pd.DataFrame(
        {
            "uf": ["sp", "sp", "sp", "sp", "ba", "ba"],
            "cd_mun_tse": ["1", "1", "2", "2", "3", "3"],
            "nr_candidato": [13, 22, 13, 22, 13, 22],
            "votos": [60, 40, 100, 200, 500, 100],
        }
    )
    vw = base.vencedor_municipal(cand)
    area = pd.DataFrame(
        {"uf": ["sp", "sp", "ba"], "cd_mun_tse": ["1", "2", "3"], "area_km2": [10.0, 30.0, 60.0]}
    )
    r = mm.resumo_vencedores(vw, municipios, cand, area).set_index("nr_candidato")
    assert r.loc[13, "n_municipios_vencidos"] == 2
    assert r.loc[22, "n_municipios_vencidos"] == 1
    assert r["pct_area_sobre_area_br"].sum() == pytest.approx(100.0)
    assert r.loc[13, "pct_area_sobre_area_br"] == pytest.approx(
        70.0
    )  # municípios 1 e 3: 70 km² de 100
    assert r.loc[22, "votos_do_candidato_nos_vencidos"] == 200
    # 22 recebeu 40 + 200 + 100 = 340 votos nacionais; 200 deles nos municípios que venceu
    assert r.loc[22, "pct_votos_do_candidato_nos_vencidos"] == pytest.approx(100 * 200 / 340)


# ---------------------------------------------------------------- invariantes com dados reais


@pytest.fixture(scope="module")
def reais():
    t = carga.totais_2026()
    c = carga.candidatos_2026()
    b = base.base_municipal(t, carga.capitais())
    return t, c, b


def test_real_soma_candidatos_igual_validos_em_cada_municipio(reais):
    _, c, b = reais
    s = c.groupby(["uf", "cd_mun_tse"])["votos"].sum().rename("soma").reset_index()
    m = s.merge(b[["uf", "cd_mun_tse", "validos"]], on=["uf", "cd_mun_tse"], validate="1:1")
    assert (m["soma"] == m["validos"]).all()


def test_real_numero_de_municipios_e_exterior(reais):
    _, _, b = reais
    assert len(b) == 5757
    assert (b["uf"] == "zz").sum() == 186
    assert len(base.apenas_brasil(b)) == 5571


def test_real_capitais_uma_por_uf(reais):
    _, _, b = reais
    cap = b[b["eh_capital"]]
    assert len(cap) == 27 and cap["uf"].nunique() == 27


def test_real_votos_brasil_batem_com_bloco_de_known_issue(reais):
    """Soma dos municípios (com exterior) = total BR do parquet + divergência catalogada da BA."""
    _, c, _ = reais
    br = pd.read_parquet(carga.PROC / "presidente_t1_br.parquet").set_index("nr_candidato")["votos"]
    soma = c.groupby("nr_candidato")["votos"].sum()
    dif = soma - br
    # Catálogo: BA, municípios 33693/34673/36013, candidatos 13,14,21,22,55,70,80
    assert dif.loc[22] == -236
    assert dif.loc[13] == -967


def test_real_ranking_abstencao_corte_10k_mostra_mg_no_topo(reais):
    _, _, b = reais
    m = pa.adicionar_abstencao(base.apenas_brasil(b))
    r = pa.ranking_participacao(m, corte_eleitorado=10_000, n=20)
    assert (m["eleitorado"] >= 10_000).sum() == 2631
    assert r["maior_abstencao"].iloc[0]["nm_mun"].upper().startswith("RIO VERMELHO")
    assert r["maior_abstencao"].iloc[0]["pct_abstencao_sobre_eleitorado"] == pytest.approx(
        40.09, abs=0.01
    )


def test_agrupar_outros_preserva_codigos_e_soma_os_pequenos():
    from eleicao.analise import graficos as gr

    tab = pd.DataFrame(
        {
            "regiao": ["N"] * 3,
            "nr_candidato": [13, 22, 30],
            "pct_sobre_validos_grupo": [40.0, 50.0, 10.0],
        }
    )
    nac = {13: 45.0, 22: 47.0, 30: 0.3, 99: 7.7}  # 30 é < 1% nacional -> "outros"
    out = gr.agrupar_outros_grafico(tab, "regiao", "pct_sobre_validos_grupo", nac)
    assert set(out["nr_candidato"]) == {13, 22, "outros"}
    assert out.loc[out.nr_candidato == "outros", "pct_sobre_validos_grupo"].item() == pytest.approx(
        10.0
    )
    assert out.loc[out.nr_candidato == 13, "pct_sobre_validos_grupo"].item() == pytest.approx(40.0)
