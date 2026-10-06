"""Testes de perfil (WLS/VIF), estatística espacial (Moran/LISA/BH) e bolsões.

Casos sintéticos com resposta conhecida; reprodução do perfil real a partir dos Parquet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from libpysal.weights import W
from statsmodels.stats.multitest import multipletests

from eleicao.analise import base, carga, perfil
from eleicao.analise import bolsoes as bo
from eleicao.analise import espacial as esp

# ---------------------------------------------------------------- perfil: partição de idade


def _perfil_sintetico(n: int = 4) -> pd.DataFrame:
    """Linhas com partição de idade que fecha em 100 (derivadas = soma das nativas)."""
    d = {}
    d["pct_faixa_facultativa_16_17"] = np.full(n, 2.0)
    d["pct_faixa_facultativa_70_mais"] = np.full(n, 5.0)
    d["pct_faixa_invalida"] = np.full(n, 0.5)
    # 16 e 17 nativos somam a derivada
    d["pct_faixa_16"] = np.full(n, 1.0)
    d["pct_faixa_17"] = np.full(n, 1.0)
    d["pct_faixa_70_74"] = np.full(n, 5.0)
    for c in perfil.IDADE_18_59_NATIVAS:
        d[c] = np.full(n, 0.0)
    d["pct_faixa_18"] = np.full(
        n, 100 - 2 - 5 - 0.5 - 0.0 - 0.0
    )  # 92.5 para fechar em 100 com 60-69 = 0
    for c in perfil.IDADE_60_69_NATIVAS:
        d[c] = np.full(n, 0.0)
    return pd.DataFrame(d)


def test_checar_soma_idade_aceita_particao_que_fecha():
    perfil.checar_soma_idade(_perfil_sintetico())


def test_checar_soma_idade_recusa_dupla_contagem():
    d = _perfil_sintetico()
    # somar as nativas 16 e 17 *além* da derivada (erro proibido) deve ser pego
    d["pct_faixa_facultativa_16_17"] = d["pct_faixa_facultativa_16_17"] + 2.0
    with pytest.raises(ValueError):
        perfil.checar_soma_idade(d)


def test_preparar_variaveis_nao_duplica_16_17_nem_70():
    d = _perfil_sintetico()
    d["pib_per_capita_reais"] = 10_000.0
    d["populacao_censo_2022"] = 1_000.0
    d["pct_sexo_feminino"] = 50.0
    d["pct_grau_superior_completo"] = 10.0
    d["pct_grau_analfabeto"] = 2.0
    x = perfil.preparar_variaveis(d)
    assert (x["pct_16_17"] == 2.0).all()  # derivada, não 2 + 1 + 1
    assert (x["pct_70_mais"] == 5.0).all()  # derivada, não somada às nativas 70_74...
    assert set(perfil.VARIAVEIS_MODELO_COMPLETO) <= set(x.columns)
    assert "pct_faixa_16" not in x.columns


# ---------------------------------------------------------------- WLS e VIF


def test_wls_recupera_coeficientes_exatos():
    rng = np.random.default_rng(1)
    x1 = rng.uniform(0, 10, 200)
    x2 = rng.uniform(0, 10, 200)
    y = 3.0 + 2.0 * x1 - 1.5 * x2
    d = pd.DataFrame({"y": y, "x1": x1, "x2": x2, "eleitorado": rng.uniform(1, 5, 200)})
    tab, r2, n = perfil.ajustar_wls(d, "y", ["x1", "x2"], "eleitorado")
    coef = dict(zip(tab.termo, tab.coef, strict=True))
    assert coef["const"] == pytest.approx(3.0, abs=1e-8)
    assert coef["x1"] == pytest.approx(2.0, abs=1e-8)
    assert coef["x2"] == pytest.approx(-1.5, abs=1e-8)
    assert r2 == pytest.approx(1.0) and n == 200


def test_wls_pondera_pelo_peso():
    # dois grupos com regressões opostas; peso alto no grupo A deve puxar a inclinação para ele
    d = pd.DataFrame(
        {
            "y": [0, 1, 2, 3, 0, -1, -2, -3],
            "x": [0, 1, 2, 3, 0, 1, 2, 3],
            "w": [100, 100, 100, 100, 1, 1, 1, 1],
        }
    )
    tab, _, _ = perfil.ajustar_wls(d, "y", ["x"], "w")
    assert tab.set_index("termo").loc["x", "coef"] > 0.9


def test_vif_detecta_colinearidade_perfeita_aproximada():
    rng = np.random.default_rng(2)
    a = rng.normal(size=300)
    d = pd.DataFrame({"a": a, "b": a + rng.normal(scale=0.01, size=300), "c": rng.normal(size=300)})
    v = perfil.vif(d, ["a", "b", "c"]).set_index("variavel")["vif"]
    assert v["a"] > 100 and v["b"] > 100
    assert v["c"] < 2


def test_vif_independentes_perto_de_um():
    rng = np.random.default_rng(3)
    d = pd.DataFrame(rng.normal(size=(500, 3)), columns=["a", "b", "c"])
    v = perfil.vif(d, ["a", "b", "c"])["vif"]
    assert (v < 1.2).all()


# ---------------------------------------------------------------- espacial


def _grade(n: int) -> W:
    """Vizinhança rook/queen em grade n×n (indexação por linha)."""
    viz = {}
    for i in range(n):
        for j in range(n):
            k = i * n + j
            lst = []
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if (di, dj) == (0, 0):
                        continue
                    a, b = i + di, j + dj
                    if 0 <= a < n and 0 <= b < n:
                        lst.append(a * n + b)
            viz[k] = lst
    return W(viz, silence_warnings=True)


def test_sem_ilhas_remove_isolados_e_mantem_vizinhanca():
    viz = {0: [1], 1: [0, 2], 2: [1], 3: []}  # 3 é ilha
    w = W(viz, silence_warnings=True)
    w2, manter = esp.sem_ilhas(w)
    assert manter.tolist() == [True, True, True, False]
    assert w2.n == 3 and len(w2.islands) == 0
    assert sorted(w2.neighbors[1]) == [0, 2]


def test_moran_global_positivo_para_padrao_em_blocos():
    w = _grade(6)
    y = np.array([[1.0 if j < 3 else 0.0 for j in range(6)] for _ in range(6)]).ravel()
    m = esp.moran_global(y, w, permutacoes=199, seed=1)
    assert m["I"] > 0.5 and m["p_sim"] <= 0.05


def test_moran_global_recusa_ilhas():
    w = W({0: [1], 1: [0], 2: []}, silence_warnings=True)
    with pytest.raises(ValueError):
        esp.moran_global(np.array([1.0, 2.0, 3.0]), w)


def test_lisa_bh_detecta_cluster_alto_alto_e_marca_quadrante():
    w = _grade(7)
    y = np.zeros((7, 7))
    y[:3, :3] = 10.0
    y = y.ravel() + np.random.default_rng(4).normal(scale=0.01, size=49)
    ids = np.array([f"m{i}" for i in range(49)])
    r = esp.lisa_com_fdr(y, w, ids, alpha=0.05, permutacoes=499, seed=1)
    assert len(r) == 49  # sem ilhas, nada é descartado
    # m8 = (linha 1, coluna 1): interior do bloco alto, com todos os vizinhos altos.
    # (O canto m0 tem 3 vizinhos altos e com 199 permutações não passa no FDR: limite do teste.)
    centro = r.loc[r.id == "m8"].iloc[0]
    assert centro["quadrante"] == "alto-alto"
    assert centro["significativo_fdr"]
    assert (r.loc[~r.significativo_fdr, "quadrante_sig"] == "não significativo").all()
    assert (r.loc[r.significativo_fdr, "quadrante_sig"] == "alto-alto").sum() >= 5


def test_bh_valores_conhecidos():
    """Benjamini-Hochberg à mão: p=[.001,.01,.02,.03,.2,.5], m=6; p*m/i com mínimo acumulado."""
    p = np.array([0.001, 0.01, 0.02, 0.03, 0.2, 0.5])
    _, p_fdr, _, _ = multipletests(p, alpha=0.05, method="fdr_bh")
    # i=4: 0,03*6/4=0,045 ; i=5: 0,2*6/5=0,24 ; mínimo acumulado vindo de cima
    esperado = np.array([0.006, 0.03, 0.04, 0.045, 0.24, 0.5])
    assert np.allclose(p_fdr, esperado)


# ---------------------------------------------------------------- bolsões


def test_componentes_conexas_separa_blocos():
    viz = {0: [1], 1: [0], 2: [3], 3: [2], 4: []}
    mascara = np.array([True, True, False, True, True])
    comps = bo.componentes_conexas(mascara, viz)
    assert comps[0] == [0, 1]
    assert sorted(comps[1:]) == [[3], [4]]


def test_bolsoes_limiar_3x_e_agrupamento():
    m = pd.DataFrame(
        {
            "uf": ["go", "go", "mg", "sp"],
            "cd_mun_tse": ["1", "2", "3", "4"],
            "nome": ["A", "B", "C", "D"],
            "eleitorado": [100, 200, 300, 400],
            "pct": [9.0, 8.5, 9.5, 1.0],  # média nacional 2.0 -> limiar 6.0
        }
    )
    viz = {0: [1], 1: [0], 2: [], 3: []}
    b = bo.bolsoes(m, "pct", 2.0, viz, 3.0)
    assert len(b) == 2  # {A,B} e {C}
    assert b.n_municipios.tolist() == [2, 1]
    assert b.iloc[0]["eleitorado"] == 300


def test_bolsao_nao_existe_quando_ninguem_passa_do_limiar():
    m = pd.DataFrame(
        {"uf": ["go"], "cd_mun_tse": ["1"], "nome": ["A"], "eleitorado": [10], "pct": [1.0]}
    )
    vazio = bo.bolsoes(m, "pct", 2.0, {0: []}, 3.0)
    assert len(vazio) == 0
    # esquema preservado mesmo sem linhas (o notebook ordena por n_municipios)
    assert {"n_municipios", "eleitorado", "pct_maximo"} <= set(vazio.columns)


def test_resumo_reduto_razao_com_denominador_da_uf():
    m = pd.DataFrame(
        {
            "uf": ["go", "go", "mg"],
            "votos": [60, 40, 10],
            "validos": [100, 100, 100],
            "pct": [31.0, 20.0, 1.0],
        }
    )
    r = bo.resumo_reduto(m, "pct", "go", 10.0)
    assert r["pct_uf_sobre_validos"] == pytest.approx(50.0)
    assert r["razao_vs_nacional"] == pytest.approx(5.0)
    assert r["n_municipios_acima_3x"] == 1  # 31 > 30; 20 não passa do limiar de 30


# ---------------------------------------------------------------- reprodução com dados reais


@pytest.fixture(scope="module")
def reais():
    t = carga.totais_2026()
    b = base.enriquecer(
        base.base_municipal(t, carga.capitais()), carga.perfil_eleitorado_2026(), carga.ibge()
    )
    return b


def test_real_partição_de_idade_fecha(reais):
    perfil.checar_soma_idade(reais[~reais["eh_exterior"]])


def test_real_wls_pt_r2_e_vif_sem_colinearidade_severa(reais):
    """Número-chave do 15_perfil: R² do modelo completo para PT (1T 2026), e VIF máximo."""
    cand = carga.candidatos_2026()
    cand = cand[(cand.nr_candidato == 13) & (cand.uf != "zz")]
    m = reais[(reais.uf != "zz")].dropna(subset=["pib_per_capita_reais"])
    m = m.merge(cand[["uf", "cd_mun_tse", "votos"]], on=["uf", "cd_mun_tse"])
    m["y"] = 100 * m["votos"] / m["validos"]
    x = perfil.preparar_variaveis(m)
    dados = pd.concat([m[["y", "eleitorado"]], x], axis=1)
    tab, r2, n = perfil.ajustar_wls(dados, "y", perfil.VARIAVEIS_MODELO_COMPLETO, "eleitorado")
    assert n == 5570
    assert r2 == pytest.approx(0.56, abs=0.01)
    assert perfil.vif(dados, perfil.VARIAVEIS_MODELO_COMPLETO)["vif"].max() < 10


def test_real_correlacao_superior_renda_e_forte_colinearidade_ecologica(reais):
    """Escolaridade superior × log PIB pc é o par colinear esperado (ρ≈0,65, nível município)."""
    from eleicao.analise import participacao as pa

    m = reais[(reais.uf != "zz")].dropna(subset=["pib_per_capita_reais"]).copy()
    m["log_pib"] = np.log10(m["pib_per_capita_reais"])
    r = pa.correlacao_ecologica(m, "pct_grau_superior_completo", "log_pib", "spearman")
    assert r["r"] == pytest.approx(0.65, abs=0.02)
