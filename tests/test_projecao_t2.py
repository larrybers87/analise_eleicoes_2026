"""Testes de eleicao.projecao_t2 (usam data/processed/; pulam se os parquet não existirem)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from eleicao import inferencia_ecologica as ie
from eleicao import projecao_t2 as pj

RAIZ = Path(__file__).resolve().parents[1]
PROC = RAIZ / "data" / "processed"
CFG = RAIZ / "config" / "projecao_t2.yaml"
PRECISA = [
    "presidente_t1_municipio.parquet",
    "presidente_2022_t2_municipio.parquet",
    "presidente_2018_t2_municipio.parquet",
    "snapshot_t1_2026.json",
]
pytestmark = pytest.mark.skipif(
    not all((PROC / f).exists() for f in PRECISA), reason="parquet de 2018/2022/2026 ausentes"
)


@pytest.fixture(scope="module")
def cfg():
    return pj.carregar_config_projecao(CFG)


@pytest.fixture(scope="module")
def saidas():
    return pj.executar(PROC, CFG, n_boot=3, semente=1)


@pytest.fixture(scope="module")
def ins():
    return pj.carregar_insumos(PROC)


def test_veredito_regra_indistinguivel():
    assert pj.veredito(51.5, 2.0) == "indistinguivel"
    assert pj.veredito(52.0, 2.0) == "indistinguivel"
    assert pj.veredito(52.1, 2.0) == "PL"
    assert pj.veredito(47.0, 2.5) == "PT"
    assert pj.veredito(float("nan"), 2.0) == "sem_votos_validos"


def test_yaml_aprovado_e_cenarios_minimos(cfg):
    assert cfg["meta"]["status"] == "APROVADO"
    for c in ("base", "desmob_2018", "analogos", "analogos_desmob_2018"):
        assert c in cfg["cenarios"]
    assert cfg["faixa_heuristica"]["pct_pl_validos_br_pp"] == 2.0
    assert cfg["faixa_heuristica"]["pct_pl_validos_uf_pp"] == 2.5
    assert cfg["faixa_heuristica"]["abstencao_aptos_pp"] == 1.5


def test_b_nao_negativo_e_linhas_somam_1(cfg, ins):
    for esc in pj.ESCOPOS:
        d, _ = pj.montar_dados(ins, cfg, esc)
        p = pj.estimar(d)
        for b in (p.b22, p.b18):
            assert b.to_numpy().min() >= -1e-9
            assert np.allclose(b.sum(axis=1), 1.0, atol=1e-6)
        for lin in p.linhas.values():
            assert lin.min() >= -1e-9 and abs(lin.sum() - 1) < 1e-6


def test_matrizes_de_todos_os_cenarios_validas(cfg, ins):
    pars = {}
    for esc in pj.ESCOPOS:
        d, _ = pj.montar_dados(ins, cfg, esc)
        pars[esc] = pj.estimar(d)
    for cen in cfg["cenarios"]:
        for m in pj.matrizes_cenario(cfg, cen, pars["br"], pars["zz"]):
            assert m.to_numpy().min() >= -1e-9
            assert np.allclose(m.sum(axis=1), 1.0, atol=1e-6)


def test_eixo_abst_bn_troca_apenas_essas_linhas(cfg, ins):
    d, _ = pj.montar_dados(ins, cfg, "br")
    p = pj.estimar(d)
    base = ie.matriz_t2(cfg, "base", {"b_2022": p.b22, "b_2018": p.b18}, p.linhas)
    des = ie.matriz_t2(cfg, "desmob_2018", {"b_2022": p.b22, "b_2018": p.b18}, p.linhas)
    assert np.allclose(des.loc["bn_2026"], p.b18.loc["bn"])
    assert np.allclose(des.loc["abst_2026"], p.b18.loc["abst"])
    assert np.allclose(base.loc["bn_2026"], p.b22.loc["bn_2022"])
    resto = [i for i in base.index if i not in ("bn_2026", "abst_2026")]
    assert np.allclose(base.loc[resto], des.loc[resto])


def test_outros_usa_composicao_no_base_e_goodman_em_cenario(cfg, ins):
    d, _ = pj.montar_dados(ins, cfg, "br")
    p = pj.estimar(d)
    f = {"b_2022": p.b22, "b_2018": p.b18}
    base = ie.matriz_t2(cfg, "base", f, p.linhas)
    og = ie.matriz_t2(cfg, "outros_goodman", f, p.linhas)
    assert np.allclose(base.loc["outros_2026"], p.linhas["outros_2026"])
    assert np.allclose(og.loc["outros_2026"], p.b22.loc["outros_2022"])


def test_municipio_uf_br_fecham_e_categorias_somam_aptos(saidas, cfg):
    mun, uf, br = saidas["municipio"], saidas["uf"], saidas["br"]
    cols = ["aptos", *ie.COLS_T2]
    for cen in cfg["cenarios"]:
        m = mun[mun["cenario"] == cen]
        assert np.allclose(m[ie.COLS_T2].sum(axis=1), m["aptos"], rtol=1e-9, atol=1e-6)
        u = uf[uf["cenario"] == cen].set_index("uf")
        por_uf = m.groupby("uf")[cols].sum()
        assert np.allclose(por_uf.loc[u.index, cols], u[cols])
        b = br[br["cenario"] == cen].set_index("recorte")
        assert np.allclose(u[cols].sum(), b.loc["total_oficial_com_zz", cols].astype(float))
        assert np.allclose(
            b.loc["brasil_sem_zz", cols].astype(float) + b.loc["zz_exterior", cols].astype(float),
            b.loc["total_oficial_com_zz", cols].astype(float),
        )
        assert np.allclose(m[cols].sum(), b.loc["total_oficial_com_zz", cols].astype(float))


def test_br_tem_3_linhas_por_cenario_e_rotulos_distintos(saidas, cfg):
    br = saidas["br"]
    for cen in cfg["cenarios"]:
        b = br[br["cenario"] == cen]
        assert sorted(b["recorte"]) == ["brasil_sem_zz", "total_oficial_com_zz", "zz_exterior"]
    rot = br.set_index("recorte")["rotulo"].to_dict()
    assert rot["total_oficial_com_zz"] != rot["brasil_sem_zz"]
    assert "com exterior" in rot["total_oficial_com_zz"]
    assert not any(r.strip() == "Brasil" for r in br["rotulo"])


def test_sem_par_listado_e_ainda_projetado(saidas):
    sp = saidas["sem_par"]
    assert ("mt", "73709") in set(map(tuple, sp[ie.CHAVE].to_numpy()))  # Boa Esperança do Norte
    assert {"29629", "99279", "99295", "99490", "99503", "99511", "99252"} <= set(sp["cd_mun_tse"])
    mun = saidas["municipio"]
    ben = mun[(mun["uf"] == "mt") & (mun["cd_mun_tse"] == "73709") & (mun["cenario"] == "base")]
    assert len(ben) == 1 and ben["aptos"].iloc[0] > 0
    assert np.isclose(ben[ie.COLS_T2].sum(axis=1).iloc[0], ben["aptos"].iloc[0])
    # nenhuma chave sem par sumiu da projeção
    chaves_proj = set(map(tuple, mun[ie.CHAVE].to_numpy()))
    for u, c in sp[ie.CHAVE].to_numpy():
        if c != "99252":  # posto que só existia em 2022 não tem T1 2026 para projetar
            assert (u, c) in chaves_proj


def test_metadados_do_snapshot_nas_saidas(saidas):
    for nome in ("municipio", "uf", "br"):
        df = saidas[nome]
        assert (df["t1_and"] == "f").all() and (df["t1_tf"] == "s").all()
        assert df["t1_idg"].nunique() == 1


def test_agregacao_soma_votos_nao_media_de_pct(saidas):
    mun = saidas["municipio"]
    m = mun[(mun["cenario"] == "base") & (mun["uf"] != "zz")]
    pct_agregado = 100 * m["PL"].sum() / (m["PL"].sum() + m["PT"].sum())
    b = saidas["br"].query("cenario == 'base' and recorte == 'brasil_sem_zz'")
    assert np.isclose(b["pct_pl_validos"].iloc[0], pct_agregado)
    assert not np.isclose(m["pct_pl_validos"].mean(), pct_agregado, atol=0.01)


def test_faixas_heuristicas_e_rotulo(saidas):
    br = saidas["br"]
    assert set(br["rotulo_faixa"]) == {"faixa heuristica (n=1)"}
    base = br[br["cenario"] == "base"].set_index("recorte")
    assert base.loc["brasil_sem_zz", "faixa_pl_pp"] == 2.0
    assert (br["faixa_abst_pp"] == 1.5).all()
    assert (saidas["uf"]["faixa_pp"] == 2.5).all()


def test_apresentacao_frase_antes_do_numero(saidas):
    f = pj.frase_vencedor_br(saidas["br"], "base")
    assert f.startswith("O método não distingue vencedor") or f.startswith("Vencedor projetado")
    ind = saidas["br"].query("cenario == 'base' and recorte == 'brasil_sem_zz'")["veredito"].iloc[0]
    assert (ind == "indistinguivel") == f.startswith("O método não distingue vencedor")
    assert len(pj.tabela_resumo(saidas["br"])) == 3 * len(saidas["br"]["cenario"].unique())


def test_identidade_sem_retorno_abst_e_r(cfg, ins):
    d, _ = pj.montar_dados(ins, cfg, "br")
    p = pj.estimar(d)
    assert 0.0 <= p.r <= 0.1
    for cid, lin in p.linhas_sr.items():
        assert np.isclose(lin.sum(), 1.0) and np.isclose(lin[3], p.r)
        # a razão PL:PT da linha composta é preservada
        if p.linhas[cid][:2].sum() > 0 and lin[:2].sum() > 0:
            assert (
                np.isclose(
                    lin[0] / lin[:2].sum(), p.linhas[cid][0] / p.linhas[cid][:2].sum(), atol=1e-9
                )
                or p.linhas[cid][2] > 0
            )
    pars = {"br": p, "zz": pj.estimar(pj.montar_dados(ins, cfg, "zz")[0])}
    base, _ = pj.matrizes_cenario(cfg, "base", pars["br"], pars["zz"])
    sr, _ = pj.matrizes_cenario(cfg, "identidade_sem_retorno_abst", pars["br"], pars["zz"])
    for cid in pj.TERCEIROS:
        assert np.isclose(sr.loc[cid, "ABST"], p.r)
    resto = [i for i in base.index if i not in pj.TERCEIROS]
    assert np.allclose(base.loc[resto], sr.loc[resto])


def test_exterior_usa_matriz_nacional_na_base_e_propria_em_cenario(cfg, ins):
    pars = {e: pj.estimar(pj.montar_dados(ins, cfg, e)[0]) for e in pj.ESCOPOS}
    assert cfg["meta"]["matriz_zz_base"] == "nacional"
    for cen in cfg["cenarios"]:
        m_br, m_zz = pj.matrizes_cenario(cfg, cen, pars["br"], pars["zz"])
        if cen == "zz_propria":
            assert not np.allclose(m_br.to_numpy(), m_zz.to_numpy())
        else:
            assert m_br.equals(m_zz)  # inclusive nos cenários cruzados (desmob_2018, analogos...)
    assert "zz_nacional" not in cfg["cenarios"]


def test_cenarios_incluem_o_novo_e_mantem_os_4_cruzados(cfg):
    for c in (
        "base",
        "desmob_2018",
        "analogos",
        "analogos_desmob_2018",
        "identidade_sem_retorno_abst",
        "zz_propria",
    ):
        assert c in cfg["cenarios"]
