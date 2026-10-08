"""Invariantes e totais de referência de Presidente 2018 (Dados Abertos TSE).

Valores de referência: resultado oficial do TSE, conferido contra a página
da Wikipedia "Eleição presidencial no Brasil em 2018" (2º turno: candidatos,
comparecimento de ambos os turnos e eleitorado) e contra a soma dos próprios
dados. Rode `scripts/processar_presidente_2018.py` antes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from eleicao import config

D = config.DATA_PROCESSED

pytestmark = pytest.mark.skipif(
    not (D / "presidente_2018_t1_municipio_totais.parquet").exists(),
    reason="rode scripts/processar_presidente_2018.py",
)


def _ler(turno: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_parquet(D / f"presidente_2018_t{turno}_municipio.parquet"),
        pd.read_parquet(D / f"presidente_2018_t{turno}_municipio_totais.parquet"),
    )


T1 = {
    17: 49_277_010,
    13: 31_342_051,
    12: 13_344_371,
    45: 5_096_350,
    30: 2_679_745,
}
T2 = {17: 57_797_847, 13: 47_040_906}


@pytest.mark.parametrize(("turno", "esperado"), [(1, T1), (2, T2)])
def test_votos_nacionais_por_candidato(turno, esperado):
    cand, _ = _ler(turno)
    soma = cand.groupby("nr_candidato")["votos"].sum()
    for nr, votos in esperado.items():
        assert soma[nr] == votos


def test_totais_br_t1():
    _, t = _ler(1)
    assert t["eleitorado"].sum() == 147_306_295
    assert t["comparecimento"].sum() == 117_364_654
    assert t["abstencao"].sum() == 29_941_171
    assert t["validos"].sum() == 107_050_749
    assert t["brancos"].sum() == 3_106_937
    assert t["nulos_tvn"].sum() == 7_206_222


def test_totais_br_t2():
    _, t = _ler(2)
    assert t["eleitorado"].sum() == 147_306_294
    assert t["comparecimento"].sum() == 115_933_451
    assert t["abstencao"].sum() == 31_372_373
    assert t["validos"].sum() == 104_838_753
    assert t["brancos"].sum() == 2_486_593
    assert t["nulos_tvn"].sum() == 8_608_105


@pytest.mark.parametrize("turno", [1, 2])
def test_soma_candidatos_igual_validos_por_municipio(turno):
    cand, t = _ler(turno)
    soma = cand.groupby(["uf", "cd_mun_tse"])["votos"].sum()
    validos = t.set_index(["uf", "cd_mun_tse"])["validos"]
    soma = soma.reindex(validos.index, fill_value=0)
    assert (soma == validos).all()
    # municípios sem linha de candidato são só postos do exterior sem voto
    sem_linha = validos.index.difference(cand.set_index(["uf", "cd_mun_tse"]).index)
    assert all(uf == "zz" for uf, _ in sem_linha)
    assert validos.loc[sem_linha].sum() == 0


def test_pct_validos_soma_100_por_municipio_com_votos():
    cand, _ = _ler(1)
    pct = cand.groupby(["uf", "cd_mun_tse"])["pct_validos"].sum()
    assert ((pct - 100).abs() < 1e-6).all()


def test_fecha_comparecimento_exceto_salvador_t1():
    """validos+brancos+nulos+anulados == comparecimento; única exceção: Salvador T1 (-746)."""
    _, t1 = _ler(1)
    _, t2 = _ler(2)
    r2 = t2.validos + t2.brancos + t2.nulos_tvn + t2.anulados + t2.anulados_sub_judice
    assert (r2 == t2.comparecimento).all()
    r1 = t1.validos + t1.brancos + t1.nulos_tvn + t1.anulados + t1.anulados_sub_judice
    dif = t1.loc[r1 != t1.comparecimento]
    assert list(dif["cd_mun_tse"]) == ["38490"]
    assert (r1 - t1.comparecimento)[dif.index[0]] == -746


@pytest.mark.parametrize("turno", [1, 2])
def test_comparecimento_mais_abstencao_so_falha_no_exterior_sem_votantes(turno):
    _, t = _ler(turno)
    dif = t.loc[t.comparecimento + t.abstencao != t.eleitorado]
    assert len(dif) == 33
    assert (dif["uf"] == "zz").all()
    assert (dif["comparecimento"] == 0).all()
    assert dif["eleitorado"].sum() == 470


def test_exterior_presente():
    _, t = _ler(1)
    assert (t["uf"] == "zz").sum() == 171
    assert t["cd_mun_ibge"].notna().sum() == (t["uf"] != "zz").sum()
