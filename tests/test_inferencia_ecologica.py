"""Testes de eleicao.inferencia_ecologica (dados sintéticos; sem dependência de 2018/2026)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from eleicao import inferencia_ecologica as ie

RAIZ = Path(__file__).resolve().parents[1]


def _sintetico(n=400, k=4, j=4, ruido=0.002, semente=1, n_uf=4):
    rng = np.random.default_rng(semente)
    b_real = rng.dirichlet(np.ones(j) * 0.7, size=k)
    x = rng.dirichlet(np.ones(k), size=n)
    y = x @ b_real + rng.normal(0, ruido, size=(n, j))
    y = np.clip(y, 0, None)
    y = y / y.sum(axis=1, keepdims=True)
    w = rng.integers(2_000, 200_000, size=n).astype(float)
    uf = np.array([f"u{i % n_uf}" for i in range(n)])
    return x, y, w, uf, b_real


def test_b_nao_negativo_e_linhas_somam_1():
    x, y, w, _, _ = _sintetico(ruido=0.05)  # ruído alto força restrições a agir
    b = ie.goodman_restrito(x, y, w)
    assert b.min() >= -1e-9
    assert np.allclose(b.sum(axis=1), 1.0, atol=1e-6)


def test_recupera_b_conhecida():
    x, y, w, _, b_real = _sintetico(n=800, ruido=0.002)
    b = ie.goodman_restrito(x, y, w)
    assert np.abs(b - b_real).max() < 0.03


def test_shrinkage_extremos():
    x, y, w, uf, _ = _sintetico()
    alvos = ie.alvos_leave_one_uf_out(x, y, w, uf)
    inf = ie.goodman_por_uf(x, y, w, uf, np.inf, alvos)
    for u in alvos:
        assert np.allclose(inf[u], alvos[u])
    por_uf = ie.goodman_por_uf(x, y, w, uf, 1e-6, alvos)
    for b in por_uf.values():
        assert b.min() >= -1e-9 and np.allclose(b.sum(axis=1), 1.0, atol=1e-6)


def test_selecionar_lambda_devolve_valor_da_grade():
    x, y, w, uf, _ = _sintetico(n=200)
    lam, tab = ie.selecionar_lambda(x, y, w, uf, [0.0, 1.0, np.inf], n_folds=3)
    assert lam in (0.0, 1.0, np.inf)
    assert len(tab) == 3 and tab["erro_cv"].notna().all()


def _contagens_sinteticas():
    rng = np.random.default_rng(3)
    n = 60
    uf = np.array(["aa"] * 20 + ["bb"] * 20 + ["zz"] * 20)
    cod = [f"{i:05d}" for i in range(n)]
    elet = rng.integers(500, 5000, size=n)
    c = pd.DataFrame({"uf": uf, "cd_mun_tse": cod})
    for col in ["lula", "bol", "ter", "bn"]:
        c[col] = (elet * rng.uniform(0.05, 0.25, size=n)).astype(int)
    c["abst"] = elet - c[["lula", "bol", "ter", "bn"]].sum(axis=1)
    return c


MAT = pd.DataFrame(
    [[0.1, 0.7, 0.1, 0.1], [0.8, 0.05, 0.05, 0.1], [0.4, 0.3, 0.1, 0.2], [0.0, 0.0, 1.0, 0.0]],
    index=["lula", "bol", "ter", "bn"],
    columns=ie.COLS_T2,
)
MAT.loc["abst"] = [0, 0, 0, 1.0]


def test_projecao_soma_aptos_por_municipio():
    c = _contagens_sinteticas()
    p = ie.projetar(c, MAT)
    aptos = c.drop(columns=ie.CHAVE).sum(axis=1)
    ie.checar_somas(p, aptos)
    assert np.allclose(p[ie.COLS_T2].sum(axis=1), aptos)


def test_projecao_rejeita_coluna_fora_da_matriz():
    c = _contagens_sinteticas().assign(extra=1)
    with pytest.raises(ValueError, match="fora da matriz"):
        ie.projetar(c, MAT)


def test_municipio_soma_uf_soma_br_e_rotulos_zz():
    c = _contagens_sinteticas()
    p = ie.projetar(c, MAT)
    por_uf = ie.agregar(p, ["uf"])
    br = ie.agregar(p, None)
    assert np.allclose(por_uf[ie.COLS_T2].sum().to_numpy(), br[ie.COLS_T2].iloc[0].to_numpy())
    for u in ["aa", "bb", "zz"]:
        mun = p[p["uf"] == u][ie.COLS_T2].sum().to_numpy()
        assert np.allclose(mun, por_uf[por_uf["uf"] == u][ie.COLS_T2].iloc[0].to_numpy())
    r = ie.agregados_rotulados(p)
    assert set(r) == {"brasil_sem_zz", "zz_exterior", "total_oficial_com_zz"}
    soma = r["brasil_sem_zz"].iloc[0] + r["zz_exterior"].iloc[0]
    assert np.allclose(soma.to_numpy(), r["total_oficial_com_zz"].iloc[0].to_numpy())
    zz = p[p["uf"] == "zz"]
    assert np.allclose(r["zz_exterior"][ie.COLS_T2].iloc[0].to_numpy(), zz[ie.COLS_T2].sum())


def test_pareamento_lista_sem_par_e_conserva_chaves():
    a = pd.DataFrame(
        {"uf": ["sp", "sp", "zz", "mt"], "cd_mun_tse": ["1", "2", "3", "4"], "ap": [5, 5, 5, 0]}
    )
    b = pd.DataFrame(
        {"uf": ["sp", "sp", "zz", "mt"], "cd_mun_tse": ["1", "9", "3", "4"], "ap": [5, 5, 0, 7]}
    )
    par, sem = ie.parear_chaves(a, b, "2022", "2026", col_aptos="ap")
    chaves = lambda d: set(map(tuple, d[ie.CHAVE].to_numpy()))  # noqa: E731
    assert chaves(par) == {("sp", "1")}
    assert chaves(sem) == {("sp", "2"), ("sp", "9"), ("zz", "3"), ("mt", "4")}
    assert chaves(par) | chaves(sem) == chaves(a) | chaves(b)
    assert not (chaves(par) & chaves(sem))
    assert (sem["motivo"].str.len() > 0).all()


def test_pareamento_rejeita_chave_duplicada():
    a = pd.DataFrame({"uf": ["sp", "sp"], "cd_mun_tse": ["1", "1"]})
    with pytest.raises(ValueError, match="duplicada"):
        ie.parear_chaves(a, a)


def test_montar_contagens_nao_descarta_candidato():
    cand = pd.DataFrame(
        {
            "uf": ["sp"] * 3,
            "cd_mun_tse": ["1"] * 3,
            "nr_candidato": [13, 22, 99],
            "votos": [50, 30, 5],
        }
    )
    tot = pd.DataFrame(
        {
            "uf": ["sp"],
            "cd_mun_tse": ["1"],
            "eleitorado": [120],
            "comparecimento": [100],
            "validos": [85],
        }
    )
    with pytest.raises(ValueError, match="fora de qualquer grupo"):
        ie.montar_contagens(cand, tot, {"lula": [13], "bol": [22]})
    c = ie.montar_contagens(cand, tot, {"lula": [13], "bol": [22], "out": [99]})
    assert c.loc[0, ["lula", "bol", "out", "bn", "abst"]].tolist() == [50, 30, 5, 15, 20]


def test_bootstrap_estratificado_preserva_tamanho_por_uf():
    uf = np.array(["a"] * 5 + ["b"] * 3)
    idx = ie.reamostrar_estratificado(uf, np.random.default_rng(0))
    assert (uf[idx] == "a").sum() == 5 and (uf[idx] == "b").sum() == 3


def test_composicao_soma_1_por_categoria():
    x, y, w, _, _ = _sintetico(k=4, j=5)
    beta, comp = ie.regressao_composicao(x, y, w)
    assert np.allclose(comp.sum(axis=0), 1.0)
    assert np.allclose(beta.sum(axis=1), 1.0, atol=1e-6)
    linha = ie.linha_t2_por_composicao(comp[:, 0])
    assert np.isclose(linha.sum(), 1.0)


def test_matriz_t2_do_yaml_e_fallback_explicito():
    cfg = ie.carregar_config(RAIZ / "config" / "projecao_t2.yaml")
    ids22 = list(cfg["categorias_2022_t1"])
    b = pd.DataFrame(np.full((len(ids22), 4), 0.25), index=ids22, columns=ie.COLS_T2)
    b.loc["tebet_15"] = [0.2, 0.4, 0.1, 0.3]
    reg = {k: np.array([0.4, 0.2, 0.1, 0.3]) for k in ("cury", "renan", "caiado", "outros_2026")}
    base = ie.matriz_t2(cfg, "base", b, reg)
    assert np.allclose(base.loc["caiado"], [0.4, 0.2, 0.1, 0.3])
    fb = ie.matriz_t2(cfg, "base", b, reg, usar_fallback=["caiado"])
    assert np.allclose(fb.loc["caiado"], [0.2, 0.4, 0.1, 0.3])
    with pytest.raises(KeyError):
        ie.matriz_t2(cfg, "base", b, None)  # sem regressão e sem pedir fallback
    div = ie.matriz_t2(cfg, "outros_divididos", b, reg)
    assert "outros_2026__p0" in div.index and "outros_2026" not in div.index
    assert set(ie.grupos_t1_2026(cfg, "outros_divididos")) >= {"outros_2026__p0", "outros_2026__p1"}
    assert (abs(div.sum(axis=1) - 1) < 1e-6).all()


def test_yaml_sem_percentuais_de_votacao():
    txt = (RAIZ / "config" / "projecao_t2.yaml").read_text(encoding="utf-8")
    assert "  pct_validos:" not in txt and "pct_aptos:" not in txt
    assert "criterio_aprovacao" not in txt
    assert "APROVADO" in txt


def test_ic_largo_e_metricas():
    rng = np.random.default_rng(0)
    estreito = rng.normal([0.6, 0.2, 0.1, 0.1], 0.001, size=(200, 4))
    largo = rng.normal([0.6, 0.2, 0.1, 0.1], 0.1, size=(200, 4))
    assert not ie.ic_largo(estreito, 20)[0]
    assert ie.ic_largo(largo, 20)[0]

    obs = pd.DataFrame(
        {
            "uf": ["a", "a", "b"],
            "cd_mun_tse": ["1", "2", "3"],
            "PL": [60, 40, 10],
            "PT": [40, 60, 90],
            "BN": [5, 5, 5],
            "ABST": [20, 20, 20],
        }
    )
    m = ie.metricas(obs, obs)
    assert m["erro_br_pp"] == 0 and m["mae_municipal_pp"] == 0 and m["acerto_vencedor_uf"] == 1
    pred = obs.assign(PL=obs["PL"] + 10, PT=obs["PT"] - 10)
    m2 = ie.metricas(pred, obs)
    assert m2["erro_br_pp"] > 0 and m2["mae_municipal_pp"] > 0
    res = ie.residuo_por_uf(pred, obs)
    assert res.loc["a", "res_PL_votos"] == -20


def test_prever_por_uf_e_substituir_linhas():
    c = _contagens_sinteticas()
    mats = {u: MAT.to_numpy() for u in ["aa", "bb", "zz"]}
    p = ie.prever_por_uf(c, list(MAT.index), mats)
    assert np.allclose(p[ie.COLS_T2].to_numpy(), ie.projetar(c, MAT)[ie.COLS_T2].to_numpy())
    with pytest.raises(KeyError):
        ie.prever_por_uf(c, list(MAT.index), {"aa": MAT.to_numpy()})
    nova = ie.substituir_linhas(MAT.to_numpy(), list(MAT.index), {"ter": np.array([1, 0, 0, 0.0])})
    assert nova[2].tolist() == [1, 0, 0, 0] and np.allclose(nova[0], MAT.to_numpy()[0])
    with pytest.raises(ValueError):
        ie.substituir_linhas(MAT.to_numpy(), list(MAT.index), {"ter": np.array([1, 1, 0, 0.0])})


def test_resumo_erros_uf():
    r = ie.resumo_erros_uf(pd.Series([-2.0, 1.0, 0.0, 3.0]))
    assert r["max_abs"] == 3.0 and r["media_com_sinal"] == 0.5


def test_linha_sem_retorno_abst():
    comp = np.array([0.2, 0.4, 0.1, 0.3])  # lula22, bolsonaro22, bn22, abst22
    r = 0.02
    lin = ie.linha_sem_retorno_abst(comp, r)
    assert np.isclose(lin.sum(), 1.0) and np.isclose(lin[3], r)
    # PL/PT/BN mantêm as proporções relativas da composição, sem o componente ABST22
    assert np.allclose(lin[:3] / lin[:3].sum(), np.array([0.4, 0.2, 0.1]) / 0.7)
    assert np.allclose(ie.linha_sem_retorno_abst(np.array([0, 0, 0, 1.0]), r), [0, 0, 0, 1])
    with pytest.raises(ValueError):
        ie.linha_sem_retorno_abst(comp, 1.5)


def test_taxa_abstencao_votantes_ponderada():
    b = np.array([[0, 1.0, 0, 0], [0.5, 0, 0, 0.5], [0, 0, 1.0, 0]])
    r = ie.taxa_abstencao_votantes(b, np.array([100.0, 100.0, 999.0]), [0, 1])
    assert np.isclose(r, 0.25)
