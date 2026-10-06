"""Testes do swing 2022→2026, da lente PL×teto e do tratamento de municípios sem par."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from eleicao.analise import base, carga
from eleicao.analise import swing as sw


def _totais(uf, cd, nome, validos):
    return pd.DataFrame(
        {"uf": uf, "cd_mun_tse": cd, "nm_mun_tse": nome, "nm_mun": nome, "validos": validos}
    )


def _cand(uf, cd, nr, votos):
    return pd.DataFrame({"uf": uf, "cd_mun_tse": cd, "nr_candidato": nr, "votos": votos})


# ---------------------------------------------------------------- pareamento sintético


def test_pareamento_separa_sem_par_com_motivo():
    t22 = _totais(
        ["sp", "sp", "zz"], ["00001", "00002", "99252"], ["A", "B", "VATICANO"], [100, 100, 50]
    )
    t26 = _totais(
        ["sp", "mt", "zz"], ["00001", "73709", "29629"], ["A", "BOA", "DACCA"], [100, 80, 30]
    )
    par, sem = sw.parear(t22, t26)
    assert sorted(zip(par.uf, par.cd_mun_tse, strict=True)) == [("sp", "00001")]
    assert len(sem) == 4
    motivos = dict(zip(zip(sem.uf, sem.cd_mun_tse, strict=True), sem.motivo, strict=True))
    assert motivos[("sp", "00002")] == "ausente em 2026"
    assert motivos[("zz", "99252")].startswith("posto consular de 2022")
    assert motivos[("mt", "73709")].startswith("município criado")
    assert motivos[("zz", "29629")].startswith("posto consular novo")


def test_sem_par_nunca_entra_no_swing():
    t22 = _totais(["sp", "sp"], ["00001", "00002"], ["A", "B"], [100, 100])
    t26 = _totais(["sp", "mt"], ["00001", "73709"], ["A", "BOA"], [100, 100])
    c22 = _cand(["sp", "sp"], ["00001", "00002"], 22, [50, 50])
    c26 = _cand(["sp", "mt"], ["00001", "73709"], 22, [60, 60])
    par, _ = sw.parear(t22, t26)
    s = sw.swing_municipal(par, c22, t22, c26, t26, 22, 22)
    assert s.shape[0] == 1
    assert ("mt", "73709") not in set(zip(s.uf, s.cd_mun_tse, strict=True))
    assert not s["swing_pp"].isna().any()


def test_swing_e_diferenca_de_percentuais_sobre_validos_de_cada_ano():
    t22 = _totais(["sp"], ["00001"], ["A"], [200])
    t26 = _totais(["sp"], ["00001"], ["A"], [400])
    c22 = _cand(["sp"], ["00001"], 13, [50])  # 25% em 2022
    c26 = _cand(["sp"], ["00001"], 13, [100])  # 25% em 2026
    par, _ = sw.parear(t22, t26)
    s = sw.swing_municipal(par, c22, t22, c26, t26, 13, 13).iloc[0]
    assert s["pct_2022"] == pytest.approx(25.0) and s["pct_2026"] == pytest.approx(25.0)
    assert s["swing_pp"] == pytest.approx(0.0)


def test_agregado_ponderado_difere_da_media_simples():
    # Município grande (1000 válidos) cai 10 pp; pequeno (100 válidos) sobe 40 pp.
    s = pd.DataFrame(
        {
            "regiao": ["NE", "NE"],
            "votos_2022": [500, 40],
            "validos_2022": [1000, 100],
            "votos_2026": [400, 80],
            "validos_2026": [1000, 100],
            "swing_pp": [-10.0, 40.0],
        }
    )
    ag = sw.agregado_ponderado(s, "regiao").iloc[0]
    assert ag["pct_2022_agregado"] == pytest.approx(540 / 1100 * 100)
    assert ag["pct_2026_agregado"] == pytest.approx(480 / 1100 * 100)
    assert ag["swing_agregado_pp"] == pytest.approx((480 - 540) / 1100 * 100)
    media = sw.media_simples_swing(s, "regiao").iloc[0]["media_simples_swing_pp"]
    assert media == pytest.approx(15.0)
    assert media != pytest.approx(ag["swing_agregado_pp"])


def test_teste_uniformidade_detecta_grupos_diferentes():
    rng = np.random.default_rng(0)
    d = pd.DataFrame(
        {
            "regiao": np.repeat(["N", "S"], 50),
            "swing_pp": np.r_[rng.normal(-5, 1, 50), rng.normal(5, 1, 50)],
        }
    )
    r = sw.teste_uniformidade(d, "regiao")
    assert r["kruskal_p"] < 1e-6 and r["anova_p"] < 1e-6
    assert r["eta2"] > 0.9


def test_teste_uniformidade_grupos_iguais_eta_zero():
    d = pd.DataFrame({"regiao": ["a", "a", "b", "b"], "swing_pp": [1.0, 3.0, 1.0, 3.0]})
    r = sw.teste_uniformidade(d, "regiao")
    assert r["eta2"] == pytest.approx(0.0, abs=1e-12)


def test_teste_uniformidade_exige_dois_grupos():
    with pytest.raises(ValueError):
        sw.teste_uniformidade(
            pd.DataFrame({"regiao": ["a"] * 3, "swing_pp": [1.0, 2, 3]}), "regiao"
        )


def test_lente_teto_diferenca_e_erro_sem_par_no_2t():
    swing = pd.DataFrame(
        {
            "uf": ["sp", "sp"],
            "cd_mun_tse": ["1", "2"],
            "nome": ["A", "B"],
            "regiao": ["SE", "SE"],
            "pct_2026": [30.0, 10.0], "votos_2026": [30, 10], "validos_2026": [100, 100],
        }
    )  # fmt: skip
    cand_t2 = _cand(["sp", "sp"], ["1", "2"], 22, [20, 40])
    tot_t2 = _totais(["sp", "sp"], ["1", "2"], ["A", "B"], [100, 100])
    lente = sw.lente_pl_vs_teto(swing, cand_t2, tot_t2, 22)
    dif = lente.set_index("cd_mun_tse")["diferenca_pp"]
    assert dif["1"] == pytest.approx(30.0 - 20.0)
    assert dif["2"] == pytest.approx(10.0 - 40.0)
    assert sw.contagem_acima_do_teto(lente).iloc[0]["n_acima_do_teto"] == 1

    # município pareado sem 2º turno 2022 levanta erro (não há NaN silencioso)
    with pytest.raises(ValueError):
        sw.lente_pl_vs_teto(swing, cand_t2, _totais(["sp"], ["1"], ["A"], [100]), 22)


def test_lente_regional_ponderada():
    lente = pd.DataFrame(
        {
            "regiao": ["NE", "NE"],
            "votos_2026": [30, 10], "validos_2026": [100, 100],
            "votos_teto_2t_2022": [10, 40], "validos_2t_2022": [100, 100],
        }
    )  # fmt: skip
    g = sw.lente_regiao(lente).iloc[0]
    assert g["pl_2026_1t_agregado_pp"] == pytest.approx(20.0)
    assert g["teto_2t_2022_agregado_pp"] == pytest.approx(25.0)
    assert g["diferenca_agregada_pp"] == pytest.approx(-5.0)


# ---------------------------------------------------------------- invariantes com dados reais


@pytest.fixture(scope="module")
def dados_swing():
    t22 = carga.totais_2022(1)
    t26 = carga.totais_2026()
    c22 = carga.candidatos_2022(1)
    c26 = carga.candidatos_2026()
    par, sem = sw.parear(t22, t26)
    return t22, t26, c22, c26, par, sem


def test_real_sem_par_lista_exata(dados_swing):
    *_, par, sem = dados_swing
    # 5750 pares com chave; 44 saem por zero votos válidos em um dos anos (todos zz); 8 sem par
    assert len(par) == 5706
    assert len(sem) == 52
    assert (sem.ano_presente == "ambos, sem votos válidos em um ano").sum() == 44
    sem8 = sem[sem.ano_presente != "ambos, sem votos válidos em um ano"]
    assert set(zip(sem8.uf, sem8.cd_mun_tse, strict=True)) == {
        ("zz", "99252"), ("mt", "73709"), ("zz", "29629"), ("zz", "99279"),
        ("zz", "99295"), ("zz", "99490"), ("zz", "99503"), ("zz", "99511"),
    }  # fmt: skip
    assert sem.motivo.notna().all()
    # nenhum município brasileiro sai por zero válidos
    assert (sem[sem.ano_presente.str.startswith("ambos")].uf != "zz").sum() == 0


def test_real_swing_pl_municipal_sem_nan_e_intervalo(dados_swing):
    t22, t26, c22, c26, par, _ = dados_swing
    s = sw.swing_municipal(par, c22, t22, c26, t26, 22, 22)
    assert len(s) == 5706 and not s["swing_pp"].isna().any()
    assert s["swing_pp"].between(-100, 100).all()


def test_real_swing_agregado_br_sem_exterior_reproduz_numeros(dados_swing):
    t22, t26, c22, c26, par, _ = dados_swing
    s = sw.swing_municipal(par, c22, t22, c26, t26, 22, 22)
    s = s[s["uf"] != "zz"]
    # nr 22 em 2022 (Bolsonaro) e 2026 (Flávio/PL), Brasil pareado, sobre válidos de cada ano.
    # Reprodução independente a partir dos Parquet: votos e válidos dos municípios pareados BR.
    tot = s[["votos_2022", "validos_2022", "votos_2026", "validos_2026"]].sum()
    assert 100 * tot["votos_2022"] / tot["validos_2022"] == pytest.approx(
        _pct_br_pareado(c22, t22, 22, s), abs=1e-9
    )
    assert 100 * tot["votos_2026"] / tot["validos_2026"] == pytest.approx(
        _pct_br_pareado(c26, t26, 22, s), abs=1e-9
    )


def _pct_br_pareado(cand, tot, nr, s):
    chaves = set(zip(s.uf, s.cd_mun_tse, strict=True))
    t = tot[[(u, c) in chaves for u, c in zip(tot.uf, tot.cd_mun_tse, strict=True)]]
    v = cand[(cand.nr_candidato == nr)]
    v = v[[(u, c) in chaves for u, c in zip(v.uf, v.cd_mun_tse, strict=True)]]
    return 100 * v.votos.sum() / t.validos.sum()


def test_real_teste_uniformidade_regioes_eta2_pequeno_mas_significativo(dados_swing):
    t22, t26, c22, c26, par, _ = dados_swing
    b = base.base_municipal(t26, carga.capitais())[["uf", "cd_mun_tse", "regiao"]]
    s = sw.swing_municipal(par, c22, t22, c26, t26, 22, 22).merge(b, on=["uf", "cd_mun_tse"])
    s = s[s["uf"] != "zz"]
    r = sw.teste_uniformidade(s, "regiao")
    assert r["n"] == 5570  # BR pareado: 5571 - Boa Esperança do Norte
    assert r["kruskal_p"] < 1e-10
    assert 0.0 < r["eta2"] < 0.5


# ---------------------------------------------------------------- Δmargem PL−PT (D-030)


def _sw(cd, v22, val22, v26, val26):
    d = pd.DataFrame(
        {"uf": "sp", "cd_mun_tse": cd, "votos_2022": v22, "validos_2022": val22,
         "votos_2026": v26, "validos_2026": val26, "regiao": "SE"}
    )  # fmt: skip
    d["pct_2022"] = 100 * d.votos_2022 / d.validos_2022
    d["pct_2026"] = 100 * d.votos_2026 / d.validos_2026
    d["swing_pp"] = d.pct_2026 - d.pct_2022
    return d


def test_delta_margem_municipal_definicao_e_igual_a_diferenca_de_swings():
    pt = _sw(["1", "2"], [50, 40], [100, 100], [40, 45], [100, 200])
    pl = _sw(["1", "2"], [40, 50], [100, 100], [50, 100], [100, 200])
    d = sw.delta_margem_municipal(pt, pl).set_index("cd_mun_tse")
    # mun 1: (50-40) - (40-50) = +20 ; mun 2: (50-22.5) - (50-40) = +17.5
    assert d.loc["1", "delta_margem_pp"] == pytest.approx(20.0)
    assert d.loc["2", "delta_margem_pp"] == pytest.approx(17.5)
    assert np.allclose(d.delta_margem_pp, d.swing_pl_pp - d.swing_pt_pp)


def test_delta_margem_sem_mudanca_e_zero():
    pt = _sw(["1"], [50], [100], [500], [1000])
    pl = _sw(["1"], [30], [100], [300], [1000])
    assert sw.delta_margem_municipal(pt, pl).delta_margem_pp.iloc[0] == pytest.approx(0.0)


def test_delta_margem_exige_mesma_base():
    pt = _sw(["1", "2"], [50, 40], [100, 100], [40, 45], [100, 200])
    pl = _sw(["1"], [40], [100], [50], [100])
    with pytest.raises(ValueError):
        sw.delta_margem_municipal(pt, pl)
    with pytest.raises(ValueError):
        sw.delta_margem_agregado(pt, pl)


def test_delta_margem_agregado_e_ponderado_nao_media_simples():
    # mun grande (1000 válidos) sem mudança; mun pequeno (10 válidos) com +100 p.p.
    pt = _sw(["1", "2"], [500, 10], [1000, 10], [500, 0], [1000, 10])
    pl = _sw(["1", "2"], [500, 0], [1000, 10], [500, 10], [1000, 10])
    ag = sw.delta_margem_agregado(pt, pl).iloc[0]
    # ponderado: PT 2022 = 510/1010, 2026 = 500/1010 ; PL 2022 = 500/1010, 2026 = 510/1010
    assert ag["delta_margem_pp"] == pytest.approx(100 * 20 / 1010)
    media_simples = sw.delta_margem_municipal(pt, pl).delta_margem_pp.mean()
    assert media_simples == pytest.approx(100.0)
    por_regiao = sw.delta_margem_agregado(pt, pl, "regiao")
    assert por_regiao.delta_margem_pp.iloc[0] == pytest.approx(ag["delta_margem_pp"])


def test_real_delta_margem_br(dados_swing):
    t22, t26, c22, c26, par, _ = dados_swing
    pt = sw.swing_municipal(par, c22, t22, c26, t26, 13, 13)
    pl = sw.swing_municipal(par, c22, t22, c26, t26, 22, 22)
    pt, pl = pt[pt.uf != "zz"], pl[pl.uf != "zz"]
    d = sw.delta_margem_municipal(pt, pl)
    assert len(d) == 5570 and not d.delta_margem_pp.isna().any()
    ag = sw.delta_margem_agregado(pt, pl).iloc[0]
    assert ag["delta_margem_pp"] == pytest.approx(ag["swing_pl_pp"] - ag["swing_pt_pp"])
    # ANALISES.md: PT −3,3 e PL +3,8 → margem do PL sobre o PT +7,1 p.p.
    assert round(ag["delta_margem_pp"], 1) == 7.1


def test_limites_escala_delta_p1_p99_assimetricos():
    d = pd.Series(np.r_[np.linspace(-2, -0.1, 30), np.linspace(0.1, 30, 970)])
    neg, pos = sw.limites_escala_delta(d)
    assert neg == pytest.approx(np.percentile(d, 1))
    assert pos == pytest.approx(np.percentile(d, 99))
    assert neg < 0 < pos and neg != -pos


def test_limites_escala_delta_cai_para_o_extremo_quando_p1_nao_e_negativo():
    d = pd.Series([-0.5] + [5.0] * 999)
    neg, pos = sw.limites_escala_delta(d)
    assert neg == -0.5 and pos == 5.0


def test_limites_escala_delta_exige_os_dois_lados():
    with pytest.raises(ValueError):
        sw.limites_escala_delta(pd.Series([1.0, 2.0, 3.0]))
