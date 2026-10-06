"""Testes com a malha municipal do IBGE (geobr, completa): área, join com o TSE, vizinhança, mapa.

Dependem de rede/cache do geobr (leitura ~10 s). Marcados com `geo` para poder rodar isolado:
`pytest -q -m geo` (ou `-m "not geo"` para pular).
"""

from __future__ import annotations

import pytest

from eleicao.analise import base, carga
from eleicao.analise import geometria as geo
from eleicao.analise import mapa_mente as mm

pytestmark = pytest.mark.geo


@pytest.fixture(scope="module")
def malha():
    return carga.geometria_municipios_2024().reset_index(drop=True)


@pytest.fixture(scope="module")
def tse_br():
    t = carga.totais_2026()
    return base.apenas_brasil(base.base_municipal(t, carga.capitais()))


def test_malha_tem_5571_municipios_e_cobre_tse_1_para_1(malha, tse_br):
    assert len(malha) == 5571
    assert malha["cd_mun_ibge"].is_unique
    assert set(malha["cd_mun_ibge"]) == set(tse_br["cd_mun_ibge"])


def test_area_total_bate_com_area_oficial_brasil(malha):
    g = geo.areas_km2(malha)
    total = g["area_km2"].sum()
    # IBGE (Áreas Territoriais 2022): 8.510.345 km². Desvio aceito: 0,5%.
    assert abs(total / geo.AREA_OFICIAL_BR_KM2 - 1) < 0.005


def test_queen_ilhas_sao_noronha_e_ilhabela(malha):
    w = geo.pesos_queen(malha)
    nomes = set(malha.iloc[w.islands]["name_muni"])
    assert nomes == {"Fernando de Noronha", "Ilhabela"}
    assert w.n == 5571


def test_real_mapa_mente_vencedores_reproduz_numeros(malha, tse_br):
    """Número-chave do 12_mapa_mente: municípios vencidos por nº 22 e 13 (1º turno 2026)."""
    c = carga.candidatos_2026()
    cbr = c[c["uf"] != "zz"]
    vw = base.vencedor_municipal(cbr)
    assert vw["nr_vencedor"].value_counts().to_dict() == {22: 2906, 13: 2663}
    assert vw["nr_vencedor"].isna().sum() == 2  # empates exatos (SP 62448, TO 73555)
    area = geo.areas_km2(malha)
    area = area.merge(tse_br[["cd_mun_ibge", "uf", "cd_mun_tse"]], on="cd_mun_ibge")[
        ["uf", "cd_mun_tse", "area_km2"]
    ]
    res = mm.resumo_vencedores(
        vw, tse_br[["uf", "cd_mun_tse", "eleitorado", "validos"]], cbr, area
    ).set_index("nr_candidato")
    assert res.loc[22, "n_municipios_vencidos"] == 2906
    assert res.loc[13, "n_municipios_vencidos"] == 2663
    # área: os 2 empates ficam fora de qualquer candidato; a soma das duas é < 100%
    assert res["pct_area_sobre_area_br"].sum() < 100.0
    assert res["pct_area_sobre_area_br"].sum() > 99.9
